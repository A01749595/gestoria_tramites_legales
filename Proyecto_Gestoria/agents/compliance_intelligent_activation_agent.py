"""
Intelligent Activation Agent - Orchestrates multi-agent workflows
Coordinates actions across document monitoring, validation, email, and alert agents
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
import logging
from schemas.schemas import (
    Branch, Document, ComplianceResult, RouterDecision,
    UrgencyLevel, DocumentStatus, AgentType, LegalRiskLevel
)

logger = logging.getLogger(__name__)


class IntelligentActivationAgent:
    """
    Agent responsible for orchestrating complex workflows across multiple agents.
    Activates appropriate subagents based on compliance status and urgency.
    """
    
    def __init__(
        self,
        document_monitoring_agent=None,
        regulatory_validation_agent=None,
        email_automation_agent=None,
        renewal_alert_agent=None
    ):
        """
        Initialize the Intelligent Activation Agent
        
        Args:
            document_monitoring_agent: Document monitoring agent instance
            regulatory_validation_agent: Regulatory validation agent instance
            email_automation_agent: Email automation agent instance
            renewal_alert_agent: Renewal alert agent instance
        """
        self.document_monitoring_agent = document_monitoring_agent
        self.regulatory_validation_agent = regulatory_validation_agent
        self.email_automation_agent = email_automation_agent
        self.renewal_alert_agent = renewal_alert_agent
        self.execution_history = []
        logger.info("Intelligent Activation Agent initialized")
    
    def execute_workflow(
        self,
        router_decision: RouterDecision,
        branch: Branch,
        documents: List[Document],
        additional_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute a complete workflow based on router decision
        
        Args:
            router_decision: Decision from router agent
            branch: Branch information
            documents: List of documents for the branch
            additional_context: Additional context for workflow
            
        Returns:
            Dictionary with workflow execution results
        """
        logger.info(
            f"Executing workflow for branch {branch.branch_id}, "
            f"urgency: {router_decision.urgency_level.value}"
        )
        
        workflow_id = f"WF-{branch.branch_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        start_time = datetime.utcnow()
        
        # Initialize workflow result
        result = {
            "workflow_id": workflow_id,
            "branch_id": branch.branch_id,
            "branch_name": branch.branch_name,
            "urgency_level": router_decision.urgency_level.value,
            "agents_executed": [],
            "actions_taken": [],
            "alerts_created": [],
            "emails_sent": [],
            "errors": [],
            "started_at": start_time.isoformat()
        }
        
        try:
            # Execute workflow based on urgency and status
            if router_decision.urgency_level == UrgencyLevel.CRITICAL:
                self._execute_critical_workflow(result, branch, documents, router_decision)
            elif router_decision.urgency_level == UrgencyLevel.HIGH:
                self._execute_high_priority_workflow(result, branch, documents, router_decision)
            elif router_decision.urgency_level == UrgencyLevel.MEDIUM:
                self._execute_medium_priority_workflow(result, branch, documents, router_decision)
            else:
                self._execute_standard_workflow(result, branch, documents, router_decision)
            
            result["status"] = "completed"
            
        except Exception as e:
            logger.error(f"Workflow execution error: {e}")
            result["status"] = "failed"
            result["errors"].append(str(e))
        
        # Calculate execution time
        end_time = datetime.utcnow()
        result["completed_at"] = end_time.isoformat()
        result["execution_time_seconds"] = (end_time - start_time).total_seconds()
        
        # Store in history
        self.execution_history.append(result)
        
        logger.info(
            f"Workflow {workflow_id} completed: {result['status']}, "
            f"agents: {len(result['agents_executed'])}, "
            f"actions: {len(result['actions_taken'])}"
        )
        
        return result
    
    def _execute_critical_workflow(
        self,
        result: Dict[str, Any],
        branch: Branch,
        documents: List[Document],
        router_decision: RouterDecision
    ):
        """Execute workflow for critical urgency situations"""
        logger.info(f"Executing CRITICAL workflow for branch {branch.branch_id}")
        
        # 1. Monitor all documents
        if self.document_monitoring_agent:
            monitoring_report = self.document_monitoring_agent.monitor_branch_documents(
                branch, documents
            )
            result["agents_executed"].append(AgentType.DOCUMENT_MONITORING.value)
            result["actions_taken"].append("Monitored all branch documents")
            result["monitoring_report"] = monitoring_report
        
        # 2. Validate compliance
        if self.regulatory_validation_agent:
            compliance_result = self.regulatory_validation_agent.validate_branch_compliance(
                branch, documents
            )
            result["agents_executed"].append(AgentType.REGULATORY_VALIDATION.value)
            result["actions_taken"].append("Validated regulatory compliance")
            result["compliance_result"] = compliance_result.dict()
        
        # 3. Send urgent emails for expired/missing documents
        if self.email_automation_agent:
            expired_docs = [d for d in documents if d.status == DocumentStatus.EXPIRED]
            for doc in expired_docs:
                email_result = self._send_urgent_email(branch, doc, "expired")
                if email_result:
                    result["emails_sent"].append(email_result["email_id"])
                    result["actions_taken"].append(f"Sent urgent email for expired {doc.document_name}")
            
            result["agents_executed"].append(AgentType.EMAIL_AUTOMATION.value)
        
        # 4. Create high-priority alerts
        if self.renewal_alert_agent:
            for doc in documents:
                if doc.status in [DocumentStatus.EXPIRED, DocumentStatus.MISSING]:
                    alert_result = self._create_urgent_alert(branch, doc)
                    if alert_result:
                        result["alerts_created"].append(alert_result["alert_id"])
                        result["actions_taken"].append(f"Created urgent alert for {doc.document_name}")
            
            result["agents_executed"].append(AgentType.RENEWAL_ALERT.value)
        
        # 5. Escalate to management
        result["actions_taken"].append("Escalated to management team")
        result["escalation"] = {
            "escalated_to": [branch.manager_email],
            "reason": "Critical compliance issues detected",
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def _execute_high_priority_workflow(
        self,
        result: Dict[str, Any],
        branch: Branch,
        documents: List[Document],
        router_decision: RouterDecision
    ):
        """Execute workflow for high priority situations"""
        logger.info(f"Executing HIGH priority workflow for branch {branch.branch_id}")
        
        # 1. Monitor documents
        if self.document_monitoring_agent:
            monitoring_report = self.document_monitoring_agent.monitor_branch_documents(
                branch, documents
            )
            result["agents_executed"].append(AgentType.DOCUMENT_MONITORING.value)
            result["actions_taken"].append("Monitored branch documents")
        
        # 2. Validate compliance
        if self.regulatory_validation_agent:
            compliance_result = self.regulatory_validation_agent.validate_branch_compliance(
                branch, documents
            )
            result["agents_executed"].append(AgentType.REGULATORY_VALIDATION.value)
            result["actions_taken"].append("Validated compliance")
            result["compliance_result"] = compliance_result.dict()
        
        # 3. Send notification emails
        problem_docs = [
            d for d in documents
            if d.status in [DocumentStatus.EXPIRED, DocumentStatus.CLOSE_TO_EXPIRATION, DocumentStatus.MISSING]
        ]
        
        if self.email_automation_agent:
            for doc in problem_docs:
                email_result = self._send_notification_email(branch, doc)
                if email_result:
                    result["emails_sent"].append(email_result["email_id"])
                    result["actions_taken"].append(f"Sent notification for {doc.document_name}")
            
            result["agents_executed"].append(AgentType.EMAIL_AUTOMATION.value)
        
        # 4. Create alerts
        if self.renewal_alert_agent:
            for doc in problem_docs:
                alert_result = self._create_alert(branch, doc)
                if alert_result:
                    result["alerts_created"].append(alert_result["alert_id"])
                    result["actions_taken"].append(f"Created alert for {doc.document_name}")
            
            result["agents_executed"].append(AgentType.RENEWAL_ALERT.value)
    
    def _execute_medium_priority_workflow(
        self,
        result: Dict[str, Any],
        branch: Branch,
        documents: List[Document],
        router_decision: RouterDecision
    ):
        """Execute workflow for medium priority situations"""
        logger.info(f"Executing MEDIUM priority workflow for branch {branch.branch_id}")
        
        # 1. Monitor documents
        if self.document_monitoring_agent:
            monitoring_report = self.document_monitoring_agent.monitor_branch_documents(
                branch, documents
            )
            result["agents_executed"].append(AgentType.DOCUMENT_MONITORING.value)
            result["actions_taken"].append("Monitored documents")
        
        # 2. Validate compliance
        if self.regulatory_validation_agent:
            compliance_result = self.regulatory_validation_agent.validate_branch_compliance(
                branch, documents
            )
            result["agents_executed"].append(AgentType.REGULATORY_VALIDATION.value)
            result["actions_taken"].append("Validated compliance")
            result["compliance_result"] = compliance_result.dict()
        
        # 3. Create renewal alerts for expiring documents
        expiring_docs = [
            d for d in documents
            if d.status == DocumentStatus.CLOSE_TO_EXPIRATION
        ]
        
        if self.renewal_alert_agent:
            for doc in expiring_docs:
                alert_result = self._create_renewal_alert(branch, doc)
                if alert_result:
                    result["alerts_created"].append(alert_result["alert_id"])
                    result["actions_taken"].append(f"Created renewal alert for {doc.document_name}")
            
            result["agents_executed"].append(AgentType.RENEWAL_ALERT.value)
        
        # 4. Send reminder emails if needed
        if self.email_automation_agent and expiring_docs:
            email_result = self._send_reminder_email(branch, expiring_docs)
            if email_result:
                result["emails_sent"].append(email_result["email_id"])
                result["actions_taken"].append("Sent renewal reminder email")
            
            result["agents_executed"].append(AgentType.EMAIL_AUTOMATION.value)
    
    def _execute_standard_workflow(
        self,
        result: Dict[str, Any],
        branch: Branch,
        documents: List[Document],
        router_decision: RouterDecision
    ):
        """Execute standard workflow for low priority situations"""
        logger.info(f"Executing STANDARD workflow for branch {branch.branch_id}")
        
        # 1. Monitor documents
        if self.document_monitoring_agent:
            monitoring_report = self.document_monitoring_agent.monitor_branch_documents(
                branch, documents
            )
            result["agents_executed"].append(AgentType.DOCUMENT_MONITORING.value)
            result["actions_taken"].append("Monitored documents")
        
        # 2. Validate compliance
        if self.regulatory_validation_agent:
            compliance_result = self.regulatory_validation_agent.validate_branch_compliance(
                branch, documents
            )
            result["agents_executed"].append(AgentType.REGULATORY_VALIDATION.value)
            result["actions_taken"].append("Validated compliance")
            result["compliance_result"] = compliance_result.dict()
        
        # 3. Schedule future alerts if needed
        if self.renewal_alert_agent:
            result["actions_taken"].append("Scheduled future renewal alerts")
            result["agents_executed"].append(AgentType.RENEWAL_ALERT.value)
    
    def _send_urgent_email(
        self,
        branch: Branch,
        document: Document,
        reason: str
    ) -> Optional[Dict[str, Any]]:
        """Send urgent email notification"""
        if not self.email_automation_agent:
            return None
        
        try:
            # This would call the actual email automation agent
            email_id = f"EMAIL-URGENT-{branch.branch_id}-{document.document_id}"
            logger.info(f"Sending urgent email {email_id}")
            
            return {
                "email_id": email_id,
                "recipient": branch.responsible_email,
                "cc": [branch.manager_email],
                "subject": f"URGENTE: {document.document_name} - {reason}",
                "sent_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error sending urgent email: {e}")
            return None
    
    def _send_notification_email(
        self,
        branch: Branch,
        document: Document
    ) -> Optional[Dict[str, Any]]:
        """Send notification email"""
        if not self.email_automation_agent:
            return None
        
        try:
            email_id = f"EMAIL-NOTIF-{branch.branch_id}-{document.document_id}"
            logger.info(f"Sending notification email {email_id}")
            
            return {
                "email_id": email_id,
                "recipient": branch.responsible_email,
                "subject": f"Notificación: {document.document_name}",
                "sent_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error sending notification email: {e}")
            return None
    
    def _send_reminder_email(
        self,
        branch: Branch,
        documents: List[Document]
    ) -> Optional[Dict[str, Any]]:
        """Send reminder email for multiple documents"""
        if not self.email_automation_agent:
            return None
        
        try:
            email_id = f"EMAIL-REMINDER-{branch.branch_id}"
            logger.info(f"Sending reminder email {email_id}")
            
            return {
                "email_id": email_id,
                "recipient": branch.responsible_email,
                "subject": f"Recordatorio: {len(documents)} documentos por renovar",
                "sent_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error sending reminder email: {e}")
            return None
    
    def _create_urgent_alert(
        self,
        branch: Branch,
        document: Document
    ) -> Optional[Dict[str, Any]]:
        """Create urgent alert"""
        if not self.renewal_alert_agent:
            return None
        
        try:
            alert_id = f"ALERT-URGENT-{branch.branch_id}-{document.document_id}"
            logger.info(f"Creating urgent alert {alert_id}")
            
            return {
                "alert_id": alert_id,
                "branch_id": branch.branch_id,
                "document_id": document.document_id,
                "urgency": "critical",
                "created_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error creating urgent alert: {e}")
            return None
    
    def _create_alert(
        self,
        branch: Branch,
        document: Document
    ) -> Optional[Dict[str, Any]]:
        """Create standard alert"""
        if not self.renewal_alert_agent:
            return None
        
        try:
            alert_id = f"ALERT-{branch.branch_id}-{document.document_id}"
            logger.info(f"Creating alert {alert_id}")
            
            return {
                "alert_id": alert_id,
                "branch_id": branch.branch_id,
                "document_id": document.document_id,
                "urgency": "high",
                "created_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error creating alert: {e}")
            return None
    
    def _create_renewal_alert(
        self,
        branch: Branch,
        document: Document
    ) -> Optional[Dict[str, Any]]:
        """Create renewal alert"""
        if not self.renewal_alert_agent:
            return None
        
        try:
            alert_id = f"ALERT-RENEWAL-{branch.branch_id}-{document.document_id}"
            logger.info(f"Creating renewal alert {alert_id}")
            
            return {
                "alert_id": alert_id,
                "branch_id": branch.branch_id,
                "document_id": document.document_id,
                "urgency": "medium",
                "created_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Error creating renewal alert: {e}")
            return None
    
    def execute_batch_workflow(
        self,
        branches_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Execute workflows for multiple branches in batch
        
        Args:
            branches_data: List of dictionaries with branch, documents, and router_decision
            
        Returns:
            Batch execution summary
        """
        logger.info(f"Executing batch workflow for {len(branches_data)} branches")
        
        batch_id = f"BATCH-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        start_time = datetime.utcnow()
        
        results = []
        successful = 0
        failed = 0
        
        for branch_data in branches_data:
            try:
                result = self.execute_workflow(
                    router_decision=branch_data["router_decision"],
                    branch=branch_data["branch"],
                    documents=branch_data["documents"],
                    additional_context=branch_data.get("additional_context")
                )
                results.append(result)
                
                if result["status"] == "completed":
                    successful += 1
                else:
                    failed += 1
                    
            except Exception as e:
                logger.error(f"Batch workflow error for branch {branch_data['branch'].branch_id}: {e}")
                failed += 1
        
        end_time = datetime.utcnow()
        
        summary = {
            "batch_id": batch_id,
            "total_branches": len(branches_data),
            "successful": successful,
            "failed": failed,
            "results": results,
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
            "execution_time_seconds": (end_time - start_time).total_seconds()
        }
        
        logger.info(
            f"Batch {batch_id} completed: {successful} successful, {failed} failed"
        )
        
        return summary
    
    def get_execution_history(
        self,
        branch_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get workflow execution history
        
        Args:
            branch_id: Optional branch ID to filter by
            limit: Maximum number of records to return
            
        Returns:
            List of workflow execution records
        """
        history = self.execution_history
        
        if branch_id:
            history = [h for h in history if h["branch_id"] == branch_id]
        
        return history[-limit:]


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    from datetime import date, timedelta
    
    # Create agent (without actual subagents for demo)
    agent = IntelligentActivationAgent()
    
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
    
    # Example documents
    documents = [
        Document(
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
        ),
        Document(
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
    ]
    
    # Example router decision
    router_decision = RouterDecision(
        selected_agent=AgentType.INTELLIGENT_ACTIVATION,
        reason_for_routing="Critical compliance issues detected",
        branch_id=branch.branch_id,
        branch_name=branch.branch_name,
        state=branch.state,
        municipality=branch.municipality,
        document_type="certificate",
        detected_status=DocumentStatus.EXPIRED,
        required_next_action="Execute multi-agent workflow",
        urgency_level=UrgencyLevel.CRITICAL
    )
    
    # Execute workflow
    print("\n=== Intelligent Activation Workflow ===")
    result = agent.execute_workflow(router_decision, branch, documents)
    print(f"Workflow ID: {result['workflow_id']}")
    print(f"Status: {result['status']}")
    print(f"Urgency: {result['urgency_level']}")
    print(f"Agents Executed: {result['agents_executed']}")
    print(f"Actions Taken: {len(result['actions_taken'])}")
    for action in result['actions_taken']:
        print(f"  - {action}")
    print(f"Execution Time: {result['execution_time_seconds']:.2f}s")

# Made with Bob