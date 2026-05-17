"""
ContratosVertiche22 — Backend API FastAPI

Reemplaza el frontend Streamlit por una API consumible desde React/Node.js,
conservando los módulos base de ContratosVertiche22: OCR, Supabase Storage,
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
from datetime import datetime, date
from typing import Optional, List, Dict, Any

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import get_config, is_configured
from schemas.schemas import Branch, Document, DocumentStatus, LegalRiskLevel
from workflows.compliance_workflow import ComplianceWorkflow
from dashboard.dashboard_service import DashboardService
from compliance_chat_assistant import build_context, call_openai_assistant

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
logger = logging.getLogger("vertiche.api")

CONFIG = get_config()
SUPABASE_URL = CONFIG["supabase"].get("url")
SUPABASE_KEY = CONFIG["supabase"].get("key")
SUPABASE_BUCKET = CONFIG["supabase"].get("bucket")
SUPABASE_PREFIX = os.getenv("SUPABASE_PREFIX", "") or ""
OPENAI_API_KEY = CONFIG["openai"].get("api_key")
CHAT_MODEL = CONFIG["openai"].get("chat_model")

supabase = None
bucket = None
supabase_error: Optional[str] = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        bucket = supabase.storage.from_(SUPABASE_BUCKET)
        try:
            bucket.list(path=SUPABASE_PREFIX)
        except Exception as e:
            supabase_error = f"Bucket no accesible: {e}"
            bucket = None
    except Exception as e:
        supabase_error = f"Supabase no inicializó: {e}"
else:
    supabase_error = "Faltan SUPABASE_URL o SUPABASE_KEY"

openai_client = None
openai_error: Optional[str] = None
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception as e:
        openai_error = f"OpenAI no inicializó: {e}"
else:
    openai_error = "Falta OPENAI_API_KEY"

workflow = ComplianceWorkflow(config=CONFIG, supabase_bucket=bucket)
dashboard_svc = DashboardService()
COMPLIANCE_CACHE: Optional[Dict[str, Any]] = None
PC_VISITS: List[Dict[str, Any]] = []

app = FastAPI(title="ContratosVertiche22 API", version="2.0.0")
'''app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)'''

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


EXTRACT_SYSTEM = """Eres un asistente experto en contratos de arrendamiento de sucursales en México.
Devuelve exclusivamente JSON válido con esta estructura:
{
  "branch_name": "nombre de sucursal o local",
  "state": "estado oficial de México",
  "municipality": "municipio o alcaldía",
  "responsible_party": "arrendatario o responsable",
  "issuing_authority": "autoridad o arrendador",
  "document_type": "contrato_arrendamiento|licencia|permiso|certificado",
  "issue_date": "YYYY-MM-DD o null",
  "expiration_date": "YYYY-MM-DD o null",
  "folio_number": "folio o número de contrato",
  "monthly_rent_mxn": número o null,
  "term_months": número o null,
  "risk_level": "low|medium|high|critical"
}
Si un campo no aparece, usa null. No inventes.
"""


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


def fields_to_branch_document(pdf_path: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not fields:
        return None
    branch_id = f"BR-{abs(hash(pdf_path)) % 100000:05d}"
    branch_name = fields.get("branch_name") or os.path.basename(pdf_path).replace(".pdf", "")
    exp = parse_date_safe(fields.get("expiration_date"))
    issue = parse_date_safe(fields.get("issue_date"))
    try:
        branch = Branch(
            branch_id=branch_id,
            branch_name=str(branch_name)[:120],
            state=fields.get("state") or "México",
            municipality=fields.get("municipality") or "N/A",
            region="Nacional",
            responsible_email=os.getenv("DEFAULT_RESPONSIBLE_EMAIL", "responsable@vertiche.mx"),
            manager_email=os.getenv("DEFAULT_MANAGER_EMAIL", "gerente@vertiche.mx"),
            whatsapp_contact=os.getenv("DEFAULT_WHATSAPP", "+520000000000"),
        )
        document = Document(
            document_id=f"DOC-{branch_id}",
            branch_id=branch_id,
            document_name=str(branch_name)[:120],
            document_type=fields.get("document_type") or "contrato_arrendamiento",
            issuing_authority=fields.get("issuing_authority") or "N/A",
            issue_date=issue,
            expiration_date=exp,
            status=status_from_expiration(exp),
            ocr_confidence=0.9,
            file_url=pdf_path,
            folio_number=fields.get("folio_number"),
            metadata={
                "risk_level": fields.get("risk_level"),
                "monthly_rent_mxn": fields.get("monthly_rent_mxn"),
                "term_months": fields.get("term_months"),
                "responsible_party": fields.get("responsible_party"),
            },
        )
        return {"branch": branch, "document": document}
    except Exception as e:
        logger.error("fields_to_branch_document(%s): %s", pdf_path, e)
        return None


def demo_dataset() -> Dict[str, Any]:
    today = date.today()
    branches = [
        Branch(branch_id="BR-DEMO-001", branch_name="Sucursal Centro CDMX", state="Ciudad de México", municipality="Cuauhtémoc", region="Centro", responsible_email="responsable@vertiche.mx", manager_email="gerente@vertiche.mx", whatsapp_contact="+525500000000"),
        Branch(branch_id="BR-DEMO-002", branch_name="Sucursal Monterrey", state="Nuevo León", municipality="Monterrey", region="Norte", responsible_email="responsable@vertiche.mx", manager_email="gerente@vertiche.mx", whatsapp_contact="+525500000000"),
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
        "ocr_stats": {"azure": 0, "pymupdf": 0, "failed_ocr": 0, "failed_llm": 0},
        "demo": True,
    }


def build_compliance_dataset(force_refresh: bool = False) -> Dict[str, Any]:
    global COMPLIANCE_CACHE
    if COMPLIANCE_CACHE and not force_refresh:
        return COMPLIANCE_CACHE
    if bucket is None or openai_client is None:
        COMPLIANCE_CACHE = demo_dataset()
        return COMPLIANCE_CACHE

    pdfs = list_all_pdfs_in_bucket()
    branches: List[Branch] = []
    documents: List[Document] = []
    compliance_scores: Dict[str, float] = {}
    extraction_log: List[Dict[str, Any]] = []
    stats = {"azure": 0, "pymupdf": 0, "failed_ocr": 0, "failed_llm": 0}

    for pdf_path in pdfs:
        run = {"file": pdf_path, "started_at": datetime.utcnow().isoformat(), "status": "pending", "error": None, "provider": None, "pages": 0, "confidence": 0.0}
        try:
            ocr_result = workflow.ocr_service.extract_text(file_path=pdf_path, document_type="contrato_arrendamiento")
            text = ocr_result.get("text", "")
            run.update({"provider": ocr_result.get("provider"), "pages": ocr_result.get("pages", 0), "confidence": ocr_result.get("confidence", 0.0)})
            if not text.strip():
                stats["failed_ocr"] += 1
                raise RuntimeError(f"OCR sin texto: {ocr_result.get('error')}")
            if ocr_result.get("provider") == "azure":
                stats["azure"] += 1
            else:
                stats["pymupdf"] += 1
            fields = extract_contract_fields(text)
            if not fields:
                stats["failed_llm"] += 1
                raise RuntimeError("OpenAI no devolvió campos")
            mapped = fields_to_branch_document(pdf_path, fields)
            if not mapped:
                raise RuntimeError("No se pudo mapear a Branch/Document")
            branches.append(mapped["branch"])
            documents.append(mapped["document"])
            status = mapped["document"].status
            score = 95.0 if status == DocumentStatus.VALID else 70.0 if status == DocumentStatus.CLOSE_TO_EXPIRATION else 30.0 if status == DocumentStatus.EXPIRED else 50.0
            compliance_scores[mapped["branch"].branch_id] = score
            run["status"] = "ok"
            run["fields"] = fields
        except Exception as e:
            run["status"] = "failed"
            run["error"] = str(e)
            logger.warning("Extracción falló para %s: %s", pdf_path, e)
        finally:
            run["finished_at"] = datetime.utcnow().isoformat()
            extraction_log.append(run)

    COMPLIANCE_CACHE = {
        "branches": branches,
        "documents": documents,
        "compliance_scores": compliance_scores,
        "extraction_log": extraction_log,
        "generated_at": datetime.utcnow().isoformat(),
        "total_pdfs": len(pdfs),
        "ocr_stats": stats,
        "demo": False,
    }
    if not branches:
        # Mantiene UI funcional aunque no haya documentos procesados todavía.
        COMPLIANCE_CACHE = demo_dataset() | {"extraction_log": extraction_log, "total_pdfs": len(pdfs), "demo": True}
    return COMPLIANCE_CACHE


def serialize_dataset(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **data,
        "branches": [model_to_dict(b) for b in data.get("branches", [])],
        "documents": [model_to_dict(d) for d in data.get("documents", [])],
    }


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
    whatsapp_to: Optional[str] = None
    title: Optional[str] = "Prueba de agentes ContratosVertiche"


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "services": {svc: is_configured(svc) for svc in ["supabase", "openai", "email", "calendar", "teams", "whatsapp"]},
        "errors": {"supabase": supabase_error, "openai": openai_error},
        "bucket": SUPABASE_BUCKET,
    }


@app.get("/api/dashboard")
def dashboard(refresh: bool = False):
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
    data = build_compliance_dataset(force_refresh=False)
    return {"documents": serialize_dataset(data)["documents"], "bucket_files": list_all_pdfs_in_bucket()}


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
    return {
        "services": [
            {"name": "OCR", "real": bool(workflow.ocr_service._azure_available or workflow.ocr_service._fitz_available)},
            {"name": "Email", "real": not workflow.email_service.simulated},
            {"name": "Google Calendar", "real": not workflow.calendar_service.simulated},
            {"name": "Microsoft Teams", "real": not workflow.teams_service.simulated},
            {"name": "WhatsApp", "real": not workflow.whatsapp_service.simulated},
            {"name": "Supabase Storage", "real": bucket is not None},
            {"name": "OpenAI", "real": openai_client is not None},
        ],
        "agents": ["RouterAgent", "DocumentMonitoringAgent", "RegulatoryValidationAgent", "EmailAutomationAgent", "RenewalAlertAgent", "IntelligentActivationAgent"],
        "extraction_log": data.get("extraction_log", []),
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
    data = build_compliance_dataset(force_refresh=False)
    docs = serialize_dataset(data)["documents"]
    rows = []
    for d in docs[:10]:
        exp = d.get("expiration_date") or "Sin fecha"
        rows.append(f"• {d.get('document_name')} — {status_label(d.get('status'))} — vence: {exp}")
    message = "Estados de documentos:\n" + "\n".join(rows or ["Sin documentos disponibles."])
    teams_result = workflow.teams_service.send_message(title=payload.title or "Prueba ContratosVertiche", text=message)
    whatsapp_to = payload.whatsapp_to or os.getenv("DEFAULT_WHATSAPP", "+520000000000")
    whatsapp_result = workflow.whatsapp_service.send_message(to=whatsapp_to, body=f"{payload.title}\n\n{message}")
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


@app.post("/api/assistant/chat")
def assistant_chat(payload: AssistantChatRequest):
    data = serialize_dataset(build_compliance_dataset(force_refresh=False))
    context = build_context(workflow=workflow, compliance_data=data, pc_visits=PC_VISITS)
    reply = call_openai_assistant(payload.messages, context)
    return {"reply": reply}
