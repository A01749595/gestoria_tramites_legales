"""
GestoriaVertiche22 — Backend API FastAPI

Reemplaza el frontend Streamlit por una API consumible desde React/Node.js,
conservando los módulos base de GestoriaVertiche22: OCR, Supabase Storage,
workflow multi-agente, Teams, WhatsApp, Calendar, dashboard y asistente.

Ejecutar:
    uvicorn app:app --reload --port 8000
"""
from dotenv import load_dotenv
load_dotenv()

import os
import re
import json
import logging
import asyncio
import threading
from contextlib import asynccontextmanager
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Union
from supabase import create_client

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr

from config import get_config, is_configured
from schemas.schemas import Branch, Document, DocumentStatus, LegalRiskLevel
from workflows.compliance_workflow import ComplianceWorkflow
from dashboard.dashboard_service import DashboardService
from compliance_chat_assistant import build_context, call_openai_assistant
from services.tramites_service import TramitesService
import services.branch_config_service as branch_config_svc

#------------------------------------------------------------------------------
# Para el Login/Registro de usuarios
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

# Importamos las herramientas que moviste a la raíz
from database import get_db, UserDB
from auth import verificar_password, obtener_password_hasheada, crear_token_acceso

class UserSchema(BaseModel):
    email: EmailStr
    password: str
# ----------------------------------------------------------------------------


logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
logger = logging.getLogger("vertiche.api")

# Servicio de trámites manuales (persistencia en JSON en disco). Se crea
# de inmediato porque no depende de Supabase ni del workflow; la primera
# vez precarga el JSON con los datos semilla de TRAMITES.docx.
tramites_service = TramitesService()

CONFIG = get_config()
SUPABASE_URL = CONFIG["supabase"].get("url")
SUPABASE_KEY = CONFIG["supabase"].get("key")
SUPABASE_BUCKET = CONFIG["supabase"].get("bucket")
SUPABASE_PREFIX = os.getenv("SUPABASE_PREFIX", "") or ""
OPENAI_API_KEY = CONFIG["openai"].get("api_key")
CHAT_MODEL = CONFIG["openai"].get("chat_model")

# Límite de PDFs procesados al arranque para no quemar minutos/tokens en el primer hit.
# Si quieres procesar TODOS, pon MAX_PDFS_AT_STARTUP=0 en .env.
MAX_PDFS_AT_STARTUP = int(os.getenv("MAX_PDFS_AT_STARTUP", "20") or 20)

# Archivo de caché en disco para el dataset OCR ya procesado.
# Evita re-procesar los PDFs cada vez que se reinicia el backend.
# Bórralo manualmente (o usa /api/refresh) si quieres forzar re-proceso completo.
COMPLIANCE_CACHE_FILE = os.getenv("COMPLIANCE_CACHE_FILE", "compliance_cache.json")


# Estado global del backend (visible vía /api/status)
supabase = None
bucket = None
supabase_error: Optional[str] = None
openai_client = None
openai_error: Optional[str] = None
workflow: Optional[ComplianceWorkflow] = None
dashboard_svc = DashboardService()

COMPLIANCE_CACHE: Optional[Dict[str, Any]] = None
PC_VISITS: List[Dict[str, Any]] = []

# Estado del worker de ingesta
INGEST_STATE: Dict[str, Any] = {
    "phase": "idle",          # idle | connecting | listing | ocr | ready | error
    "message": "Backend iniciando...",
    "processed": 0,
    "total": 0,
    "started_at": None,
    "finished_at": None,
    "error": None,
}
_ingest_lock = threading.Lock()


def _init_supabase_blocking() -> None:
    """Inicializa cliente Supabase. Bloqueante: solo llamar desde un hilo aparte."""
    global supabase, bucket, supabase_error
    if not (SUPABASE_URL and SUPABASE_KEY):
        supabase_error = "Faltan SUPABASE_URL o SUPABASE_KEY en .env"
        logger.warning(supabase_error)
        return
    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        candidate_bucket = supabase.storage.from_(SUPABASE_BUCKET)
        # Probamos acceso real al bucket (esto puede tardar / fallar por RLS).
        try:
            items = candidate_bucket.list(path=SUPABASE_PREFIX)
            logger.info(
                "Supabase conectado: bucket=%r, prefix=%r, items_at_root=%d",
                SUPABASE_BUCKET, SUPABASE_PREFIX, len(items or []),
            )
            bucket = candidate_bucket
            supabase_error = None
        except Exception as e:
            supabase_error = (
                f"Bucket '{SUPABASE_BUCKET}' no accesible: {e}. "
                "Revisa que exista en Supabase y que la KEY tenga permisos."
            )
            logger.error(supabase_error)
            bucket = None
    except Exception as e:
        supabase_error = f"Supabase no inicializó: {e}"
        logger.exception("Error inicializando Supabase")
        bucket = None


def _init_openai_blocking() -> None:
    global openai_client, openai_error
    if not OPENAI_API_KEY:
        openai_error = "Falta OPENAI_API_KEY"
        return
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception as e:
        openai_error = f"OpenAI no inicializó: {e}"


def _bootstrap_blocking() -> None:
    """
    Toda la inicialización pesada vive aquí. Corre en un thread aparte
    (vía asyncio.to_thread) para que uvicorn pueda empezar a aceptar
    conexiones de inmediato.
    """
    global workflow, COMPLIANCE_CACHE
    with _ingest_lock:
        INGEST_STATE["phase"] = "connecting"
        INGEST_STATE["message"] = "Conectando a Supabase y OpenAI..."
        INGEST_STATE["started_at"] = datetime.utcnow().isoformat()

    _init_supabase_blocking()
    _init_openai_blocking()

    try:
        workflow = ComplianceWorkflow(config=CONFIG, supabase_bucket=bucket)
    except Exception as e:
        logger.warning("ComplianceWorkflow no inicializó: %s — notificaciones en modo simulado", e)
        '''with _ingest_lock:
            INGEST_STATE["phase"] = "error"
            INGEST_STATE["error"] = f"ComplianceWorkflow: {e}"
            INGEST_STATE["message"] = "Falló la inicialización del workflow."
            INGEST_STATE["finished_at"] = datetime.utcnow().isoformat()
        return

    # Si algo crítico falta, dejamos demo y NO disparamos OCR.
    if bucket is None or openai_client is None:
        COMPLIANCE_CACHE = demo_dataset()
        with _ingest_lock:
            INGEST_STATE["phase"] = "ready"
            INGEST_STATE["message"] = (
                f"Modo demo. supabase_error={supabase_error!r} openai_error={openai_error!r}"
            )
            INGEST_STATE["finished_at"] = datetime.utcnow().isoformat()
        return'''

    # Pre-carga del dataset (esto sí hace OCR + LLM).
    try:
        with _ingest_lock:
            INGEST_STATE["phase"] = "loading"
            INGEST_STATE["message"] = "Cargando dataset desde tramites_data.json..."
        build_compliance_dataset(force_refresh=True)
        with _ingest_lock:
            INGEST_STATE["phase"] = "ready"
            INGEST_STATE["message"] = "Dataset listo."
            INGEST_STATE["finished_at"] = datetime.utcnow().isoformat()
    except Exception as e:
        logger.exception("Falló la carga del dataset")
        with _ingest_lock:
            INGEST_STATE["phase"] = "error"
            INGEST_STATE["error"] = str(e)
            INGEST_STATE["message"] = "Falló la carga del dataset."
            INGEST_STATE["finished_at"] = datetime.utcnow().isoformat()


@asynccontextmanager
async def lifespan(_: "FastAPI"):
    # Arranca el bootstrap en background. Uvicorn empieza a servir AHORA.
    task = asyncio.create_task(asyncio.to_thread(_bootstrap_blocking))
    logger.info("FastAPI listo para recibir peticiones. Ingesta corriendo en background.")
    try:
        yield
    finally:
        # Al apagar, esperamos un poquito a que termine el bootstrap si seguía.
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


app = FastAPI(title="GestoriaVertiche22 API", version="2.0.0", lifespan=lifespan)
_cors_origins = [o.strip() for o in os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173"
).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins= ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._\-]+", "_", name or "documento.pdf")


def model_to_dict(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "dict"):
        return obj.dict()
    return dict(obj)


def list_all_pdfs_in_bucket(prefix: Optional[str] = None) -> List[str]:
    if bucket is None:
        return []
    prefix = SUPABASE_PREFIX if prefix is None else prefix
    out: List[str] = []
    pendings = [prefix]
    seen_dirs: set = set()
    page_size = 1000
    while pendings:
        cur = pendings.pop(0)
        if cur in seen_dirs:
            continue
        seen_dirs.add(cur)
        offset = 0
        while True:
            try:
                items = bucket.list(path=cur, options={"limit": page_size, "offset": offset, "sortBy": {"column": "name", "order": "asc"}})
            except TypeError:
                try:
                    items = bucket.list(path=cur)
                except Exception as e:
                    logger.warning("bucket.list(%r): %s", cur, e)
                    items = []
                offset = -1
            except Exception as e:
                logger.warning("bucket.list(%r, offset=%s): %s", cur, offset, e)
                items = []
            if not items:
                break
            for it in items:
                name = it.get("name")
                if not name:
                    continue
                full = f"{cur}/{name}".strip("/") if cur else name
                is_folder = it.get("id") is None and it.get("metadata") is None
                if is_folder:
                    pendings.append(full)
                else:
                    meta = it.get("metadata") or {}
                    mimetype = (meta.get("mimetype") or "").lower()
                    if name.lower().endswith(".pdf") or "pdf" in mimetype:
                        out.append(full)
            if offset < 0 or len(items) < page_size:
                break
            offset += page_size
    return out


EXTRACT_SYSTEM = """Eres un asistente experto en contratos de arrendamiento y trámites legales de
sucursales comerciales en México. Tu única salida debe ser un objeto JSON con esta estructura
exacta. Usa nombres oficiales y normalizados (sin abreviaturas), todo en español.

{
    "branch_name": "nombre comercial o número de la sucursal/tienda (ej. 'Tienda 21 Coyoacán', 'Sucursal Centro CDMX')",
    "state": "nombre oficial completo del estado mexicano (ej. 'Ciudad de México', no 'CDMX'; 'Estado de México', no 'Edomex')",
    "municipality": "municipio o alcaldía oficial (ej. 'Coyoacán', 'Cuauhtémoc')",
    "responsible_party": "razón social del arrendatario o responsable",
    "issuing_authority": "autoridad o arrendador que emite o firma el documento",
    "document_type": "uno de: contrato_arrendamiento | licencia_funcionamiento | permiso | certificado | aviso | constancia | otro",
    "issue_date": "fecha de emisión en formato YYYY-MM-DD, o null",
    "expiration_date": "fecha de vencimiento en formato YYYY-MM-DD, o null",
    "folio_number": "folio, número de contrato o número de permiso (string), o null",
    "monthly_rent_mxn": número decimal en MXN o null,
    "term_months": número entero de meses o null,
    "risk_level": "low | medium | high | critical (high si vence en menos de 90 días, critical si ya venció o falta info esencial)"
}

Reglas estrictas:
- Si un campo no aparece en el texto, usa null. NUNCA inventes.
- Para fechas: convierte cualquier formato a YYYY-MM-DD. Si el contrato dice "vigencia de 24 meses a partir del 1 de marzo de 2024", calcula expiration_date.
- Para state y municipality: usa el nombre oficial sin acentos faltantes ni abreviaturas.
- branch_name: si solo encuentras un número de tienda (ej. "Tienda 021"), úsalo tal cual.
"""


_STATE_NORMALIZATION = {
    "cdmx": "Ciudad de México",
    "cd mx": "Ciudad de México",
    "df": "Ciudad de México",
    "ciudad de mexico": "Ciudad de México",
    "mexico df": "Ciudad de México",
    "edomex": "Estado de México",
    "estado de mexico": "Estado de México",
    "edo mex": "Estado de México",
    "edo de mexico": "Estado de México",
    "n l": "Nuevo León",
    "nl": "Nuevo León",
    "nuevo leon": "Nuevo León",
    "qroo": "Quintana Roo",
    "q roo": "Quintana Roo",
    "bcs": "Baja California Sur",
    "bc": "Baja California",
    "slp": "San Luis Potosí",
    "san luis potosi": "San Luis Potosí",
    "yuc": "Yucatán",
    "yucatan": "Yucatán",
    "michoacan": "Michoacán",
    "queretaro": "Querétaro",
    "nayarit": "Nayarit",
}


