"""WhatsApp Service — Twilio real o SIMULADO."""

from typing import Optional, Dict, Any, List
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class WhatsAppService:
    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
    ):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.simulated = not all([account_sid, auth_token, from_number])
        self.messages_log: List[Dict[str, Any]] = []
        logger.info(f"WhatsAppService {'SIMULATED' if self.simulated else 'REAL'}")

    @staticmethod
    def _ensure_prefix(number: str) -> str:
        return number if number.startswith("whatsapp:") else f"whatsapp:{number}"

    def send_message(self, to: str, body: str) -> Dict[str, Any]:
        message_id = f"WA-SIM-{uuid.uuid4().hex[:8]}"
        record = {
            "message_id": message_id, "to": to, "body": body,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "mode": "SIMULATED" if self.simulated else "REAL",
        }
        if self.simulated:
            logger.info(f"[SIM WA] {to}")
            self.messages_log.append({**record, "status": "simulated"})
            return {"message_id": message_id, "status": "simulated"}
        try:
            from twilio.rest import Client
            client = Client(self.account_sid, self.auth_token)
            msg = client.messages.create(
                from_=self._ensure_prefix(self.from_number),
                to=self._ensure_prefix(to), body=body,
            )
            self.messages_log.append({**record, "status": "sent", "twilio_sid": msg.sid})
            return {"message_id": msg.sid, "status": "sent"}
        except Exception as e:
            logger.error(f"WhatsApp error: {e}")
            self.messages_log.append({**record, "status": "failed", "error": str(e)})
            return {"message_id": message_id, "status": "failed", "error": str(e)}
