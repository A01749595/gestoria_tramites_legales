"""
Document Monitoring Agent - Monitors document status across all branches
Extracts metadata from OCR text and classifies document status

Mejoras v2 (extracción):
  - Patrones de folio mucho más amplios: cubre 'folio', 'número', 'no.',
    'núm.', 'expediente', 'oficio', 'clave', 'permiso no.', 'licencia no.',
    incluyendo separadores '/' y '.' además de '-'.
  - Fechas en formatos mixtos: numérico (15/01/2024, 2024-01-15) y
    en español largo ('15 de enero de 2024', 'enero 15 de 2024',
    'a los 15 días del mes de enero de 2024').
  - Múltiples sinónimos de vencimiento: 'vence', 'válido hasta',
    'vigente hasta', 'expira', 'caduca', 'vigencia: ... al ...',
    'con vigencia de ... al ...'.
  - Múltiples sinónimos de emisión: 'expedida el', 'otorgada el',
    'fecha de expedición', 'fechada en ... a ...'.
  - Búsqueda case-insensitive sin destruir mayúsculas del original
    (el código viejo hacía text.lower() antes de extraer, lo cual rompía
    folios mixtos y nombres propios).
  - Autoridad emisora: catálogo de instituciones mexicanas comunes
    (SAT, IMSS, SEDESOL, Protección Civil, Secretaría de Salud, etc.)
    además del regex genérico.
  - Si el regex de fecha de vencimiento falla, intenta inferirla de
    expresiones tipo 'vigencia: del X al Y' tomando la segunda fecha.
  - RFC y CURP como campos adicionales si aparecen.
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional, Tuple
import re
import logging
from schemas.schemas import (
    Document, DocumentStatus, OCROutput, Branch
)

logger = logging.getLogger(__name__)


# -------------------------------------------------------------------- #
# Diccionarios / catálogos a nivel módulo (no dependen de instancia)   #
# -------------------------------------------------------------------- #

# Meses en español -> número, con y sin acento.
SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

# Catálogo de autoridades mexicanas comunes; se buscan por substring.
KNOWN_AUTHORITIES = [
    "Servicio de Administración Tributaria",
    "SAT",
    "Instituto Mexicano del Seguro Social",
    "IMSS",
    "Secretaría de Salud",
    "Secretaría de Hacienda",
    "Secretaría de Desarrollo Económico",
    "Secretaría del Trabajo",
    "Protección Civil",
    "Coordinación Estatal de Protección Civil",
    "COFEPRIS",
    "INFONAVIT",
    "PROFECO",
    "SEMARNAT",
    "Comisión Nacional del Agua",
    "CONAGUA",
    "Instituto Nacional Electoral",
    "INE",
    "Registro Público de Comercio",
    "Notaría Pública",
    "Ayuntamiento",
    "Gobierno del Estado",
    "Tesorería",
    "Dirección de Desarrollo Urbano",
]


class DocumentMonitoringAgent:
    """
    Agent responsible for monitoring document status across all 319 branches.
    Detects whether documents are valid, close to expiration, expired, missing,
    unreadable, or incomplete. Extracts relevant fields from OCR text.
    """

    def __init__(self, llm_client=None):
        """
        Initialize the Document Monitoring Agent

        Args:
            llm_client: Optional LLM client for advanced text extraction
        """
        self.llm_client = llm_client
        self.field_patterns = self._initialize_field_patterns()
        self.date_range_patterns = self._initialize_date_range_patterns()
        logger.info("Document Monitoring Agent initialized")

    def _initialize_field_patterns(self) -> Dict[str, List[str]]:
        """
        Patrones por campo. Cada campo tiene **varios** patrones; se aplican
        en orden y nos quedamos con la primera coincidencia útil.
        Todos los regex se aplican con re.IGNORECASE | re.UNICODE, pero
        sobre el texto ORIGINAL (con mayúsculas) para preservar el valor
        capturado.
        """
        # Fecha en formato corto: 15/01/2024 ó 2024-01-15 ó 15.01.24
        DATE_NUM = r"\d{1,4}[\/\-\.\s]\d{1,2}[\/\-\.\s]\d{1,4}"
        # Fecha en español largo: '15 de enero de 2024'
        DATE_ES_LONG = (
            r"\d{1,2}\s*(?:de\s+)?"
            r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
            r"septiembre|setiembre|octubre|noviembre|diciembre)"
            r"\s*(?:de\s+)?\d{2,4}"
        )
        DATE_ANY = f"(?:{DATE_NUM}|{DATE_ES_LONG})"

        return {
            "folio": [
                # Etiqueta seguida directamente del valor: "Folio: ABC-123"
                r"(?:folio|expediente|clave)\s*[:#]?\s*"
                r"([A-Z0-9][A-Z0-9\-\/\.]{2,30})",
                # "Oficio Núm. XYZ-123", "Permiso No. ABC/45", "Licencia N° 887"
                r"(?:oficio|permiso|licencia|certificado|constancia|c[eé]dula)"
                r"\s+(?:n[úu]m(?:ero)?\.?|n[°ºo]\.?|no\.?|#)\s*"
                r"([A-Z0-9][A-Z0-9\-\/\.]{2,30})",
                # Etiqueta "Núm./No." sola seguida de valor
                r"\b(?:n[úu]m(?:ero)?\.?|n[°ºo]\.?|no\.?)\s*[:#]?\s*"
                r"([A-Z]{2,}[\-\/\.]?\d[A-Z0-9\-\/\.]{2,30})",
                # Folio aislado tipo "FOLIO ABC-12345"
                r"\bFOLIO\s+([A-Z0-9][A-Z0-9\-\/\.]{2,30})\b",
            ],
            "issue_date": [
                rf"(?:fecha\s+de\s+(?:emisi[oó]n|expedici[oó]n)|"
                rf"expedid[ao]\s+el|otorgad[ao]\s+el|emitid[ao]\s+el|"
                rf"fechad[ao]\s+(?:en\s+\w+\s+)?a(?:\s+los)?|"
                rf"con\s+fecha)\s*[:]?\s*({DATE_ANY})",
                # "México, D.F. a 15 de enero de 2024"
                rf"a\s+los?\s+\d{{1,2}}\s+d[ií]as\s+del\s+mes\s+de\s+"
                rf"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
                rf"septiembre|setiembre|octubre|noviembre|diciembre)"
                rf"\s+de\s+\d{{2,4}}",
            ],
            "expiration_date": [
                # Rango "del X al Y" — debe ir primero para ganar prioridad
                rf"(?:vigencia|periodo|per[ií]odo|v[aá]lid[ao])\s*[:]?\s*"
                rf"(?:del?\s+)?{DATE_ANY}\s+(?:al?|hasta)\s+({DATE_ANY})",
                rf"\bdel\s+{DATE_ANY}\s+al\s+({DATE_ANY})",
                # Etiquetas directas de vencimiento
                rf"(?:fecha\s+de\s+(?:vencimiento|caducidad|expiraci[oó]n)|"
                rf"v[aá]lid[ao]\s+hasta|vigente\s+hasta|vigencia\s+hasta|"
                rf"vence(?:\s+el)?|caduca(?:\s+el)?|expira(?:\s+el)?)"
                rf"\s*[:]?\s*({DATE_ANY})",
                # "Fecha de vigencia: X"
                rf"fecha\s+de\s+vigencia\s*[:]?\s*({DATE_ANY})",
            ],
            "authority": [
                # Genérico: 'expedido por <institución>'. Cortamos en salto de
                # línea o palabras-tope (RFC, CURP, Folio, Fecha) para no
                # tragarnos la siguiente etiqueta.
                r"(?:autoridad(?:\s+emisora)?|expedid[ao]\s+por|otorgad[ao]\s+por|"
                r"emitid[ao]\s+por|emisor[a]?)\s*[:]?\s*"
                r"([A-ZÁÉÍÓÚÑ][A-Za-zÁ-úñÑ\s\.,]+?)"
                r"(?=\s*(?:\n|RFC|CURP|FOLIO|Folio|Fecha|N[úu]m|$))",
            ],
            "branch_name": [
                r"(?:sucursal|establecimiento|denominaci[oó]n|raz[oó]n\s+social|"
                r"denominad[ao]|nombre\s+(?:del\s+)?(?:establecimiento|comercio|negocio))"
                r"\s*[:]?\s*"
                r"([A-Za-zÁ-úñÑ0-9][A-Za-zÁ-úñÑ0-9\s\.,&\-]+?)"
                r"(?=\s*(?:\n|RFC|CURP|FOLIO|Folio|Fecha|N[úu]m|$))",
            ],
            "rfc": [
                # RFC persona moral (12) o física (13)
                r"\bRFC\s*[:]?\s*([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{2,3})\b",
                r"\b([A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3})\b",  # patrón aislado
            ],
            "curp": [
                r"\bCURP\s*[:]?\s*([A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]{2})\b",
                r"\b([A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]{2})\b",
            ],
        }

    def _initialize_date_range_patterns(self) -> List[str]:
        """
        Patrones de rango de fechas: 'del DD/MM/YYYY al DD/MM/YYYY'.
        Cuando aparecen, la segunda fecha es la de vencimiento.
        """
        DATE_NUM = r"\d{1,4}[\/\-\.\s]\d{1,2}[\/\-\.\s]\d{1,4}"
        DATE_ES_LONG = (
            r"\d{1,2}\s*(?:de\s+)?"
            r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
            r"septiembre|setiembre|octubre|noviembre|diciembre)"
            r"\s*(?:de\s+)?\d{2,4}"
        )
        DATE_ANY = f"(?:{DATE_NUM}|{DATE_ES_LONG})"
        return [
            rf"(?:vigencia|periodo|per[ií]odo|v[aá]lid[ao])\s*[:]?\s*"
            rf"(?:del?\s+)?({DATE_ANY})\s+(?:al?|hasta)\s+({DATE_ANY})",
            rf"del\s+({DATE_ANY})\s+al\s+({DATE_ANY})",
        ]

    def monitor_document(
        self,
        document: Document,
        branch: Branch,
        ocr_output: Optional[OCROutput] = None
    ) -> Dict[str, Any]:
        """
        Monitor a single document and return its status analysis
        """
        logger.info(f"Monitoring document {document.document_id} for branch {branch.branch_id}")

        # Classify document status
        status = self._classify_document_status(document)

        # Extract fields if OCR output is available
        extracted_fields = {}
        if ocr_output:
            extracted_fields = self._extract_fields_from_ocr(ocr_output)
        elif document.extracted_text:
            # Create OCR output from document text
            temp_ocr = OCROutput(
                document_id=document.document_id,
                extracted_text=document.extracted_text,
                confidence=document.ocr_confidence,
                extracted_fields={},
                processing_time=0.0
            )
            extracted_fields = self._extract_fields_from_ocr(temp_ocr)

        # Validate completeness
        completeness = self._validate_completeness(document, extracted_fields)

        # Generate status report
        report = {
            "document_id": document.document_id,
            "branch_id": branch.branch_id,
            "branch_name": branch.branch_name,
            "state": branch.state,
            "municipality": branch.municipality,
            "document_name": document.document_name,
            "document_type": document.document_type,
            "current_status": status.value,
            "issuing_authority": document.issuing_authority or extracted_fields.get("authority"),
            "issue_date": document.issue_date.isoformat() if document.issue_date else None,
            "expiration_date": document.expiration_date.isoformat() if document.expiration_date else None,
            "folio_number": document.folio_number or extracted_fields.get("folio"),
            "ocr_confidence": document.ocr_confidence,
            "is_complete": completeness["is_complete"],
            "missing_fields": completeness["missing_fields"],
            "extracted_fields": extracted_fields,
            "days_to_expiration": self._calculate_days_to_expiration(document),
            "requires_action": status in [
                DocumentStatus.EXPIRED,
                DocumentStatus.CLOSE_TO_EXPIRATION,
                DocumentStatus.MISSING,
                DocumentStatus.INCOMPLETE
            ],
            "monitored_at": datetime.utcnow().isoformat()
        }

        logger.info(
            f"Document {document.document_id} status: {status.value}, "
            f"complete: {completeness['is_complete']}, "
            f"fields_extracted: {len(extracted_fields)}"
        )

        return report

    def monitor_branch_documents(
        self,
        branch: Branch,
        documents: List[Document]
    ) -> Dict[str, Any]:
        """
        Monitor all documents for a specific branch
        """
        logger.info(f"Monitoring {len(documents)} documents for branch {branch.branch_id}")

        document_reports = []
        status_counts = {status.value: 0 for status in DocumentStatus}

        for doc in documents:
            report = self.monitor_document(doc, branch)
            document_reports.append(report)
            status_counts[report["current_status"]] += 1

        # Calculate branch-level metrics
        total_docs = len(documents)
        valid_docs = status_counts[DocumentStatus.VALID.value]
        compliance_percentage = (valid_docs / total_docs * 100) if total_docs > 0 else 0

        branch_report = {
            "branch_id": branch.branch_id,
            "branch_name": branch.branch_name,
            "state": branch.state,
            "municipality": branch.municipality,
            "total_documents": total_docs,
            "status_summary": status_counts,
            "compliance_percentage": round(compliance_percentage, 2),
            "valid_documents": status_counts[DocumentStatus.VALID.value],
            "expired_documents": status_counts[DocumentStatus.EXPIRED.value],
            "close_to_expiration": status_counts[DocumentStatus.CLOSE_TO_EXPIRATION.value],
            "missing_documents": status_counts[DocumentStatus.MISSING.value],
            "incomplete_documents": status_counts[DocumentStatus.INCOMPLETE.value],
            "unreadable_documents": status_counts[DocumentStatus.UNREADABLE.value],
            "requires_immediate_action": (
                status_counts[DocumentStatus.EXPIRED.value] +
                status_counts[DocumentStatus.MISSING.value]
            ),
            "documents": document_reports,
            "monitored_at": datetime.utcnow().isoformat()
        }

        logger.info(
            f"Branch {branch.branch_id} compliance: {compliance_percentage:.1f}%, "
            f"{status_counts[DocumentStatus.EXPIRED.value]} expired, "
            f"{status_counts[DocumentStatus.MISSING.value]} missing"
        )

        return branch_report

    def monitor_all_branches(
        self,
        branches_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Monitor documents across all 319 branches
        """
        logger.info(f"Starting system-wide monitoring for {len(branches_data)} branches")

        branch_reports = []
        system_status_counts = {status.value: 0 for status in DocumentStatus}
        total_documents = 0

        for branch_data in branches_data:
            branch = branch_data["branch"]
            documents = branch_data["documents"]

            branch_report = self.monitor_branch_documents(branch, documents)
            branch_reports.append(branch_report)

            # Aggregate system-wide counts
            for status, count in branch_report["status_summary"].items():
                system_status_counts[status] += count
            total_documents += branch_report["total_documents"]

        # Calculate system-wide metrics
        compliant_branches = sum(
            1 for report in branch_reports
            if report["compliance_percentage"] >= 90
        )
        at_risk_branches = sum(
            1 for report in branch_reports
            if 50 <= report["compliance_percentage"] < 90
        )
        non_compliant_branches = sum(
            1 for report in branch_reports
            if report["compliance_percentage"] < 50
        )

        system_report = {
            "total_branches": len(branches_data),
            "total_documents": total_documents,
            "compliant_branches": compliant_branches,
            "at_risk_branches": at_risk_branches,
            "non_compliant_branches": non_compliant_branches,
            "system_status_summary": system_status_counts,
            "average_compliance": round(
                sum(r["compliance_percentage"] for r in branch_reports) / len(branch_reports),
                2
            ) if branch_reports else 0,
            "branches_requiring_immediate_action": sum(
                1 for report in branch_reports
                if report["requires_immediate_action"] > 0
            ),
            "branch_reports": branch_reports,
            "monitored_at": datetime.utcnow().isoformat()
        }

        logger.info(
            f"System-wide monitoring complete: {compliant_branches} compliant, "
            f"{at_risk_branches} at risk, {non_compliant_branches} non-compliant"
        )

        return system_report

    def _classify_document_status(self, document: Document) -> DocumentStatus:
        """Classify document status based on dates and OCR confidence"""

        # Check if document is missing
        if document.status == DocumentStatus.MISSING:
            return DocumentStatus.MISSING

        # Check OCR confidence
        if document.ocr_confidence < 0.5:
            return DocumentStatus.UNREADABLE

        # Check if required fields are missing
        if not document.expiration_date or not document.issue_date:
            if document.ocr_confidence < 0.7:
                return DocumentStatus.INCOMPLETE

        # Check expiration status
        if document.expiration_date:
            days_to_expiration = (document.expiration_date - date.today()).days

            if days_to_expiration < 0:
                return DocumentStatus.EXPIRED
            elif days_to_expiration <= 45:
                return DocumentStatus.CLOSE_TO_EXPIRATION
            else:
                return DocumentStatus.VALID

        # Default to valid if no expiration date
        return DocumentStatus.VALID

    # ------------------------------------------------------------------ #
    # Extracción de campos desde el texto OCR (versión mejorada)          #
    # ------------------------------------------------------------------ #

    def _extract_fields_from_ocr(self, ocr_output: OCROutput) -> Dict[str, Any]:
        """
        Extract structured fields from OCR text using regex patterns.
        Trabaja sobre el texto ORIGINAL (no lower-case) para conservar
        mayúsculas en folios, RFC, autoridades, etc.
        """
        raw_text = ocr_output.extracted_text or ""
        if not raw_text:
            return {}

        # Normalizamos un poco antes de buscar (espacios, saltos, acentos
        # raros) pero NO bajamos a minúsculas: la búsqueda usa IGNORECASE.
        text = self._normalize_for_extraction(raw_text)

        extracted: Dict[str, Any] = {}

        # Aplicamos cada lista de patrones por campo y tomamos la primera
        # coincidencia razonable.
        for field_name, patterns in self.field_patterns.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE | re.UNICODE)
                if match:
                    # Algunos patrones (e.g. "a los X días del mes...") no
                    # tienen grupo de captura; tomamos el match completo.
                    try:
                        value = match.group(1)
                    except IndexError:
                        value = match.group(0)
                    value = value.strip(" :,.;\n\t-")
                    if value and len(value) >= 2:
                        extracted[field_name] = value
                        break  # siguiente campo

        # ---- Fallbacks específicos ----

        # 1) Si falta fecha de emisión (o vencimiento), intentar rango
        #    "del X al Y". El primer regex de expiration_date ya captura la
        #    segunda fecha; este fallback rellena la PRIMERA cuando aplica.
        if "issue_date" not in extracted or "expiration_date" not in extracted:
            for rng_pat in self.date_range_patterns:
                m = re.search(rng_pat, text, re.IGNORECASE | re.UNICODE)
                if m:
                    if "issue_date" not in extracted:
                        extracted["issue_date"] = m.group(1).strip()
                    if "expiration_date" not in extracted:
                        extracted["expiration_date"] = m.group(2).strip()
                    break

        # 2) Autoridad: si no salió por regex, intentar por catálogo
        if "authority" not in extracted:
            authority_match = self._match_known_authority(text)
            if authority_match:
                extracted["authority"] = authority_match

        # 3) Parse de fechas a ISO
        if "issue_date" in extracted:
            iso = self._parse_date(extracted["issue_date"])
            if iso:
                extracted["issue_date_parsed"] = iso

        if "expiration_date" in extracted:
            iso = self._parse_date(extracted["expiration_date"])
            if iso:
                extracted["expiration_date_parsed"] = iso

        return extracted

    @staticmethod
    def _normalize_for_extraction(text: str) -> str:
        """
        Limpieza mínima preservando mayúsculas:
        - Reemplaza saltos múltiples y tabs por espacios.
        - Convierte non-breaking spaces.
        - Une palabras partidas por guión al final de línea.
        - Une etiquetas seguidas de salto: 'Folio:\n123' -> 'Folio: 123'.
        """
        if not text:
            return ""
        t = text.replace("\u00a0", " ")
        # palabras partidas
        t = re.sub(r"-\n(\w)", r"\1", t)
        # etiqueta : <salto> valor -> etiqueta: valor
        t = re.sub(
            r"(folio|n[úu]mero|n[°º]|fecha|vigencia|autoridad|RFC|CURP|"
            r"expedido\s+por|otorgado\s+por|vence|expira|caduca)\s*:\s*\n+\s*",
            r"\1: ",
            t,
            flags=re.IGNORECASE,
        )
        t = re.sub(r"[ \t]+", " ", t)
        return t

    @staticmethod
    def _match_known_authority(text: str) -> Optional[str]:
        """Busca instituciones conocidas como substring (case-insensitive)."""
        text_lower = text.lower()
        # Recorremos de más largo a más corto: queremos el match más específico
        # (e.g. 'Secretaría de Salud' antes que 'Salud').
        for auth in sorted(KNOWN_AUTHORITIES, key=len, reverse=True):
            if auth.lower() in text_lower:
                return auth
        return None

    def _parse_date(self, date_str: str) -> Optional[str]:
        """
        Parse date string to ISO format.
        Acepta:
          - 15/01/2024, 15-01-2024, 15.01.2024
          - 2024-01-15, 2024/01/15
          - 15 de enero de 2024, '15 enero 2024', 'enero 15 de 2024'
          - 15/1/24 (años cortos)
        """
        if not date_str:
            return None

        s = date_str.strip().lower()
        # quitar palabras de relleno
        s = re.sub(r"\b(de|del|a|al|los|d[ií]as|mes)\b", " ", s)
        s = re.sub(r"\s+", " ", s).strip(" ,.;:-/")

        # 1) Intentar formato en español largo: "15 enero 2024" o "enero 15 2024"
        es_pattern = (
            r"(?:(\d{1,2})\s+(\w+)\s+(\d{2,4}))"
            r"|(?:(\w+)\s+(\d{1,2})\s+(\d{2,4}))"
        )
        m = re.search(es_pattern, s, re.UNICODE)
        if m:
            if m.group(1):
                day, month_name, year = m.group(1), m.group(2), m.group(3)
            else:
                month_name, day, year = m.group(4), m.group(5), m.group(6)
            month_name = self._strip_accents(month_name)
            if month_name in SPANISH_MONTHS:
                try:
                    d = int(day)
                    mo = SPANISH_MONTHS[month_name]
                    y = int(year)
                    if y < 100:
                        y += 2000 if y < 50 else 1900
                    return date(y, mo, d).isoformat()
                except (ValueError, TypeError):
                    pass

        # 2) Intentar formatos numéricos clásicos
        # Normalizar separadores
        s_num = re.sub(r"[\.\s]", "/", s)
        s_num = re.sub(r"-", "/", s_num)
        s_num = re.sub(r"/+", "/", s_num)

        date_formats = [
            "%d/%m/%Y", "%d/%m/%y",
            "%Y/%m/%d",
            "%m/%d/%Y", "%m/%d/%y",
        ]

        for fmt in date_formats:
            try:
                parsed = datetime.strptime(s_num, fmt)
                # Sanity check: año razonable
                if 1990 <= parsed.year <= 2099:
                    return parsed.date().isoformat()
            except ValueError:
                continue

        return None

    @staticmethod
    def _strip_accents(s: str) -> str:
        replacements = {
            "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
            "Á": "a", "É": "e", "Í": "i", "Ó": "o", "Ú": "u",
            "ñ": "n", "Ñ": "n",
        }
        for k, v in replacements.items():
            s = s.replace(k, v)
        return s.lower()

    def _validate_completeness(
        self,
        document: Document,
        extracted_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate if document has all required fields"""

        required_fields = [
            "document_name",
            "issuing_authority",
            "issue_date",
            "expiration_date"
        ]

        # Mapeo de nombres de campo del Document -> claves de extracted_fields
        # para considerar también lo que vino del OCR como completo.
        extracted_aliases = {
            "issuing_authority": ["authority"],
            "issue_date": ["issue_date", "issue_date_parsed"],
            "expiration_date": ["expiration_date", "expiration_date_parsed"],
            "document_name": ["branch_name"],
        }

        missing_fields = []

        for field in required_fields:
            doc_value = getattr(document, field, None)

            extracted_value = None
            for alias in extracted_aliases.get(field, [field]):
                if extracted_fields.get(alias):
                    extracted_value = extracted_fields[alias]
                    break

            if not doc_value and not extracted_value:
                missing_fields.append(field)

        return {
            "is_complete": len(missing_fields) == 0,
            "missing_fields": missing_fields,
            "completeness_score": (
                (len(required_fields) - len(missing_fields)) / len(required_fields)
            ) if required_fields else 1.0
        }

    def _calculate_days_to_expiration(self, document: Document) -> Optional[int]:
        """Calculate days until document expiration"""
        if document.expiration_date:
            return (document.expiration_date - date.today()).days
        return None

    def get_expiring_documents(
        self,
        documents: List[Document],
        days_threshold: int = 45
    ) -> List[Dict[str, Any]]:
        """
        Get list of documents expiring within threshold
        """
        expiring = []

        for doc in documents:
            if doc.expiration_date:
                days_to_exp = (doc.expiration_date - date.today()).days

                if 0 <= days_to_exp <= days_threshold:
                    expiring.append({
                        "document_id": doc.document_id,
                        "document_name": doc.document_name,
                        "branch_id": doc.branch_id,
                        "expiration_date": doc.expiration_date.isoformat(),
                        "days_remaining": days_to_exp,
                        "urgency": "high" if days_to_exp <= 15 else "medium"
                    })

        # Sort by days remaining
        expiring.sort(key=lambda x: x["days_remaining"])

        return expiring


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create agent
    agent = DocumentMonitoringAgent()

    # Example branch
    branch = Branch(
        branch_id="BR-001",
        branch_name="Sucursal Centro CDMX",
        state="Ciudad de México",
        municipality="Cuauhtémoc",
        region="Centro",
        responsible_email="responsable@empresa.com",
        manager_email="gerente@empresa.com",
        whatsapp_contact="+525512345678"
    )

    # Example documents
    documents = [
        Document(
            document_id="DOC-001",
            branch_id="BR-001",
            document_name="Licencia de Funcionamiento",
            document_type="license",
            issuing_authority="Secretaría de Desarrollo Económico",
            issue_date=date(2024, 1, 15),
            expiration_date=date(2025, 1, 15),
            status=DocumentStatus.VALID,
            ocr_confidence=0.95,
            file_url="s3://docs/BR-001/lic.pdf"
        ),
        Document(
            document_id="DOC-002",
            branch_id="BR-001",
            document_name="Certificado Sanitario",
            document_type="certificate",
            issuing_authority="Secretaría de Salud",
            issue_date=date(2023, 1, 1),
            expiration_date=date(2024, 1, 1),
            status=DocumentStatus.EXPIRED,
            ocr_confidence=0.88,
            file_url="s3://docs/BR-001/cert.pdf"
        ),
        Document(
            document_id="DOC-003",
            branch_id="BR-001",
            document_name="Permiso de Protección Civil",
            document_type="permit",
            issuing_authority="Protección Civil",
            issue_date=date(2024, 1, 1),
            expiration_date=date.today() + timedelta(days=30),
            status=DocumentStatus.CLOSE_TO_EXPIRATION,
            ocr_confidence=0.92,
            file_url="s3://docs/BR-001/perm.pdf"
        )
    ]

    # Monitor branch documents
    print("\n=== Branch Monitoring Report ===")
    report = agent.monitor_branch_documents(branch, documents)
    print(f"Branch: {report['branch_name']}")
    print(f"Compliance: {report['compliance_percentage']}%")
    print(f"Valid: {report['valid_documents']}")
    print(f"Expired: {report['expired_documents']}")
    print(f"Close to expiration: {report['close_to_expiration']}")
    print(f"Requires action: {report['requires_immediate_action']}")

    # Get expiring documents
    print("\n=== Expiring Documents (45 days) ===")
    expiring = agent.get_expiring_documents(documents, days_threshold=45)
    for doc in expiring:
        print(f"- {doc['document_name']}: {doc['days_remaining']} days (urgency: {doc['urgency']})")

# Made with Bob