def normalize_state(value: Optional[str]) -> str:
    if not value or not str(value).strip():
        return "Sin estado"
    raw = str(value).strip()
    key = raw.lower().replace(".", "").replace("-", " ")
    key = re.sub(r"\s+", " ", key)
    return _STATE_NORMALIZATION.get(key, raw.title() if raw.islower() else raw)


_DOCUMENT_TYPE_LABELS = {
    "contrato_arrendamiento": "Contrato de arrendamiento",
    "contrato-arrendamiento": "Contrato de arrendamiento",
    "contrato": "Contrato",
    "licencia": "Licencia",
    "licencia_funcionamiento": "Licencia de funcionamiento",
    "licencia-funcionamiento": "Licencia de funcionamiento",
    "permiso": "Permiso",
    "certificado": "Certificado",
    "aviso": "Aviso",
    "constancia": "Constancia",
    "otro": "Otro",
}


def humanize_document_type(value: Optional[str]) -> str:
    if not value:
        return "Documento"
    key = str(value).strip().lower().replace(" ", "_")
    return _DOCUMENT_TYPE_LABELS.get(key, str(value).replace("_", " ").capitalize())


def _slug_branch_key(branch_name: str, state: str, municipality: str) -> str:
    """Clave estable para agrupar PDFs de la MISMA sucursal aunque vengan en archivos distintos."""
    raw = f"{branch_name}|{state}|{municipality}".lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return raw or "sin-sucursal"


# Tabla en memoria branch_key -> branch_id (estable durante la vida del proceso)
_BRANCH_ID_REGISTRY: Dict[str, str] = {}


def _stable_branch_id(branch_name: str, state: str, municipality: str) -> str:
    """Devuelve un branch_id consistente: misma sucursal → mismo id, sin importar el PDF."""
    key = _slug_branch_key(branch_name, state, municipality)
    if key in _BRANCH_ID_REGISTRY:
        return _BRANCH_ID_REGISTRY[key]
    new_id = f"BR-{len(_BRANCH_ID_REGISTRY) + 1:05d}"
    _BRANCH_ID_REGISTRY[key] = new_id
    return new_id


def _pretty_document_name(pdf_path: str, document_type: str, folio: Optional[str]) -> str:
    """
    Devuelve el nombre del documento TAL CUAL está guardado el archivo en
    el bucket (incluyendo su extensión). Antes se construía un nombre
    "bonito" a partir del tipo y el folio; ahora se respeta el nombre real
    del archivo para que el usuario pueda identificarlo en Supabase.

    Ejemplos:
        "2026/CDMX/Aviso_funcionamiento_T-001.pdf"
            -> "Aviso_funcionamiento_T-001.pdf"
        "Licencia ambiental Puebla.pdf"
            -> "Licencia ambiental Puebla.pdf"

    Si por alguna razón no hay ruta, cae de vuelta al tipo de documento.
    """
    base = os.path.basename(pdf_path or "").strip()
    if base:
        return base
    return humanize_document_type(document_type)


EXTRACT_SYSTEM_LEGACY = """Eres un asistente experto en contratos de arrendamiento de sucursales en México."""


def extract_contract_fields(text: str) -> Optional[Dict[str, Any]]:
    if openai_client is None or not text.strip():
        return None
    try:
        resp = openai_client.chat.completions.create(
            model=CHAT_MODEL,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": text[:15000]}],
        )
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        logger.error("extract_contract_fields: %s", e)
        return None


def parse_date_safe(value) -> Optional[date]:
    if not value or value in ("null", "None"):
        return None
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None


def status_from_expiration(exp: Optional[date]) -> DocumentStatus:
    if exp is None:
        return DocumentStatus.INCOMPLETE
    days = (exp - date.today()).days
    if days < 0:
        return DocumentStatus.EXPIRED
    if days <= 45:
        return DocumentStatus.CLOSE_TO_EXPIRATION
    return DocumentStatus.VALID


# ---------------------------------------------------------------------- #
# Inferencia de fechas por carpeta (cuando el LLM no encuentra fecha)    #
# ---------------------------------------------------------------------- #
#
# El bucket de Supabase está organizado por año: "2026/...", "2025/...",
# "2024/...", etc. Cuando OpenAI NO logra extraer expiration_date del
# texto OCR, usamos el año de la carpeta para decidir el estado del
# documento sin marcarlo como "Sin fecha":
#
#   - 2026/... -> Documento del año en curso. Lo asumimos VIGENTE
#                 (expiration_date = 31 de diciembre de 2026). Es el
#                 año prioritario del proyecto.
#   - 2025/... -> Documento del año anterior. POR VENCER (vencimiento
#                 estimado 31 de diciembre de 2025; ya cerró el año
#                 fiscal pero puede seguir vigente algunas semanas).
#   - 2024 o anterior -> VENCIDO (expiration_date = 31 de diciembre
#                 del año detectado en la ruta).
#   - Sin año detectable -> queda como INCOMPLETE / "Sin fecha".
#
# Esto se controla con la variable PRIORITY_YEAR (default 2026). Si en
# 2027 quieren cambiarlo, basta con setear PRIORITY_YEAR=2027 en .env.

PRIORITY_YEAR = int(os.getenv("PRIORITY_YEAR", "2026") or 2026)

# Match años de 4 dígitos al inicio de cualquier segmento de la ruta:
# "2026/...", "tramites/2025/...", etc.
_YEAR_IN_PATH_RE = re.compile(r"(?:^|/)(20\d{2})(?:/|$)")


def detect_year_from_path(pdf_path: str) -> Optional[int]:
    """
    Devuelve el primer año (2000-2099) que aparezca como segmento
    independiente en la ruta, o None si no encuentra ninguno.

    Ejemplos:
        "2026/CDMX/contrato.pdf"       -> 2026
        "tramites/2025/MTY/lic.pdf"    -> 2025
        "documentos/sucursal_42.pdf"   -> None
    """
    if not pdf_path:
        return None
    match = _YEAR_IN_PATH_RE.search(pdf_path)
    if not match:
        return None
    try:
        year = int(match.group(1))
    except (TypeError, ValueError):
        return None
    if 2000 <= year <= 2099:
        return year
    return None


def fallback_expiration_from_year(year: int) -> date:
    """
    Para documentos sin fecha de vencimiento real, asignamos el
    último día del año detectado. Esto produce un estado coherente
    cuando entra a status_from_expiration():
        - año < hoy.year   -> EXPIRED
        - año == hoy.year  -> CLOSE_TO_EXPIRATION o VALID (depende del mes)
        - año > hoy.year   -> VALID
    """
    return date(year, 12, 31)


def folder_priority(pdf_path: str) -> int:
    """
    Prioridad de procesamiento para ordenar la cola de OCR.
    Menor = más prioritario.
        PRIORITY_YEAR (2026)        -> 0  (se procesa primero)
        Año actual o el anterior     -> 1
        Resto de años / sin año      -> 2
    Permite que el dashboard arranque viendo lo del año en curso y lo
    más reciente, dejando archivos antiguos para el final.
    """
    year = detect_year_from_path(pdf_path)
    if year is None:
        return 2
    if year == PRIORITY_YEAR:
        return 0
    current = date.today().year
    if year >= current - 1:
        return 1
    return 2


def fields_to_branch_document(pdf_path: str, fields: Dict[str, Any], extracted_text: Optional[str] = None,
                                ocr_confidence: float = 0.9) -> Optional[Dict[str, Any]]:
    if not fields:
        return None
    # --- Normalización de campos del LLM ---
    raw_branch_name = fields.get("branch_name")
    branch_name = (raw_branch_name or os.path.basename(pdf_path).rsplit(".", 1)[0] or "Sin nombre").strip()
    state = normalize_state(fields.get("state"))
    municipality = (fields.get("municipality") or "Sin municipio").strip().title() if fields.get("municipality") else "Sin municipio"

    # --- IDs estables ---
    branch_id = _stable_branch_id(branch_name, state, municipality)
    folio = fields.get("folio_number")
    if folio is not None:
        folio = str(folio).strip() or None
    document_type = (fields.get("document_type") or "otro").strip().lower()

    # document_id estable a partir del path del PDF (un PDF = un documento)
    document_id = f"DOC-{abs(hash(pdf_path)) % 10_000_000:07d}"

    exp = parse_date_safe(fields.get("expiration_date"))
    issue = parse_date_safe(fields.get("issue_date"))

    # ── Fallback por carpeta ──
    # Si el LLM no encontró expiration_date, miramos el año de la
    # carpeta donde está guardado el PDF. Esto evita que MUCHOS
    # documentos terminen en "Sin fecha" cuando el OCR no logró
    # capturar la fecha en el texto, pero la organización por carpetas
    # ya nos dice de qué año son.
    folder_year = detect_year_from_path(pdf_path)
    inferred_from_folder = False
    if exp is None and folder_year is not None:
        exp = fallback_expiration_from_year(folder_year)
        inferred_from_folder = True

    document_name = _pretty_document_name(pdf_path, document_type, folio)

    try:
        branch = Branch(
            branch_id=branch_id,
            branch_name=str(branch_name)[:120],
            state=state,
            municipality=str(municipality)[:120],
            region="Nacional",
            responsible_email=os.getenv("DEFAULT_RESPONSIBLE_EMAIL", "responsable@vertiche.mx"),
            manager_email=os.getenv("DEFAULT_MANAGER_EMAIL", "gerente@vertiche.mx"),
            supervisor_email=os.getenv("DEFAULT_SUPERVISOR_EMAIL") or None,
            director_email=os.getenv("DEFAULT_DIRECTOR_EMAIL") or None,
            whatsapp_contact=os.getenv("DEFAULT_WHATSAPP", "+520000000000"),
        )
        document = Document(
            document_id=document_id,
            branch_id=branch_id,
            document_name=document_name[:200],
            document_type=document_type,
            issuing_authority=(fields.get("issuing_authority") or "Sin especificar")[:200],
            issue_date=issue,
            expiration_date=exp,
            status=status_from_expiration(exp),
            ocr_confidence=float(ocr_confidence or 0.0),
            file_url=pdf_path,
            folio_number=folio,
            extracted_text=(extracted_text[:2000] if extracted_text else None),
            metadata={
                "risk_level": fields.get("risk_level"),
                "monthly_rent_mxn": fields.get("monthly_rent_mxn"),
                "term_months": fields.get("term_months"),
                "responsible_party": fields.get("responsible_party"),
                # Pistas útiles para mostrar / depurar en el frontend
                "branch_name": branch.branch_name,
                "state": branch.state,
                "municipality": branch.municipality,
                "document_type_label": humanize_document_type(document_type),
                # Marca si la fecha de vencimiento vino del año detectado
                # en la ruta del bucket (no del texto del PDF). El frontend
                # lo usa para mostrar "fecha inferida por carpeta".
                "folder_year": folder_year,
                "expiration_inferred_from_folder": inferred_from_folder,
            },
        )
        return {"branch": branch, "document": document}
    except Exception as e:
        logger.error("fields_to_branch_document(%s): %s", pdf_path, e)
        return None


