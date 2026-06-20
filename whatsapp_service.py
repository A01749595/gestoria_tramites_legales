"""
WhatsApp Service — CallMeBot (gratuito, sin instalación de servidor).

CÓMO ACTIVAR POR NÚMERO DESTINATARIO
--------------------------------------
Cada número que vaya a RECIBIR mensajes debe hacer esto UNA sola vez:
  1. Agregar el contacto +34 644 44 44 75 a su WhatsApp.
  2. Enviarle este mensaje exacto:
         I allow callmebot to send me messages
  3. Recibirá un mensaje con su apikey personal (ej. "1234567").

CONFIGURACIÓN EN .env
----------------------
Cada número destinatario necesita su propia apikey. El formato en .env es:

  # Un solo número (el más común):
  DEFAULT_WHATSAPP=+525567845166
  CALLMEBOT_APIKEYS=+525567845166:1234567

  # Varios números:
  CALLMEBOT_APIKEYS=+525511111111:1234567,+525522222222:7654321

  Si un número no tiene apikey configurada, el mensaje pasa a modo SIMULADO
  para ese destinatario (se registra en log pero no se envía).

LIMITACIONES DE CALLMEBOT
--------------------------
  - Gratuito, sin límite de mensajes documentado.
  - Solo texto (no imágenes ni documentos).
  - El destinatario debe haber activado el servicio una vez (ver arriba).
  - Los emojis y el formato *negrita* de WhatsApp funcionan correctamente.
"""

from typing import Optional, Dict, Any, List, Union, Iterable
import logging
import re
import uuid
import time
from datetime import datetime, timezone
from urllib.parse import quote

logger = logging.getLogger(__name__)

# URL base de CallMeBot
_CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"

# E.164: "+" seguido de 8 a 15 dígitos
_E164_CLEANUP_RE = re.compile(r"[\s\-\(\)]")
_E164_VALID_RE   = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone_e164(raw: str) -> Optional[str]:
    """
    Limpia y valida un número en formato E.164.
        "+52 55 1234 5678" -> "+525512345678"
        "5512345678"       -> None  (sin código de país)
    Devuelve None si el número no cumple E.164.
    """
    if not raw:
        return None
    cleaned = _E164_CLEANUP_RE.sub("", str(raw).strip())
    if cleaned and not cleaned.startswith("+") and not cleaned.startswith("whatsapp:"):
        return None
    cleaned = cleaned.replace("whatsapp:", "")
    return cleaned if _E164_VALID_RE.match(cleaned) else None


def to_callmebot_phone(e164: str) -> str:
    """
    Convierte un número E.164 al formato que espera CallMeBot.

    CallMeBot para México requiere el "1" de marcación móvil entre el
    código de país (52) y el número de 10 dígitos:
        "+525567845166"  ->  "+5215567845166"

    Para otros países devuelve el número sin cambios.
    """
    mx = re.match(r"^\+52([2-9]\d{9})$", e164)
    if mx:
        return f"+521{mx.group(1)}"
    return e164


def parse_recipients(raw: Union[str, Iterable[str], None]) -> List[str]:
    """
    Acepta un número, varios separados por coma/punto y coma, o una lista.
    Devuelve lista de strings sin limpiar (la validación E.164 va después).
    """
    if not raw:
        return []
    if isinstance(raw, str):
        parts = re.split(r"[,;\n]+", raw)
    else:
        parts = list(raw)
    return [p.strip() for p in parts if p and p.strip()]


def parse_apikeys(raw: Optional[str]) -> Dict[str, str]:
    """
    Parsea la variable CALLMEBOT_APIKEYS del .env.
    Formato: "+525511111111:1234567,+525522222222:7654321"
    Devuelve dict {numero_normalizado: apikey}.
    """
    if not raw:
        return {}
    result: Dict[str, str] = {}
    for pair in re.split(r"[,;\n]+", raw):
        pair = pair.strip()
        if ":" not in pair:
            continue
        phone, _, apikey = pair.partition(":")
        normalized = normalize_phone_e164(phone.strip())
        if normalized and apikey.strip():
            result[normalized] = apikey.strip()
    return result


