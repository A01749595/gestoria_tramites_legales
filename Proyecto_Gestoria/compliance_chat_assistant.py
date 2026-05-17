"""
Asistente de Compliance — ContratosVertiche
Versión backend/API usando OpenAI.

Este módulo reemplaza la llamada original a Anthropic por OpenAI y conserva la
lógica de contexto del asistente para alertas, notificaciones, vencimientos y
visitas de Protección Civil.
"""

import json
import logging
from datetime import datetime, date
from typing import Optional, Dict, Any, List

from config import get_config

logger = logging.getLogger("vertiche.assistant")

ASSISTANT_MODEL = get_config().get("openai", {}).get("chat_model") or "gpt-4o-mini"

SYSTEM_PROMPT = """Eres Verti, el asistente amistoso de cumplimiento (compliance) de ContratosVertiche.
Tu trabajo es ayudar al equipo a entender el estado de los contratos, alertas, notificaciones,
vencimientos y visitas de Protección Civil de manera clara, accesible y sin tecnicismos.

Reglas:
- Responde siempre en español, con tono profesional y amigable.
- Usa emojis moderadamente.
- Explica brevemente los números importantes.
- Señala claramente lo urgente sin alarmar innecesariamente.
- Si un dato no existe en el contexto, dilo sin inventar.
- Puedes resumir, comparar y recomendar acciones basadas en los datos.
"""


def _count_pc_visits(visits: List[Dict[str, Any]], period: str) -> int:
    today = date.today()
    if period == "mensual":
        start = today.replace(day=1)
    elif period == "trimestral":
        month_start = ((today.month - 1) // 3) * 3 + 1
        start = today.replace(month=month_start, day=1)
    elif period == "semestral":
        month_start = 1 if today.month <= 6 else 7
        start = today.replace(month=month_start, day=1)
    elif period == "anual":
        start = today.replace(month=1, day=1)
    else:
        return len(visits)

    count = 0
    for v in visits:
        try:
            visit_date = datetime.strptime(v.get("fecha", ""), "%Y-%m-%d").date()
            if visit_date >= start:
                count += 1
        except Exception:
            continue
    return count


def _pc_visits_by_branch(visits: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for v in visits:
        suc = v.get("sucursal", "Desconocida")
        counts[suc] = counts.get(suc, 0) + 1
    return counts


def build_context(workflow=None, compliance_data: Optional[Dict[str, Any]] = None, pc_visits: Optional[List[Dict[str, Any]]] = None) -> str:
    ctx: Dict[str, Any] = {}
    visits = pc_visits or []

    if compliance_data:
        docs = compliance_data.get("documents", []) or []
        branches = compliance_data.get("branches", []) or []
        scores = compliance_data.get("compliance_scores", {}) or {}
        ocr_stats = compliance_data.get("ocr_stats", {}) or {}

        today = date.today()
        criticas, altas, medias = [], [], []
        for doc in docs:
            exp = doc.get("expiration_date") if isinstance(doc, dict) else getattr(doc, "expiration_date", None)
            if isinstance(exp, str) and exp:
                try:
                    exp = datetime.fromisoformat(exp).date()
                except Exception:
                    exp = None
            if not exp:
                continue
            name = doc.get("document_name") if isinstance(doc, dict) else getattr(doc, "document_name", "Documento")
            branch = doc.get("branch_id") if isinstance(doc, dict) else getattr(doc, "branch_id", "?")
            days = (exp - today).days
            entry = {
                "documento": name,
                "sucursal": branch,
                "dias_para_vencer": days,
                "fecha_vencimiento": exp.strftime("%d/%m/%Y"),
            }
            if days <= 7:
                criticas.append(entry)
            elif days <= 30:
                altas.append(entry)
            elif days <= 60:
                medias.append(entry)

        avg_score = sum(scores.values()) / len(scores) if scores else 0
        ctx["compliance"] = {
            "total_sucursales": len(branches),
            "total_documentos": len(docs),
            "score_promedio": round(avg_score, 1),
            "alertas_criticas": len(criticas),
            "alertas_altas": len(altas),
            "alertas_medias": len(medias),
            "detalle_criticas": criticas[:10],
            "detalle_altas": altas[:10],
            "pdfs_procesados": compliance_data.get("total_pdfs", 0),
            "ocr_azure": ocr_stats.get("azure", 0),
            "ocr_pymupdf": ocr_stats.get("pymupdf", 0),
            "ocr_fallidos": ocr_stats.get("failed_ocr", 0),
        }

    if workflow:
        email_log = getattr(workflow.email_service, "sent_log", [])
        cal_log = getattr(workflow.calendar_service, "events_log", [])
        teams_log = getattr(workflow.teams_service, "messages_log", [])
        wa_log = getattr(workflow.whatsapp_service, "messages_log", [])
        ctx["notificaciones"] = {
            "emails_enviados": len(email_log),
            "eventos_calendar": len(cal_log),
            "mensajes_teams": len(teams_log),
            "mensajes_whatsapp": len(wa_log),
            "ultimos_emails": email_log[-5:],
            "ultimos_teams": teams_log[-5:],
            "ultimos_whatsapp": wa_log[-5:],
        }

    ctx["proteccion_civil"] = {
        "total_historico": len(visits),
        "visitas_mes_actual": _count_pc_visits(visits, "mensual"),
        "visitas_trimestre": _count_pc_visits(visits, "trimestral"),
        "visitas_semestre": _count_pc_visits(visits, "semestral"),
        "visitas_anual": _count_pc_visits(visits, "anual"),
        "por_sucursal": _pc_visits_by_branch(visits),
        "ultimas_5": visits[-5:],
    }
    ctx["fecha_reporte"] = datetime.now().strftime("%d/%m/%Y %H:%M")
    return json.dumps(ctx, ensure_ascii=False, default=str, indent=2)


def call_openai_assistant(messages: List[Dict[str, str]], context: str) -> str:
    """Llama OpenAI usando OPENAI_API_KEY del .env."""
    cfg = get_config()
    api_key = cfg.get("openai", {}).get("api_key")
    model = cfg.get("openai", {}).get("chat_model") or ASSISTANT_MODEL
    if not api_key:
        return "⚠️ Falta `OPENAI_API_KEY` en el `.env`. Configúrala para usar el asistente Verti."

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT + "\n\n--- DATOS ACTUALES DEL SISTEMA ---\n" + context,
                },
                *messages,
            ],
        )
        return response.choices[0].message.content or "No recibí respuesta del modelo."
    except ImportError:
        return "⚠️ Falta instalar `openai`. Ejecuta: `pip install openai`."
    except Exception as e:
        logger.exception("Error llamando a OpenAI")
        return f"Lo siento, tuve un problema al procesar tu mensaje: {e}"