def demo_dataset() -> Dict[str, Any]:
    today = date.today()
    branches = [
        Branch(branch_id="BR-DEMO-001", branch_name="Sucursal Centro CDMX", state="Ciudad de México", municipality="Cuauhtémoc", region="Centro", responsible_email="responsable@vertiche.mx", manager_email="gerente@vertiche.mx", supervisor_email=os.getenv("DEFAULT_SUPERVISOR_EMAIL") or None, director_email=os.getenv("DEFAULT_DIRECTOR_EMAIL") or None, whatsapp_contact="+525500000000"),
        Branch(branch_id="BR-DEMO-002", branch_name="Sucursal Monterrey", state="Nuevo León", municipality="Monterrey", region="Norte", responsible_email="responsable@vertiche.mx", manager_email="gerente@vertiche.mx", supervisor_email=os.getenv("DEFAULT_SUPERVISOR_EMAIL") or None, director_email=os.getenv("DEFAULT_DIRECTOR_EMAIL") or None, whatsapp_contact="+525500000000"),
    ]
    docs = [
        Document(document_id="DOC-DEMO-001", branch_id="BR-DEMO-001", document_name="Contrato de arrendamiento", document_type="contrato_arrendamiento", issuing_authority="Arrendador", issue_date=today, expiration_date=today.replace(year=today.year + 1), status=DocumentStatus.VALID, ocr_confidence=0.95, file_url="demo/contrato.pdf"),
        Document(document_id="DOC-DEMO-002", branch_id="BR-DEMO-002", document_name="Licencia de funcionamiento", document_type="licencia", issuing_authority="Municipio", issue_date=today, expiration_date=today, status=DocumentStatus.CLOSE_TO_EXPIRATION, ocr_confidence=0.88, file_url="demo/licencia.pdf"),
    ]
    return {
        "branches": branches,
        "documents": docs,
        "compliance_scores": {"BR-DEMO-001": 95.0, "BR-DEMO-002": 70.0},
        "extraction_log": [],
        "generated_at": datetime.utcnow().isoformat(),
        "total_pdfs": 0,
        "ocr_stats": {
            "tesseract": 0,
            "pymupdf": 0,
            "hybrid": 0,
            "failed_ocr": 0,
            "failed_llm": 0,
            "ok": 0,
        },
        "demo": True,
    }


# ─── Mapeos para construcción desde JSON ──────────────────────────────────────

_PERMISO_TO_DOCTYPE: Dict[str, str] = {
    "aviso de funcionamiento": "aviso",
    "aviso funcionamiento": "aviso",
    "uso de suelo": "permiso",
    "uso suelo": "permiso",
    "anuncio": "permiso",
    "proteccion civil": "certificado",
    "proteccion civil visto bueno": "certificado",
    "licencia ambiental": "licencia_funcionamiento",
    "licencia de funcionamiento": "licencia_funcionamiento",
    "dictamen de bomberos": "certificado",
    "dictamen bomberos": "certificado",
}

_TRAMITES_ESTADO_TO_STATUS: Dict[str, DocumentStatus] = {
    "vigente": DocumentStatus.VALID,
    "por_vencer": DocumentStatus.CLOSE_TO_EXPIRATION,
    "vencido": DocumentStatus.EXPIRED,
    "en_tramite": DocumentStatus.PENDING_REVIEW,
    "sin_tramite": DocumentStatus.MISSING,
    "sin_dato": DocumentStatus.INCOMPLETE,
}

# Estado y municipio conocidos por tramite_id (el JSON los tiene vacíos por defecto).
_BRANCH_LOCATION: Dict[str, tuple] = {
    "T-001": ("Ciudad de México",  "Iztacalco"),
    "T-003": ("Ciudad de México",  "Benito Juárez"),
    "T-007": ("Estado de México",  "Tlalnepantla de Baz"),
    "T-008": ("Estado de México",  "Chalco"),
    "T-014": ("Puebla",            "San Andrés Cholula"),
    "T-015": ("Puebla",            "Atlixco"),
    "T-016": ("Puebla",            "Puebla"),
    "T-017": ("Puebla",            "Izúcar de Matamoros"),
    "T-018": ("Tlaxcala",          "Huamantla"),
    "T-019": ("Veracruz",          "Orizaba"),
    "T-022": ("Veracruz",          "Veracruz"),
    "T-023": ("Guerrero",          "Chilpancingo de los Bravo"),
    "T-024": ("Michoacán",         "Zamora"),
    "T-025": ("Michoacán",         "Uruapan"),
    "T-028": ("Yucatán",           "Mérida"),
    "T-030": ("Veracruz",          "Tuxpan"),
    "T-032": ("Chiapas",           "Tuxtla Gutiérrez"),
    "T-034": ("Tabasco",           "Villahermosa"),
    "T-035": ("Morelos",           "Cuautla"),
    "T-037": ("Tlaxcala",          "Apizaco"),
    "T-038": ("Estado de México",  "Toluca"),
}

# Coordenadas exactas por sucursal (lat, lng) para el mapa.
_BRANCH_COORDS: Dict[str, tuple] = {
    "T-001": (19.413, -99.108),
    "T-003": (19.388, -99.164),
    "T-007": (19.538, -99.196),
    "T-008": (19.261, -98.900),
    "T-014": (19.053, -98.285),
    "T-015": (18.909, -98.439),
    "T-016": (19.041, -98.206),
    "T-017": (18.598, -98.467),
    "T-018": (19.313, -97.921),
    "T-019": (18.851, -97.100),
    "T-022": (19.185, -96.142),
    "T-023": (17.551, -99.501),
    "T-024": (19.984, -102.284),
    "T-025": (19.415, -102.062),
    "T-028": (20.967, -89.623),
    "T-030": (20.955, -97.407),
    "T-032": (16.752, -93.115),
    "T-034": (17.989, -92.932),
    "T-035": (18.817, -98.945),
    "T-037": (19.415, -98.133),
    "T-038": (19.289, -99.656),
}

# Regex para parsear rutas del bucket: prefijo/T-XXX Nombre/YYYY/N. descripcion.pdf
_BUCKET_PATH_RE = re.compile(
    r"^[^/]+/(T-\d+)\s+[^/]+/(\d{4})/(\d+)\.",
    re.IGNORECASE,
)


def build_compliance_dataset_from_json() -> Dict[str, Any]:
    """
    Construye Branch + Document desde tramites_data.json.
    Si Supabase está disponible, crea un Document por cada PDF en el bucket
    (166 archivos) enriqueciéndolos con los metadatos del JSON.
    Si no hay bucket, crea un Document por permiso del JSON (110 registros).
    Sin OCR ni OpenAI en ningún caso.
    """
    import unicodedata
    from services.tramites_service import clasificar_vigencia

    def _norm_key(text: str) -> str:
        n = "".join(
            c for c in unicodedata.normalize("NFD", text or "")
            if unicodedata.category(c) != "Mn"
        ).lower()
        n = re.sub(r"[^a-z0-9 ]", " ", n)
        return re.sub(r"\s+", " ", n).strip()

    json_data = tramites_service.get_all()

    # Índices rápidos para lookup por (tramite_id, permiso_no)
    suc_index: Dict[str, Any] = {}
    perm_index: Dict[str, Dict[str, Any]] = {}
    for suc in json_data["sucursales"]:
        tid = suc["tramite_id"]
        suc_index[tid] = suc
        perm_index[tid] = {str(p["no"]): p for p in suc.get("permisos", [])}

    branches: List[Branch] = []
    documents: List[Document] = []
    compliance_scores: Dict[str, float] = {}

    # ── 1. Construir Branches (siempre desde JSON + ubicaciones conocidas) ──
    for suc in json_data["sucursales"]:
        tramite_id = suc["tramite_id"]
        branch_id  = f"BR-{tramite_id}"
        branch_name = (suc.get("nombre") or f"Sucursal {tramite_id}").strip()

        raw_state = (suc.get("estado") or "").strip()
        raw_muni  = (suc.get("municipio") or "").strip()
        loc_state, loc_muni = _BRANCH_LOCATION.get(tramite_id, ("Sin estado", "Sin municipio"))
        state        = normalize_state(raw_state) if raw_state else loc_state
        municipality = raw_muni if raw_muni else loc_muni

        try:
            branch = Branch(
                branch_id=branch_id,
                branch_name=branch_name[:120],
                state=state,
                municipality=municipality[:120],
                region="Nacional",
                responsible_email=os.getenv("DEFAULT_RESPONSIBLE_EMAIL", "responsable@vertiche.mx"),
                manager_email=os.getenv("DEFAULT_MANAGER_EMAIL", "gerente@vertiche.mx"),
                supervisor_email=os.getenv("DEFAULT_SUPERVISOR_EMAIL") or None,
                director_email=os.getenv("DEFAULT_DIRECTOR_EMAIL") or None,
                whatsapp_contact=os.getenv("DEFAULT_WHATSAPP", "+520000000000"),
            )
            branches.append(branch)
        except Exception as e:
            logger.warning("Branch inválida (%s): %s — saltando", tramite_id, e)
            continue

        cumpl = suc.get("cumplimiento", {})
        compliance_scores[branch_id] = float(cumpl.get("porcentaje", 0.0))

    # ── 2a. Documentos desde Supabase bucket (un Document por PDF) ──
    if bucket is not None:
        pdf_paths = list_all_pdfs_in_bucket()
        for pdf_path in pdf_paths:
            m = _BUCKET_PATH_RE.match(pdf_path)
            tramite_id  = m.group(1) if m else None
            year        = int(m.group(2)) if m else detect_year_from_path(pdf_path)
            permiso_no  = m.group(3) if m else None

            branch_id  = f"BR-{tramite_id}" if tramite_id else "BR-DESCONOCIDO"
            suc        = suc_index.get(tramite_id) if tramite_id else None
            perm       = perm_index.get(tramite_id, {}).get(permiso_no) if tramite_id and permiso_no else None

            # Vigencia: usar la del año de la carpeta (2025 o 2026)
            vigencia_key = f"vigencia_{year}" if year in (2025, 2026) else "vigencia_2026"
            vigencia_val = (perm or {}).get(vigencia_key, "") if perm else ""

            if vigencia_val:
                cls      = clasificar_vigencia(vigencia_val)
                estado   = cls["estado"]
                fecha    = cls["fecha"]
            else:
                folder_year = detect_year_from_path(pdf_path)
                fecha  = fallback_expiration_from_year(folder_year) if folder_year else None
                estado = "sin_dato"

            doc_status    = _TRAMITES_ESTADO_TO_STATUS.get(estado, DocumentStatus.INCOMPLETE)
            nombre_permiso = (perm or {}).get("permiso") or os.path.basename(pdf_path).rsplit(".", 1)[0]
            doc_type      = _PERMISO_TO_DOCTYPE.get(_norm_key(nombre_permiso), "otro")
            if re.search(r'\bfac(tura)?\b', os.path.basename(pdf_path), re.IGNORECASE):
                doc_type = "factura"

            loc_state, loc_muni = _BRANCH_LOCATION.get(tramite_id or "", ("Sin estado", "Sin municipio"))
            branch_name   = ((suc or {}).get("nombre") or "").strip()
            raw_state     = ((suc or {}).get("estado") or "").strip()
            raw_muni      = ((suc or {}).get("municipio") or "").strip()
            state_doc     = normalize_state(raw_state) if raw_state else loc_state
            muni_doc      = raw_muni if raw_muni else loc_muni

            doc_id   = f"DOC-{abs(hash(pdf_path)) % 10_000_000:07d}"
            doc_name = os.path.basename(pdf_path)

            try:
                doc = Document(
                    document_id=doc_id,
                    branch_id=branch_id,
                    document_name=doc_name,
                    document_type=doc_type,
                    issuing_authority="Sin especificar",
                    issue_date=None,
                    expiration_date=fecha,
                    status=doc_status,
                    ocr_confidence=1.0,
                    file_url=pdf_path,
                    folio_number=None,
                    extracted_text=None,
                    metadata={
                        "from_json": True,
                        "vigencia_val": vigencia_val,
                        "folder_year": year,
                        "branch_name": branch_name,
                        "state": state_doc,
                        "municipality": muni_doc,
                        "document_type_label": humanize_document_type(doc_type),
                    },
                )
                documents.append(doc)
            except Exception as e:
                logger.warning("Document inválido (%s): %s — saltando", pdf_path, e)

    else:
        # ── 2b. Sin bucket: un Document por permiso en el JSON ──
        for suc in json_data["sucursales"]:
            tramite_id  = suc["tramite_id"]
            branch_id   = f"BR-{tramite_id}"
            branch_name = (suc.get("nombre") or f"Sucursal {tramite_id}").strip()
            raw_state   = (suc.get("estado") or "").strip()
            raw_muni    = (suc.get("municipio") or "").strip()
            loc_state, loc_muni = _BRANCH_LOCATION.get(tramite_id, ("Sin estado", "Sin municipio"))
            state       = normalize_state(raw_state) if raw_state else loc_state
            municipality = raw_muni if raw_muni else loc_muni

            for permiso in suc.get("permisos", []):
                no            = str(permiso.get("no", "0")).strip() or "0"
                nombre_permiso = (permiso.get("permiso") or "Documento").strip()
                vigencia_val  = permiso.get("vigencia_2026", "")
                cls    = clasificar_vigencia(vigencia_val)
                estado = cls["estado"]
                if estado == "no_aplica":
                    continue
                fecha      = cls["fecha"]
                doc_status = _TRAMITES_ESTADO_TO_STATUS.get(estado, DocumentStatus.INCOMPLETE)
                doc_type   = _PERMISO_TO_DOCTYPE.get(_norm_key(nombre_permiso), "otro")
                try:
                    doc = Document(
                        document_id=f"DOC-{tramite_id}-{no}",
                        branch_id=branch_id,
                        document_name=nombre_permiso,
                        document_type=doc_type,
                        issuing_authority="Sin especificar",
                        issue_date=None,
                        expiration_date=fecha,
                        status=doc_status,
                        ocr_confidence=1.0,
                        file_url=f"json/{tramite_id}/{no}",
                        folio_number=None,
                        extracted_text=None,
                        metadata={
                            "from_json": True,
                            "vigencia_2026": vigencia_val,
                            "vigencia_2025": permiso.get("vigencia_2025", ""),
                            "branch_name": branch_name,
                            "state": state,
                            "municipality": municipality,
                            "document_type_label": humanize_document_type(doc_type),
                        },
                    )
                    documents.append(doc)
                except Exception as e:
                    logger.warning("Document inválido (%s/%s): %s — saltando", tramite_id, no, e)

    ok_count = len(documents)
    logger.info(
        "Dataset desde JSON+bucket: %d sucursales, %d documentos",
        len(branches), ok_count,
    )
    return {
        "branches": branches,
        "documents": documents,
        "compliance_scores": compliance_scores,
        "extraction_log": [],
        "generated_at": datetime.utcnow().isoformat(),
        "total_pdfs": ok_count,
        "ocr_stats": {
            "tesseract": 0, "pymupdf": 0, "hybrid": 0,
            "failed_ocr": 0, "failed_llm": 0,
            "ok": ok_count,
        },
        "demo": False,
        "source": "tramites_json",
    }


