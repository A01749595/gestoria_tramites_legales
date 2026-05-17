"""
Router Agent - Central decision maker for the compliance system
Analyzes incoming requests and routes to appropriate specialized agents
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional
import logging
from schemas.schemas import (
    RouterDecision, AgentType, UrgencyLevel, DocumentStatus,
    OCROutput, Branch, Document
)

logger = logging.getLogger(__name__)


class RouterAgent:
    """
    Central router agent responsible for analyzing incoming requests and routing
    to the appropriate specialized agent based on document metadata, OCR results,
    branch information, and compliance status.
    """
    
    def __init__(self, llm_client=None):
        """
        Initialize the Router Agent
        
        Args:
            llm_client: Optional LLM client for advanced routing decisions
        """
        self.llm_client = llm_client
        self.routing_rules = self._initialize_routing_rules()
        logger.info("Router Agent initialized")
    
    def _initialize_routing_rules(self) -> Dict[str, Any]:
        """Initialize routing rules and decision criteria"""
        return {
            "document_upload": {
                "primary_agent": AgentType.DOCUMENT_MONITORING,
                "secondary_agents": [AgentType.REGULATORY_VALIDATION]
            },
            "compliance_check": {
                "primary_agent": AgentType.REGULATORY_VALIDATION,
                "secondary_agents": [AgentType.INTELLIGENT_ACTIVATION]
            },
            "expiration_alert": {
                "primary_agent": AgentType.RENEWAL_ALERT,
                "secondary_agents": []
            },
            "missing_document": {
                "primary_agent": AgentType.EMAIL_AUTOMATION,
                "secondary_agents": [AgentType.RENEWAL_ALERT]
            },
            "expired_document": {
                "primary_agent": AgentType.EMAIL_AUTOMATION,
                "secondary_agents": [AgentType.RENEWAL_ALERT]
            }
        }
    
    def route_request(
        self,
        request_type: str,
        branch: Branch,
        document: Optional[Document] = None,
        ocr_output: Optional[OCROutput] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> RouterDecision:
        """
        Main routing method - analyzes request and determines which agent should handle it
        
        Args:
            request_type: Type of request (document_upload, compliance_check, etc.)
            branch: Branch information
            document: Document information if applicable
            ocr_output: OCR extraction results if applicable
            additional_context: Additional context for routing decision
            
        Returns:
            RouterDecision with selected agent and routing details
        """
        logger.info(f"Routing request type '{request_type}' for branch {branch.branch_id}")
        
        # Analyze the request context
        analysis = self._analyze_request_context(
            request_type, branch, document, ocr_output, additional_context
        )
        
        # Determine urgency level
        urgency = self._determine_urgency(document, analysis)
        
        # Select appropriate agent
        selected_agent = self._select_agent(request_type, analysis, urgency)
        
        # Generate routing reason
        reason = self._generate_routing_reason(
            selected_agent, request_type, analysis, urgency
        )
        
        # Determine next action
        next_action = self._determine_next_action(selected_agent, analysis)
        
        # Build router decision
        decision = RouterDecision(
            selected_agent=selected_agent,
            reason_for_routing=reason,
            branch_id=branch.branch_id,
            branch_name=branch.branch_name,
            state=branch.state,
            municipality=branch.municipality,
            document_type=document.document_type if document else None,
            detected_status=document.status if document else None,
            required_next_action=next_action,
            urgency_level=urgency,
            additional_context=analysis
        )
        
        logger.info(
            f"Routed to {selected_agent.value} with urgency {urgency.value} "
            f"for branch {branch.branch_id}"
        )
        
        return decision
    
    def _analyze_request_context(
        self,
        request_type: str,
        branch: Branch,
        document: Optional[Document],
        ocr_output: Optional[OCROutput],
        additional_context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Analyze the full context of the request"""
        analysis = {
            "request_type": request_type,
            "has_document": document is not None,
            "has_ocr": ocr_output is not None,
            "branch_active": branch.active
        }
        
        if document:
            analysis.update({
                "document_status": document.status.value,
                "has_expiration": document.expiration_date is not None,
                "ocr_confidence": document.ocr_confidence,
                "low_confidence": document.ocr_confidence < 0.7
            })
            
            # Check expiration status
            if document.expiration_date:
                days_to_expiration = (document.expiration_date - date.today()).days
                analysis.update({
                    "days_to_expiration": days_to_expiration,
                    "expired": days_to_expiration < 0,
                    "expiring_soon_45": 0 <= days_to_expiration <= 45,
                    "expiring_soon_15": 0 <= days_to_expiration <= 15
                })
        
        if ocr_output:
            analysis.update({
                "ocr_confidence": ocr_output.confidence,
                "fields_extracted": len(ocr_output.extracted_fields),
                "has_expiration_date": ocr_output.expiration_date is not None
            })
        
        if additional_context:
            analysis.update(additional_context)
        
        return analysis
    
    def _determine_urgency(
        self,
        document: Optional[Document],
        analysis: Dict[str, Any]
    ) -> UrgencyLevel:
        """Determine urgency level based on document status and context"""
        
        # Critical: Expired documents or very low OCR confidence
        if analysis.get("expired", False):
            return UrgencyLevel.CRITICAL
        
        if analysis.get("low_confidence", False) and analysis.get("ocr_confidence", 1.0) < 0.5:
            return UrgencyLevel.CRITICAL
        
        # High: Documents expiring within 15 days or missing mandatory documents
        if analysis.get("expiring_soon_15", False):
            return UrgencyLevel.HIGH
        
        if document and document.status == DocumentStatus.MISSING:
            return UrgencyLevel.HIGH
        
        # Medium: Documents expiring within 45 days or low OCR confidence
        if analysis.get("expiring_soon_45", False):
            return UrgencyLevel.MEDIUM
        
        if analysis.get("low_confidence", False):
            return UrgencyLevel.MEDIUM
        
        # Low: Everything else
        return UrgencyLevel.LOW
    
    def _select_agent(
        self,
        request_type: str,
        analysis: Dict[str, Any],
        urgency: UrgencyLevel
    ) -> AgentType:
        """Select the appropriate agent based on request type and analysis"""
        
        # Handle document upload scenarios
        if request_type == "document_upload":
            if analysis.get("low_confidence", False):
                # Low confidence OCR needs monitoring first
                return AgentType.DOCUMENT_MONITORING
            else:
                # Good OCR goes to validation
                return AgentType.REGULATORY_VALIDATION
        
        # Handle compliance check requests
        if request_type == "compliance_check":
            return AgentType.REGULATORY_VALIDATION
        
        # Handle missing documents
        if request_type == "missing_document" or analysis.get("document_status") == "missing":
            return AgentType.EMAIL_AUTOMATION
        
        # Handle expired documents
        if request_type == "expired_document" or analysis.get("expired", False):
            # Critical urgency goes to activation agent for orchestration
            if urgency == UrgencyLevel.CRITICAL:
                return AgentType.INTELLIGENT_ACTIVATION
            else:
                return AgentType.EMAIL_AUTOMATION
        
        # Handle expiration alerts
        if analysis.get("expiring_soon_45", False) or analysis.get("expiring_soon_15", False):
            return AgentType.RENEWAL_ALERT
        
        # Handle scheduled renewals
        if request_type == "renewal_alert":
            return AgentType.RENEWAL_ALERT
        
        # Handle manual review requests
        if request_type == "manual_review":
            return AgentType.DOCUMENT_MONITORING
        
        # Default to intelligent activation for complex scenarios
        if urgency in [UrgencyLevel.HIGH, UrgencyLevel.CRITICAL]:
            return AgentType.INTELLIGENT_ACTIVATION
        
        # Default fallback
        return AgentType.DOCUMENT_MONITORING
    
    def _generate_routing_reason(
        self,
        selected_agent: AgentType,
        request_type: str,
        analysis: Dict[str, Any],
        urgency: UrgencyLevel
    ) -> str:
        """Generate human-readable reason for routing decision"""
        
        reasons = []
        
        # Add request type context
        reasons.append(f"Request type: {request_type}")
        
        # Add document status context
        if "document_status" in analysis:
            reasons.append(f"Document status: {analysis['document_status']}")
        
        # Add expiration context
        if analysis.get("expired"):
            reasons.append("Document is expired - immediate action required")
        elif analysis.get("expiring_soon_15"):
            days = analysis.get("days_to_expiration", 0)
            reasons.append(f"Document expiring in {days} days - urgent renewal needed")
        elif analysis.get("expiring_soon_45"):
            days = analysis.get("days_to_expiration", 0)
            reasons.append(f"Document expiring in {days} days - renewal alert scheduled")
        
        # Add OCR confidence context
        if analysis.get("low_confidence"):
            confidence = analysis.get("ocr_confidence", 0)
            reasons.append(f"Low OCR confidence ({confidence:.2%}) - requires monitoring")
        
        # Add urgency context
        reasons.append(f"Urgency level: {urgency.value}")
        
        # Add agent-specific reasoning
        if selected_agent == AgentType.DOCUMENT_MONITORING:
            reasons.append("Routing to Document Monitoring for status classification")
        elif selected_agent == AgentType.REGULATORY_VALIDATION:
            reasons.append("Routing to Regulatory Validation for compliance check")
        elif selected_agent == AgentType.INTELLIGENT_ACTIVATION:
            reasons.append("Routing to Intelligent Activation for orchestrated response")
        elif selected_agent == AgentType.EMAIL_AUTOMATION:
            reasons.append("Routing to Email Automation for notification generation")
        elif selected_agent == AgentType.RENEWAL_ALERT:
            reasons.append("Routing to Renewal Alert for calendar and notification scheduling")
        
        return " | ".join(reasons)
    
    def _determine_next_action(
        self,
        selected_agent: AgentType,
        analysis: Dict[str, Any]
    ) -> str:
        """Determine the next action required based on selected agent"""
        
        if selected_agent == AgentType.DOCUMENT_MONITORING:
            if analysis.get("low_confidence"):
                return "Extract and validate document fields, request manual review if needed"
            return "Monitor document status and extract metadata"
        
        elif selected_agent == AgentType.REGULATORY_VALIDATION:
            return "Validate document against legal requirements matrix for state and municipality"
        
        elif selected_agent == AgentType.INTELLIGENT_ACTIVATION:
            if analysis.get("expired"):
                return "Execute multi-agent workflow: send notifications, create alerts, escalate to management"
            return "Orchestrate appropriate subagents based on compliance analysis"
        
        elif selected_agent == AgentType.EMAIL_AUTOMATION:
            if analysis.get("document_status") == "missing":
                return "Generate and send email notification for missing document"
            elif analysis.get("expired"):
                return "Generate and send urgent email notification for expired document"
            return "Generate and send email notification to responsible parties"
        
        elif selected_agent == AgentType.RENEWAL_ALERT:
            days = analysis.get("days_to_expiration", 0)
            if days <= 15:
                return f"Create high-priority renewal alert ({days} days remaining) across all channels"
            elif days <= 45:
                return f"Create renewal alert ({days} days remaining) and schedule calendar event"
            return "Schedule renewal alert and create calendar event"
        
        return "Process request according to agent capabilities"
    
    def route_batch_requests(
        self,
        requests: list[Dict[str, Any]]
    ) -> list[RouterDecision]:
        """
        Route multiple requests in batch
        
        Args:
            requests: List of request dictionaries with branch, document, etc.
            
        Returns:
            List of RouterDecision objects
        """
        decisions = []
        
        for req in requests:
            try:
                decision = self.route_request(
                    request_type=req.get("request_type", "document_upload"),
                    branch=req["branch"],
                    document=req.get("document"),
                    ocr_output=req.get("ocr_output"),
                    additional_context=req.get("additional_context")
                )
                decisions.append(decision)
            except Exception as e:
                logger.error(f"Error routing request for branch {req.get('branch', {}).get('branch_id')}: {e}")
                continue
        
        logger.info(f"Batch routed {len(decisions)} out of {len(requests)} requests")
        return decisions
    
    def get_routing_statistics(self) -> Dict[str, Any]:
        """Get statistics about routing decisions (for monitoring)"""
        # This would typically query a database or cache
        # Placeholder implementation
        return {
            "total_requests_routed": 0,
            "agents_usage": {
                agent.value: 0 for agent in AgentType
            },
            "urgency_distribution": {
                level.value: 0 for level in UrgencyLevel
            }
        }


