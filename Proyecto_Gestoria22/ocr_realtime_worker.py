"""
ocr_realtime_worker.py — Worker OCR en tiempo real
====================================================
Escucha la tabla `pending_ocr_queue` de Supabase mediante dos mecanismos
complementarios para garantizar que ningún archivo se quede sin procesar:

  1. LISTEN/pg_notify (tiempo real, < 1 s de latencia)
     PostgreSQL notifica al worker en cuanto el endpoint de upload inserta
     una fila en pending_ocr_queue. El worker toma el item, hace OCR y
     actualiza ocr_document_metadata al instante.

  2. Polling de respaldo (cada 30 s)
     Recoge items 'pending' o 'failed' que por alguna razón no llegaron
     vía notify (reconexión de red, reinicio del worker, etc.).

DISEÑO PARA TIEMPO REAL
────────────────────────
- claim_ocr_item() es atómica (SELECT … FOR UPDATE SKIP LOCKED): varios
  workers pueden correr en paralelo sin procesar el mismo archivo dos veces.
- Si el OCR falla, el item vuelve a 'pending' hasta agotar max_attempts (3).
- Al terminar cada item se llama REFRESH MATERIALIZED VIEW CONCURRENTLY
  para que el frontend lea datos actualizados sin ninguna espera adicional.
- El worker nunca para: si se cae, basta con relanzarlo y el polling
  recupera los items que quedaron en 'processing'.

USO
────
    # En una terminal aparte (mientras corre el backend FastAPI):
    python ocr_realtime_worker.py

    # Con más workers en paralelo (útil si hay muchos uploads simultáneos):
    python ocr_realtime_worker.py --workers 3

    # Solo modo polling (sin LISTEN), útil si el firewall bloquea el canal:
    python ocr_realtime_worker.py --no-listen --poll-interval 10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import select
import sys
import tempfile
import time
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ocr_worker")

# ---------------------------------------------------------------------------
# .env
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    for candidate in [Path.cwd() / ".env", Path(__file__).parent / ".env"]:
        if candidate.exists():
            load_dotenv(candidate, override=False)
            break
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Path del proyecto
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.ocr_service import OCRService  # noqa: E402

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
SUPABASE_URL     = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY     = os.getenv("SUPABASE_KEY", "")
SUPABASE_BUCKET  = os.getenv("SUPABASE_BUCKET", "tramites")
DATABASE_URL     = os.getenv("DATABASE_URL", "")   # postgresql://user:pass@host:5432/db
                                                    # Supabase lo da en Settings → Database

TESSERACT_LANG       = os.getenv("TESSERACT_LANG",       "spa+eng")
OCR_MAX_PAGES        = int(os.getenv("OCR_MAX_PAGES",    "15"))
OCR_ZOOM             = float(os.getenv("OCR_ZOOM",       "3.5"))
OCR_SPARSE_THRESHOLD = int(os.getenv("OCR_SPARSE_THRESHOLD", "300"))
TESSERACT_OEM        = os.getenv("TESSERACT_OEM",        "1")

POLL_INTERVAL = 30       # segundos entre polls de respaldo
LISTEN_CHANNEL = "ocr_queue_new"
METADATA_TABLE = "ocr_document_metadata"
QUEUE_TABLE    = "pending_ocr_queue"

# ---------------------------------------------------------------------------
# Reutilizamos exactamente la misma lógica de extracción del indexer
# ---------------------------------------------------------------------------
# (Copiadas aquí para que el worker sea un archivo independiente que no
#  necesita importar ocr_indexer.py — evita dependencias cruzadas)

DATE_DMY   = r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})"
DATE_WORDS = (
    r"(\d{1,2})\s+(?:de\s+)?"
    r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
    r"septiembre|octubre|noviembre|diciembre)"
    r"\s+(?:de\s+)?(\d{2,4})"
)
DATE_ANY = f"(?:{DATE_DMY}|{DATE_WORDS})"
MONTH_MAP = {
    "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
    "julio":7,"agosto":8,"septiembre":9,"octubre":10,"noviembre":11,"diciembre":12,
}
FIELD_PATTERNS: Dict[str, List[str]] = {
    "folio": [
        r"(?:folio|expediente|clave|n[uú]mero|no\.?|num\.?)\s*[:#]?\s*"
        r"([A-Z0-9][\w/\-]{3,30})",
    ],
    "issue_date": [
        rf"(?:fecha\s+de\s+(?:emisi[oó]n|expedici[oó]n)|"
        rf"con\s+fecha)\s*[:]?\s*({DATE_ANY})",
    ],
    "expiration_date": [
        rf"(?:vigencia|per[ií]odo|v[aá]lid[ao])\s*[:]?\s*"
        rf"(?:del?\s+{DATE_ANY}\s+al?\s+)?({DATE_ANY})",
        rf"(?:fecha\s+de\s+(?:vencimiento|caducidad|expiraci[oó]n)|"
        rf"v[aá]lid[ao]\s+hasta|vigente\s+hasta|vence(?:\s+el)?|"
        rf"caduca(?:\s+el)?|expira(?:\s+el)?)\s*[:]?\s*({DATE_ANY})",
        rf"fecha\s+de\s+vigencia\s*[:]?\s*({DATE_ANY})",
    ],
    "authority": [
        r"(?:autoridad(?:\s+emisora)?|expedid[ao]\s+por|otorgad[ao]\s+por|"
        r"emitid[ao]\s+por)\s*[:]?\s*([^\n\.]{5,60})",
    ],
}
DOCUMENT_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "licencia_funcionamiento": ["licencia de funcionamiento","licencia municipal"],
    "permiso":                 ["permiso","autorización","autoriz"],
    "certificado":             ["certificado","certific"],
    "contrato_arrendamiento":  ["contrato de arrendamiento","arrendamiento","renta"],
    "aviso":                   ["aviso de apertura","aviso de funcionamiento"],
    "constancia":              ["constancia"],
}


def _parse_date_match(groups: Tuple) -> Optional[date]:
    for offset in (0, 3):
        day_raw, mon_raw, yr_raw = groups[offset], groups[offset+1], groups[offset+2]
        if day_raw is None:
            continue
        try:
            day   = int(day_raw)
            month = int(mon_raw) if str(mon_raw).isdigit() else MONTH_MAP.get(str(mon_raw).lower().strip())
            if month is None:
                continue
            year = int(yr_raw)
            if year < 100:
                year += 2000 if year < 50 else 1900
            if 1 <= day <= 31 and 1 <= month <= 12 and 2000 <= year <= 2100:
                return date(year, month, day)
        except (ValueError, TypeError):
            continue
    return None


def extract_fields(text: str) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    if not text:
        return fields
    for fname, patterns in FIELD_PATTERNS.items():
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE | re.UNICODE)
            if m:
                raw = m.group(1).strip() if m.lastindex else ""
                if fname in ("issue_date", "expiration_date"):
                    parsed = _parse_date_match(m.groups())
                    if parsed:
                        fields[fname] = parsed.isoformat()
                elif raw:
                    fields[fname] = raw
                break
    # Rango de fechas fallback
    if "expiration_date" not in fields:
        rp = rf"del?\s+({DATE_ANY})\s+(?:al?|hasta)\s+({DATE_ANY})"
        rm = re.search(rp, text, re.IGNORECASE | re.UNICODE)
        if rm:
            n  = len(rm.groups()) // 2
            d2 = _parse_date_match(rm.groups()[n:])
            if d2:
                fields["expiration_date"] = d2.isoformat()
    # Tipo de documento
    tl = text.lower()
    for dt, kws in DOCUMENT_TYPE_KEYWORDS.items():
        if any(k in tl for k in kws):
            fields["document_type"] = dt
            break
    if "document_type" not in fields:
        fields["document_type"] = "otro"
    return fields


def status_from_expiration(exp: Optional[date]) -> str:
    if exp is None:
        return "pending_review"
    today = date.today()
    if exp < today:
        return "expired"
    if (exp - today).days <= 45:
        return "close_to_expiration"
    return "valid"


def stable_branch_id(branch_name: str, state: str, municipality: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-",
                  f"{branch_name}-{state}-{municipality}".lower()).strip("-")
    return "BR-" + hashlib.sha1(slug.encode()).hexdigest()[:8].upper()


def infer_branch(path: str) -> Tuple[str, str, str, str]:
    parts = [p for p in path.replace("\\", "/").split("/") if p.strip()]
    if parts:
        parts[-1] = re.sub(r"\.[^.]+$", "", parts[-1])
    if len(parts) >= 4:
        state, municipality, branch_name = parts[-4], parts[-3], parts[-2]
    elif len(parts) == 3:
        state, municipality, branch_name = parts[-3], parts[-2], parts[-1]
    elif len(parts) == 2:
        state = municipality = "Desconocido"; branch_name = parts[-2]
    else:
        state = municipality = branch_name = parts[0] if parts else "Desconocido"
    clean = lambda s: re.sub(r"[_\-]+", " ", s).strip().title()
    branch_name, state, municipality = clean(branch_name), clean(state), clean(municipality)
    return branch_name, state, municipality, stable_branch_id(branch_name, state, municipality)


# ===========================================================================
# Worker
# ===========================================================================

class OCRRealtimeWorker:
    """
    Worker que consume pending_ocr_queue en tiempo real.
    Usa LISTEN/pg_notify como mecanismo principal y polling como respaldo.
    """

    def __init__(
        self,
        workers:      int  = 2,
        use_listen:   bool = True,
        poll_interval: int = POLL_INTERVAL,
    ):
        self.workers       = workers
        self.use_listen    = use_listen
        self.poll_interval = poll_interval
        self._stop         = threading.Event()
        self._executor     = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ocr")

        # ── Supabase client (HTTP — para upsert, rpc, etc.) ──────────────
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY.")
        from supabase import create_client
        self.sb     = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.bucket = self.sb.storage.from_(SUPABASE_BUCKET)

        # ── psycopg2 (para LISTEN — requiere conexión TCP directa a Postgres)
        self._pg_conn = None
        if use_listen:
            if not DATABASE_URL:
                logger.warning(
                    "DATABASE_URL no está configurado. "
                    "El worker solo usará polling. "
                    "Agrega DATABASE_URL=postgresql://... al .env para activar LISTEN."
                )
                self.use_listen = False
            else:
                self._connect_pg()

        # ── OCR Service ───────────────────────────────────────────────────
        self.ocr = OCRService(
            provider              = "tesseract",
            tesseract_lang        = TESSERACT_LANG,
            max_pages             = OCR_MAX_PAGES,
            zoom                  = OCR_ZOOM,
            sparse_text_threshold = OCR_SPARSE_THRESHOLD,
            oem                   = TESSERACT_OEM,
            psm_candidates        = ("6", "4", "3", "11", "12"),
        )
        logger.info(
            "Worker listo (listen=%s, workers=%d, poll=%ds)",
            self.use_listen, self.workers, self.poll_interval,
        )

    # ── Conexión PostgreSQL directa para LISTEN ───────────────────────────

    def _connect_pg(self) -> None:
        try:
            import psycopg2
            self._pg_conn = psycopg2.connect(DATABASE_URL)
            self._pg_conn.set_isolation_level(
                psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT
            )
            cur = self._pg_conn.cursor()
            cur.execute(f"LISTEN {LISTEN_CHANNEL};")
            cur.close()
            logger.info("LISTEN activado en canal '%s'", LISTEN_CHANNEL)
        except Exception as e:
            logger.warning("No se pudo activar LISTEN: %s. Usando solo polling.", e)
            self._pg_conn  = None
            self.use_listen = False

    def _reconnect_pg(self) -> None:
        """Intenta reconectar si la conexión Postgres se cayó."""
        try:
            if self._pg_conn:
                self._pg_conn.close()
        except Exception:
            pass
        self._pg_conn = None
        time.sleep(5)
        self._connect_pg()

    # ── Claim atómico de un item de la cola ──────────────────────────────

    def _claim_item(self) -> Optional[Dict[str, Any]]:
        try:
            resp = self.sb.rpc("claim_ocr_item", {}).execute()
            if resp.data:
                return resp.data[0]
        except Exception as e:
            logger.warning("claim_ocr_item falló: %s", e)
        return None

    # ── Marcar item como terminado ────────────────────────────────────────

    def _finish_item(
        self,
        item_id:     str,
        status:      str,
        document_id: Optional[str] = None,
        confidence:  Optional[float] = None,
        error:       Optional[str] = None,
    ) -> None:
        try:
            self.sb.rpc("finish_ocr_item", {
                "p_id":          item_id,
                "p_status":      status,
                "p_document_id": document_id,
                "p_confidence":  confidence,
                "p_error":       error[:500] if error else None,
            }).execute()
        except Exception as e:
            logger.warning("finish_ocr_item(%s) falló: %s", item_id, e)

    # ── Descarga del PDF desde el bucket ─────────────────────────────────

    def _download_pdf(self, storage_path: str) -> Optional[bytes]:
        try:
            raw = self.bucket.download(storage_path)
            if isinstance(raw, (bytes, bytearray)):
                return bytes(raw)
            if hasattr(raw, "content"):
                return raw.content
            return bytes(raw)
        except Exception as e:
            logger.warning("Descarga fallida %r: %s", storage_path, e)
            return None

    # ── Upsert de metadatos en ocr_document_metadata ─────────────────────

    def _upsert_metadata(self, record: Dict[str, Any]) -> None:
        self.sb.table(METADATA_TABLE).upsert(
            record, on_conflict="storage_path"
        ).execute()

    # ── Refresco de la vista materializada ───────────────────────────────

    def _refresh_view(self) -> None:
        try:
            self.sb.rpc("refresh_ocr_dashboard_summary", {}).execute()
        except Exception as e:
            logger.debug("refresh_ocr_dashboard_summary: %s", e)

    # ── Procesamiento de un item ──────────────────────────────────────────

    def _process_item(self, item: Dict[str, Any]) -> None:
        item_id      = item["id"]
        storage_path = item["storage_path"]
        file_name    = os.path.basename(storage_path)
        logger.info("▶ Procesando: %s", storage_path)

        try:
            # 1. Descargar PDF
            pdf_bytes = self._download_pdf(storage_path)
            if pdf_bytes is None:
                raise RuntimeError(f"No se pudo descargar {storage_path!r}")

            # 2. OCR
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            try:
                ocr_result = self.ocr.extract_text(tmp_path, document_type="document")
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            text       = ocr_result.get("text", "")
            confidence = ocr_result.get("confidence", 0.0)
            error_msg  = ocr_result.get("error")

            # 3. Extraer campos
            fields         = extract_fields(text)
            folio          = fields.get("folio")
            issue_date_str = fields.get("issue_date")
            exp_date_str   = fields.get("expiration_date")
            authority      = fields.get("authority")
            document_type  = fields.get("document_type", "otro")

            if not exp_date_str:
                yr = re.search(r"20(2[0-9]|3[0-9])", storage_path)
                if yr:
                    exp_date_str = f"{yr.group(0)}-12-31"

            exp_date = None
            if exp_date_str:
                try:
                    exp_date = date.fromisoformat(exp_date_str)
                except ValueError:
                    pass

            status = status_from_expiration(exp_date)
            if ocr_result.get("mode") in ("SIMULATED", "FAILED"):
                status = "unreadable"

            # 4. Inferir branch
            branch_name, state, municipality, branch_id = infer_branch(storage_path)

            # 5. document_id estable
            slug = re.sub(r"[^a-z0-9]+", "-",
                          f"{branch_id}-{file_name}".lower()).strip("-")
            document_id = "DOC-" + hashlib.sha1(slug.encode()).hexdigest()[:10].upper()

            # 6. Nombre amigable
            base_clean    = re.sub(r"\.[^.]+$", "", file_name)
            base_clean    = re.sub(r"[_\-]+", " ", base_clean).strip().title()
            document_name = base_clean or document_type.replace("_", " ").title()

            # 7. Upsert en ocr_document_metadata
            extra_fields = {
                k: v for k, v in fields.items()
                if k not in ("folio", "issue_date", "expiration_date", "authority", "document_type")
            }
            self._upsert_metadata({
                "document_id":       document_id,
                "branch_id":         branch_id,
                "storage_bucket":    SUPABASE_BUCKET,
                "storage_path":      storage_path,
                "file_name":         file_name,
                "file_hash":         hashlib.sha256(pdf_bytes).hexdigest(),
                "document_name":     document_name,
                "document_type":     document_type,
                "issuing_authority": authority,
                "folio_number":      folio,
                "issue_date":        issue_date_str,
                "expiration_date":   exp_date_str,
                "status":            status,
                "ocr_confidence":    round(confidence, 4),
                "ocr_provider":      ocr_result.get("provider", "unknown"),
                "ocr_mode":          ocr_result.get("mode", "UNKNOWN"),
                "pages_total":       ocr_result.get("pages_processed", 0),
                "pages_digital":     ocr_result.get("pages_digital", 0),
                "pages_ocr":         ocr_result.get("pages_ocr", 0),
                "pages_hybrid":      ocr_result.get("pages_hybrid", 0),
                "processing_time":   ocr_result.get("processing_time", 0),
                "extracted_text":    text or None,
                "extracted_fields":  json.dumps(extra_fields),
                "branch_name":       branch_name,
                "state":             state,
                "municipality":      municipality,
                "last_checked_at":   datetime.utcnow().isoformat(),
                "error_message":     error_msg,
                "indexed_at":        datetime.utcnow().isoformat(),
            })

            # 8. Refrescar vista del dashboard
            self._refresh_view()

            # 9. Marcar item como done
            self._finish_item(item_id, "done", document_id, round(confidence, 4))
            logger.info(
                "✔ %s → %s (confianza=%.0f%%, %.1fs)",
                file_name, status.upper(), confidence * 100,
                ocr_result.get("processing_time", 0),
            )

        except Exception as e:
            logger.error("✘ Error procesando %r: %s", storage_path, e, exc_info=False)
            # Si quedan intentos, el claim_ocr_item lo volverá a tomar
            self._finish_item(
                item_id, "failed",
                error=str(e),
            )
            # Volver a 'pending' si no se agotaron los intentos
            try:
                self.sb.table(QUEUE_TABLE).update({"status": "pending"}).eq(
                    "id", item_id
                ).lt("attempts", 3).execute()
            except Exception:
                pass

    # ── Drain: procesa todos los items disponibles en la cola ─────────────

    def _drain_queue(self) -> int:
        """
        Toma y procesa todos los items 'pending' disponibles.
        Retorna el número de items procesados.
        """
        processed = 0
        futures   = []
        while True:
            item = self._claim_item()
            if item is None:
                break
            fut = self._executor.submit(self._process_item, item)
            futures.append(fut)
            processed += 1
        # Esperar a que terminen los del lote actual antes del siguiente drain
        for fut in futures:
            try:
                fut.result()
            except Exception as e:
                logger.error("Worker thread error: %s", e)
        return processed

    # ── Loop de LISTEN ────────────────────────────────────────────────────

    def _listen_loop(self) -> None:
        """
        Escucha pg_notify en el canal 'ocr_queue_new'.
        Al recibir una notificación hace drain de la cola completa
        (no solo el item notificado, por si llegaron varios a la vez).
        """
        logger.info("LISTEN loop iniciado.")
        while not self._stop.is_set():
            if self._pg_conn is None:
                time.sleep(5)
                self._reconnect_pg()
                continue
            try:
                # select.select con timeout de 2 s para poder chequear _stop
                ready = select.select([self._pg_conn], [], [], 2.0)[0]
                if ready:
                    self._pg_conn.poll()
                    while self._pg_conn.notifies:
                        notify = self._pg_conn.notifies.pop(0)
                        logger.info("📨 NOTIFY recibido: %s", notify.payload[:120])
                        # Pequeña espera para que el INSERT esté committed
                        time.sleep(0.2)
                        n = self._drain_queue()
                        if n:
                            logger.info("Cola drenada tras NOTIFY: %d item(s)", n)
            except Exception as e:
                logger.warning("Error en LISTEN loop: %s. Reconectando…", e)
                self._reconnect_pg()
        logger.info("LISTEN loop detenido.")

    # ── Loop de polling de respaldo ───────────────────────────────────────

    def _poll_loop(self) -> None:
        """
        Cada `poll_interval` segundos verifica si hay items pendientes
        que el LISTEN se haya perdido.
        """
        logger.info("Poll loop iniciado (intervalo=%ds).", self.poll_interval)
        while not self._stop.is_set():
            try:
                n = self._drain_queue()
                if n:
                    logger.info("Poll: %d item(s) procesados.", n)
            except Exception as e:
                logger.warning("Error en poll loop: %s", e)
            # Esperar en pequeños intervalos para responder a _stop rápido
            for _ in range(self.poll_interval * 2):
                if self._stop.is_set():
                    break
                time.sleep(0.5)
        logger.info("Poll loop detenido.")

    # ── Inicio / parada ───────────────────────────────────────────────────

    def start(self) -> None:
        """
        Arranca los loops en hilos de fondo y bloquea hasta recibir
        KeyboardInterrupt o llamar a stop().
        """
        threads: List[threading.Thread] = []

        if self.use_listen and self._pg_conn:
            t = threading.Thread(target=self._listen_loop, name="listen", daemon=True)
            t.start()
            threads.append(t)

        t = threading.Thread(target=self._poll_loop, name="poll", daemon=True)
        t.start()
        threads.append(t)

        # Drain inicial por si había items al arrancar
        n = self._drain_queue()
        if n:
            logger.info("Drain inicial: %d item(s) procesados.", n)

        logger.info("Worker en marcha. Ctrl-C para detener.")
        try:
            while not self._stop.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Deteniendo worker…")
            self.stop()

        for t in threads:
            t.join(timeout=10)
        self._executor.shutdown(wait=True, cancel_futures=False)
        logger.info("Worker detenido.")

    def stop(self) -> None:
        self._stop.set()


# ===========================================================================
# CLI
# ===========================================================================

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Worker OCR en tiempo real — escucha pending_ocr_queue"
    )
    p.add_argument(
        "--workers", type=int, default=2,
        help="Workers OCR en paralelo (default: 2)"
    )
    p.add_argument(
        "--no-listen", dest="no_listen", action="store_true",
        help="Desactivar LISTEN/pg_notify, usar solo polling"
    )
    p.add_argument(
        "--poll-interval", type=int, default=POLL_INTERVAL,
        dest="poll_interval",
        help=f"Segundos entre polls de respaldo (default: {POLL_INTERVAL})"
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    worker = OCRRealtimeWorker(
        workers       = args.workers,
        use_listen    = not args.no_listen,
        poll_interval = args.poll_interval,
    )
    worker.start()