# ─── Caché en disco ────────────────────────────────────────────────────────────

def _load_cache_from_disk() -> Optional[Dict[str, Any]]:
    """
    Carga el dataset procesado del disco (compliance_cache.json).
    Reconstruye los objetos Branch y Document desde los dicts guardados.
    Devuelve None si el archivo no existe o está corrupto.
    """
    if not os.path.exists(COMPLIANCE_CACHE_FILE):
        return None
    try:
        with open(COMPLIANCE_CACHE_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # Reconstruir objetos Pydantic desde dicts
        from schemas.schemas import Branch, Document
        raw["branches"] = [Branch(**b) for b in raw.get("branches", [])]
        raw["documents"] = [Document(**d) for d in raw.get("documents", [])]
        logger.info(
            "Caché en disco cargada: %d sucursales, %d documentos (generada %s)",
            len(raw["branches"]), len(raw["documents"]), raw.get("generated_at", "?"),
        )
        return raw
    except Exception as e:
        logger.warning("No se pudo cargar caché en disco: %s — se re-procesará", e)
        return None


def _save_cache_to_disk(data: Dict[str, Any]) -> None:
    """
    Guarda el dataset en disco para que el próximo arranque lo use
    directamente sin correr OCR.
    """
    try:
        serializable = {
            **data,
            "branches":  [model_to_dict(b) for b in data.get("branches", [])],
            "documents": [model_to_dict(d) for d in data.get("documents", [])],
        }
        tmp = COMPLIANCE_CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, default=str)
        os.replace(tmp, COMPLIANCE_CACHE_FILE)
        logger.info("Caché guardada en disco: %s", COMPLIANCE_CACHE_FILE)
    except Exception as e:
        logger.warning("No se pudo guardar caché en disco: %s", e)


def _pdfs_already_cached(cached: Dict[str, Any]) -> set:
    """Devuelve el conjunto de file_url que ya están en la caché."""
    return {d.file_url for d in cached.get("documents", []) if d.file_url}



def build_compliance_dataset(force_refresh: bool = False, max_pdfs: Optional[int] = None) -> Dict[str, Any]:
    global COMPLIANCE_CACHE
    if COMPLIANCE_CACHE and not force_refresh:
        return COMPLIANCE_CACHE
    
    try:
        COMPLIANCE_CACHE = build_compliance_dataset_from_json()
    except Exception as e:
        logger.error("build_compliance_dataset_from_json falló: %s — usando demo", e)
        COMPLIANCE_CACHE = demo_dataset()
    return COMPLIANCE_CACHE


def serialize_dataset(data: Dict[str, Any]) -> Dict[str, Any]:
    branches_raw = data.get("branches", [])
    documents_raw = data.get("documents", [])
    branches_out = [model_to_dict(b) for b in branches_raw]
    documents_out = [model_to_dict(d) for d in documents_raw]

    # Aplicar overrides de correo por sucursal (branch_config.json).
    branch_overrides = branch_config_svc.get_all()
    for b in branches_out:
        override = branch_overrides.get(b.get("branch_id"), {})
        if override.get("responsible_email"):
            b["responsible_email"] = override["responsible_email"]
        # Coordenadas exactas para el mapa (sin depender del estado como fallback).
        tid = b.get("branch_id", "").replace("BR-", "")
        coords = _BRANCH_COORDS.get(tid)
        if coords:
            b["latitude"]  = coords[0]
            b["longitude"] = coords[1]

    # Mapa branch_id -> branch dict para enriquecer cada documento.
    branch_map = {b["branch_id"]: b for b in branches_out}
    for doc in documents_out:
        b = branch_map.get(doc.get("branch_id"))
        # Etiquetas listas para usar en el frontend.
        doc["status_label"] = status_label(doc.get("status", ""))
        doc["document_type_label"] = humanize_document_type(doc.get("document_type"))
        doc["expiration_date_display"] = _format_date_es(doc.get("expiration_date"))
        doc["issue_date_display"] = _format_date_es(doc.get("issue_date"))
        if b:
            doc["branch_name"] = b.get("branch_name")
            doc["branch_state"] = b.get("state")
            doc["branch_municipality"] = b.get("municipality")
    return {
        **data,
        "branches": branches_out,
        "documents": documents_out,
    }


def _format_date_es(value: Any) -> Optional[str]:
    """Convierte ISO o date a 'dd MMM yyyy' en español; tolera None y strings extraños."""
    if not value:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value).date()
        except ValueError:
            return value  # devuélvelo tal cual si no se puede parsear
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        return str(value)
    meses = ["ene", "feb", "mar", "abr", "may", "jun",
                "jul", "ago", "sep", "oct", "nov", "dic"]
    return f"{value.day:02d} {meses[value.month - 1]} {value.year}"


def status_label(status: str) -> str:
    return {
        "valid": "Vigente",
        "close_to_expiration": "Por vencer",
        "expired": "Vencido",
        "missing": "Faltante",
        "unreadable": "No legible",
        "incomplete": "Sin fecha",
        "pending_review": "Pendiente",
    }.get(status, status)


class AssistantChatRequest(BaseModel):
    messages: List[Dict[str, str]]


class PCVisitRequest(BaseModel):
    sucursal: str
    fecha: str
    hora: Optional[str] = None
    motivo: Optional[str] = None


class NotificationTestRequest(BaseModel):
    # Acepta:
    #   "+525512345678"
    #   "+525512345678,+525587654321"
    #   ["+525512345678", "+525587654321"]
    # Si está vacío usa DEFAULT_WHATSAPP del .env.
    whatsapp_to: Optional[Union[str, List[str]]] = None
    title: Optional[str] = "Prueba de agentes GestoriaVertiche"


class ExpiredAlertRequest(BaseModel):
    """Payload para /api/agents/send-expired-alert.

    recipient_email: destinatario único del correo HTML de urgencia.
    document_ids:    None = incluir TODOS los vencidos; lista = filtrar a
                    esos document_id específicos.
    """
    recipient_email: str
    document_ids: Optional[List[str]] = None


class TramitePermiso(BaseModel):
    """Un permiso dentro de la captura manual de una sucursal."""
    no: Optional[str] = ""
    permiso: str
    vigencia_2025: Optional[str] = ""
    vigencia_2026: Optional[str] = ""


class TramiteSucursalRequest(BaseModel):
    """Payload para guardar/actualizar una sucursal en el tab de llenado manual."""
    tramite_id: str
    nombre: str
    estado: Optional[str] = ""
    municipio: Optional[str] = ""
    permisos: List[TramitePermiso] = []


class SegmentedAlertRequest(BaseModel):
    """
    Payload para /api/agents/send-segmented-alert.

    Manda una alerta de documentos vencidos filtrada por una clasificación:
        segment_type:  "sucursal" | "municipio" | "estado"
        segment_value: el valor concreto (ej. "Puebla", "Cuauhtémoc",
                        "Sucursal Centro").
    Destinatarios — todos opcionales, todos aceptan varios separados por coma:
        emails:     correos a los que mandar el correo HTML.
        whatsapp:   números E.164 a los que mandar WhatsApp.
        send_teams: si True, también publica en el canal de Teams.
    Si no se pasan emails/whatsapp, se usan los asignados a las sucursales
    afectadas (responsible_email, manager_email, whatsapp_contact).
    """
    segment_type: str
    segment_value: str
    emails: Optional[str] = None
    whatsapp: Optional[str] = None
    send_teams: bool = False


class HierarchicalAlertRequest(BaseModel):
    """
    Payload para /api/agents/send-hierarchical-alerts.

    Envía correos escalonados por jerarquía según días restantes antes del
    vencimiento de cada documento, agrupando por sucursal:

        Día 40 (20 < días <= 40): solo responsables de tienda
        Día 20 (0 < días <= 20):  supervisor + responsables de tienda
        Día  0 (días <= 0):       supervisor + responsables + director

    branch_id: filtrar a una sola sucursal (None = todas).
    dry_run:   si True, devuelve la previsualización sin enviar correos.
    """
    branch_id: Optional[str] = None
    dry_run: bool = False


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "services": {svc: is_configured(svc) for svc in ["supabase", "openai", "ocr", "email", "calendar", "teams", "whatsapp"]},
        "errors": {"supabase": supabase_error, "openai": openai_error},
        "bucket": SUPABASE_BUCKET,
        "ingest_phase": INGEST_STATE.get("phase"),
        "ocr_backend": "tesseract+pymupdf",
    }


@app.get("/api/status")
def status():
    """
    Estado de la ingesta de fondo. Úsalo desde el frontend para hacer polling
    mientras el dashboard aún no está listo.
    """
    with _ingest_lock:
        snapshot = dict(INGEST_STATE)
    snapshot["supabase_ok"] = bucket is not None
    snapshot["openai_ok"] = openai_client is not None
    snapshot["workflow_ok"] = workflow is not None
    snapshot["cache_ready"] = COMPLIANCE_CACHE is not None
    snapshot["demo"] = bool((COMPLIANCE_CACHE or {}).get("demo"))
    return snapshot


