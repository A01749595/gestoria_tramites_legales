"""
Renewal Alert Agent - Manages renewal alerts and calendar events
Creates alerts across multiple channels: Google Calendar, Teams, WhatsApp, Email
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
import logging
from schemas.schemas import (
    Branch, Document, Alert, AlertType, AlertChannel, AlertStatus,
    UrgencyLevel
)

logger = logging.getLogger(__name__)


class RenewalAlertAgent:
    """
    Agent responsible for creating and managing renewal alerts across multiple channels.
    Integrates with Google Calendar, Microsoft Teams, WhatsApp, and Email.
    """
    
    def __init__(
        self,
        calendar_service=None,
        teams_service=None,
        whatsapp_service=None,
        email_service=None
    ):
        """
        Initialize the Renewal Alert Agent
        
        Args:
            calendar_service: Google Calendar service instance
            teams_service: Microsoft Teams service instance
            whatsapp_service: WhatsApp service instance
            email_service: Email service instance
        """
        self.calendar_service = calendar_service
        self.teams_service = teams_service
        self.whatsapp_service = whatsapp_service
        self.email_service = email_service
        self.alert_history = []
        logger.info("Renewal Alert Agent initialized")
    
    def create_renewal_alert(
        self,
        branch: Branch,
        document: Document,
        channels: Optional[List[AlertChannel]] = None
    ) -> List[Alert]:
        """
        Create renewal alert across specified channels
        
        Args:
            branch: Branch information
            document: Document requiring renewal
            channels: List of channels to send alert (default: all)
            
        Returns:
            List of created alerts
        """
        if not document.expiration_date:
            logger.warning(f"Document {document.document_id} has no expiration date")
            return []
        
        logger.info(f"Creating renewal alert for document {document.document_id}")
        
        # Determine alert type based on days to expiration
        days_to_expiration = (document.expiration_date - date.today()).days
        alert_type = self._determine_alert_type(days_to_expiration)
        
        # Use all channels if none specified
        if channels is None:
            channels = [
                AlertChannel.GOOGLE_CALENDAR,
                AlertChannel.MICROSOFT_TEAMS,
                AlertChannel.EMAIL
            ]
            # Add WhatsApp for urgent alerts
            if days_to_expiration <= 15:
                channels.append(AlertChannel.WHATSAPP)
        
        # Create alerts for each channel
        alerts = []
        for channel in channels:
            alert = self._create_alert_for_channel(
                branch, document, alert_type, channel, days_to_expiration
            )
            if alert:
                alerts.append(alert)
                self.alert_history.append(alert)
        
        logger.info(f"Created {len(alerts)} alerts for document {document.document_id}")
        return alerts
    
    def create_batch_alerts(
        self,
        branch: Branch,
        documents: List[Document],
        channels: Optional[List[AlertChannel]] = None
    ) -> Dict[str, Any]:
        """
        Create alerts for multiple documents
        
        Args:
            branch: Branch information
            documents: List of documents requiring alerts
            channels: List of channels to send alerts
            
        Returns:
            Summary of created alerts
        """
        logger.info(f"Creating batch alerts for {len(documents)} documents")
        
        all_alerts = []
        for document in documents:
            alerts = self.create_renewal_alert(branch, document, channels)
            all_alerts.extend(alerts)
        
        summary = {
            "branch_id": branch.branch_id,
            "branch_name": branch.branch_name,
            "total_documents": len(documents),
            "total_alerts_created": len(all_alerts),
            "alerts_by_channel": self._count_alerts_by_channel(all_alerts),
            "alerts_by_type": self._count_alerts_by_type(all_alerts),
            "created_at": datetime.utcnow().isoformat()
        }
        
        return summary
    
    def schedule_calendar_event(
        self,
        branch: Branch,
        document: Document,
        days_before_expiration: int = 15
    ) -> Optional[Alert]:
        """
        Schedule a Google Calendar event for document renewal
        
        Args:
            branch: Branch information
            document: Document to schedule renewal for
            days_before_expiration: Days before expiration to schedule event
            
        Returns:
            Alert object with calendar event details
        """
        if not document.expiration_date:
            return None
        
        logger.info(f"Scheduling calendar event for document {document.document_id}")
        
        # Calculate event date
        event_date = document.expiration_date - timedelta(days=days_before_expiration)
        
        # Create calendar event
        event_details = {
            "summary": f"Renovar: {document.document_name}",
            "description": self._generate_calendar_description(branch, document),
            "start": event_date.isoformat(),
            "end": event_date.isoformat(),
            "attendees": [branch.responsible_email, branch.manager_email],
            "reminders": [
                {"method": "email", "minutes": 24 * 60},  # 1 day before
                {"method": "popup", "minutes": 60}  # 1 hour before
            ]
        }
        
        calendar_event_id = None
        status = AlertStatus.PENDING
        
        try:
            if self.calendar_service:
                calendar_event_id = self.calendar_service.create_event(event_details)
                status = AlertStatus.SENT
                logger.info(f"Calendar event created: {calendar_event_id}")
            else:
                # Simulate if no service
                calendar_event_id = f"CAL-{document.document_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
                logger.info(f"Calendar event simulated: {calendar_event_id}")
        except Exception as e:
            logger.error(f"Error creating calendar event: {e}")
            status = AlertStatus.FAILED
        
        # Create alert record
        alert = Alert(
            alert_id=f"ALERT-CAL-{branch.branch_id}-{document.document_id}",
            branch_id=branch.branch_id,
            branch_name=branch.branch_name,
            document_name=document.document_name,
            document_id=document.document_id,
            expiration_date=document.expiration_date if document.expiration_date else date.today(),
            alert_type=self._determine_alert_type((document.expiration_date - date.today()).days) if document.expiration_date else AlertType.MISSING_DOCUMENT,
            channel=AlertChannel.GOOGLE_CALENDAR,
            status=status,
            recipient=branch.responsible_email,
            message=event_details["description"],
            calendar_event_id=calendar_event_id,
            sent_at=datetime.utcnow() if status == AlertStatus.SENT else None
        )
        
        return alert
    
    def send_teams_notification(
        self,
        branch: Branch,
        document: Document,
        urgency: UrgencyLevel = UrgencyLevel.MEDIUM
    ) -> Optional[Alert]:
        """
        Send Microsoft Teams notification
        
        Args:
            branch: Branch information
            document: Document information
            urgency: Urgency level
            
        Returns:
            Alert object with Teams message details
        """
        if not branch.teams_channel:
            logger.warning(f"No Teams channel configured for branch {branch.branch_id}")
            return None
        
        logger.info(f"Sending Teams notification for document {document.document_id}")
        
        days_to_expiration = (document.expiration_date - date.today()).days if document.expiration_date else 0
        
        # Create Teams message
        message = self._generate_teams_message(branch, document, days_to_expiration, urgency)
        
        teams_message_id = None
        status = AlertStatus.PENDING
        
        try:
            if self.teams_service:
                teams_message_id = self.teams_service.send_message(
                    channel_id=branch.teams_channel,
                    message=message
                )
                status = AlertStatus.SENT
                logger.info(f"Teams message sent: {teams_message_id}")
            else:
                # Simulate if no service
                teams_message_id = f"TEAMS-{document.document_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
                logger.info(f"Teams message simulated: {teams_message_id}")
        except Exception as e:
            logger.error(f"Error sending Teams message: {e}")
            status = AlertStatus.FAILED
        
        # Create alert record
        alert = Alert(
            alert_id=f"ALERT-TEAMS-{branch.branch_id}-{document.document_id}",
            branch_id=branch.branch_id,
            branch_name=branch.branch_name,
            document_name=document.document_name,
            document_id=document.document_id,
            expiration_date=document.expiration_date if document.expiration_date else date.today(),
            alert_type=self._determine_alert_type(days_to_expiration),
            channel=AlertChannel.MICROSOFT_TEAMS,
            status=status,
            recipient=branch.teams_channel if branch.teams_channel else "unknown",
            message=message,
            teams_message_id=teams_message_id,
            sent_at=datetime.utcnow() if status == AlertStatus.SENT else None
        )
        
        return alert
    
    def send_whatsapp_notification(
        self,
        branch: Branch,
        document: Document
    ) -> Optional[Alert]:
        """
        Send WhatsApp notification
        
        Args:
            branch: Branch information
            document: Document information
            
        Returns:
            Alert object with WhatsApp message details
        """
        if not branch.whatsapp_contact:
            logger.warning(f"No WhatsApp contact for branch {branch.branch_id}")
            return None
        
        logger.info(f"Sending WhatsApp notification for document {document.document_id}")
        
        days_to_expiration = (document.expiration_date - date.today()).days if document.expiration_date else 0
        
        # Create WhatsApp message
        message = self._generate_whatsapp_message(branch, document, days_to_expiration)
        
        whatsapp_message_id = None
        status = AlertStatus.PENDING
        
        try:
            if self.whatsapp_service:
                whatsapp_message_id = self.whatsapp_service.send_message(
                    to=branch.whatsapp_contact,
                    message=message
                )
                status = AlertStatus.SENT
                logger.info(f"WhatsApp message sent: {whatsapp_message_id}")
            else:
                # Simulate if no service
                whatsapp_message_id = f"WA-{document.document_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
                logger.info(f"WhatsApp message simulated: {whatsapp_message_id}")
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            status = AlertStatus.FAILED
        
        # Create alert record
        alert = Alert(
            alert_id=f"ALERT-WA-{branch.branch_id}-{document.document_id}",
            branch_id=branch.branch_id,
            branch_name=branch.branch_name,
            document_name=document.document_name,
            document_id=document.document_id,
            expiration_date=document.expiration_date if document.expiration_date else date.today(),
            alert_type=self._determine_alert_type(days_to_expiration),
            channel=AlertChannel.WHATSAPP,
            status=status,
            recipient=branch.whatsapp_contact,
            message=message,
            whatsapp_message_id=whatsapp_message_id,
            sent_at=datetime.utcnow() if status == AlertStatus.SENT else None
        )
        
        return alert
    
    def _create_alert_for_channel(
        self,
        branch: Branch,
        document: Document,
        alert_type: AlertType,
        channel: AlertChannel,
        days_to_expiration: int
    ) -> Optional[Alert]:
        """Create alert for specific channel"""
        
        if channel == AlertChannel.GOOGLE_CALENDAR:
            return self.schedule_calendar_event(branch, document)
        elif channel == AlertChannel.MICROSOFT_TEAMS:
            urgency = UrgencyLevel.HIGH if days_to_expiration <= 15 else UrgencyLevel.MEDIUM
            return self.send_teams_notification(branch, document, urgency)
        elif channel == AlertChannel.WHATSAPP:
            return self.send_whatsapp_notification(branch, document)
        elif channel == AlertChannel.EMAIL:
            # Email alerts are handled by EmailAutomationAgent
            # Create a placeholder alert record
            return Alert(
                alert_id=f"ALERT-EMAIL-{branch.branch_id}-{document.document_id}",
                branch_id=branch.branch_id,
                branch_name=branch.branch_name,
                document_name=document.document_name,
                document_id=document.document_id,
                expiration_date=document.expiration_date if document.expiration_date else date.today(),
                alert_type=alert_type,
                channel=AlertChannel.EMAIL,
                status=AlertStatus.PENDING,
                recipient=branch.responsible_email,
                message="Email notification scheduled"
            )
        
        return None
    
    def _determine_alert_type(self, days_to_expiration: int) -> AlertType:
        """Determine alert type based on days to expiration"""
        if days_to_expiration < 0:
            return AlertType.OVERDUE
        elif days_to_expiration == 0:
            return AlertType.EXPIRATION_TODAY
        elif days_to_expiration <= 15:
            return AlertType.EXPIRATION_15_DAYS
        elif days_to_expiration <= 45:
            return AlertType.EXPIRATION_45_DAYS
        else:
            return AlertType.EXPIRATION_45_DAYS
    
    def _generate_calendar_description(self, branch: Branch, document: Document) -> str:
        """Generate calendar event description"""
        days_to_exp = (document.expiration_date - date.today()).days if document.expiration_date else 0
        
        return f"""