# Example usage and testing
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create router instance
    router = RouterAgent()
    
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
    
    # Example 1: New document upload with good OCR
    print("\n=== Example 1: Document Upload (Good OCR) ===")
    document1 = Document(
        document_id="DOC-001",
        branch_id="BR-001",
        document_name="Licencia de Funcionamiento",
        document_type="license",
        issuing_authority="Secretaría de Desarrollo Económico",
        issue_date=date(2024, 1, 15),
        expiration_date=date(2025, 1, 15),
        status=DocumentStatus.VALID,
        ocr_confidence=0.95,
        file_url="s3://docs/BR-001/lic.pdf"
    )
    
    decision1 = router.route_request(
        request_type="document_upload",
        branch=branch,
        document=document1
    )
    print(f"Selected Agent: {decision1.selected_agent.value}")
    print(f"Urgency: {decision1.urgency_level.value}")
    print(f"Reason: {decision1.reason_for_routing}")
    print(f"Next Action: {decision1.required_next_action}")
    
    # Example 2: Expired document
    print("\n=== Example 2: Expired Document ===")
    document2 = Document(
        document_id="DOC-002",
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
    
    decision2 = router.route_request(
        request_type="expired_document",
        branch=branch,
        document=document2
    )
    print(f"Selected Agent: {decision2.selected_agent.value}")
    print(f"Urgency: {decision2.urgency_level.value}")
    print(f"Reason: {decision2.reason_for_routing}")
    print(f"Next Action: {decision2.required_next_action}")
    
    # Example 3: Document expiring soon (15 days)
    print("\n=== Example 3: Document Expiring Soon ===")
    document3 = Document(
        document_id="DOC-003",
        branch_id="BR-001",
        document_name="Permiso de Protección Civil",
        document_type="permit",
        issuing_authority="Protección Civil",
        issue_date=date(2024, 1, 1),
        expiration_date=date.today() + timedelta(days=12),
        status=DocumentStatus.CLOSE_TO_EXPIRATION,
        ocr_confidence=0.92,
        file_url="s3://docs/BR-001/perm.pdf"
    )
    
    decision3 = router.route_request(
        request_type="document_upload",
        branch=branch,
        document=document3
    )
    print(f"Selected Agent: {decision3.selected_agent.value}")
    print(f"Urgency: {decision3.urgency_level.value}")
    print(f"Reason: {decision3.reason_for_routing}")
    print(f"Next Action: {decision3.required_next_action}")

# Made with Bob