def _empty_dashboard_payload(reason: str) -> Dict[str, Any]:
    """Respuesta rápida cuando aún no hay dataset listo. Evita timeouts del frontend."""
    empty_data = {
        "branches": [],
        "documents": [],
        "compliance_scores": {},
        "extraction_log": [],
        "generated_at": datetime.utcnow().isoformat(),
        "total_pdfs": INGEST_STATE.get("total", 0),
        "ocr_stats": {
            "tesseract": 0,
            "pymupdf": 0,
            "hybrid": 0,
            "failed_ocr": 0,
            "failed_llm": 0,
            "ok": 0,
        },
        "demo": False,
        "pending": True,
        "reason": reason,
    }
    return {
        "overview": {
            "total_branches": 0,
            "total_documents": 0,
            "documents_by_status": {},
            "expiring_soon_count": 0,
            "expired_count": 0,
        },
        "compliance_summary": {"average_score": 0},
        "alerts_summary": {},
        "state_analysis": {"states": {}},
        "document_type_analysis": {},
        "data": empty_data,
        "pending": True,
        "ingest": dict(INGEST_STATE),
    }


@app.get("/api/dashboard")
def dashboard(refresh: bool = False):
    # Si la cache aún no está lista y la ingesta sigue corriendo, devolvemos un payload
    # vacío inmediato. El frontend ya hace polling de /api/status y recargará cuando termine.
    with _ingest_lock:
        phase = INGEST_STATE.get("phase", "idle")
    if COMPLIANCE_CACHE is None and phase in {"connecting", "listing", "ocr"} and not refresh:
        return _empty_dashboard_payload(f"Ingesta en curso ({phase}).")

    data = build_compliance_dataset(force_refresh=refresh)
    branches = data["branches"]
    documents = data["documents"]
    scores = data["compliance_scores"]
    overview = dashboard_svc.get_overview_metrics(branches, documents)
    compliance = dashboard_svc.get_compliance_summary(branches, scores)
    alerts = dashboard_svc.get_alerts_summary(documents)
    states = dashboard_svc.get_state_analysis(branches, scores)
    doctype = dashboard_svc.get_document_type_analysis(documents)

    return {
        "overview": overview,
        "compliance_summary": compliance,
        "alerts_summary": alerts,
        "state_analysis": states,
        "document_type_analysis": doctype,
        "data": serialize_dataset(data),
    }


@app.get("/api/documents")
def documents():
    """
    Endpoint enriquecido para el tab de Documentos del frontend.

    Devuelve:
        - documents: docs ya procesados por OCR + LLM (con datos extraídos).
        - bucket_files: lista de PDFs realmente presentes en Supabase Storage.
        - totals: conteos para mostrar en el dashboard:
                * bucket_total: PDFs en Supabase
                * processed_total: PDFs con extracción exitosa
                * pending_total: PDFs en bucket aún no procesados
                * failed_ocr / failed_llm: errores por etapa
                * by_provider: { tesseract, pymupdf, hybrid }
                * by_status: { valid, expired, close_to_expiration, ... }
        - supabase: estado de la conexión (ok, bucket, error si lo hay).
        - ingest: snapshot del worker de ingesta (fase, % avance).
    """
    with _ingest_lock:
        phase = INGEST_STATE.get("phase", "idle")
        ingest_snapshot = dict(INGEST_STATE)

    # Conexión Supabase: la validamos siempre, esté o no listo el dataset
    supabase_info = {
        "connected": bucket is not None,
        "bucket": SUPABASE_BUCKET,
        "url_set": bool(SUPABASE_URL),
        "key_set": bool(SUPABASE_KEY),
        "error": supabase_error,
    }

    # Si la ingesta sigue en curso devolvemos lo que ya tengamos del bucket
    # para que el frontend al menos vea los archivos disponibles.
    if COMPLIANCE_CACHE is None and phase in {"connecting", "listing", "ocr"}:
        bucket_files = list_all_pdfs_in_bucket() if bucket is not None else []
        return {
            "documents": [],
            "bucket_files": bucket_files,
            "totals": {
                "bucket_total": len(bucket_files),
                "processed_total": 0,
                "pending_total": len(bucket_files),
                "failed_ocr": 0,
                "failed_llm": 0,
                "by_provider": {"tesseract": 0, "pymupdf": 0, "hybrid": 0},
                "by_status": {},
            },
            "supabase": supabase_info,
            "pending": True,
            "ingest": ingest_snapshot,
        }

    data = build_compliance_dataset(force_refresh=False)
    serialized = serialize_dataset(data)
    docs_out = serialized["documents"]
    bucket_files = list_all_pdfs_in_bucket() if bucket is not None else []
    ocr_stats = data.get("ocr_stats", {}) or {}

    # Conteo por estado de cumplimiento (vigente / por vencer / vencido / ...)
    by_status: Dict[str, int] = {}
    for d in docs_out:
        s = d.get("status") or "unknown"
        by_status[s] = by_status.get(s, 0) + 1

    # Conteo por tipo de documento
    by_type: Dict[str, int] = {}
    for d in docs_out:
        t = d.get("document_type") or "otro"
        by_type[t] = by_type.get(t, 0) + 1

    processed_total = int(ocr_stats.get("ok", len(docs_out)))
    bucket_total = len(bucket_files)
    pending_total = max(bucket_total - processed_total, 0)

    totals = {
        "bucket_total": bucket_total,
        "processed_total": processed_total,
        "pending_total": pending_total,
        "failed_ocr": int(ocr_stats.get("failed_ocr", 0)),
        "failed_llm": int(ocr_stats.get("failed_llm", 0)),
        "by_provider": {
            "tesseract": int(ocr_stats.get("tesseract", 0)),
            "pymupdf": int(ocr_stats.get("pymupdf", 0)),
            "hybrid": int(ocr_stats.get("hybrid", 0)),
        },
        "by_status": by_status,
        "by_type": by_type,
    }

    return {
        "documents": docs_out,
        "bucket_files": bucket_files,
        "totals": totals,
        "supabase": supabase_info,
        "pending": False,
        "ingest": ingest_snapshot,
    }


@app.post("/api/documents/upload")
async def upload_documents(files: List[UploadFile] = File(...), target_folder: str = Form(""), overwrite: bool = Form(False)):
    global COMPLIANCE_CACHE
    if bucket is None:
        raise HTTPException(status_code=400, detail=f"Supabase no está conectado: {supabase_error}")
    results = []
    folder = target_folder.strip().strip("/")
    for uf in files:
        try:
            fname = safe_filename(uf.filename)
            dest = f"{folder}/{fname}".strip("/") if folder else fname
            content = await uf.read()
            if overwrite:
                try:
                    bucket.remove([dest])
                except Exception:
                    pass
            bucket.upload(dest, content, file_options={"content-type": uf.content_type or "application/pdf"})
            results.append({"file": dest, "status": "uploaded", "bytes": len(content)})
        except Exception as e:
            results.append({"file": uf.filename, "status": "failed", "error": str(e)})
    COMPLIANCE_CACHE = None
    return {"results": results}


@app.get("/api/monitoring")
def monitoring():
    data = build_compliance_dataset(force_refresh=False)
    if workflow is None:
        return {
            "services": [
                {"name": "Supabase Storage", "real": bucket is not None},
                {"name": "OpenAI", "real": openai_client is not None},
            ],
            "agents": [],
            "extraction_log": data.get("extraction_log", []),
            "ocr_stats": data.get("ocr_stats", {}),
            "logs": {},
            "ingest": INGEST_STATE,
        }

    # OCR considerado "real" si Tesseract o PyMuPDF están disponibles localmente.
    ocr_real = bool(
        getattr(workflow.ocr_service, "_tesseract_available", False)
        or getattr(workflow.ocr_service, "_fitz_available", False)
    )
    return {
        "services": [
            {
                "name": "OCR (Tesseract + PyMuPDF)",
                "real": ocr_real,
                "details": {
                    "tesseract": getattr(workflow.ocr_service, "_tesseract_available", False),
                    "pymupdf": getattr(workflow.ocr_service, "_fitz_available", False),
                    "lang": getattr(workflow.ocr_service, "tesseract_lang", "spa+eng"),
                },
            },
            {"name": "Email", "real": not workflow.email_service.simulated},
            {"name": "Google Calendar", "real": not workflow.calendar_service.simulated},
            {"name": "Microsoft Teams", "real": not workflow.teams_service.simulated},
            {"name": "WhatsApp", "real": not workflow.whatsapp_service.simulated},
            {"name": "Supabase Storage", "real": bucket is not None},
            {"name": "OpenAI", "real": openai_client is not None},
        ],
        "agents": ["RouterAgent", "DocumentMonitoringAgent", "RegulatoryValidationAgent", "EmailAutomationAgent", "RenewalAlertAgent", "IntelligentActivationAgent"],
        "extraction_log": data.get("extraction_log", []),
        "ocr_stats": data.get("ocr_stats", {}),
        "logs": {
            "emails": workflow.email_service.sent_log,
            "calendar": workflow.calendar_service.events_log,
            "teams": workflow.teams_service.messages_log,
            "whatsapp": workflow.whatsapp_service.messages_log,
            "ocr": workflow.ocr_service.runs_log,
        },
    }


@app.post("/api/agents/test-notifications")
def test_notifications(payload: NotificationTestRequest):
    if workflow is None:
        raise HTTPException(status_code=503, detail="El backend aún se está inicializando. Intenta en unos segundos.")
    data = build_compliance_dataset(force_refresh=False)
    docs = serialize_dataset(data)["documents"]
    rows = []
    for d in docs[:10]:
        exp = d.get("expiration_date") or "Sin fecha"
        rows.append(f"• {d.get('document_name')} — {status_label(d.get('status'))} — vence: {exp}")
    message = "Estados de documentos:\n" + "\n".join(rows or ["Sin documentos disponibles."])
    teams_result = workflow.teams_service.send_message(title=payload.title or "Prueba GestoriaVertiche", text=message)
    # WhatsApp: ahora aceptamos string con comas o lista. Si no se pasa
    # nada, intentamos DEFAULT_WHATSAPP del .env (que también puede ser
    # una lista separada por comas).
    raw_to = payload.whatsapp_to or os.getenv("DEFAULT_WHATSAPP", "")
    whatsapp_result = workflow.whatsapp_service.send_message(to=raw_to, body=f"{payload.title}\n\n{message}")
    return {"teams": teams_result, "whatsapp": whatsapp_result, "preview": message}


@app.get("/api/pc-visits")
def get_pc_visits():
    return {"visits": PC_VISITS}


@app.post("/api/pc-visits")
def add_pc_visit(payload: PCVisitRequest):
    visit = {
        "id": f"PC-{len(PC_VISITS)+1:04d}",
        "sucursal": payload.sucursal,
        "fecha": payload.fecha,
        "hora": payload.hora or datetime.now().strftime("%H:%M"),
        "motivo": payload.motivo or "Sin observaciones",
        "registrado_en": datetime.now().isoformat(),
    }
    PC_VISITS.append(visit)
    return {"visit": visit, "visits": PC_VISITS}


