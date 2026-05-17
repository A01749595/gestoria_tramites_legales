"""
OCR Service — Azure Document Intelligence con fallback automático a PyMuPDF.

Estrategia:
  1) Si hay credenciales Azure (endpoint + key) -> usa Azure prebuilt-read.
     Maneja PDFs escaneados, manuscritos, calidad pobre.
  2) Si Azure falla, no responde, o no está configurado -> intenta PyMuPDF
     local (rápido, gratis, pero solo funciona con PDFs digitales).
  3) Si ambos fallan -> retorna modo SIMULATED con el motivo.

Esto resuelve el caso en que solo 80/166 PDFs se extraen: los restantes
suelen ser PDFs escaneados que PyMuPDF no puede leer.
"""

from typing import Dict, Any, Optional, List
import logging
import time
import os

logger = logging.getLogger(__name__)


class OCRService:
    def __init__(
        self,
        provider: str = "azure",
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        supabase_bucket=None,
        fallback_to_pymupdf: bool = True,
    ):
        """
        Args:
            provider: "azure" o "local_pymupdf" (forzar)
            api_key: Azure Document Intelligence key
            endpoint: Azure Document Intelligence endpoint
            supabase_bucket: bucket de Supabase para descargar PDFs por path
            fallback_to_pymupdf: si Azure falla, intentar PyMuPDF
        """
        self.provider = provider
        self.api_key = api_key
        self.endpoint = endpoint
        self.supabase_bucket = supabase_bucket
        self.fallback_to_pymupdf = fallback_to_pymupdf

        # --- Azure ---
        self._azure_client = None
        self._azure_available = False
        if api_key and endpoint:
            try:
                from azure.core.credentials import AzureKeyCredential
                from azure.ai.documentintelligence import DocumentIntelligenceClient
                self._azure_client = DocumentIntelligenceClient(
                    endpoint=endpoint,
                    credential=AzureKeyCredential(api_key),
                )
                self._azure_available = True
                logger.info("OCRService: Azure Document Intelligence inicializado.")
            except ImportError:
                logger.warning(
                    "OCRService: faltan paquetes Azure. Instala: "
                    "pip install azure-ai-documentintelligence azure-core"
                )
            except Exception as e:
                logger.error(f"OCRService: error inicializando Azure: {e}")

        # --- PyMuPDF (fallback) ---
        try:
            import fitz  # noqa
            self._fitz_available = True
        except ImportError:
            self._fitz_available = False
            if not self._azure_available:
                logger.warning("OCRService: PyMuPDF tampoco está. SIMULADO total.")

        self.runs_log: List[Dict[str, Any]] = []
        logger.info(
            f"OCRService listo (azure={self._azure_available}, "
            f"pymupdf={self._fitz_available})"
        )

    @property
    def simulated(self) -> bool:
        return not self._azure_available and not self._fitz_available

    # ------------------------------------------------------------------ #
    # API pública                                                         #
    # ------------------------------------------------------------------ #

    def extract_text(
        self,
        file_path: str,
        document_type: str = "document",
        max_pages: int = 50,
    ) -> Dict[str, Any]:
        """
        Devuelve dict con: text, confidence, fields, processing_time, pages,
        source, provider, mode, [error]
        """
        t0 = time.time()
        pdf_bytes = self._load_pdf_bytes(file_path)

        if pdf_bytes is None:
            return self._record(file_path, t0, mode="SIMULATED",
                                error="PDF no encontrado en disco ni en Supabase")

        # --- Intentar Azure primero ---
        if self._azure_available:
            try:
                result = self._extract_azure(pdf_bytes, file_path, t0)
                if result["text"].strip():
                    self._log_run(file_path, result)
                    return result
                else:
                    logger.warning(f"Azure devolvió texto vacío para {file_path}")
            except Exception as e:
                logger.warning(f"Azure falló para {file_path}: {e}")
                if not self.fallback_to_pymupdf:
                    return self._record(file_path, t0, mode="FAILED",
                                        error=f"Azure: {e}")

        # --- Fallback a PyMuPDF ---
        if self._fitz_available:
            try:
                result = self._extract_pymupdf(pdf_bytes, file_path, t0, max_pages)
                self._log_run(file_path, result)
                return result
            except Exception as e:
                logger.error(f"PyMuPDF falló para {file_path}: {e}")
                return self._record(file_path, t0, mode="FAILED",
                                    error=f"PyMuPDF: {e}")

        # --- Sin proveedores disponibles ---
        return self._record(file_path, t0, mode="SIMULATED",
                            error="Ningún backend OCR disponible")

    # ------------------------------------------------------------------ #
    # Backend: Azure                                                      #
    # ------------------------------------------------------------------ #

    def _extract_azure(self, pdf_bytes: bytes, file_path: str, t0: float) -> Dict[str, Any]:
        """Llama al modelo prebuilt-read de Azure Document Intelligence."""
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

        try:
            poller = self._azure_client.begin_analyze_document(
                "prebuilt-read",
                AnalyzeDocumentRequest(bytes_source=pdf_bytes),
            )
        except TypeError:
            # Compatibilidad con versiones antiguas del SDK
            poller = self._azure_client.begin_analyze_document(
                "prebuilt-read",
                analyze_request=pdf_bytes,
                content_type="application/octet-stream",
            )

        result = poller.result()

        full_text = (result.content or "").strip()
        pages_count = len(result.pages) if result.pages else 0

        # Confianza promedio basada en palabras
        confidences: List[float] = []
        for page in (result.pages or []):
            for word in (page.words or []):
                if word.confidence is not None:
                    confidences.append(word.confidence)
        avg_confidence = (sum(confidences) / len(confidences)) if confidences else 0.9

        return {
            "text": full_text,
            "confidence": avg_confidence,
            "fields": {},
            "processing_time": time.time() - t0,
            "pages": pages_count,
            "source": file_path,
            "provider": "azure",
            "mode": "REAL",
            "words_count": len(confidences),
        }

    # ------------------------------------------------------------------ #
    # Backend: PyMuPDF                                                    #
    # ------------------------------------------------------------------ #

    def _extract_pymupdf(self, pdf_bytes: bytes, file_path: str, t0: float,
                          max_pages: int) -> Dict[str, Any]:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_text = []
        for i in range(min(len(doc), max_pages)):
            try:
                t = doc[i].get_text("text").strip()
                if t:
                    pages_text.append(t)
            except Exception as e:
                logger.warning(f"PyMuPDF página {i + 1} de {file_path}: {e}")

        full_text = "\n\n".join(pages_text)
        return {
            "text": full_text,
            "confidence": 0.95 if full_text else 0.0,
            "fields": {},
            "processing_time": time.time() - t0,
            "pages": len(pages_text),
            "source": file_path,
            "provider": "pymupdf",
            "mode": "REAL" if full_text else "FAILED",
            "error": None if full_text else "PDF sin texto extraíble (¿escaneado?)",
        }

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _load_pdf_bytes(self, file_path: str) -> Optional[bytes]:
        if os.path.isfile(file_path):
            try:
                with open(file_path, "rb") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Disco {file_path}: {e}")
                return None
        if self.supabase_bucket is not None:
            try:
                return self.supabase_bucket.download(file_path)
            except Exception as e:
                logger.error(f"Supabase {file_path}: {e}")
                return None
        return None

    def _record(self, file_path: str, t0: float, mode: str,
                error: Optional[str] = None) -> Dict[str, Any]:
        rec = {
            "text": "", "confidence": 0.0, "fields": {},
            "processing_time": time.time() - t0, "pages": 0,
            "source": file_path, "provider": self.provider,
            "mode": mode, "error": error,
        }
        self._log_run(file_path, rec)
        return rec

    def _log_run(self, file_path: str, result: Dict[str, Any]) -> None:
        self.runs_log.append({
            "file": file_path,
            "pages": result.get("pages", 0),
            "provider": result.get("provider", self.provider),
            "mode": result.get("mode", "?"),
            "error": result.get("error"),
            "confidence": round(result.get("confidence", 0.0), 3),
            "processing_time": round(result.get("processing_time", 0.0), 2),
        })
