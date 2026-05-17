"""
Compliance Workflow - Orchestrates the complete compliance checking process
Integrates all agents and services for end-to-end document compliance management
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

from agents.router_agent import RouterAgent
from agents.document_monitoring_agent import DocumentMonitoringAgent
from agents.regulatory_validation_agent import RegulatoryValidationAgent
from agents.intelligent_activation_agent import IntelligentActivationAgent
from agents.email_automation_agent import EmailAutomationAgent
from agents.renewal_alert_agent import RenewalAlertAgent

from services.ocr_service import OCRService
from services.email_service import EmailService
from services.calendar_service import CalendarService
from services.teams_service import TeamsService
from services.whatsapp_service import WhatsAppService

from schemas.schemas import Branch, Document, LegalRequirement

logger = logging.getLogger(__name__)


class ComplianceWorkflow:
    """
    Main workflow orchestrator for the compliance system.
    Coordinates all agents and services to process documents and ensure compliance.
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        supabase_bucket=None,
    ):
        """
        Args:
            config: dict de configuración (de config.get_config()).
            supabase_bucket: bucket para que el OCR lea PDFs por path.
        """
        self.config = config or {}
        ocr_cfg = self.config.get("ocr", {}) or {}
        email_cfg = self.config.get("email", {}) or {}
        cal_cfg = self.config.get("calendar", {}) or {}
        teams_cfg = self.config.get("teams", {}) or {}
        wa_cfg = self.config.get("whatsapp", {}) or {}

        # OCR híbrido: Azure Document Intelligence con fallback a PyMuPDF
        self.ocr_service = OCRService(
            provider=ocr_cfg.get("provider", "azure"),
            api_key=ocr_cfg.get("azure_key"),
            endpoint=ocr_cfg.get("azure_endpoint"),
            supabase_bucket=supabase_bucket,
            fallback_to_pymupdf=ocr_cfg.get("fallback_to_pymupdf", True),
        )
        self.email_service = EmailService(
            smtp_host=email_cfg.get("smtp_host", "smtp.gmail.com"),
            smtp_port=email_cfg.get("smtp_port", 587),
            username=email_cfg.get("smtp_username"),
            password=email_cfg.get("smtp_password"),
            from_email=email_cfg.get("from_email"),
            use_tls=email_cfg.get("use_tls", True),
            use_ssl=email_cfg.get("use_ssl", False),
        )
        self.calendar_service = CalendarService(
            credentials_path=cal_cfg.get("google_credentials_path"),
            calendar_id=cal_cfg.get("calendar_id", "primary"),
            default_timezone=cal_cfg.get("timezone", "America/Mexico_City"),
        )
        self.teams_service = TeamsService(
            webhook_url=teams_cfg.get("webhook_url"),
        )
        self.whatsapp_service = WhatsAppService(
            account_sid=wa_cfg.get("twilio_account_sid"),
            auth_token=wa_cfg.get("twilio_auth_token"),
            from_number=wa_cfg.get("twilio_whatsapp_number"),
        )
        
        # Initialize agents
        self.router_agent = RouterAgent()
        self.document_monitoring_agent = DocumentMonitoringAgent()
        self.regulatory_validation_agent = RegulatoryValidationAgent()
        self.email_automation_agent = EmailAutomationAgent(self.email_service)
        self.renewal_alert_agent = RenewalAlertAgent(
            calendar_service=self.calendar_service,
            teams_service=self.teams_service,
            whatsapp_service=self.whatsapp_service,
            email_service=self.email_service
        )
        self.intelligent_activation_agent = IntelligentActivationAgent(
            document_monitoring_agent=self.document_monitoring_agent,
            regulatory_validation_agent=self.regulatory_validation_agent,
            email_automation_agent=self.email_automation_agent,
            renewal_alert_agent=self.renewal_alert_agent
        )
        
        logger.info("Compliance Workflow initialized")
    
    def process_document_upload(
        self,
        branch: Branch,
        file_path: str,
        document_type: str
    ) -> Dict[str, Any]:
        """
        Process a newly uploaded document
        
        Args:
            branch: Branch information
            file_path: Path to uploaded document
            document_type: Type of document
            
        Returns:
            Processing result with compliance status
        """
        logger.info(f"Processing document upload for branch {branch.branch_id}")
        
        workflow_result = {
            "workflow_id": f"WF-UPLOAD-{branch.branch_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "branch_id": branch.branch_id,
            "file_path": file_path,
            "steps": [],
            "started_at": datetime.utcnow().isoformat()
        }
        
        try:
            # Step 1: OCR extraction
            logger.info("Step 1: OCR extraction")
            ocr_result = self.ocr_service.extract_text(file_path, document_type)
            workflow_result["steps"].append({
                "step": "ocr_extraction",
                "status": "completed",
                "confidence": ocr_result.get("confidence", 0)
            })
            
            # Step 2: Create document record (simulated)
            logger.info("Step 2: Create document record")
            from schemas.schemas import Document, DocumentStatus, OCROutput
            from datetime import date
            
            # Parse extracted fields
            fields = ocr_result.get("fields", {})
            
            document = Document(
                document_id=f"DOC-{branch.branch_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                branch_id=branch.branch_id,
                document_name=fields.get("establishment", "Documento"),
                document_type=document_type,
                issuing_authority=fields.get("authority", "Autoridad"),
                issue_date=date.today(),
                expiration_date=None,  # Would be parsed from OCR
                status=DocumentStatus.VALID,
                ocr_confidence=ocr_result.get("confidence", 0),
                file_url=file_path,
                extracted_text=ocr_result.get("text", "")
            )
            
            ocr_output = OCROutput(
                document_id=document.document_id,
                extracted_text=ocr_result.get("text", ""),
                confidence=ocr_result.get("confidence", 0),
                extracted_fields=fields,
                processing_time=ocr_result.get("processing_time", 0)
            )
            
            workflow_result["steps"].append({
                "step": "document_creation",
                "status": "completed",
                "document_id": document.document_id
            })
            
            # Step 3: Route to appropriate agent
            logger.info("Step 3: Route to appropriate agent")
            router_decision = self.router_agent.route_request(
                request_type="document_upload",
                branch=branch,
                document=document,
                ocr_output=ocr_output
            )
            
            workflow_result["steps"].append({
                "step": "routing",
                "status": "completed",
                "selected_agent": router_decision.selected_agent.value,
                "urgency": router_decision.urgency_level.value
            })
            
            # Step 4: Execute agent workflow
            logger.info("Step 4: Execute agent workflow")
            execution_result = self.intelligent_activation_agent.execute_workflow(
                router_decision=router_decision,
                branch=branch,
                documents=[document]
            )
            
            workflow_result["steps"].append({
                "step": "agent_execution",
                "status": "completed",
                "agents_executed": execution_result.get("agents_executed", []),
                "actions_taken": execution_result.get("actions_taken", [])
            })
            
            workflow_result["status"] = "completed"
            workflow_result["result"] = execution_result
            
        except Exception as e:
            logger.error(f"Workflow error: {e}")
            workflow_result["status"] = "failed"
            workflow_result["error"] = str(e)
        
        workflow_result["completed_at"] = datetime.utcnow().isoformat()
        return workflow_result
    
    def check_branch_compliance(
        self,
        branch: Branch,
        documents: List[Document],
        legal_requirements: List[LegalRequirement]
    ) -> Dict[str, Any]:
        """
        Check compliance for a branch
        
        Args:
            branch: Branch to check
            documents: Branch documents
            legal_requirements: Applicable legal requirements
            
        Returns:
            Compliance check result
        """
        logger.info(f"Checking compliance for branch {branch.branch_id}")
        
        # Load legal matrix
        self.regulatory_validation_agent.load_legal_matrix(legal_requirements)
        
        # Monitor documents
        monitoring_report = self.document_monitoring_agent.monitor_branch_documents(
            branch, documents
        )
        
        # Validate compliance
        compliance_result = self.regulatory_validation_agent.validate_branch_compliance(
            branch, documents
        )
        
        # Route based on compliance
        router_decision = self.router_agent.route_request(
            request_type="compliance_check",
            branch=branch,
            additional_context={
                "compliance_score": compliance_result.compliance_score,
                "risk_level": compliance_result.legal_risk_level.value
            }
        )
        
        # Execute workflow if needed
        if router_decision.urgency_level.value in ["high", "critical"]:
            execution_result = self.intelligent_activation_agent.execute_workflow(
                router_decision=router_decision,
                branch=branch,
                documents=documents
            )
        else:
            execution_result = None
        
        return {
            "branch_id": branch.branch_id,
            "monitoring_report": monitoring_report,
            "compliance_result": compliance_result.dict(),
            "router_decision": router_decision.dict(),
            "execution_result": execution_result,
            "checked_at": datetime.utcnow().isoformat()
        }
    
    def process_batch_branches(
        self,
        branches_data: List[Dict[str, Any]],
        legal_requirements: List[LegalRequirement]
    ) -> Dict[str, Any]:
        """
        Process compliance check for multiple branches
        
        Args:
            branches_data: List of branch data with documents
            legal_requirements: Legal requirements matrix
            
        Returns:
            Batch processing summary
        """
        logger.info(f"Processing batch of {len(branches_data)} branches")
        
        # Load legal matrix
        self.regulatory_validation_agent.load_legal_matrix(legal_requirements)
        
        results = []
        for branch_data in branches_data:
            try:
                result = self.check_branch_compliance(
                    branch=branch_data["branch"],
                    documents=branch_data["documents"],
                    legal_requirements=legal_requirements
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing branch {branch_data['branch'].branch_id}: {e}")
                results.append({
                    "branch_id": branch_data["branch"].branch_id,
                    "status": "error",
                    "error": str(e)
                })
        
        # Generate summary
        summary = {
            "total_branches": len(branches_data),
            "successful": len([r for r in results if r.get("status") != "error"]),
            "failed": len([r for r in results if r.get("status") == "error"]),
            "results": results,
            "processed_at": datetime.utcnow().isoformat()
        }
        
        return summary


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create workflow
    workflow = ComplianceWorkflow()
    
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
    
    # Process document upload
    print("\n=== Processing Document Upload ===")
    result = workflow.process_document_upload(
        branch=branch,
        file_path="s3://docs/licencia_funcionamiento.pdf",
        document_type="license"
    )
    print(f"Workflow ID: {result['workflow_id']}")
    print(f"Status: {result['status']}")
    print(f"Steps completed: {len(result['steps'])}")

# Made with Bob