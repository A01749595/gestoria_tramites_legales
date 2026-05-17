"""
Dashboard Service
Provides data aggregation and visualization support for the compliance dashboard
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta, timezone
from collections import defaultdict
import logging

from schemas.schemas import Branch, Document, DocumentStatus, LegalRiskLevel


# --- Helpers inlineados (antes en utils/helpers.py) ---
def calculate_days_until(target):
    """Días hasta target (negativo si ya pasó, 9999 si None/inválido)."""
    if target is None:
        return 9999
    if isinstance(target, str):
        try:
            target = datetime.fromisoformat(target).date()
        except ValueError:
            try:
                target = datetime.strptime(target, "%d/%m/%Y").date()
            except ValueError:
                return 9999
    if isinstance(target, datetime):
        target = target.date()
    return (target - date.today()).days


def calculate_compliance_score(total_requirements: int, met_requirements: int) -> float:
    """Score 0-100 de cumplimiento."""
    if total_requirements <= 0:
        return 100.0
    return round((met_requirements / total_requirements) * 100, 2)

logger = logging.getLogger(__name__)


class DashboardService:
    """
    Service for generating dashboard data and metrics
    """
    
    def __init__(self):
        """Initialize dashboard service"""
        logger.info("Dashboard service initialized")
    
    def get_overview_metrics(
        self,
        branches: List[Branch],
        documents: List[Document]
    ) -> Dict[str, Any]:
        """
        Get overview metrics for the dashboard
        
        Args:
            branches: List of branches
            documents: List of all documents
            
        Returns:
            Overview metrics dictionary
        """
        total_branches = len(branches)
        total_documents = len(documents)
        
        # Document status counts
        status_counts = defaultdict(int)
        for doc in documents:
            status_counts[doc.status.value] += 1
        
        # Expiring documents (next 30 days)
        expiring_soon = [
            doc for doc in documents
            if doc.expiration_date and 0 <= calculate_days_until(doc.expiration_date) <= 30
        ]
        
        # Expired documents
        expired = [
            doc for doc in documents
            if doc.expiration_date and calculate_days_until(doc.expiration_date) < 0
        ]
        
        return {
            "total_branches": total_branches,
            "total_documents": total_documents,
            "documents_by_status": dict(status_counts),
            "expiring_soon_count": len(expiring_soon),
            "expired_count": len(expired),
            "valid_documents": status_counts[DocumentStatus.VALID.value],
            "pending_review": status_counts[DocumentStatus.PENDING_REVIEW.value],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def get_compliance_summary(
        self,
        branches: List[Branch],
        compliance_scores: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Get compliance summary across all branches
        
        Args:
            branches: List of branches
            compliance_scores: Dictionary mapping branch_id to compliance score
            
        Returns:
            Compliance summary
        """
        if not compliance_scores:
            return {
                "average_score": 0,
                "compliant_branches": 0,
                "non_compliant_branches": 0,
                "at_risk_branches": 0
            }
        
        scores = list(compliance_scores.values())
        average_score = sum(scores) / len(scores) if scores else 0
        
        # Categorize branches
        compliant = sum(1 for score in scores if score >= 90)
        at_risk = sum(1 for score in scores if 70 <= score < 90)
        non_compliant = sum(1 for score in scores if score < 70)
        
        return {
            "average_score": round(average_score, 2),
            "compliant_branches": compliant,
            "at_risk_branches": at_risk,
            "non_compliant_branches": non_compliant,
            "total_branches": len(branches),
            "compliance_rate": round((compliant / len(branches) * 100), 2) if branches else 0
        }
    
    def get_expiring_documents_timeline(
        self,
        documents: List[Document],
        days_ahead: int = 90
    ) -> Dict[str, Any]:
        """
        Get timeline of expiring documents
        
        Args:
            documents: List of documents
            days_ahead: Number of days to look ahead
            
        Returns:
            Timeline data
        """
        today = date.today()
        timeline = defaultdict(list)
        
        for doc in documents:
            if not doc.expiration_date:
                continue
            
            days_until = calculate_days_until(doc.expiration_date)
            
            if 0 <= days_until <= days_ahead:
                # Group by week
                week_number = days_until // 7
                timeline[f"Week {week_number + 1}"].append({
                    "document_id": doc.document_id,
                    "document_name": doc.document_name,
                    "document_type": doc.document_type,
                    "branch_id": doc.branch_id,
                    "expiration_date": doc.expiration_date.isoformat(),
                    "days_until_expiration": days_until
                })
        
        return {
            "timeline": dict(timeline),
            "total_expiring": sum(len(docs) for docs in timeline.values()),
            "days_ahead": days_ahead
        }
    
    def get_branch_compliance_details(
        self,
        branch: Branch,
        documents: List[Document],
        required_documents: List[str]
    ) -> Dict[str, Any]:
        """
        Get detailed compliance information for a branch
        
        Args:
            branch: Branch to analyze
            documents: Branch documents
            required_documents: List of required document types
            
        Returns:
            Branch compliance details
        """
        # Document types present
        present_types = set(doc.document_type for doc in documents)
        missing_types = set(required_documents) - present_types
        
        # Status breakdown
        status_counts = defaultdict(int)
        for doc in documents:
            status_counts[doc.status.value] += 1
        
        # Expiring documents
        expiring = [
            doc for doc in documents
            if doc.expiration_date and 0 <= calculate_days_until(doc.expiration_date) <= 30
        ]
        
        # Calculate compliance score
        compliance_score = calculate_compliance_score(
            total_requirements=len(required_documents),
            met_requirements=len(present_types)
        )
        
        return {
            "branch_id": branch.branch_id,
            "branch_name": branch.branch_name,
            "compliance_score": compliance_score,
            "total_documents": len(documents),
            "required_documents": len(required_documents),
            "missing_documents": list(missing_types),
            "documents_by_status": dict(status_counts),
            "expiring_soon": len(expiring),
            "expiring_documents": [
                {
                    "document_id": doc.document_id,
                    "document_name": doc.document_name,
                    "expiration_date": doc.expiration_date.isoformat() if doc.expiration_date else None,
                    "days_until": calculate_days_until(doc.expiration_date) if doc.expiration_date else 0
                }
                for doc in expiring
            ]
        }
    
    def get_regional_analysis(
        self,
        branches: List[Branch],
        compliance_scores: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Get compliance analysis by region
        
        Args:
            branches: List of branches
            compliance_scores: Dictionary mapping branch_id to compliance score
            
        Returns:
            Regional analysis
        """
        regional_data: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "branches": [],
            "scores": [],
            "average_score": 0
        })
        
        for branch in branches:
            region = branch.region or "Unknown"
            score = compliance_scores.get(branch.branch_id, 0)
            
            regional_data[region]["branches"].append(branch.branch_id)
            regional_data[region]["scores"].append(score)
        
        # Calculate averages
        for region, data in regional_data.items():
            if data["scores"]:
                data["average_score"] = round(
                    sum(data["scores"]) / len(data["scores"]), 2
                )
                data["branch_count"] = len(data["branches"])
        
        return {
            "regions": dict(regional_data),
            "total_regions": len(regional_data)
        }
    
    def get_state_analysis(
        self,
        branches: List[Branch],
        compliance_scores: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Get compliance analysis by state
        
        Args:
            branches: List of branches
            compliance_scores: Dictionary mapping branch_id to compliance score
            
        Returns:
            State analysis
        """
        state_data: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "branches": [],
            "scores": [],
            "average_score": 0
        })
        
        for branch in branches:
            state = branch.state or "Unknown"
            score = compliance_scores.get(branch.branch_id, 0)
            
            state_data[state]["branches"].append(branch.branch_id)
            state_data[state]["scores"].append(score)
        
        # Calculate averages
        for state, data in state_data.items():
            if data["scores"]:
                data["average_score"] = round(
                    sum(data["scores"]) / len(data["scores"]), 2
                )
                data["branch_count"] = len(data["branches"])
        
        return {
            "states": dict(state_data),
            "total_states": len(state_data)
        }
    
    def get_document_type_analysis(
        self,
        documents: List[Document]
    ) -> Dict[str, Any]:
        """
        Get analysis by document type
        
        Args:
            documents: List of documents
            
        Returns:
            Document type analysis
        """
        type_data = defaultdict(lambda: {
            "total": 0,
            "valid": 0,
            "expired": 0,
            "expiring_soon": 0,
            "pending_review": 0
        })
        
        for doc in documents:
            doc_type = doc.document_type
            type_data[doc_type]["total"] += 1
            
            if doc.status == DocumentStatus.VALID:
                type_data[doc_type]["valid"] += 1
            elif doc.status == DocumentStatus.EXPIRED:
                type_data[doc_type]["expired"] += 1
            elif doc.status == DocumentStatus.PENDING_REVIEW:
                type_data[doc_type]["pending_review"] += 1
            
            if doc.expiration_date and 0 <= calculate_days_until(doc.expiration_date) <= 30:
                type_data[doc_type]["expiring_soon"] += 1
        
        return {
            "document_types": dict(type_data),
            "total_types": len(type_data)
        }
    
    def get_alerts_summary(
        self,
        documents: List[Document]
    ) -> Dict[str, Any]:
        """
        Get summary of alerts and notifications needed
        
        Args:
            documents: List of documents
            
        Returns:
            Alerts summary
        """
        critical_alerts = []
        high_priority = []
        medium_priority = []
        
        for doc in documents:
            if not doc.expiration_date:
                continue
            
            days_until = calculate_days_until(doc.expiration_date)
            
            alert_data = {
                "document_id": doc.document_id,
                "document_name": doc.document_name,
                "branch_id": doc.branch_id,
                "days_until_expiration": days_until
            }
            
            if days_until < 0:
                critical_alerts.append(alert_data)
            elif days_until <= 7:
                critical_alerts.append(alert_data)
            elif days_until <= 30:
                high_priority.append(alert_data)
            elif days_until <= 60:
                medium_priority.append(alert_data)
        
        return {
            "critical_alerts": critical_alerts,
            "high_priority": high_priority,
            "medium_priority": medium_priority,
            "total_alerts": len(critical_alerts) + len(high_priority) + len(medium_priority)
        }
    
    def generate_dashboard_data(
        self,
        branches: List[Branch],
        documents: List[Document],
        compliance_scores: Dict[str, float],
        required_documents: List[str]
    ) -> Dict[str, Any]:
        """
        Generate complete dashboard data
        
        Args:
            branches: List of branches
            documents: List of documents
            compliance_scores: Compliance scores by branch
            required_documents: List of required document types
            
        Returns:
            Complete dashboard data
        """
        return {
            "overview": self.get_overview_metrics(branches, documents),
            "compliance_summary": self.get_compliance_summary(branches, compliance_scores),
            "expiring_timeline": self.get_expiring_documents_timeline(documents),
            "regional_analysis": self.get_regional_analysis(branches, compliance_scores),
            "state_analysis": self.get_state_analysis(branches, compliance_scores),
            "document_type_analysis": self.get_document_type_analysis(documents),
            "alerts": self.get_alerts_summary(documents),
            "generated_at": datetime.now(timezone.utc).isoformat()
        }


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Create service
    dashboard = DashboardService()
    
    # Mock data
    branches = [
        Branch(
            branch_id="BR-001",
            branch_name="Centro CDMX",
            state="Ciudad de México",
            municipality="Cuauhtémoc",
            region="Centro",
            responsible_email="resp@example.com",
            manager_email="mgr@example.com",
            whatsapp_contact="+525512345678"
        )
    ]
    
    documents = []
    compliance_scores = {"BR-001": 85.5}
    required_documents = ["license", "permit", "certificate"]
    
    # Generate dashboard
    dashboard_data = dashboard.generate_dashboard_data(
        branches=branches,
        documents=documents,
        compliance_scores=compliance_scores,
        required_documents=required_documents
    )
    
    print("Dashboard data generated successfully")
    print(f"Total branches: {dashboard_data['overview']['total_branches']}")

# Made with Bob