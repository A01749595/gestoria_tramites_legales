"""
Pydantic schemas for the Legal Compliance Multi-Agent System
Defines all data models for branches, documents, legal requirements, compliance results, alerts, and email logs
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, EmailStr, validator


# ============================================================================
# ENUMS
# ============================================================================

class DocumentStatus(str, Enum):
    """Document status enumeration"""
    VALID = "valid"
    CLOSE_TO_EXPIRATION = "close_to_expiration"
    EXPIRED = "expired"
    MISSING = "missing"
    UNREADABLE = "unreadable"
    INCOMPLETE = "incomplete"
    PENDING_REVIEW = "pending_review"


class UrgencyLevel(str, Enum):
    """Urgency level for actions"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LegalRiskLevel(str, Enum):
    """Legal risk level"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentType(str, Enum):
    """Agent types in the system"""
    DOCUMENT_MONITORING = "document_monitoring"
    REGULATORY_VALIDATION = "regulatory_validation"
    INTELLIGENT_ACTIVATION = "intelligent_activation"
    EMAIL_AUTOMATION = "email_automation"
    RENEWAL_ALERT = "renewal_alert"


class AlertType(str, Enum):
    """Alert types"""
    EXPIRATION_45_DAYS = "expiration_45_days"
    EXPIRATION_15_DAYS = "expiration_15_days"
    EXPIRATION_TODAY = "expiration_today"
    OVERDUE = "overdue"
    MISSING_DOCUMENT = "missing_document"


class AlertChannel(str, Enum):
    """Alert notification channels"""
    GOOGLE_CALENDAR = "google_calendar"
    MICROSOFT_TEAMS = "microsoft_teams"
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class AlertStatus(str, Enum):
    """Alert status"""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    ACKNOWLEDGED = "acknowledged"


# ============================================================================
# BRANCH MODEL
# ============================================================================

class Branch(BaseModel):
    """Branch information model"""
    branch_id: str = Field(..., description="Unique branch identifier")
    branch_name: str = Field(..., description="Branch name")
    state: str = Field(..., description="State where branch is located")
    municipality: str = Field(..., description="Municipality where branch is located")
    region: str = Field(..., description="Regional classification")
    responsible_email: EmailStr = Field(..., description="Email of responsible person")
    manager_email: EmailStr = Field(..., description="Email of branch manager")
    whatsapp_contact: str = Field(..., description="WhatsApp contact number")
    teams_channel: Optional[str] = Field(default=None, description="Microsoft Teams channel ID")
    address: Optional[str] = Field(default=None, description="Branch physical address")
    active: bool = Field(default=True, description="Whether branch is active")
    
    class Config:
        json_schema_extra = {
            "example": {
                "branch_id": "BR-001",
                "branch_name": "Sucursal Centro CDMX",
                "state": "Ciudad de México",
                "municipality": "Cuauhtémoc",
                "region": "Centro",
                "responsible_email": "responsable.centro@empresa.com",
                "manager_email": "gerente.centro@empresa.com",
                "whatsapp_contact": "+525512345678",
                "teams_channel": "19:abc123@thread.tacv2",
                "active": True
            }
        }


# ============================================================================
# DOCUMENT MODEL
# ============================================================================

class Document(BaseModel):
    """Document information model"""
    document_id: str = Field(..., description="Unique document identifier")
    branch_id: str = Field(..., description="Associated branch ID")
    document_name: str = Field(..., description="Document name")
    document_type: str = Field(..., description="Type of document (license, permit, certificate, etc.)")
    issuing_authority: str = Field(..., description="Authority that issued the document")
    issue_date: Optional[date] = Field(default=None, description="Date when document was issued")
    expiration_date: Optional[date] = Field(default=None, description="Document expiration date")
    status: DocumentStatus = Field(..., description="Current document status")
    ocr_confidence: float = Field(..., ge=0.0, le=1.0, description="OCR extraction confidence score")
    file_url: str = Field(..., description="URL or path to document file")
    folio_number: Optional[str] = Field(default=None, description="Document folio or permit number")
    extracted_text: Optional[str] = Field(default=None, description="Full OCR extracted text")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Record creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Record update timestamp")
    
    @validator('expiration_date')
    def validate_expiration_date(cls, v, values):
        """Validate that expiration date is after issue date"""
        if v and 'issue_date' in values and values['issue_date']:
            if v < values['issue_date']:
                raise ValueError('Expiration date must be after issue date')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "DOC-001-2024",
                "branch_id": "BR-001",
                "document_name": "Licencia de Funcionamiento",
                "document_type": "license",
                "issuing_authority": "Secretaría de Desarrollo Económico CDMX",
                "issue_date": "2024-01-15",
                "expiration_date": "2025-01-15",
                "status": "valid",
                "ocr_confidence": 0.95,
                "file_url": "s3://documents/BR-001/licencia_2024.pdf",
                "folio_number": "LIC-2024-001234"
            }
        }


# ============================================================================
# LEGAL REQUIREMENT MODEL
# ============================================================================

class LegalRequirement(BaseModel):
    """Legal requirement model for compliance matrix"""
    requirement_id: str = Field(..., description="Unique requirement identifier")
    state: str = Field(..., description="State where requirement applies")
    municipality: str = Field(..., description="Municipality where requirement applies")
    required_document: str = Field(..., description="Name of required document")
    legal_category: str = Field(..., description="Legal category (operational, health, safety, etc.)")
    renewal_period: int = Field(..., description="Renewal period in days")
    authority: str = Field(..., description="Issuing authority")
    mandatory: bool = Field(True, description="Whether document is mandatory")
    risk_level: LegalRiskLevel = Field(..., description="Risk level if not compliant")
    legal_reference: Optional[str] = Field(None, description="Legal reference or regulation number")
    description: Optional[str] = Field(None, description="Requirement description")
    
    class Config:
        json_schema_extra = {
            "example": {
                "requirement_id": "REQ-CDMX-001",
                "state": "Ciudad de México",
                "municipality": "Cuauhtémoc",
                "required_document": "Licencia de Funcionamiento",
                "legal_category": "operational",
                "renewal_period": 365,
                "authority": "Secretaría de Desarrollo Económico",
                "mandatory": True,
                "risk_level": "high",
                "legal_reference": "Ley de Establecimientos Mercantiles CDMX"
            }
        }


# ============================================================================
# COMPLIANCE RESULT MODEL
# ============================================================================

class ComplianceResult(BaseModel):
    """Compliance analysis result model"""
    branch_id: str = Field(..., description="Branch identifier")
    branch_name: str = Field(..., description="Branch name")
    state: str = Field(..., description="Branch state")
    municipality: str = Field(..., description="Branch municipality")
    compliance_score: float = Field(..., ge=0.0, le=100.0, description="Compliance score (0-100)")
    missing_documents: List[str] = Field(default_factory=list, description="List of missing documents")
    expired_documents: List[str] = Field(default_factory=list, description="List of expired documents")
    soon_to_expire_documents: List[Dict[str, Any]] = Field(
        default_factory=list, 
        description="Documents expiring soon with dates"
    )
    valid_documents: List[str] = Field(default_factory=list, description="List of valid documents")
    non_compliant_documents: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Documents that don't match requirements"
    )
    legal_risk_level: LegalRiskLevel = Field(..., description="Overall legal risk level")
    recommended_actions: List[str] = Field(default_factory=list, description="Recommended corrective actions")
    analysis_date: datetime = Field(default_factory=datetime.utcnow, description="Analysis timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "branch_id": "BR-001",
                "branch_name": "Sucursal Centro CDMX",
                "state": "Ciudad de México",
                "municipality": "Cuauhtémoc",
                "compliance_score": 75.0,
                "missing_documents": ["Permiso de Protección Civil"],
                "expired_documents": ["Certificado Sanitario"],
                "soon_to_expire_documents": [
                    {"document": "Licencia de Funcionamiento", "expiration_date": "2024-12-15", "days_remaining": 30}
                ],
                "valid_documents": ["Registro Patronal IMSS", "Alta en Hacienda"],
                "legal_risk_level": "medium",
                "recommended_actions": [
                    "Renovar Certificado Sanitario inmediatamente",
                    "Solicitar Permiso de Protección Civil"
                ]
            }
        }


# ============================================================================
# ROUTER DECISION MODEL
# ============================================================================

class RouterDecision(BaseModel):
    """Router agent decision output"""
    selected_agent: AgentType = Field(..., description="Selected agent for processing")
    reason_for_routing: str = Field(..., description="Explanation for routing decision")
    branch_id: str = Field(..., description="Branch identifier")
    branch_name: str = Field(..., description="Branch name")
    state: str = Field(..., description="Branch state")
    municipality: str = Field(..., description="Branch municipality")
    document_type: Optional[str] = Field(None, description="Document type being processed")
    detected_status: Optional[DocumentStatus] = Field(None, description="Detected document status")
    required_next_action: str = Field(..., description="Next action required")
    urgency_level: UrgencyLevel = Field(..., description="Urgency level")
    additional_context: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional context for the selected agent"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Decision timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "selected_agent": "regulatory_validation",
                "reason_for_routing": "Document uploaded requires validation against legal matrix",
                "branch_id": "BR-001",
                "branch_name": "Sucursal Centro CDMX",
                "state": "Ciudad de México",
                "municipality": "Cuauhtémoc",
                "document_type": "license",
                "detected_status": "valid",
                "required_next_action": "Validate compliance with municipal requirements",
                "urgency_level": "medium"
            }
        }


# ============================================================================
# ALERT MODEL
# ============================================================================

class Alert(BaseModel):
    """Alert model for renewal notifications"""
    alert_id: str = Field(..., description="Unique alert identifier")
    branch_id: str = Field(..., description="Associated branch ID")
    branch_name: str = Field(..., description="Branch name")
    document_name: str = Field(..., description="Document name")
    document_id: str = Field(..., description="Document identifier")
    expiration_date: date = Field(..., description="Document expiration date")
    alert_type: AlertType = Field(..., description="Type of alert")
    alert_date: datetime = Field(default_factory=datetime.utcnow, description="When alert was created")
    channel: AlertChannel = Field(..., description="Notification channel")
    status: AlertStatus = Field(default=AlertStatus.PENDING, description="Alert status")
    recipient: str = Field(..., description="Alert recipient")
    message: Optional[str] = Field(default=None, description="Alert message content")
    calendar_event_id: Optional[str] = Field(default=None, description="Google Calendar event ID")
    teams_message_id: Optional[str] = Field(default=None, description="Teams message ID")
    whatsapp_message_id: Optional[str] = Field(default=None, description="WhatsApp message ID")
    sent_at: Optional[datetime] = Field(default=None, description="When alert was sent")
    acknowledged_at: Optional[datetime] = Field(default=None, description="When alert was acknowledged")
    
    class Config:
        json_schema_extra = {
            "example": {
                "alert_id": "ALT-001-2024",
                "branch_id": "BR-001",
                "branch_name": "Sucursal Centro CDMX",
                "document_name": "Licencia de Funcionamiento",
                "document_id": "DOC-001-2024",
                "expiration_date": "2025-01-15",
                "alert_type": "expiration_45_days",
                "channel": "google_calendar",
                "status": "sent",
                "recipient": "responsable.centro@empresa.com"
            }
        }


# ============================================================================
# EMAIL LOG MODEL
# ============================================================================

class EmailLog(BaseModel):
    """Email log model for audit trail"""
    email_id: str = Field(..., description="Unique email identifier")
    branch_id: str = Field(..., description="Associated branch ID")
    branch_name: str = Field(..., description="Branch name")
    recipient: EmailStr = Field(..., description="Email recipient")
    cc: Optional[List[EmailStr]] = Field(default_factory=list, description="CC recipients")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body content")
    document_references: List[str] = Field(default_factory=list, description="Referenced document IDs")
    sent_at: datetime = Field(default_factory=datetime.utcnow, description="When email was sent")
    status: str = Field(..., description="Email delivery status")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    template_used: Optional[str] = Field(None, description="Email template identifier")
    
    class Config:
        json_schema_extra = {
            "example": {
                "email_id": "EMAIL-001-2024",
                "branch_id": "BR-001",
                "branch_name": "Sucursal Centro CDMX",
                "recipient": "responsable.centro@empresa.com",
                "cc": ["gerente.centro@empresa.com"],
                "subject": "Action Required: Missing Compliance Document",
                "body": "Dear team, please upload the missing Permiso de Protección Civil...",
                "document_references": ["DOC-001-2024"],
                "status": "sent"
            }
        }


# ============================================================================
# OCR INPUT MODEL
# ============================================================================

class OCRInput(BaseModel):
    """OCR input model for document processing"""
    document_id: str = Field(..., description="Document identifier")
    branch_id: str = Field(..., description="Branch identifier")
    file_url: str = Field(..., description="Document file URL")
    file_type: str = Field(..., description="File type (pdf, jpg, png, etc.)")
    ocr_provider: str = Field(..., description="OCR provider used")
    
    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "DOC-001-2024",
                "branch_id": "BR-001",
                "file_url": "s3://documents/BR-001/licencia_2024.pdf",
                "file_type": "pdf",
                "ocr_provider": "azure_document_intelligence"
            }
        }


class OCROutput(BaseModel):
    """OCR output model with extracted data"""
    document_id: str = Field(..., description="Document identifier")
    extracted_text: str = Field(..., description="Full extracted text")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence score")
    extracted_fields: Dict[str, Any] = Field(default_factory=dict, description="Structured extracted fields")
    document_name: Optional[str] = Field(default=None, description="Detected document name")
    issuing_authority: Optional[str] = Field(default=None, description="Detected issuing authority")
    issue_date: Optional[str] = Field(default=None, description="Detected issue date")
    expiration_date: Optional[str] = Field(default=None, description="Detected expiration date")
    folio_number: Optional[str] = Field(default=None, description="Detected folio number")
    processing_time: float = Field(..., description="OCR processing time in seconds")
    
    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "DOC-001-2024",
                "extracted_text": "LICENCIA DE FUNCIONAMIENTO...",
                "confidence": 0.95,
                "extracted_fields": {
                    "document_name": "Licencia de Funcionamiento",
                    "folio": "LIC-2024-001234",
                    "expiration": "15/01/2025"
                },
                "processing_time": 2.5
            }
        }


# ============================================================================
# WORKFLOW MODELS
# ============================================================================

class WorkflowRequest(BaseModel):
    """Workflow execution request"""
    request_id: str = Field(..., description="Unique request identifier")
    branch_id: str = Field(..., description="Branch identifier")
    document_id: Optional[str] = Field(None, description="Document identifier if applicable")
    workflow_type: str = Field(..., description="Type of workflow to execute")
    input_data: Dict[str, Any] = Field(..., description="Input data for workflow")
    priority: UrgencyLevel = Field(default=UrgencyLevel.MEDIUM, description="Workflow priority")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Request creation time")


class WorkflowResult(BaseModel):
    """Workflow execution result"""
    request_id: str = Field(..., description="Request identifier")
    workflow_type: str = Field(..., description="Workflow type executed")
    status: str = Field(..., description="Execution status")
    agents_executed: List[AgentType] = Field(default_factory=list, description="Agents that were executed")
    actions_taken: List[str] = Field(default_factory=list, description="Actions performed")
    compliance_result: Optional[ComplianceResult] = Field(None, description="Compliance analysis result")
    alerts_created: List[str] = Field(default_factory=list, description="Alert IDs created")
    emails_sent: List[str] = Field(default_factory=list, description="Email IDs sent")
    errors: List[str] = Field(default_factory=list, description="Errors encountered")
    execution_time: float = Field(..., description="Total execution time in seconds")
    completed_at: datetime = Field(default_factory=datetime.utcnow, description="Completion timestamp")


# ============================================================================
# DASHBOARD MODELS
# ============================================================================

class DashboardSummary(BaseModel):
    """Dashboard summary statistics"""
    total_branches: int = Field(..., description="Total number of branches monitored")
    compliant_branches: int = Field(..., description="Number of compliant branches")
    branches_with_missing_docs: int = Field(..., description="Branches with missing documents")
    branches_with_expired_docs: int = Field(..., description="Branches with expired documents")
    branches_expiring_45_days: int = Field(..., description="Branches with docs expiring in 45 days")
    branches_expiring_15_days: int = Field(..., description="Branches with docs expiring in 15 days")
    average_compliance_score: float = Field(..., description="Average compliance score across all branches")
    high_risk_branches: int = Field(..., description="Number of high-risk branches")
    critical_risk_branches: int = Field(..., description="Number of critical-risk branches")
    total_alerts_pending: int = Field(..., description="Total pending alerts")
    total_emails_sent_today: int = Field(..., description="Emails sent today")
    last_updated: datetime = Field(default_factory=datetime.utcnow, description="Last update timestamp")


class BranchComplianceStatus(BaseModel):
    """Individual branch compliance status for dashboard"""
    branch_id: str
    branch_name: str
    state: str
    municipality: str
    compliance_score: float
    status: str  # "compliant", "at_risk", "non_compliant"
    missing_count: int
    expired_count: int
    expiring_soon_count: int
    valid_count: int
    risk_level: LegalRiskLevel
    last_checked: datetime


class ComplianceReport(BaseModel):
    """Compliance report model"""
    report_id: str = Field(..., description="Unique report identifier")
    report_type: str = Field(..., description="Type of report")
    start_date: Optional[date] = Field(None, description="Report start date")
    end_date: Optional[date] = Field(None, description="Report end date")
    branches: List[BranchComplianceStatus] = Field(default_factory=list, description="Branch compliance statuses")
    summary: DashboardSummary = Field(..., description="Summary statistics")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="Report generation timestamp")
    generated_by: Optional[str] = Field(None, description="User who generated the report")

# Made with Bob
