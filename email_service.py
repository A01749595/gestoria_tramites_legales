"""Email Service — SMTP real o modo SIMULADO."""

from typing import Optional, List, Dict, Any
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        username: Optional[str] = None,
        password: Optional[str] = None,
        from_email: Optional[str] = None,
        use_tls: bool = True,
        use_ssl: bool = False,
    ):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email or username
        self.use_tls = use_tls
        self.use_ssl = use_ssl
        self.simulated = not all([smtp_host, username, password, self.from_email])
        self.sent_log: List[Dict[str, Any]] = []
        logger.info(f"EmailService {'SIMULATED' if self.simulated else 'REAL'}")

    def send_email(self, to: str, subject: str, body: str,
                   cc: Optional[List[str]] = None, html: bool = False) -> Dict[str, Any]:
        record = {
            "to": to, "cc": cc or [], "subject": subject,
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "mode": "SIMULATED" if self.simulated else "REAL",
        }
        if self.simulated:
            logger.info(f"[SIM EMAIL] {to} | {subject}")
            self.sent_log.append({**record, "status": "simulated"})
            return {"status": "simulated", "to": to}
        try:
            msg = MIMEMultipart()
            msg["From"] = self.from_email
            msg["To"] = to
            if cc:
                msg["Cc"] = ", ".join(cc)
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "html" if html else "plain", "utf-8"))
            recipients = [to] + (cc or [])
            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30)
                if self.use_tls:
                    server.starttls()
            server.login(self.username, self.password)
            server.sendmail(self.from_email, recipients, msg.as_string())
            server.quit()
            self.sent_log.append({**record, "status": "sent"})
            return {"status": "sent", "to": to}
        except Exception as e:
            logger.error(f"Email error: {e}")
            self.sent_log.append({**record, "status": "failed", "error": str(e)})
            return {"status": "failed", "error": str(e)}
