"""Calendar Service — modo SIMULADO por defecto."""

from typing import Optional, Dict, Any, List
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CalendarService:
    def __init__(
        self,
        credentials_path: Optional[str] = None,
        calendar_id: str = "primary",
        default_timezone: str = "America/Mexico_City",
    ):
        self.credentials_path = credentials_path
        self.calendar_id = calendar_id
        self.default_timezone = default_timezone
        self.simulated = not credentials_path
        self.events_log: List[Dict[str, Any]] = []
        logger.info(f"CalendarService {'SIMULATED' if self.simulated else 'REAL'}")

    def create_event(
        self,
        title: str,
        description: str = "",
        start_date=None,
        end_date=None,
        attendees: Optional[List[str]] = None,
        reminders_minutes: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        event_id = f"CAL-SIM-{uuid.uuid4().hex[:8]}"
        record = {
            "event_id": event_id, "title": title,
            "start_date": str(start_date), "end_date": str(end_date) if end_date else None,
            "attendees": attendees or [], "reminders_minutes": reminders_minutes or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": "SIMULATED" if self.simulated else "REAL",
        }
        self.events_log.append(record)
        logger.info(f"[CAL] {event_id} | {title}")
        return {"event_id": event_id, "status": "created", **record}