📄 Renovación de Documento

Documento: {document.document_name}
Sucursal: {branch.branch_name}
Ubicación: {branch.municipality}, {branch.state}
Fecha de vencimiento: {document.expiration_date.strftime('%d/%m/%Y') if document.expiration_date else 'N/A'}
Días restantes: {days_to_exp}
Autoridad emisora: {document.issuing_authority}

Responsable: {branch.responsible_email}
Gerente: {branch.manager_email}

⚠️ Acción requerida: Iniciar proceso de renovación
"""
    
    def _generate_teams_message(
        self,
        branch: Branch,
        document: Document,
        days_to_expiration: int,
        urgency: UrgencyLevel
    ) -> str:
        """Generate Teams message"""
        urgency_emoji = "🔴" if urgency == UrgencyLevel.CRITICAL else "⚠️" if urgency == UrgencyLevel.HIGH else "📅"
        
        return f"""
{urgency_emoji} **Alerta de Renovación de Documento**

**Documento:** {document.document_name}
**Sucursal:** {branch.branch_name}
**Ubicación:** {branch.municipality}, {branch.state}
**Vencimiento:** {document.expiration_date.strftime('%d/%m/%Y') if document.expiration_date else 'N/A'}
**Días restantes:** {days_to_expiration}

**Responsable:** {branch.responsible_email}

