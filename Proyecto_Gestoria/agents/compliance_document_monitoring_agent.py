"""
Document Monitoring Agent - Monitors document status across all branches
Extracts metadata from OCR text and classifies document status
"""

from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
import re
import logging
from schemas.schemas import (
    Document, DocumentStatus, OCROutput, Branch
)

logger = logging.getLogger(__name__)


class DocumentMonitoringAgent:
    """
    Agent responsible for monitoring document status across all 319 branches.
    Detects whether documents are valid, close to expiration, expired, missing,
    unreadable, or incomplete. Extracts relevant fields from OCR text.
    """
    
    def __init__(self, llm_client=None):
        """
        Initialize the Document Monitoring Agent
        
        Args:
            llm_client: Optional LLM client for advanced text extraction
        """
        self.llm_client = llm_client
        self.field_patterns = self._initialize_field_patterns()
        logger.info("Document Monitoring Agent initialized")
    
    def _initialize_field_patterns(self) -> Dict[str, str]:
        """Initialize regex patterns for field extraction"""
        return {
            "folio": r"(?:folio|número|no\.|núm\.|número de folio)[:\s]*([A-Z0-9\-]+)",
            "issue_date": r"(?:fecha de emisión|expedición|emitido)[:\s]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})",
            "expiration_date": r"(?:fecha de vencimiento|vigencia|válido hasta|expira)[:\s]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})",
            "authority": r"(?:autoridad|expedido por|emitido por)[:\s]*([A-Za-zÁ-ú\s]+)",
            "branch_name": r"(?:sucursal|establecimiento|nombre)[:\s]*([A-Za-zÁ-ú0-9\s]+)",
        }
    
    def monitor_document(
        self,
        document: Document,
        branch: Branch,
        ocr_output: Optional[OCROutput] = None
    ) -> Dict[str, Any]:
        """
        Monitor a single document and return its status analysis
        
        Args:
            document: Document to monitor
            branch: Associated branch
            ocr_output: Optional OCR extraction results
            
        Returns:
            Dictionary with monitoring results
        """
        logger.info(f"Monitoring document {document.document_id} for branch {branch.branch_id}")
        
        # Classify document status
        status = self._classify_document_status(document)
        
        # Extract fields if OCR output is available
        extracted_fields = {}
        if ocr_output:
            extracted_fields = self._extract_fields_from_ocr(ocr_output)
        elif document.extracted_text:
            # Create OCR output from document text
            temp_ocr = OCROutput(
                document_id=document.document_id,
                extracted_text=document.extracted_text,
                confidence=document.ocr_confidence,
                extracted_fields={},
                processing_time=0.0
            )
            extracted_fields = self._extract_fields_from_ocr(temp_ocr)
        
        # Validate completeness
        completeness = self._validate_completeness(document, extracted_fields)
        
        # Generate status report
        report = {
            "document_id": document.document_id,
            "branch_id": branch.branch_id,
            "branch_name": branch.branch_name,
            "state": branch.state,
            "municipality": branch.municipality,
            "document_name": document.document_name,
            "document_type": document.document_type,
            "current_status": status.value,
            "issuing_authority": document.issuing_authority,
            "issue_date": document.issue_date.isoformat() if document.issue_date else None,
            "expiration_date": document.expiration_date.isoformat() if document.expiration_date else None,
            "folio_number": document.folio_number or extracted_fields.get("folio"),
            "ocr_confidence": document.ocr_confidence,
            "is_complete": completeness["is_complete"],
            "missing_fields": completeness["missing_fields"],
            "extracted_fields": extracted_fields,
            "days_to_expiration": self._calculate_days_to_expiration(document),
            "requires_action": status in [
                DocumentStatus.EXPIRED,
                DocumentStatus.CLOSE_TO_EXPIRATION,
                DocumentStatus.MISSING,
                DocumentStatus.INCOMPLETE
            ],
            "monitored_at": datetime.utcnow().isoformat()
        }
        
        logger.info(
            f"Document {document.document_id} status: {status.value}, "
            f"complete: {completeness['is_complete']}"
        )
        
        return report
    
    def monitor_branch_documents(
        self,
        branch: Branch,
        documents: List[Document]
    ) -> Dict[str, Any]:
        """
        Monitor all documents for a specific branch
        
        Args:
            branch: Branch to monitor
            documents: List of documents for the branch
            
        Returns:
            Comprehensive branch compliance status report
        """
        logger.info(f"Monitoring {len(documents)} documents for branch {branch.branch_id}")
        
        document_reports = []
        status_counts = {status.value: 0 for status in DocumentStatus}
        
        for doc in documents:
            report = self.monitor_document(doc, branch)
            document_reports.append(report)
            status_counts[report["current_status"]] += 1
        
        # Calculate branch-level metrics
        total_docs = len(documents)
        valid_docs = status_counts[DocumentStatus.VALID.value]
        compliance_percentage = (valid_docs / total_docs * 100) if total_docs > 0 else 0
        
        branch_report = {
            "branch_id": branch.branch_id,
            "branch_name": branch.branch_name,
            "state": branch.state,
            "municipality": branch.municipality,
            "total_documents": total_docs,
            "status_summary": status_counts,
            "compliance_percentage": round(compliance_percentage, 2),
            "valid_documents": status_counts[DocumentStatus.VALID.value],
            "expired_documents": status_counts[DocumentStatus.EXPIRED.value],
            "close_to_expiration": status_counts[DocumentStatus.CLOSE_TO_EXPIRATION.value],
            "missing_documents": status_counts[DocumentStatus.MISSING.value],
            "incomplete_documents": status_counts[DocumentStatus.INCOMPLETE.value],
            "unreadable_documents": status_counts[DocumentStatus.UNREADABLE.value],
            "requires_immediate_action": (
                status_counts[DocumentStatus.EXPIRED.value] +
                status_counts[DocumentStatus.MISSING.value]
            ),
            "documents": document_reports,
            "monitored_at": datetime.utcnow().isoformat()
        }
        
        logger.info(
            f"Branch {branch.branch_id} compliance: {compliance_percentage:.1f}%, "
            f"{status_counts[DocumentStatus.EXPIRED.value]} expired, "
            f"{status_counts[DocumentStatus.MISSING.value]} missing"
        )
        
        return branch_report
    
    def monitor_all_branches(
        self,
        branches_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Monitor documents across all 319 branches
        
        Args:
            branches_data: List of dictionaries with branch and documents data
            
        Returns:
            System-wide monitoring report
        """
        logger.info(f"Starting system-wide monitoring for {len(branches_data)} branches")
        
        branch_reports = []
        system_status_counts = {status.value: 0 for status in DocumentStatus}
        total_documents = 0
        
        for branch_data in branches_data:
            branch = branch_data["branch"]
            documents = branch_data["documents"]
            
            branch_report = self.monitor_branch_documents(branch, documents)
            branch_reports.append(branch_report)
            
            # Aggregate system-wide counts
            for status, count in branch_report["status_summary"].items():
                system_status_counts[status] += count
            total_documents += branch_report["total_documents"]
        
        # Calculate system-wide metrics
        compliant_branches = sum(
            1 for report in branch_reports 
            if report["compliance_percentage"] >= 90
        )
        at_risk_branches = sum(
            1 for report in branch_reports 
            if 50 <= report["compliance_percentage"] < 90
        )
        non_compliant_branches = sum(
            1 for report in branch_reports 
            if report["compliance_percentage"] < 50
        )
        
        system_report = {
            "total_branches": len(branches_data),
            "total_documents": total_documents,
            "compliant_branches": compliant_branches,
            "at_risk_branches": at_risk_branches,
            "non_compliant_branches": non_compliant_branches,
            "system_status_summary": system_status_counts,
            "average_compliance": round(
                sum(r["compliance_percentage"] for r in branch_reports) / len(branch_reports),
                2
            ) if branch_reports else 0,
            "branches_requiring_immediate_action": sum(
                1 for report in branch_reports 
                if report["requires_immediate_action"] > 0
            ),
            "branch_reports": branch_reports,
            "monitored_at": datetime.utcnow().isoformat()
        }
        
        logger.info(
            f"System-wide monitoring complete: {compliant_branches} compliant, "
            f"{at_risk_branches} at risk, {non_compliant_branches} non-compliant"
        )
        
        return system_report
    
    def _classify_document_status(self, document: Document) -> DocumentStatus:
        """Classify document status based on dates and OCR confidence"""
        
        # Check if document is missing
        if document.status == DocumentStatus.MISSING:
            return DocumentStatus.MISSING
        
        # Check OCR confidence
        if document.ocr_confidence < 0.5:
            return DocumentStatus.UNREADABLE
        
        # Check if required fields are missing
        if not document.expiration_date or not document.issue_date:
            if document.ocr_confidence < 0.7:
                return DocumentStatus.INCOMPLETE
        
        # Check expiration status
        if document.expiration_date:
            days_to_expiration = (document.expiration_date - date.today()).days
            
            if days_to_expiration < 0:
                return DocumentStatus.EXPIRED
            elif days_to_expiration <= 45:
                return DocumentStatus.CLOSE_TO_EXPIRATION
            else:
                return DocumentStatus.VALID
        
        # Default to valid if no expiration date
        return DocumentStatus.VALID
    
    def _extract_fields_from_ocr(self, ocr_output: OCROutput) -> Dict[str, Any]:
        """Extract structured fields from OCR text using regex patterns"""
        
        extracted = {}
        text = ocr_output.extracted_text.lower()
        
        for field_name, pattern in self.field_patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted[field_name] = match.group(1).strip()
        
        # Parse dates if found
        if "issue_date" in extracted:
            extracted["issue_date_parsed"] = self._parse_date(extracted["issue_date"])
        
        if "expiration_date" in extracted:
            extracted["expiration_date_parsed"] = self._parse_date(extracted["expiration_date"])
        
        return extracted
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse date string to ISO format"""
        date_formats = [
            "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
            "%Y/%m/%d", "%Y-%m-%d"
        ]
        
        for fmt in date_formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                return parsed.date().isoformat()
            except ValueError:
                continue
        
        return None
    
    def _validate_completeness(
        self,
        document: Document,
        extracted_fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate if document has all required fields"""
        
        required_fields = [
            "document_name",
            "issuing_authority",
            "issue_date",
            "expiration_date"
        ]
        
        missing_fields = []
        
        for field in required_fields:
            doc_value = getattr(document, field, None)
            extracted_value = extracted_fields.get(field)
            
            if not doc_value and not extracted_value:
                missing_fields.append(field)
        
        return {
            "is_complete": len(missing_fields) == 0,
            "missing_fields": missing_fields,
            "completeness_score": (
                (len(required_fields) - len(missing_fields)) / len(required_fields)
            ) if required_fields else 1.0
        }
    
    def _calculate_days_to_expiration(self, document: Document) -> Optional[int]:
        """Calculate days until document expiration"""
        if document.expiration_date:
            return (document.expiration_date - date.today()).days
        return None
    
    def get_expiring_documents(
        self,
        documents: List[Document],
        days_threshold: int = 45
    ) -> List[Dict[str, Any]]:
        """
        Get list of documents expiring within threshold
        
        Args:
            documents: List of documents to check
            days_threshold: Number of days threshold
            
        Returns:
            List of expiring documents with details
        """
        expiring = []
        
        for doc in documents:
            if doc.expiration_date:
                days_to_exp = (doc.expiration_date - date.today()).days
                
                if 0 <= days_to_exp <= days_threshold:
                    expiring.append({
                        "document_id": doc.document_id,
                        "document_name": doc.document_name,
                        "branch_id": doc.branch_id,
                        "expiration_date": doc.expiration_date.isoformat(),
                        "days_remaining": days_to_exp,
                        "urgency": "high" if days_to_exp <= 15 else "medium"
                    })
        
        # Sort by days remaining
        expiring.sort(key=lambda x: x["days_remaining"])
        
        return expiring


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create agent
    agent = DocumentMonitoringAgent()
    
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
        ),
        Document(
            document_id="DOC-003",
            branch_id="BR-001",
            document_name="Permiso de Protección Civil",
            document_type="permit",
            issuing_authority="Protección Civil",
            issue_date=date(2024, 1, 1),
            expiration_date=date.today() + timedelta(days=30),
            status=DocumentStatus.CLOSE_TO_EXPIRATION,
            ocr_confidence=0.92,
            file_url="s3://docs/BR-001/perm.pdf"
        )
    ]
    
    # Monitor branch documents
    print("\n=== Branch Monitoring Report ===")
    report = agent.monitor_branch_documents(branch, documents)
    print(f"Branch: {report['branch_name']}")
    print(f"Compliance: {report['compliance_percentage']}%")
    print(f"Valid: {report['valid_documents']}")
    print(f"Expired: {report['expired_documents']}")
    print(f"Close to expiration: {report['close_to_expiration']}")
    print(f"Requires action: {report['requires_immediate_action']}")
    
    # Get expiring documents
    print("\n=== Expiring Documents (45 days) ===")
    expiring = agent.get_expiring_documents(documents, days_threshold=45)
    for doc in expiring:
        print(f"- {doc['document_name']}: {doc['days_remaining']} days (urgency: {doc['urgency']})")

# Made with Bob