@app.post("/api/agents/send-expired-alert")
def send_expired_alert(payload: ExpiredAlertRequest):
    """
    Envía un correo HTML de URGENCIA ALTA con la lista de documentos vencidos.

    - Si `document_ids` viene en el payload, filtra a esos IDs.
    - Si no, manda todos los documentos con status="expired".
    - Requiere SMTP configurado en .env (si no, devuelve 400 explicando).

    El correo trae diseño rojo de alerta, tabla con sucursal/ubicación/folio,
    y un bloque amber con la acción recomendada.
    """
    if workflow is None:
        raise HTTPException(status_code=503, detail="El backend aún se está inicializando.")
    if workflow.email_service.simulated:
        raise HTTPException(
            status_code=400,
            detail="El servicio de email está en modo simulado. Configura SMTP en .env.",
        )

    data = serialize_dataset(build_compliance_dataset(force_refresh=False))
    all_docs = data["documents"]

    expired = [d for d in all_docs if d.get("status") == "expired"]
    if payload.document_ids:
        expired = [d for d in expired if d.get("document_id") in payload.document_ids]

    if not expired:
        return {"status": "no_expired", "sent": 0, "message": "No hay documentos vencidos para alertar."}

    rows_html = ""
    rows_text = ""
    for d in expired:
        nombre = d.get("document_name") or "Documento"
        sucursal = d.get("branch_name") or d.get("branch_id") or "—"
        estado = d.get("branch_state") or "—"
        municipio = d.get("branch_municipality") or "—"
        vencimiento = d.get("expiration_date_display") or d.get("expiration_date") or "Sin fecha"
        folio = d.get("folio_number") or "—"
        rows_html += f"""
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid #fee2e2;">{nombre}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #fee2e2;">{sucursal}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #fee2e2;">{estado} · {municipio}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #fee2e2;color:#b91c1c;font-weight:700;">{vencimiento}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #fee2e2;">{folio}</td>
        </tr>"""
        rows_text += f"  • {nombre} | {sucursal} | {estado} | Vencido: {vencimiento}\n"

    total = len(expired)
    subject = f"🚨 ALERTA URGENTE — {total} documento{'s' if total > 1 else ''} vencido{'s' if total > 1 else ''} · GestoriaVertiche"

    html_body = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#fff7f7;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#fff7f7;padding:32px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;border:2px solid #ef4444;">

        <!-- Cabecera roja urgente -->
        <tr>
          <td style="background:#dc2626;padding:24px 32px;text-align:center;">
            <div style="font-size:36px;margin-bottom:8px;">🚨</div>
            <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:800;letter-spacing:-0.5px;">
              ALERTA DE URGENCIA ALTA
            </h1>
            <p style="margin:8px 0 0;color:#fecaca;font-size:14px;">
              Sistema de Compliance Legal · GestoriaVertiche
            </p>
          </td>
        </tr>

        <!-- Mensaje principal -->
        <tr>
          <td style="padding:28px 32px 16px;">
            <p style="margin:0 0 12px;font-size:15px;color:#1a1a1a;line-height:1.6;">
              Se han detectado <strong style="color:#dc2626;">{total} documento{'s' if total > 1 else ''} vencido{'s' if total > 1 else ''}</strong>
              que requieren atención <strong>inmediata</strong>.
            </p>
            <p style="margin:0 0 20px;font-size:15px;color:#1a1a1a;line-height:1.6;">
              ⚠️ Un contrato o permiso vencido puede representar <strong>sanciones legales,
              suspensión de operaciones o multas</strong> para la sucursal.
              Es indispensable iniciar el proceso de renovación <strong>lo antes posible</strong>.
            </p>

            <!-- Pastilla de urgencia -->
            <div style="background:#fef2f2;border:1px solid #fca5a5;border-radius:8px;padding:14px 18px;margin-bottom:24px;display:inline-block;">
              <span style="color:#dc2626;font-weight:800;font-size:13px;text-transform:uppercase;letter-spacing:0.08em;">
                🔴 Nivel de urgencia: ALTA
              </span>
            </div>
          </td>
        </tr>

        <!-- Tabla de documentos vencidos -->
        <tr>
          <td style="padding:0 32px 28px;">
            <h2 style="margin:0 0 14px;font-size:15px;color:#7f1d1d;font-weight:700;">
              Documentos vencidos ({total})
            </h2>
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="border-collapse:collapse;font-size:13px;border:1px solid #fca5a5;border-radius:8px;overflow:hidden;">
              <thead>
                <tr style="background:#fee2e2;">
                  <th style="padding:10px 14px;text-align:left;color:#7f1d1d;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Documento</th>
                  <th style="padding:10px 14px;text-align:left;color:#7f1d1d;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Sucursal</th>
                  <th style="padding:10px 14px;text-align:left;color:#7f1d1d;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Ubicación</th>
                  <th style="padding:10px 14px;text-align:left;color:#7f1d1d;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Venció</th>
                  <th style="padding:10px 14px;text-align:left;color:#7f1d1d;font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Folio</th>
                </tr>
              </thead>
              <tbody>{rows_html}</tbody>
            </table>
          </td>
        </tr>

        <!-- Acción recomendada -->
        <tr>
          <td style="padding:0 32px 28px;">
            <div style="background:#fffbeb;border:1px solid #fbbf24;border-radius:8px;padding:16px 20px;">
              <p style="margin:0 0 8px;font-weight:700;color:#92400e;font-size:14px;">📋 Acción recomendada</p>
              <p style="margin:0;color:#78350f;font-size:13px;line-height:1.6;">
                Contacta de inmediato a la autoridad emisora de cada documento para iniciar
                el trámite de renovación. Hasta que el documento esté renovado, la sucursal
                opera fuera de cumplimiento legal.
              </p>
            </div>
          </td>
        </tr>

        <!-- Pie -->
        <tr>
          <td style="background:#f9fafb;border-top:1px solid #fee2e2;padding:16px 32px;text-align:center;">
            <p style="margin:0;font-size:11px;color:#9ca3af;">
              Este mensaje fue generado automáticamente por el sistema de agentes GestoriaVertiche.<br>
              Generado el {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

    # recipient_email puede traer varios correos separados por coma.
    # Mandamos el correo a cada uno y devolvemos el detalle por destinatario.
    destinatarios = _split_recipients(payload.recipient_email)
    if not destinatarios:
        raise HTTPException(status_code=400, detail="Debes indicar al menos un correo destinatario.")

    email_results = []
    for addr in destinatarios:
        r = workflow.email_service.send_email(
            to=addr, subject=subject, body=html_body, html=True,
        )
        email_results.append({"to": addr, "status": r.get("status"), "error": r.get("error")})

    overall = "sent" if any(r["status"] in ("sent", "simulated") for r in email_results) else "failed"
    return {
        "status": overall,
        "sent_to": destinatarios,
        "expired_count": total,
        "documents": [d.get("document_name") for d in expired],
        "email_result": email_results,
    }


@app.post("/api/assistant/chat")
def assistant_chat(payload: AssistantChatRequest):
    data = serialize_dataset(build_compliance_dataset(force_refresh=False))
    context = build_context(workflow=workflow, compliance_data=data, pc_visits=PC_VISITS)
    reply = call_openai_assistant(payload.messages, context)
    return {"reply": reply}


# ====================================================================== #
#  TRÁMITES POR SUCURSAL — captura manual con persistencia en JSON       #
# ====================================================================== #

@app.get("/api/tramites")
def get_tramites():
    """
    Devuelve todas las sucursales del tab de llenado manual, cada una con
    su % de cumplimiento calculado sobre los 5 trámites requeridos.
    """
    return tramites_service.get_all()


@app.get("/api/tramites/resumen")
def get_tramites_resumen():
    """
    Resumen compacto por sucursal para el dashboard (porcentajes,
    conteos de vigentes / por vencer / vencidos).
    """
    resumen = tramites_service.resumen_por_sucursal()
    promedio = round(sum(r["porcentaje"] for r in resumen) / len(resumen), 1) if resumen else 0.0
    completas = sum(1 for r in resumen if r["completo"])
    return {
        "sucursales": resumen,
        "promedio_global": promedio,
        "total_sucursales": len(resumen),
        "sucursales_completas": completas,
        "tramites_requeridos": tramites_service.requeridos,
    }


@app.post("/api/tramites/sucursal")
def save_tramite_sucursal(payload: TramiteSucursalRequest):
    """Inserta o actualiza una sucursal en el JSON de trámites."""
    sucursal = {
        "tramite_id": payload.tramite_id.strip(),
        "nombre": payload.nombre.strip(),
        "estado": (payload.estado or "").strip(),
        "municipio": (payload.municipio or "").strip(),
        "permisos": [p.dict() for p in payload.permisos],
    }
    if not sucursal["tramite_id"]:
        raise HTTPException(status_code=400, detail="El identificador del trámite (tramite_id) es obligatorio.")
    saved = tramites_service.save_sucursal(sucursal)
    return {"status": "ok", "sucursal": saved}


@app.delete("/api/tramites/sucursal/{tramite_id}")
def delete_tramite_sucursal(tramite_id: str):
    """Elimina una sucursal del JSON de trámites."""
    ok = tramites_service.delete_sucursal(tramite_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"No se encontró la sucursal {tramite_id}.")
    return {"status": "deleted", "tramite_id": tramite_id}


@app.post("/api/tramites/reset")
def reset_tramites():
    """Restaura el JSON de trámites a los datos semilla del documento original."""
    return {"status": "reset", **tramites_service.reset_to_seed()}


# ====================================================================== #
#  CONFIGURACIÓN DE CORREOS POR SUCURSAL                                 #
# ====================================================================== #

class BranchEmailConfigRequest(BaseModel):
    """Payload para asignar el correo responsable de una sucursal."""
    responsible_email: str


@app.get("/api/branches")
def list_branches_with_config():
    """
    Lista todas las sucursales del dataset con su correo responsable actual
    (ya con el override de branch_config.json aplicado) y el conteo de
    documentos por estado. Sirve para poblar el selector de la UI.
    """
    if COMPLIANCE_CACHE is None:
        with _ingest_lock:
            snapshot = dict(INGEST_STATE)
        return {
            "branches": [],
            "total": 0,
            "pending": True,
            "message": f"El dataset aún se está procesando ({snapshot.get('processed', 0)}/{snapshot.get('total', '?')} PDFs).",
        }
    data = serialize_dataset(build_compliance_dataset(force_refresh=False))
    branches = data["branches"]
    docs = data["documents"]

    from collections import Counter
    doc_stats: Dict[str, Counter] = {}
    for d in docs:
        bid = d.get("branch_id")
        if bid:
            doc_stats.setdefault(bid, Counter())[d.get("status", "unknown")] += 1

    result = []
    for b in branches:
        bid = b["branch_id"]
        stats = doc_stats.get(bid, Counter())
        result.append({
            "branch_id": bid,
            "branch_name": b.get("branch_name"),
            "state": b.get("state"),
            "municipality": b.get("municipality"),
            "responsible_email": b.get("responsible_email"),
            "supervisor_email": b.get("supervisor_email"),
            "director_email": b.get("director_email"),
            "docs_expired": stats.get("expired", 0),
            "docs_expiring": stats.get("close_to_expiration", 0),
            "docs_valid": stats.get("valid", 0),
            "docs_total": sum(stats.values()),
        })
    return {"branches": result, "total": len(result)}


@app.post("/api/branches/{branch_id}/config")
def set_branch_email_config(branch_id: str, payload: BranchEmailConfigRequest):
    """
    Asigna el correo responsable a una sucursal específica.
    Este correo tiene prioridad sobre DEFAULT_RESPONSIBLE_EMAIL del .env.
    """
    email = payload.responsible_email.strip()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="El correo no es válido.")
    saved = branch_config_svc.save(branch_id, email)
    return {"status": "ok", "branch_id": branch_id, "config": saved}


@app.delete("/api/branches/{branch_id}/config")
def delete_branch_email_config(branch_id: str):
    """Elimina la configuración de correo de una sucursal (vuelve al DEFAULT)."""
    existed = branch_config_svc.delete(branch_id)
    if not existed:
        raise HTTPException(
            status_code=404,
            detail=f"No hay configuración guardada para {branch_id}."
        )
    return {"status": "deleted", "branch_id": branch_id}


# ====================================================================== #
#  ALERTAS SEGMENTADAS — por sucursal / municipio / estado               #
# ====================================================================== #