class WhatsAppService:
    """
    Servicio de WhatsApp basado en CallMeBot (API gratuita).

    Mantiene la misma interfaz pública que versiones anteriores
    (send_message, messages_log, simulated) para no romper los agentes.
    """

    def __init__(
        self,
        # Parámetros CallMeBot
        apikeys: Optional[Union[str, Dict[str, str]]] = None,
        send_delay_seconds: float = 1.0,
        # Compatibilidad con versión open-wa anterior (ignorados)
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        session_name: str = "gestoria",
        # Compatibilidad con versión Twilio anterior (ignorados)
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
    ):
        """
        Args:
            apikeys: dict {numero_e164: apikey} o string con formato
                     "+52551234:111111,+52559876:222222".
                     También se puede pasar None y configurar vía .env
                     (CALLMEBOT_APIKEYS). Si está vacío -> modo SIMULADO
                     para todos los números sin apikey.
            send_delay_seconds: pausa entre mensajes a distintos números.
        """
        if account_sid or auth_token or from_number or api_url:
            logger.warning(
                "WhatsAppService: credenciales de Twilio/open-wa ignoradas. "
                "Esta versión usa CallMeBot. Configura CALLMEBOT_APIKEYS en .env."
            )

        # Cargar apikeys
        if isinstance(apikeys, dict):
            self._apikeys: Dict[str, str] = apikeys
        elif isinstance(apikeys, str):
            self._apikeys = parse_apikeys(apikeys)
        else:
            # Intentar leer desde .env / entorno
            import os
            self._apikeys = parse_apikeys(os.getenv("CALLMEBOT_APIKEYS", ""))

        self.send_delay_seconds = max(0.0, send_delay_seconds)
        self.messages_log: List[Dict[str, Any]] = []

        # simulated=True solo si no hay NINGUNA apikey cargada
        self.simulated = len(self._apikeys) == 0

        logger.info(
            "WhatsAppService CallMeBot — %d número(s) con apikey. Modo: %s",
            len(self._apikeys),
            "SIMULATED" if self.simulated else "REAL",
        )

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def send_message(
        self,
        to: Union[str, Iterable[str], None],
        body: Optional[str] = None,
        message: Optional[str] = None,          # alias legacy
        content_sid: Optional[str] = None,       # ignorado (Twilio legacy)
        content_variables: Optional[Dict] = None, # ignorado (Twilio legacy)
    ) -> Dict[str, Any]:
        """
        Envía un mensaje WhatsApp a uno o varios destinatarios via CallMeBot.

        Args:
            to: número E.164 ("+525512345678"), varios separados por coma,
                o lista de números.
            body / message: texto del mensaje. Soporta emojis y *negrita*.

        Returns:
            {
              "results": [ {"to", "status", "message_id", "error"}, ... ],
              "summary": {"sent", "failed", "invalid", "total", "simulated"}
            }
        """
        if content_sid:
            logger.info("content_sid ignorado (CallMeBot no usa plantillas).")

        if body is None and message is not None:
            body = message
        if body is None:
            body = ""

        recipients = parse_recipients(to)
        if not recipients:
            return {
                "results": [],
                "summary": {
                    "sent": 0, "failed": 0, "invalid": 0, "total": 0,
                    "error": "No se proporcionó ningún destinatario",
                },
            }

        results: List[Dict[str, Any]] = []
        for idx, raw_to in enumerate(recipients):
            normalized = normalize_phone_e164(raw_to)
            if not normalized:
                results.append({
                    "to": raw_to,
                    "status": "invalid",
                    "message_id": None,
                    "error": (
                        "Formato inválido. Usa E.164: +<código país><número>, "
                        "ej. +525512345678"
                    ),
                    "mode": "invalid",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                })
                continue

            if idx > 0 and self.send_delay_seconds:
                time.sleep(self.send_delay_seconds)

            results.append(self._send_single(normalized, body))

        summary = {
            "total": len(results),
            "sent":    sum(1 for r in results if r["status"] in ("sent", "simulated")),
            "failed":  sum(1 for r in results if r["status"] == "failed"),
            "invalid": sum(1 for r in results if r["status"] == "invalid"),
            "simulated": all(
                r["status"] == "simulated"
                for r in results
                if r["status"] != "invalid"
            ),
        }
        return {"results": results, "summary": summary}

    def _send_single(self, to: str, body: str) -> Dict[str, Any]:
        """Envía a UN número ya normalizado en E.164."""
        record: Dict[str, Any] = {
            "to": to,
            "body": body,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "message_id": f"WA-{uuid.uuid4().hex[:8]}",
            "error": None,
        }

        apikey = self._apikeys.get(to)

        if not apikey:
            # Sin apikey para este número → simular
            logger.info(
                "[SIM CallMeBot] %s (sin apikey — el destinatario debe activar "
                "CallMeBot enviando 'I allow callmebot to send me messages' "
                "al +34 644 44 44 75)", to
            )
            record["status"] = "simulated"
            record["mode"] = "SIMULATED"
            self.messages_log.append(record)
            return record

        try:
            import requests
            params = {
                "phone":  to_callmebot_phone(to),
                "text":   body,
                "apikey": apikey,
            }
            resp = requests.get(_CALLMEBOT_URL, params=params, timeout=15)
            resp.raise_for_status()

            record["status"] = "sent"
            record["mode"]   = "REAL"
            self.messages_log.append(record)
            logger.info("CallMeBot → %s ✓", to)
            return record

        except Exception as e:  # noqa: BLE001
            error_msg = str(e)
            # Mensaje de ayuda si el número no activó el servicio
            if "403" in error_msg or "not allowed" in error_msg.lower():
                error_msg = (
                    f"El número {to} no ha activado CallMeBot. "
                    "Debe enviar 'I allow callmebot to send me messages' "
                    "al +34 644 44 44 75 desde su WhatsApp."
                )
            logger.error("CallMeBot error (%s): %s", to, error_msg)
            record["status"] = "failed"
            record["mode"]   = "REAL"
            record["error"]  = error_msg
            self.messages_log.append(record)
            return record

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def add_apikey(self, phone: str, apikey: str) -> bool:
        """
        Registra la apikey de un número en tiempo de ejecución.
        Útil si las apikeys se guardan en base de datos en lugar del .env.
        Devuelve True si el número es válido y se registró.
        """
        normalized = normalize_phone_e164(phone)
        if not normalized:
            logger.warning("add_apikey: número inválido '%s'", phone)
            return False
        self._apikeys[normalized] = apikey.strip()
        self.simulated = False
        logger.info("ApiKey registrada para %s", normalized)
        return True

    def check_connection(self) -> Dict[str, Any]:
        """Health-check: informa cuántos números tienen apikey configurada."""
        return {
            "connected": len(self._apikeys) > 0,
            "simulated": self.simulated,
            "numbers_with_apikey": len(self._apikeys),
            "detail": (
                f"{len(self._apikeys)} número(s) con apikey CallMeBot configurada."
                if self._apikeys
                else (
                    "Sin apikeys configuradas (modo simulado). "
                    "Agrega CALLMEBOT_APIKEYS=+52XXXXXXXXXX:APIKEY al .env. "
                    "El destinatario activa su apikey enviando "
                    "'I allow callmebot to send me messages' al +34 644 44 44 75."
                )
            ),
        }

    def get_status(self) -> Dict[str, Any]:
        """Alias de check_connection para el dashboard."""
        return self.check_connection()