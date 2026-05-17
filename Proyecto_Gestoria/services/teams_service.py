"""Teams Service — webhook real o SIMULADO."""

from typing import Optional, Dict, Any, List
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class TeamsService:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url
        self.simulated = not webhook_url
        self.messages_log: List[Dict[str, Any]] = []
        logger.info(f"TeamsService {'SIMULATED' if self.simulated else 'REAL'}")

    def send_message(
        self, title: str, text: str, color: str = "0078D4",
        facts: Optional[List[Dict[str, str]]] = None,
        action_url: Optional[str] = None, action_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        message_id = f"TEAMS-SIM-{uuid.uuid4().hex[:8]}"
        record = {
            "message_id": message_id, "title": title, "text": text, "color": color,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "mode": "SIMULATED" if self.simulated else "REAL",
        }
        if self.simulated:
            logger.info(f"[SIM TEAMS] {title}")
            self.messages_log.append({**record, "status": "simulated"})
            return {"message_id": message_id, "status": "simulated"}
        try:
            import requests
            payload = {
                "@type": "MessageCard", "@context": "https://schema.org/extensions",
                "themeColor": color, "title": title, "text": text,
            }
            if facts:
                payload["sections"] = [{"facts": facts}]
            if action_url and action_label:
                payload["potentialAction"] = [{
                    "@type": "OpenUri", "name": action_label,
                    "targets": [{"os": "default", "uri": action_url}],
                }]
            resp = requests.post(self.webhook_url, json=payload, timeout=15)
            resp.raise_for_status()
            self.messages_log.append({**record, "status": "sent"})
            return {"message_id": message_id, "status": "sent"}
        except Exception as e:
            logger.error(f"Teams error: {e}")
            self.messages_log.append({**record, "status": "failed", "error": str(e)})
            return {"message_id": message_id, "status": "failed", "error": str(e)}
