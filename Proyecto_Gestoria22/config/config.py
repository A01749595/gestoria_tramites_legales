"""
Configuración centralizada del sistema de compliance.
Lee credenciales desde variables de entorno (.env o st.secrets).
Las variables no configuradas dejan al servicio en modo SIMULADO.
"""

import os
from pathlib import Path
from typing import Dict, Any

# --- Cargar .env automáticamente si existe ---
# Busca .env en el directorio actual y va subiendo.
try:
    from dotenv import load_dotenv
    # Busca primero en cwd, después en el padre del archivo config/config.py
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for env_path in candidates:
        if env_path.exists():
            load_dotenv(env_path, override=False)
            break
except ImportError:
    # python-dotenv no instalado; las vars deberán venir del entorno.
    pass


def _env(key: str, default=None):
    """
    Lee una variable. Prioridad:
    1. os.environ (incluye .env si load_dotenv ya corrió)
    2. st.secrets (solo si estamos en Streamlit y existe el secret)
    """
    val = os.getenv(key)
    if val is not None and val.strip() != "":
        return val
    # Fallback: st.secrets (útil para Streamlit Cloud y .streamlit/secrets.toml)
    try:
        import streamlit as st
        if key in st.secrets:
            v = st.secrets[key]
            if isinstance(v, str) and v.strip() == "":
                return default
            return v
    except Exception:
        pass
    return default


def get_config() -> Dict[str, Any]:
    """
    Devuelve la config completa lista para inyectar a ComplianceWorkflow.
    OCR: Tesseract (pytesseract) + PyMuPDF, sin Azure.
    """
    return {
        # OCR Tesseract + PyMuPDF (mismo stack que GestoriaVertiche)
        "ocr": {
            "provider": "tesseract",
            # Idiomas: 'spa+eng' funciona muy bien para documentos legales
            # mexicanos. Si solo tienes el paquete 'spa' instalado, cámbialo
            # con la variable de entorno TESSERACT_LANG.
            "tesseract_lang": _env("TESSERACT_LANG", "spa+eng"),
            # Páginas máximas por PDF. Sube esto si tus contratos son largos
            # y necesitas leer fechas/folios que están en páginas avanzadas.
            "max_pages": int(_env("OCR_MAX_PAGES", 4) or 4),
            # Zoom de rasterización antes del OCR (1.8 es buen compromiso).
            "zoom": float(_env("OCR_ZOOM", 1.8) or 1.8),
            # Si la página digital tiene MENOS de N caracteres, asumimos
            # que es escaneada y forzamos OCR.
            "sparse_text_threshold": int(_env("OCR_SPARSE_THRESHOLD", 140) or 140),
        },
        # SMTP / Email
        "email": {
            "smtp_host": _env("SMTP_HOST", "smtp.gmail.com"),
            "smtp_port": int(_env("SMTP_PORT", 587) or 587),
            "smtp_username": _env("SMTP_USERNAME"),
            "smtp_password": _env("SMTP_PASSWORD"),
            "from_email": _env("SMTP_FROM_EMAIL") or _env("SMTP_USERNAME"),
            "use_tls": (_env("SMTP_USE_TLS", "true") or "true").lower() == "true",
            "use_ssl": (_env("SMTP_USE_SSL", "false") or "false").lower() == "true",
        },
        # Google Calendar
        "calendar": {
            "google_credentials_path": _env("GOOGLE_CALENDAR_CREDENTIALS"),
            "calendar_id": _env("GOOGLE_CALENDAR_ID", "primary"),
            "timezone": _env("CALENDAR_TIMEZONE", "America/Mexico_City"),
        },
        # Microsoft Teams
        "teams": {
            "webhook_url": _env("TEAMS_WEBHOOK_URL"),
        },
        # Twilio WhatsApp
        "whatsapp": {
            "twilio_account_sid": _env("TWILIO_ACCOUNT_SID"),
            "twilio_auth_token": _env("TWILIO_AUTH_TOKEN"),
            "twilio_whatsapp_number": _env("TWILIO_WHATSAPP_NUMBER"),
        },
        # Supabase
        "supabase": {
            "url": _env("SUPABASE_URL"),
            "key": _env("SUPABASE_KEY"),
            "bucket": _env("SUPABASE_BUCKET", "tramites"),
        },
        # OpenAI
        "openai": {
            "api_key": _env("OPENAI_API_KEY"),
            "embedding_model": _env("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            "chat_model": _env("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        },
    }


def is_configured(service: str) -> bool:
    """¿Tiene credenciales reales este servicio?"""
    cfg = get_config()
    s = cfg.get(service, {})
    if service == "ocr":
        # OCR ahora corre 100% local: si PyMuPDF + Tesseract están instalados, está OK.
        try:
            import fitz  # noqa: F401
        except ImportError:
            return False
        try:
            import pytesseract  # noqa: F401
            import shutil
            return bool(
                shutil.which("tesseract")
                or os.path.exists("/usr/bin/tesseract")
                or os.path.exists("/usr/local/bin/tesseract")
                or os.path.exists("/opt/homebrew/bin/tesseract")
            )
        except ImportError:
            # PyMuPDF solo (sin Tesseract) sigue sirviendo para PDFs digitales.
            return True
    if service == "email":
        return all([s.get("smtp_host"), s.get("smtp_username"), s.get("smtp_password")])
    if service == "calendar":
        return bool(s.get("google_credentials_path"))
    if service == "teams":
        return bool(s.get("webhook_url"))
    if service == "whatsapp":
        return all([s.get("twilio_account_sid"), s.get("twilio_auth_token"), s.get("twilio_whatsapp_number")])
    if service == "supabase":
        return all([s.get("url"), s.get("key")])
    if service == "openai":
        return bool(s.get("api_key"))
    return False
