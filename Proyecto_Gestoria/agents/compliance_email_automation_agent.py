"""
Email Automation Agent - Generates and sends automated email notifications
Handles missing documents, expired documents, and renewal reminders
"""

from datetime import datetime, date
from typing import Dict, Any, List, Optional
import logging
from schemas.schemas import (
    Branch, Document, DocumentStatus, EmailLog, ComplianceResult,
    UrgencyLevel
)

logger = logging.getLogger(__name__)


class EmailAutomationAgent:
    """
    Agent responsible for generating and sending automated email notifications
    to branch managers and responsible parties about compliance issues.
    """
    
    def __init__(self, email_service=None):
        """
        Initialize the Email Automation Agent
        
        Args:
            email_service: Email service instance for sending emails
        """
        self.email_service = email_service
        self.email_templates = self._initialize_email_templates()
        self.email_history = []
        logger.info("Email Automation Agent initialized")
    
    def _initialize_email_templates(self) -> Dict[str, Dict[str, str]]:
        """Initialize email templates for different scenarios"""
        return {
            "expired_document": {
                "subject": "🚨 URGENTE: Documento Vencido - {document_name}",
                "template": """
Estimado/a responsable de {branch_name},

Le informamos que el siguiente documento ha VENCIDO y requiere atención inmediata:

📄 Documento: {document_name}
🏢 Sucursal: {branch_name}
📍 Ubicación: {municipality}, {state}
📅 Fecha de vencimiento: {expiration_date}
⏰ Días vencido: {days_overdue}
🏛️ Autoridad emisora: {issuing_authority}

⚠️ ACCIÓN REQUERIDA:
Debe renovar este documento de inmediato para mantener el cumplimiento legal de la sucursal.

Pasos a seguir:
1. Contactar a {issuing_authority}
2. Iniciar proceso de renovación
3. Cargar el nuevo documento al sistema una vez obtenido

Este es un asunto de alta prioridad que requiere su atención inmediata.

Saludos cordiales,
Sistema de Cumplimiento Legal
"""
            },
            "missing_document": {
                "subject": "⚠️ Documento Faltante - {document_name}",
                "template": """
Estimado/a responsable de {branch_name},

Le informamos que falta el siguiente documento obligatorio:

📄 Documento: {document_name}
🏢 Sucursal: {branch_name}
📍 Ubicación: {municipality}, {state}
🏛️ Autoridad emisora: {issuing_authority}
⚖️ Categoría legal: {legal_category}
🔴 Nivel de riesgo: {risk_level}

⚠️ ACCIÓN REQUERIDA:
Este documento es obligatorio para el cumplimiento legal de la sucursal.

Pasos a seguir:
1. Solicitar el documento ante {issuing_authority}
2. Completar los trámites necesarios
3. Cargar el documento al sistema una vez obtenido

Por favor, atienda este asunto a la brevedad posible.

Saludos cordiales,
Sistema de Cumplimiento Legal
"""
            },
            "expiring_soon_15": {
                "subject": "🔔 URGENTE: Documento por Vencer en {days_remaining} días - {document_name}",
                "template": """
Estimado/a responsable de {branch_name},

Le recordamos que el siguiente documento está próximo a vencer:

📄 Documento: {document_name}
🏢 Sucursal: {branch_name}
📍 Ubicación: {municipality}, {state}
📅 Fecha de vencimiento: {expiration_date}
⏰ Días restantes: {days_remaining}
🏛️ Autoridad emisora: {issuing_authority}

⚠️ ACCIÓN URGENTE REQUERIDA:
Debe iniciar el proceso de renovación INMEDIATAMENTE para evitar que el documento venza.

Pasos a seguir:
1. Contactar a {issuing_authority} HOY
2. Iniciar proceso de renovación
3. Dar seguimiento diario al trámite
4. Cargar el nuevo documento al sistema una vez obtenido

Este documento vence en menos de 15 días. No espere más.

Saludos cordiales,
Sistema de Cumplimiento Legal
"""
            },
            "expiring_soon_45": {
                "subject": "📅 Recordatorio: Documento por Vencer - {document_name}",
                "template": """
Estimado/a responsable de {branch_name},

Le recordamos que el siguiente documento requiere renovación próximamente:

📄 Documento: {document_name}
🏢 Sucursal: {branch_name}
📍 Ubicación: {municipality}, {state}
📅 Fecha de vencimiento: {expiration_date}
⏰ Días restantes: {days_remaining}
🏛️ Autoridad emisora: {issuing_authority}

📋 ACCIÓN REQUERIDA:
Por favor, programe la renovación de este documento para evitar vencimientos.

Pasos a seguir:
1. Contactar a {issuing_authority}
2. Verificar requisitos de renovación
3. Iniciar proceso de renovación
4. Cargar el nuevo documento al sistema una vez obtenido

Le recomendamos iniciar el proceso pronto para evitar contratiempos.

Saludos cordiales,
Sistema de Cumplimiento Legal
"""
            },
            "compliance_report": {
                "subject": "📊 Reporte de Cumplimiento - {branch_name}",
                "template": """
Estimado/a gerente de {branch_name},

Adjunto encontrará el reporte de cumplimiento legal de su sucursal:

🏢 Sucursal: {branch_name}
📍 Ubicación: {municipality}, {state}
📊 Puntuación de cumplimiento: {compliance_score}%
🎯 Nivel de riesgo: {risk_level}

📈 RESUMEN:
✅ Documentos válidos: {valid_count}
⚠️ Por vencer (45 días): {expiring_45_count}
🔴 Por vencer (15 días): {expiring_15_count}
❌ Documentos vencidos: {expired_count}
📋 Documentos faltantes: {missing_count}

{recommendations}

Por favor, revise el reporte completo y tome las acciones necesarias.

Saludos cordiales,
Sistema de Cumplimiento Legal
"""
            },
            "batch_reminder": {
                "subject": "📋 Recordatorio: {count} Documentos Requieren Atención",
                "template": """
Estimado/a responsable de {branch_name},

Le informamos que tiene {count} documentos que requieren su atención:

🏢 Sucursal: {branch_name}
📍 Ubicación: {municipality}, {state}

{document_list}

⚠️ ACCIÓN REQUERIDA:
Por favor, revise cada documento y tome las acciones correspondientes.

Saludos cordiales,
Sistema de Cumplimiento Legal
"""
            }
        }
    
    def send_expired_document_email(
        self,
        branch: Branch,
        document: Document
    ) -> EmailLog:
        """
        Send email notification for expired document
        
        Args:
            branch: Branch information
            document: Expired document
            
        Returns:
            EmailLog with send status
        """
        logger.info(f"Sending expired document email for {document.document_id}")
        
        days_overdue = abs((date.today() - document.expiration_date).days) if document.expiration_date else 0
        
        template_vars = {
            "branch_name": branch.branch_name,
            "document_name": document.document_name,
            "municipality": branch.municipality,
            "state": branch.state,
            "expiration_date": document.expiration_date.strftime("%d/%m/%Y") if document.expiration_date else "N/A",
            "days_overdue": days_overdue,
            "issuing_authority": document.issuing_authority
        }
        
        subject = self.email_templates["expired_document"]["subject"].format(**template_vars)
        body = self.email_templates["expired_document"]["template"].format(**template_vars)
        
        email_log = self._send_email(
            branch=branch,
            subject=subject,
            body=body,
            document_references=[document.document_id],
            template_used="expired_document",
            cc=[branch.manager_email]
        )
        
        return email_log
    
    def send_missing_document_email(
        self,
        branch: Branch,
        document_name: str,
        issuing_authority: str,
        legal_category: str = "operational",
        risk_level: str = "high"
    ) -> EmailLog:
        """
        Send email notification for missing document
        
        Args:
            branch: Branch information
            document_name: Name of missing document
            issuing_authority: Authority that issues the document
            legal_category: Legal category of the document
            risk_level: Risk level if not obtained
            
        Returns:
            EmailLog with send status
        """
        logger.info(f"Sending missing document email for {document_name}")
        
        template_vars = {
            "branch_name": branch.branch_name,
            "document_name": document_name,
            "municipality": branch.municipality,
            "state": branch.state,
            "issuing_authority": issuing_authority,
            "legal_category": legal_category,
            "risk_level": risk_level.upper()
        }
        
        subject = self.email_templates["missing_document"]["subject"].format(**template_vars)
        body = self.email_templates["missing_document"]["template"].format(**template_vars)
        
        email_log = self._send_email(
            branch=branch,
            subject=subject,
            body=body,
            document_references=[],
            template_used="missing_document",
            cc=[branch.manager_email]
        )
        
        return email_log
    
    def send_expiring_soon_email(
        self,
        branch: Branch,
        document: Document,
        urgency: UrgencyLevel = UrgencyLevel.MEDIUM
    ) -> EmailLog:
        """
        Send email notification for document expiring soon
        
        Args:
            branch: Branch information
            document: Document expiring soon
            urgency: Urgency level (determines template)
            
        Returns:
            EmailLog with send status
        """
        logger.info(f"Sending expiring soon email for {document.document_id}")
        
        days_remaining = (document.expiration_date - date.today()).days if document.expiration_date else 0
        
        # Select template based on urgency
        template_key = "expiring_soon_15" if days_remaining <= 15 else "expiring_soon_45"
        
        template_vars = {
            "branch_name": branch.branch_name,
            "document_name": document.document_name,
            "municipality": branch.municipality,
            "state": branch.state,
            "expiration_date": document.expiration_date.strftime("%d/%m/%Y") if document.expiration_date else "N/A",
            "days_remaining": days_remaining,
            "issuing_authority": document.issuing_authority
        }
        
        subject = self.email_templates[template_key]["subject"].format(**template_vars)
        body = self.email_templates[template_key]["template"].format(**template_vars)
        
        email_log = self._send_email(
            branch=branch,
            subject=subject,
            body=body,
            document_references=[document.document_id],
            template_used=template_key,
            cc=[branch.manager_email] if days_remaining <= 15 else []
        )
        
        return email_log
    
    def send_compliance_report_email(
        self,
        branch: Branch,
        compliance_result: ComplianceResult
    ) -> EmailLog:
        """
        Send comprehensive compliance report email
        
        Args:
            branch: Branch information
            compliance_result: Compliance analysis result
            
        Returns:
            EmailLog with send status
        """
        logger.info(f"Sending compliance report for branch {branch.branch_id}")
        
        # Format recommendations
        recommendations = "\n🔧 ACCIONES RECOMENDADAS:\n"
        for i, action in enumerate(compliance_result.recommended_actions, 1):
            recommendations += f"{i}. {action}\n"
        
        template_vars = {
            "branch_name": branch.branch_name,
            "municipality": branch.municipality,
            "state": branch.state,
            "compliance_score": compliance_result.compliance_score,
            "risk_level": compliance_result.legal_risk_level.value.upper(),
            "valid_count": len(compliance_result.valid_documents),
            "expiring_45_count": len([d for d in compliance_result.soon_to_expire_documents if d.get("days_remaining", 0) > 15]),
            "expiring_15_count": len([d for d in compliance_result.soon_to_expire_documents if d.get("days_remaining", 0) <= 15]),
            "expired_count": len(compliance_result.expired_documents),
            "missing_count": len(compliance_result.missing_documents),
            "recommendations": recommendations
        }
        
        subject = self.email_templates["compliance_report"]["subject"].format(**template_vars)
        body = self.email_templates["compliance_report"]["template"].format(**template_vars)
        
        email_log = self._send_email(
            branch=branch,
            subject=subject,
            body=body,
            document_references=[],
            template_used="compliance_report",
            cc=[branch.manager_email]
        )
        
        return email_log
    
    def send_batch_reminder_email(
        self,
        branch: Branch,
        documents: List[Document]
    ) -> EmailLog:
        """
        Send batch reminder for multiple documents
        
        Args:
            branch: Branch information
            documents: List of documents requiring attention
            
        Returns:
            EmailLog with send status
        """
        logger.info(f"Sending batch reminder for {len(documents)} documents")
        
        # Format document list
        document_list = ""
        for i, doc in enumerate(documents, 1):
            days_remaining = (doc.expiration_date - date.today()).days if doc.expiration_date else 0
            status_emoji = "🔴" if days_remaining < 0 else "⚠️" if days_remaining <= 15 else "📅"
            document_list += f"{i}. {status_emoji} {doc.document_name} - "
            
            if days_remaining < 0:
                document_list += f"VENCIDO hace {abs(days_remaining)} días\n"
            elif days_remaining <= 15:
                document_list += f"Vence en {days_remaining} días (URGENTE)\n"
            else:
                document_list += f"Vence en {days_remaining} días\n"
        
        template_vars = {
            "branch_name": branch.branch_name,
            "municipality": branch.municipality,
            "state": branch.state,
            "count": len(documents),
            "document_list": document_list
        }
        
        subject = self.email_templates["batch_reminder"]["subject"].format(**template_vars)
        body = self.email_templates["batch_reminder"]["template"].format(**template_vars)
        
        email_log = self._send_email(
            branch=branch,
            subject=subject,
            body=body,
            document_references=[doc.document_id for doc in documents],
            template_used="batch_reminder"
        )
        
        return email_log
    
    def _send_email(
        self,
        branch: Branch,
        subject: str,
        body: str,
        document_references: List[str],
        template_used: str,
        cc: Optional[List[str]] = None
    ) -> EmailLog:
        """
        Internal method to send email and create log
        
        Args:
            branch: Branch information
            subject: Email subject
            body: Email body
            document_references: List of document IDs referenced
            template_used: Template identifier used
            cc: Optional CC recipients
            
        Returns:
            EmailLog with send status
        """
        email_id = f"EMAIL-{branch.branch_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        try:
            # Send email using email service
            if self.email_service:
                self.email_service.send_email(
                    to=branch.responsible_email,
                    cc=cc or [],
                    subject=subject,
                    body=body
                )
                status = "sent"
                error_message = None
            else:
                # Simulate sending if no service configured
                logger.info(f"Email simulated (no service configured): {email_id}")
                status = "simulated"
                error_message = None
            
        except Exception as e:
            logger.error(f"Error sending email {email_id}: {e}")
            status = "failed"
            error_message = str(e)
        
        # Create email log
        email_log = EmailLog(
            email_id=email_id,
            branch_id=branch.branch_id,
            branch_name=branch.branch_name,
            recipient=branch.responsible_email,
            cc=cc or [],
            subject=subject,
            body=body,
            document_references=document_references,
            status=status,
            error_message=error_message,
            template_used=template_used
        )
        
        # Store in history
        self.email_history.append(email_log)
        
        logger.info(f"Email {email_id} status: {status}")
        
        return email_log
    
    def get_email_history(
        self,
        branch_id: Optional[str] = None,
        limit: int = 100
    ) -> List[EmailLog]:
        """
        Get email history
        
        Args:
            branch_id: Optional branch ID to filter by
            limit: Maximum number of records to return
            
        Returns:
            List of email logs
        """
        history = self.email_history
        
        if branch_id:
            history = [log for log in history if log.branch_id == branch_id]
        
        return history[-limit:]


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    from datetime import timedelta
    
    # Create agent
    agent = EmailAutomationAgent()
    
    # Example branch
    branch = Branch(
        branch_id="BR-001",
        branch_name="Sucursal Centro CDMX",
        state="Ciudad de México",
        municipality="Cuauhtémoc",
        region="Centro",
        responsible_email="responsable@empresa.com",
        manager_email="gerente@empresa.com",
        whatsapp_contact="+525512345678"
    )
    
    # Example 1: Expired document
    print("\n=== Expired Document Email ===")
    expired_doc = Document(
        document_id="DOC-001",
        branch_id="BR-001",
        document_name="Certificado Sanitario",
        document_type="certificate",
        issuing_authority="Secretaría de Salud",
        issue_date=date(2023, 1, 1),
        expiration_date=date(2024, 1, 1),
        status=DocumentStatus.EXPIRED,
        ocr_confidence=0.88,
        file_url="s3://docs/BR-001/cert.pdf"
    )
    
    email_log = agent.send_expired_document_email(branch, expired_doc)
    print(f"Email ID: {email_log.email_id}")
    print(f"Status: {email_log.status}")
    print(f"Subject: {email_log.subject}")
    
    # Example 2: Expiring soon
    print("\n=== Expiring Soon Email ===")
    expiring_doc = Document(
        document_id="DOC-002",
        branch_id="BR-001",
        document_name="Licencia de Funcionamiento",
        document_type="license",
        issuing_authority="Secretaría de Desarrollo Económico",
        issue_date=date(2024, 1, 1),
        expiration_date=date.today() + timedelta(days=12),
        status=DocumentStatus.CLOSE_TO_EXPIRATION,
        ocr_confidence=0.95,
        file_url="s3://docs/BR-001/lic.pdf"
    )
    
    email_log = agent.send_expiring_soon_email(branch, expiring_doc, UrgencyLevel.HIGH)
    print(f"Email ID: {email_log.email_id}")
    print(f"Status: {email_log.status}")
    print(f"Subject: {email_log.subject}")
    
    # Example 3: Missing document
    print("\n=== Missing Document Email ===")
    email_log = agent.send_missing_document_email(
        branch=branch,
        document_name="Permiso de Protección Civil",
        issuing_authority="Protección Civil CDMX",
        legal_category="safety",
        risk_level="high"
    )
    print(f"Email ID: {email_log.email_id}")
    print(f"Status: {email_log.status}")
    print(f"Subject: {email_log.subject}")

# Made with Bob