{'🚨 **ACCIÓN URGENTE REQUERIDA**' if urgency in [UrgencyLevel.HIGH, UrgencyLevel.CRITICAL] else '📋 Acción requerida'}
"""
    
    def _generate_whatsapp_message(
        self,
        branch: Branch,
        document: Document,
        days_to_expiration: int
    ) -> str:
        """Generate WhatsApp message"""
        urgency_emoji = "🔴" if days_to_expiration <= 15 else "⚠️"
        
        return f"""
{urgency_emoji} *Alerta de Renovación*

📄 *{document.document_name}*
🏢 {branch.branch_name}
📍 {branch.municipality}, {branch.state}
📅 Vence: {document.expiration_date.strftime('%d/%m/%Y') if document.expiration_date else 'N/A'}
⏰ Días restantes: *{days_to_expiration}*

{'🚨 *URGENTE* - Renovar inmediatamente' if days_to_expiration <= 15 else '📋 Programar renovación'}
"""
    
    def _count_alerts_by_channel(self, alerts: List[Alert]) -> Dict[str, int]:
        """Count alerts by channel"""
        counts = {channel.value: 0 for channel in AlertChannel}
        for alert in alerts:
            counts[alert.channel.value] += 1
        return counts
    
    def _count_alerts_by_type(self, alerts: List[Alert]) -> Dict[str, int]:
        """Count alerts by type"""
        counts = {alert_type.value: 0 for alert_type in AlertType}
        for alert in alerts:
            counts[alert.alert_type.value] += 1
        return counts
    
    def get_pending_alerts(
        self,
        branch_id: Optional[str] = None
    ) -> List[Alert]:
        """
        Get pending alerts
        
        Args:
            branch_id: Optional branch ID to filter by
            
        Returns:
            List of pending alerts
        """
        alerts = [a for a in self.alert_history if a.status == AlertStatus.PENDING]
        
        if branch_id:
            alerts = [a for a in alerts if a.branch_id == branch_id]
        
        return alerts
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """
        Mark alert as acknowledged
        
        Args:
            alert_id: Alert identifier
            
        Returns:
            True if acknowledged, False if not found
        """
        for alert in self.alert_history:
            if alert.alert_id == alert_id:
                alert.status = AlertStatus.ACKNOWLEDGED
                alert.acknowledged_at = datetime.utcnow()
                logger.info(f"Alert {alert_id} acknowledged")
                return True
        
        logger.warning(f"Alert {alert_id} not found")
        return False
    
    def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alert statistics"""
        total_alerts = len(self.alert_history)
        
        if total_alerts == 0:
            return {
                "total_alerts": 0,
                "by_status": {},
                "by_channel": {},
                "by_type": {}
            }
        
        return {
            "total_alerts": total_alerts,
            "by_status": {
                status.value: len([a for a in self.alert_history if a.status == status])
                for status in AlertStatus
            },
            "by_channel": self._count_alerts_by_channel(self.alert_history),
            "by_type": self._count_alerts_by_type(self.alert_history)
        }


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    from schemas.schemas import DocumentStatus
    
    # Create agent
    agent = RenewalAlertAgent()
    
    # Example branch
    branch = Branch(
        branch_id="BR-001",
        branch_name="Sucursal Centro CDMX",
        state="Ciudad de México",
        municipality="Cuauhtémoc",
        region="Centro",
        responsible_email="responsable@empresa.com",
        manager_email="gerente@empresa.com",
        whatsapp_contact="+525512345678",
        teams_channel="19:abc123@thread.tacv2"
    )
    
    # Example document expiring soon
    document = Document(
        document_id="DOC-001",
        branch_id="BR-001",
        document_name="Licencia de Funcionamiento",
        document_type="license",
        issuing_authority="Secretaría de Desarrollo Económico",
        issue_date=date(2024, 1, 15),
        expiration_date=date.today() + timedelta(days=12),
        status=DocumentStatus.CLOSE_TO_EXPIRATION,
        ocr_confidence=0.95,
        file_url="s3://docs/BR-001/lic.pdf"
    )
    
    # Create renewal alerts
    print("\n=== Creating Renewal Alerts ===")
    alerts = agent.create_renewal_alert(branch, document)
    print(f"Created {len(alerts)} alerts")
    for alert in alerts:
        print(f"- {alert.channel.value}: {alert.status.value}")
    
    # Get statistics
    print("\n=== Alert Statistics ===")
    stats = agent.get_alert_statistics()
    print(f"Total alerts: {stats['total_alerts']}")
    print(f"By channel: {stats['by_channel']}")
    print(f"By status: {stats['by_status']}")

# Made with Bob