def _build_expired_email_html(expired: List[Dict[str, Any]], titulo_segmento: str) -> str:
    """
    Construye el cuerpo HTML del correo de alerta de documentos vencidos.
    titulo_segmento es una frase descriptiva del filtro aplicado, p.ej.
    "Sucursal Centro CDMX" o "Estado: Puebla".
    """
    total = len(expired)
    plural = "s" if total != 1 else ""
    rows_html = ""
    for d in expired:
        nombre = d.get("document_name") or "Documento"
        sucursal = d.get("branch_name") or d.get("branch_id") or "—"
        estado = d.get("branch_state") or "—"
        municipio = d.get("branch_municipality") or "—"
        vencimiento = d.get("expiration_date_display") or d.get("expiration_date") or "Sin fecha"
        folio = d.get("folio_number") or "—"
        rows_html += f"""
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid #fee2e2;">{nombre}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #fee2e2;">{sucursal}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #fee2e2;">{estado} · {municipio}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #fee2e2;color:#b91c1c;font-weight:700;">{vencimiento}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #fee2e2;">{folio}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#fff7f7;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#fff7f7;padding:32px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;border:2px solid #ef4444;">
        <tr>
          <td style="background:#dc2626;padding:24px 32px;text-align:center;">
            <div style="font-size:36px;margin-bottom:8px;">🚨</div>
            <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:800;letter-spacing:-0.5px;">
              ALERTA DE URGENCIA ALTA
            </h1>
            <p style="margin:8px 0 0;color:#fecaca;font-size:14px;">
              Sistema de Compliance Legal · GestoriaVertiche
            </p>
          </td>
        </tr>
        <tr>
          <td style="padding:28px 32px 16px;">
            <div style="background:#eff6ff;border:1px solid #93c5fd;border-radius:8px;padding:10px 14px;margin-bottom:16px;">
              <span style="color:#1d4ed8;font-weight:700;font-size:13px;">📍 Segmento: {titulo_segmento}</span>
            </div>
            <p style="margin:0 0 12px;font-size:15px;color:#1a1a1a;line-height:1.6;">
              Se han detectado <strong style="color:#dc2626;">{total} documento{plural} vencido{plural}</strong>
              en este segmento que requieren atención <strong>inmediata</strong>.
            </p>
            <p style="margin:0 0 20px;font-size:15px;color:#1a1a1a;line-height:1.6;">
              ⚠️ Un contrato o permiso vencido puede representar <strong>sanciones legales,
              suspensión de operaciones o multas</strong> para la sucursal.
            </p>
          </td>
        </tr>
        <tr>
          <td style="padding:0 32px 28px;">
            <h2 style="margin:0 0 14px;font-size:15px;color:#7f1d1d;font-weight:700;">
              Documentos vencidos ({total})
            </h2>
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="border-collapse:collapse;font-size:13px;border:1px solid #fca5a5;border-radius:8px;overflow:hidden;">
              <thead>
                <tr style="background:#fee2e2;">
                  <th style="padding:10px 14px;text-align:left;color:#7f1d1d;font-size:11px;text-transform:uppercase;">Documento</th>
                  <th style="padding:10px 14px;text-align:left;color:#7f1d1d;font-size:11px;text-transform:uppercase;">Sucursal</th>
                  <th style="padding:10px 14px;text-align:left;color:#7f1d1d;font-size:11px;text-transform:uppercase;">Ubicación</th>
                  <th style="padding:10px 14px;text-align:left;color:#7f1d1d;font-size:11px;text-transform:uppercase;">Venció</th>
                  <th style="padding:10px 14px;text-align:left;color:#7f1d1d;font-size:11px;text-transform:uppercase;">Folio</th>
                </tr>
              </thead>
              <tbody>{rows_html}</tbody>
            </table>
          </td>
        </tr>
        <tr>
          <td style="background:#f9fafb;border-top:1px solid #fee2e2;padding:16px 32px;text-align:center;">
            <p style="margin:0;font-size:11px;color:#9ca3af;">
              Generado automáticamente por GestoriaVertiche · {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _split_recipients(raw: Optional[str]) -> List[str]:
    """Separa una cadena de correos/teléfonos por coma, punto y coma o salto de línea."""
    if not raw:
        return []
    return [x.strip() for x in re.split(r"[,;\n]+", raw) if x.strip()]


# ── Colores y etiquetas por nivel de escalamiento ──────────────────────────
_TIER_CONFIG = {
    1: {
        "header_bg": "#1d4ed8",
        "border": "#93c5fd",
        "row_border": "#dbeafe",
        "header_row_bg": "#eff6ff",
        "header_text": "#1e3a5f",
        "date_color": "#1d4ed8",
        "urgency_bg": "#eff6ff",
        "urgency_border": "#93c5fd",
        "urgency_color": "#1d4ed8",
        "urgency_label": "PREVENTIVA",
        "urgency_emoji": "📅",
        "icon": "📅",
        "title": "AVISO PREVENTIVO DE VENCIMIENTO",
        "subtitle": "Los documentos listados vencerán en los próximos 40 días.",
        "action_bg": "#f0f9ff",
        "action_border": "#7dd3fc",
        "action_text_color": "#075985",
        "action_label": "Acción recomendada",
        "action_body": (
            "Inicia el proceso de renovación con anticipación para evitar contratiempos. "
            "Contacta a la autoridad emisora y ten listos los documentos requeridos."
        ),
        "footer_border": "#dbeafe",
        "col_date_label": "Vence",
    },
    2: {
        "header_bg": "#d97706",
        "border": "#fcd34d",
        "row_border": "#fef3c7",
        "header_row_bg": "#fffbeb",
        "header_text": "#78350f",
        "date_color": "#b45309",
        "urgency_bg": "#fffbeb",
        "urgency_border": "#fcd34d",
        "urgency_color": "#b45309",
        "urgency_label": "ALTA",
        "urgency_emoji": "⚠️",
        "icon": "⚠️",
        "title": "ALERTA — DOCUMENTOS POR VENCER",
        "subtitle": "Los documentos listados vencerán en 20 días o menos.",
        "action_bg": "#fffbeb",
        "action_border": "#fbbf24",
        "action_text_color": "#92400e",
        "action_label": "Acción urgente",
        "action_body": (
            "Confirma que el trámite de renovación ya está en proceso. "
            "Si no ha iniciado, hazlo de inmediato y da seguimiento diario."
        ),
        "footer_border": "#fef3c7",
        "col_date_label": "Vence en",
    },
    3: {
        "header_bg": "#dc2626",
        "border": "#ef4444",
        "row_border": "#fee2e2",
        "header_row_bg": "#fee2e2",
        "header_text": "#7f1d1d",
        "date_color": "#b91c1c",
        "urgency_bg": "#fef2f2",
        "urgency_border": "#fca5a5",
        "urgency_color": "#dc2626",
        "urgency_label": "CRÍTICA",
        "urgency_emoji": "🚨",
        "icon": "🚨",
        "title": "URGENTE — DOCUMENTOS VENCIDOS",
        "subtitle": "Los documentos listados ya vencieron. Se requiere acción inmediata.",
        "action_bg": "#fffbeb",
        "action_border": "#fbbf24",
        "action_text_color": "#78350f",
        "action_label": "Acción inmediata requerida",
        "action_body": (
            "Contacta de inmediato a la autoridad emisora para iniciar la renovación. "
            "Hasta que el documento esté renovado, la sucursal opera fuera de cumplimiento legal."
        ),
        "footer_border": "#fee2e2",
        "col_date_label": "Venció",
    },
}


def _build_hierarchical_email_html(
    docs: List[Dict[str, Any]],
    tier: int,
    branch_name: str,
    recipients_label: str,
) -> str:
    """
    Genera el HTML del correo jerárquico para un nivel de escalamiento:
      tier=1 → aviso preventivo (40 días)
      tier=2 → alerta (20 días)
      tier=3 → urgente / vencido (día 0)
    """
    cfg = _TIER_CONFIG[tier]
    total = len(docs)
    plural = "s" if total != 1 else ""

    rows_html = ""
    for d in docs:
        nombre = d.get("document_name") or "Documento"
        folio = d.get("folio_number") or "—"
        venc_display = d.get("expiration_date_display") or d.get("expiration_date") or "Sin fecha"
        exp_raw = d.get("expiration_date")
        days_str = "—"
        if exp_raw:
            try:
                exp_dt = date.fromisoformat(str(exp_raw)[:10])
                days_left = (exp_dt - date.today()).days
                if days_left < 0:
                    days_str = f"hace {abs(days_left)} día{'s' if abs(days_left) != 1 else ''}"
                elif days_left == 0:
                    days_str = "hoy"
                else:
                    days_str = f"{days_left} día{'s' if days_left != 1 else ''}"
            except ValueError:
                days_str = "—"
        rows_html += f"""
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid {cfg['row_border']};">{nombre}</td>
          <td style="padding:10px 14px;border-bottom:1px solid {cfg['row_border']};color:{cfg['date_color']};font-weight:700;">{venc_display}</td>
          <td style="padding:10px 14px;border-bottom:1px solid {cfg['row_border']};">{days_str}</td>
          <td style="padding:10px 14px;border-bottom:1px solid {cfg['row_border']};">{folio}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:32px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:12px;overflow:hidden;border:2px solid {cfg['border']};">

        <tr>
          <td style="background:{cfg['header_bg']};padding:24px 32px;text-align:center;">
            <div style="font-size:36px;margin-bottom:8px;">{cfg['icon']}</div>
            <h1 style="margin:0;color:#ffffff;font-size:20px;font-weight:800;letter-spacing:-0.5px;">
              {cfg['title']}
            </h1>
            <p style="margin:8px 0 0;color:rgba(255,255,255,0.85);font-size:13px;">
              {cfg['subtitle']}
            </p>
          </td>
        </tr>

        <tr>
          <td style="padding:20px 32px 8px;">
            <div style="background:{cfg['urgency_bg']};border:1px solid {cfg['urgency_border']};border-radius:8px;padding:10px 14px;margin-bottom:16px;">
              <span style="color:{cfg['urgency_color']};font-weight:700;font-size:12px;text-transform:uppercase;letter-spacing:0.08em;">
                {cfg['urgency_emoji']} Nivel de urgencia: {cfg['urgency_label']}
              </span>
            </div>
            <p style="margin:0 0 6px;font-size:15px;color:#1a1a1a;line-height:1.6;">
              <strong>Sucursal:</strong> {branch_name}
            </p>
            <p style="margin:0 0 6px;font-size:14px;color:#4b5563;">
              <strong>Destinatarios de este aviso:</strong> {recipients_label}
            </p>
            <p style="margin:0 0 16px;font-size:14px;color:#1a1a1a;line-height:1.6;">
              Se han detectado <strong>{total} documento{plural}</strong> en la sucursal que requieren atención.
            </p>
          </td>
        </tr>

        <tr>
          <td style="padding:0 32px 24px;">
            <h2 style="margin:0 0 12px;font-size:14px;color:{cfg['header_text']};font-weight:700;">
              Documentos ({total})
            </h2>
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="border-collapse:collapse;font-size:13px;border:1px solid {cfg['border']};border-radius:8px;overflow:hidden;">
              <thead>
                <tr style="background:{cfg['header_row_bg']};">
                  <th style="padding:9px 14px;text-align:left;color:{cfg['header_text']};font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Documento</th>
                  <th style="padding:9px 14px;text-align:left;color:{cfg['header_text']};font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">{cfg['col_date_label']}</th>
                  <th style="padding:9px 14px;text-align:left;color:{cfg['header_text']};font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Días</th>
                  <th style="padding:9px 14px;text-align:left;color:{cfg['header_text']};font-size:11px;text-transform:uppercase;letter-spacing:0.06em;">Folio</th>
                </tr>
              </thead>
              <tbody>{rows_html}</tbody>
            </table>
          </td>
        </tr>

        <tr>
          <td style="padding:0 32px 28px;">
            <div style="background:{cfg['action_bg']};border:1px solid {cfg['action_border']};border-radius:8px;padding:16px 20px;">
              <p style="margin:0 0 6px;font-weight:700;color:{cfg['action_text_color']};font-size:13px;">
                📋 {cfg['action_label']}
              </p>
              <p style="margin:0;color:{cfg['action_text_color']};font-size:13px;line-height:1.6;">
                {cfg['action_body']}
              </p>
            </div>
          </td>
        </tr>

        <tr>
          <td style="background:#f9fafb;border-top:1px solid {cfg['footer_border']};padding:14px 32px;text-align:center;">
            <p style="margin:0;font-size:11px;color:#9ca3af;">
              Generado automáticamente por GestoriaVertiche · {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


@app.post("/api/agents/send-hierarchical-alerts")
def send_hierarchical_alerts(payload: HierarchicalAlertRequest):
    """
    Envía correos jerárquicos por vencimiento de documentos, agrupados por sucursal.

    Escalamiento según días restantes antes del vencimiento:
      • 20 < días ≤ 40 → responsables de tienda (responsible_email)
      • 0 < días ≤ 20  → supervisor + responsables de tienda
      • días ≤ 0       → supervisor + responsables + director

    Los campos supervisor_email y director_email se configuran en .env como
    DEFAULT_SUPERVISOR_EMAIL y DEFAULT_DIRECTOR_EMAIL, o por sucursal en el
    modelo Branch.
    """
    if workflow is None:
        raise HTTPException(status_code=503, detail="El backend aún se está inicializando.")

    data = serialize_dataset(build_compliance_dataset(force_refresh=False))
    all_docs = data["documents"]
    branches_map = {b["branch_id"]: b for b in data["branches"]}

    if payload.branch_id:
        all_docs = [d for d in all_docs if d.get("branch_id") == payload.branch_id]
        if not all_docs:
            raise HTTPException(
                status_code=404,
                detail=f"No se encontraron documentos para la sucursal '{payload.branch_id}'.",
            )

    today = date.today()

    # Agrupar docs por sucursal y por tier
    by_branch: Dict[str, Dict[str, Any]] = {}
    for doc in all_docs:
        exp_raw = doc.get("expiration_date")
        if not exp_raw:
            continue
        try:
            exp_dt = date.fromisoformat(str(exp_raw)[:10])
        except ValueError:
            continue

        days_left = (exp_dt - today).days
        if days_left > 40 or days_left <= -180:
            continue  # fuera del rango de interés (muy lejos o muy vencido)

        if days_left > 20:
            tier = 1
        elif days_left > 0:
            tier = 2
        else:
            tier = 3

        bid = doc.get("branch_id", "UNKNOWN")
        if bid not in by_branch:
            by_branch[bid] = {"tier1": [], "tier2": [], "tier3": []}
        by_branch[bid][f"tier{tier}"].append(doc)

    if not by_branch:
        return {
            "status": "no_documents",
            "message": "No hay documentos dentro del rango de alerta (0–40 días antes del vencimiento).",
            "branches_processed": 0,
            "emails_sent": 0,
        }

    results = []
    total_emails = 0
    simulated_mode = workflow.email_service.simulated

    for branch_id, tiers in by_branch.items():
        branch = branches_map.get(branch_id, {})
        branch_name = branch.get("branch_name") or branch_id
        responsible = branch.get("responsible_email")
        supervisor = branch.get("supervisor_email")
        director = branch.get("director_email")

        branch_result: Dict[str, Any] = {
            "branch_id": branch_id,
            "branch_name": branch_name,
            "tiers": {},
        }

        tier_specs = [
            (1, tiers["tier1"], [responsible], "Responsables de tienda"),
            (2, tiers["tier2"], [responsible, supervisor], "Supervisor + Responsables de tienda"),
            (3, tiers["tier3"], [responsible, supervisor, director], "Supervisor + Responsables + Director"),
        ]

        for tier_num, docs, raw_recipients, recipients_label in tier_specs:
            if not docs:
                branch_result["tiers"][f"tier{tier_num}"] = {"docs": 0, "skipped": True}
                continue

            # Filtrar None y duplicados, mantener orden
            to_list = list(dict.fromkeys(r for r in raw_recipients if r))
            if not to_list:
                branch_result["tiers"][f"tier{tier_num}"] = {
                    "docs": len(docs),
                    "skipped": True,
                    "reason": "Sin destinatarios configurados para este nivel.",
                }
                continue

            tier_result: Dict[str, Any] = {
                "docs": len(docs),
                "recipients": to_list,
                "recipients_label": recipients_label,
            }

            if not payload.dry_run:
                subjects = {
                    1: f"📅 Aviso Preventivo — {len(docs)} documento{'s' if len(docs) != 1 else ''} por vencer · {branch_name}",
                    2: f"⚠️ Alerta — {len(docs)} documento{'s' if len(docs) != 1 else ''} por vencer en 20 días · {branch_name}",
                    3: f"🚨 URGENTE — {len(docs)} documento{'s' if len(docs) != 1 else ''} vencido{'s' if len(docs) != 1 else ''} · {branch_name}",
                }
                subject = subjects[tier_num]
                html = _build_hierarchical_email_html(docs, tier_num, branch_name, recipients_label)

                to_addr = to_list[0]
                cc_addrs = to_list[1:] if len(to_list) > 1 else []

                send_res = workflow.email_service.send_email(
                    to=to_addr, subject=subject, body=html, cc=cc_addrs, html=True
                )
                tier_result["send_result"] = send_res
                tier_result["status"] = send_res.get("status", "unknown")
                if send_res.get("status") in ("sent", "simulated"):
                    total_emails += 1
            else:
                tier_result["status"] = "dry_run"

            branch_result["tiers"][f"tier{tier_num}"] = tier_result

        results.append(branch_result)

    return {
        "status": "simulated" if simulated_mode else "ok",
        "dry_run": payload.dry_run,
        "branches_processed": len(results),
        "emails_sent": total_emails,
        "note": "Email en modo simulado. Configura SMTP en .env." if simulated_mode else None,
        "results": results,
    }


@app.post("/api/agents/send-segmented-alert")
def send_segmented_alert(payload: SegmentedAlertRequest):
    """
    Envía una alerta de documentos vencidos filtrada por sucursal,
    municipio o estado. Replica /api/agents/send-expired-alert pero
    segmentado, y permite designar destinatarios manualmente (varios,
    separados por coma) tanto para email como para WhatsApp y Teams.

    Si no se designan destinatarios, usa los asignados a las sucursales
    afectadas (responsible_email, manager_email, whatsapp_contact).
    """
    if workflow is None:
        raise HTTPException(status_code=503, detail="El backend aún se está inicializando.")

    seg_type = (payload.segment_type or "").strip().lower()
    seg_value = (payload.segment_value or "").strip()
    if seg_type not in ("sucursal", "municipio", "estado"):
        raise HTTPException(status_code=400, detail="segment_type debe ser 'sucursal', 'municipio' o 'estado'.")
    if not seg_value:
        raise HTTPException(status_code=400, detail="segment_value no puede estar vacío.")

    data = serialize_dataset(build_compliance_dataset(force_refresh=False))
    all_docs = data["documents"]
    branches = {b["branch_id"]: b for b in data["branches"]}

    # Campo del documento por el que filtramos según el tipo de segmento.
    field_map = {
        "sucursal": "branch_name",
        "municipio": "branch_municipality",
        "estado": "branch_state",
    }
    field = field_map[seg_type]

    # Documentos vencidos dentro del segmento (comparación sin distinción
    # de mayúsculas/minúsculas para tolerar diferencias de captura).
    expired = [
        d for d in all_docs
        if d.get("status") == "expired"
        and (d.get(field) or "").strip().lower() == seg_value.lower()
    ]

    if not expired:
        return {
            "status": "no_expired",
            "sent": 0,
            "segment": f"{seg_type}: {seg_value}",
            "message": f"No hay documentos vencidos para {seg_type} '{seg_value}'.",
        }

    titulo = {
        "sucursal": f"Sucursal: {seg_value}",
        "municipio": f"Municipio: {seg_value}",
        "estado": f"Estado: {seg_value}",
    }[seg_type]
    total = len(expired)
    plural = "s" if total != 1 else ""
    subject = f"🚨 ALERTA URGENTE — {total} documento{plural} vencido{plural} · {titulo}"

    # ── Resolver destinatarios ──
    # Email: lo designado manualmente, o los correos de las sucursales.
    emails = _split_recipients(payload.emails)
    if not emails:
        branch_ids = {d.get("branch_id") for d in expired}
        for bid in branch_ids:
            b = branches.get(bid, {})
            for key in ("responsible_email", "manager_email"):
                v = b.get(key)
                if v:
                    emails.append(v)
        emails = sorted(set(emails))

    # WhatsApp: lo designado manualmente, o los contactos de las sucursales.
    whatsapp_nums = _split_recipients(payload.whatsapp)
    if not whatsapp_nums:
        branch_ids = {d.get("branch_id") for d in expired}
        for bid in branch_ids:
            b = branches.get(bid, {})
            v = b.get("whatsapp_contact")
            if v:
                whatsapp_nums.append(v)
        whatsapp_nums = sorted(set(whatsapp_nums))

    results: Dict[str, Any] = {
        "status": "ok",
        "segment": f"{seg_type}: {seg_value}",
        "expired_count": total,
        "documents": [d.get("document_name") for d in expired],
    }

    # ── Email ──
    if emails:
        if workflow.email_service.simulated:
            results["email"] = {"status": "simulated", "recipients": emails,
                                "note": "Email en modo simulado. Configura SMTP en .env."}
        else:
            html = _build_expired_email_html(expired, titulo)
            email_results = []
            for addr in emails:
                r = workflow.email_service.send_email(to=addr, subject=subject, body=html, html=True)
                email_results.append({"to": addr, "status": r.get("status"), "error": r.get("error")})
            results["email"] = {"recipients": emails, "results": email_results}
    else:
        results["email"] = {"status": "skipped", "note": "Sin destinatarios de correo."}

    # ── WhatsApp ──
    if whatsapp_nums:
        lines = [f"🚨 ALERTA — {titulo}", f"{total} documento{plural} vencido{plural}:", ""]
        for d in expired[:15]:
            venc = d.get("expiration_date_display") or d.get("expiration_date") or "Sin fecha"
            lines.append(f"• {d.get('document_name')} ({d.get('branch_name') or '—'}) — venció {venc}")
        wa_body = "\n".join(lines)
        wa_result = workflow.whatsapp_service.send_message(to=",".join(whatsapp_nums), body=wa_body)
        results["whatsapp"] = wa_result
    else:
        results["whatsapp"] = {"status": "skipped", "note": "Sin destinatarios de WhatsApp."}

    # ── Teams ──
    if payload.send_teams:
        teams_text = f"{total} documento{plural} vencido{plural} en {titulo}.\n\n"
        teams_text += "\n".join(
            f"• {d.get('document_name')} — {d.get('branch_name') or '—'}" for d in expired[:20]
        )
        results["teams"] = workflow.teams_service.send_message(
            title=subject, text=teams_text,
        )
    else:
        results["teams"] = {"status": "skipped"}

    return results


@app.get("/api/agents/segments")
def get_alert_segments():
    """
    Devuelve los valores disponibles para segmentar alertas (sucursales,
    municipios y estados) junto con cuántos documentos vencidos tiene cada
    uno. Sirve para poblar los selectores del frontend.
    """
    data = serialize_dataset(build_compliance_dataset(force_refresh=False))
    all_docs = data["documents"]

    def _agg(field: str) -> List[Dict[str, Any]]:
        counts: Dict[str, Dict[str, int]] = {}
        for d in all_docs:
            val = (d.get(field) or "").strip()
            if not val:
                continue
            if val not in counts:
                counts[val] = {"total": 0, "expired": 0}
            counts[val]["total"] += 1
            if d.get("status") == "expired":
                counts[val]["expired"] += 1
        return sorted(
            [{"value": k, "total": v["total"], "expired": v["expired"]} for k, v in counts.items()],
            key=lambda x: (-x["expired"], x["value"]),
        )

    return {
        "sucursales": _agg("branch_name"),
        "municipios": _agg("branch_municipality"),
        "estados": _agg("branch_state"),
    }

# ==========================================
# ENDPOINTS DE AUTENTICACIÓN
# ==========================================
@app.post("/register")
def registrar_usuario(user: UserSchema, db: Session = Depends(get_db)):
    # Comprobar si el usuario ya existe en SQLite
    db_user = db.query(UserDB).filter(UserDB.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    
    # Encriptar contraseña y guardar
    new_user = UserDB(
        email=user.email,
        hashed_password=obtener_password_hasheada(user.password)
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "Usuario creado con éxito"}

@app.post("/login")
def login(user: UserSchema, db: Session = Depends(get_db)):
    # Buscar al usuario por email en SQLite
    db_user = db.query(UserDB).filter(UserDB.email == user.email).first()
    if not db_user:
        raise HTTPException(status_code=400, detail="El usuario no existe. ¡Regístrate primero!")
    
    # Verificar si la contraseña coincide
    if not verificar_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=400, detail="Contraseña incorrecta. Inténtalo de nuevo.")
    
    # Generar y retornar su Token JWT
    token = crear_token_acceso(data={"sub": db_user.email})
    return {"access_token": token, "token_type": "bearer"}
# ==========================================