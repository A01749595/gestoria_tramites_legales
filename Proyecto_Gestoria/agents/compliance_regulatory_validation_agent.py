"""
Regulatory Validation Agent - Validates documents against legal requirements matrix
Checks compliance with state and municipal regulations for all 319 branches
"""

from datetime import datetime, date
from typing import Dict, Any, List, Optional
import logging
from schemas.schemas import (
    Document, Branch, LegalRequirement, ComplianceResult,
    LegalRiskLevel, DocumentStatus
)

logger = logging.getLogger(__name__)


class RegulatoryValidationAgent:
    """
    Agent responsible for validating documents against the legal requirements matrix.
    Ensures each branch complies with state and municipal regulations.
    """
    
    def __init__(self, legal_matrix: Optional[List[LegalRequirement]] = None):
        """
        Initialize the Regulatory Validation Agent
        
        Args:
            legal_matrix: List of legal requirements for all states/municipalities
        """
        self.legal_matrix = legal_matrix or []
        self.validation_cache = {}
        logger.info("Regulatory Validation Agent initialized")
    
    def load_legal_matrix(self, legal_matrix: List[LegalRequirement]):
        """Load or update the legal requirements matrix"""
        self.legal_matrix = legal_matrix
        self.validation_cache.clear()
        logger.info(f"Loaded {len(legal_matrix)} legal requirements")
    
    def validate_branch_compliance(
        self,
        branch: Branch,
        documents: List[Document]
    ) -> ComplianceResult:
        """
        Validate all documents for a branch against legal requirements
        
        Args:
            branch: Branch to validate
            documents: List of documents for the branch
            
        Returns:
            ComplianceResult with detailed compliance analysis
        """
        logger.info(f"Validating compliance for branch {branch.branch_id}")
        
        # Get applicable requirements for this branch
        requirements = self._get_requirements_for_branch(branch)
        
        if not requirements:
            logger.warning(
                f"No legal requirements found for {branch.state}, {branch.municipality}"
            )
            return self._create_empty_result(branch)
        
        # Analyze documents against requirements
        analysis = self._analyze_compliance(branch, documents, requirements)
        
        # Calculate compliance score
        compliance_score = self._calculate_compliance_score(analysis)
        
        # Determine risk level
        risk_level = self._determine_risk_level(analysis, compliance_score)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(analysis, requirements)
        
        # Build compliance result
        result = ComplianceResult(
            branch_id=branch.branch_id,
            branch_name=branch.branch_name,
            state=branch.state,
            municipality=branch.municipality,
            compliance_score=compliance_score,
            missing_documents=analysis["missing_documents"],
            expired_documents=analysis["expired_documents"],
            soon_to_expire_documents=analysis["soon_to_expire_documents"],
            valid_documents=analysis["valid_documents"],
            non_compliant_documents=analysis["non_compliant_documents"],
            legal_risk_level=risk_level,
            recommended_actions=recommendations
        )
        
        logger.info(
            f"Branch {branch.branch_id} compliance: {compliance_score:.1f}%, "
            f"risk: {risk_level.value}"
        )
        
        return result
    
    def validate_document(
        self,
        document: Document,
        branch: Branch
    ) -> Dict[str, Any]:
        """
        Validate a single document against legal requirements
        
        Args:
            document: Document to validate
            branch: Associated branch
            
        Returns:
            Dictionary with validation results
        """
        logger.info(f"Validating document {document.document_id}")
        
        # Find matching requirement
        requirement = self._find_matching_requirement(document, branch)
        
        if not requirement:
            return {
                "document_id": document.document_id,
                "document_name": document.document_name,
                "is_compliant": False,
                "reason": "No matching legal requirement found",
                "risk_level": LegalRiskLevel.LOW.value,
                "validated_at": datetime.utcnow().isoformat()
            }
        
        # Validate document against requirement
        validation = self._validate_against_requirement(document, requirement)
        
        return {
            "document_id": document.document_id,
            "document_name": document.document_name,
            "requirement_id": requirement.requirement_id,
            "is_compliant": validation["is_compliant"],
            "reason": validation["reason"],
            "risk_level": requirement.risk_level.value,
            "authority": requirement.authority,
            "legal_reference": requirement.legal_reference,
            "issues_found": validation["issues"],
            "validated_at": datetime.utcnow().isoformat()
        }
    
    def get_missing_documents(
        self,
        branch: Branch,
        documents: List[Document]
    ) -> List[Dict[str, Any]]:
        """
        Identify missing mandatory documents for a branch
        
        Args:
            branch: Branch to check
            documents: Current documents for the branch
            
        Returns:
            List of missing document requirements
        """
        requirements = self._get_requirements_for_branch(branch)
        document_names = {doc.document_name.lower() for doc in documents}
        
        missing = []
        for req in requirements:
            if req.mandatory:
                req_name_lower = req.required_document.lower()
                if req_name_lower not in document_names:
                    missing.append({
                        "requirement_id": req.requirement_id,
                        "document_name": req.required_document,
                        "authority": req.authority,
                        "legal_category": req.legal_category,
                        "risk_level": req.risk_level.value,
                        "legal_reference": req.legal_reference,
                        "renewal_period_days": req.renewal_period
                    })
        
        logger.info(f"Found {len(missing)} missing documents for branch {branch.branch_id}")
        return missing
    
    def check_renewal_requirements(
        self,
        document: Document,
        branch: Branch
    ) -> Dict[str, Any]:
        """
        Check renewal requirements for a document
        
        Args:
            document: Document to check
            branch: Associated branch
            
        Returns:
            Dictionary with renewal information
        """
        requirement = self._find_matching_requirement(document, branch)
        
        if not requirement:
            return {
                "requires_renewal": False,
                "reason": "No matching requirement found"
            }
        
        if not document.expiration_date:
            return {
                "requires_renewal": False,
                "reason": "Document has no expiration date"
            }
        
        days_to_expiration = (document.expiration_date - date.today()).days
        
        return {
            "requires_renewal": days_to_expiration <= 45,
            "days_to_expiration": days_to_expiration,
            "renewal_period_days": requirement.renewal_period,
            "authority": requirement.authority,
            "urgency": "critical" if days_to_expiration < 0 else
                      "high" if days_to_expiration <= 15 else
                      "medium" if days_to_expiration <= 45 else "low",
            "legal_reference": requirement.legal_reference
        }
    
    def _get_requirements_for_branch(self, branch: Branch) -> List[LegalRequirement]:
        """Get applicable legal requirements for a branch"""
        cache_key = f"{branch.state}_{branch.municipality}"
        
        if cache_key in self.validation_cache:
            return self.validation_cache[cache_key]
        
        requirements = [
            req for req in self.legal_matrix
            if req.state == branch.state and req.municipality == branch.municipality
        ]
        
        self.validation_cache[cache_key] = requirements
        return requirements
    
    def _analyze_compliance(
        self,
        branch: Branch,
        documents: List[Document],
        requirements: List[LegalRequirement]
    ) -> Dict[str, Any]:
        """Analyze compliance status of all documents"""
        
        analysis = {
            "missing_documents": [],
            "expired_documents": [],
            "soon_to_expire_documents": [],
            "valid_documents": [],
            "non_compliant_documents": [],
            "total_required": len([r for r in requirements if r.mandatory]),
            "total_provided": len(documents)
        }
        
        # Create document lookup
        doc_lookup = {doc.document_name.lower(): doc for doc in documents}
        
        # Check each requirement
        for req in requirements:
            req_name_lower = req.required_document.lower()
            
            if req_name_lower not in doc_lookup:
                if req.mandatory:
                    analysis["missing_documents"].append(req.required_document)
            else:
                doc = doc_lookup[req_name_lower]
                
                # Check document status
                if doc.status == DocumentStatus.EXPIRED:
                    analysis["expired_documents"].append(doc.document_name)
                elif doc.status == DocumentStatus.CLOSE_TO_EXPIRATION:
                    days_to_exp = (doc.expiration_date - date.today()).days if doc.expiration_date else 0
                    analysis["soon_to_expire_documents"].append({
                        "document": doc.document_name,
                        "expiration_date": doc.expiration_date.isoformat() if doc.expiration_date else None,
                        "days_remaining": days_to_exp
                    })
                elif doc.status == DocumentStatus.VALID:
                    analysis["valid_documents"].append(doc.document_name)
                
                # Check if document matches requirement
                validation = self._validate_against_requirement(doc, req)
                if not validation["is_compliant"]:
                    analysis["non_compliant_documents"].append({
                        "document": doc.document_name,
                        "requirement": req.required_document,
                        "issues": validation["issues"]
                    })
        
        return analysis
    
    def _validate_against_requirement(
        self,
        document: Document,
        requirement: LegalRequirement
    ) -> Dict[str, Any]:
        """Validate a document against a specific requirement"""
        
        issues = []
        
        # Check issuing authority
        if document.issuing_authority:
            if requirement.authority.lower() not in document.issuing_authority.lower():
                issues.append(f"Issuing authority mismatch: expected {requirement.authority}")
        
        # Check expiration
        if document.expiration_date:
            if document.status == DocumentStatus.EXPIRED:
                issues.append("Document is expired")
            
            # Check renewal period
            if document.issue_date and document.expiration_date:
                actual_period = (document.expiration_date - document.issue_date).days
                expected_period = requirement.renewal_period
                
                # Allow 10% variance
                if abs(actual_period - expected_period) > (expected_period * 0.1):
                    issues.append(
                        f"Renewal period mismatch: {actual_period} days vs expected {expected_period} days"
                    )
        
        # Check OCR confidence
        if document.ocr_confidence < 0.7:
            issues.append(f"Low OCR confidence: {document.ocr_confidence:.2%}")
        
        return {
            "is_compliant": len(issues) == 0,
            "reason": "Document complies with requirements" if len(issues) == 0 else "Issues found",
            "issues": issues
        }
    
    def _find_matching_requirement(
        self,
        document: Document,
        branch: Branch
    ) -> Optional[LegalRequirement]:
        """Find the legal requirement that matches a document"""
        
        requirements = self._get_requirements_for_branch(branch)
        doc_name_lower = document.document_name.lower()
        
        # Try exact match first
        for req in requirements:
            if req.required_document.lower() == doc_name_lower:
                return req
        
        # Try partial match
        for req in requirements:
            if req.required_document.lower() in doc_name_lower or \
               doc_name_lower in req.required_document.lower():
                return req
        
        return None
    
    def _calculate_compliance_score(self, analysis: Dict[str, Any]) -> float:
        """Calculate overall compliance score (0-100)"""
        
        total_required = analysis["total_required"]
        if total_required == 0:
            return 100.0
        
        # Count compliant documents
        valid_count = len(analysis["valid_documents"])
        
        # Penalize missing and expired
        missing_count = len(analysis["missing_documents"])
        expired_count = len(analysis["expired_documents"])
        
        # Partial credit for expiring soon
        expiring_count = len(analysis["soon_to_expire_documents"])
        
        # Calculate score
        compliant_count = valid_count + (expiring_count * 0.5)
        score = (compliant_count / total_required) * 100
        
        return round(max(0.0, min(100.0, score)), 2)
    
    def _determine_risk_level(
        self,
        analysis: Dict[str, Any],
        compliance_score: float
    ) -> LegalRiskLevel:
        """Determine legal risk level based on compliance analysis"""
        
        missing_count = len(analysis["missing_documents"])
        expired_count = len(analysis["expired_documents"])
        
        # Critical: Multiple expired or missing mandatory documents
        if expired_count >= 3 or missing_count >= 3:
            return LegalRiskLevel.CRITICAL
        
        # Critical: Very low compliance
        if compliance_score < 50:
            return LegalRiskLevel.CRITICAL
        
        # High: Any expired or multiple missing
        if expired_count > 0 or missing_count >= 2:
            return LegalRiskLevel.HIGH
        
        # High: Low compliance
        if compliance_score < 70:
            return LegalRiskLevel.HIGH
        
        # Medium: One missing or documents expiring soon
        if missing_count == 1 or len(analysis["soon_to_expire_documents"]) > 2:
            return LegalRiskLevel.MEDIUM
        
        # Medium: Moderate compliance
        if compliance_score < 90:
            return LegalRiskLevel.MEDIUM
        
        # Low: Good compliance
        return LegalRiskLevel.LOW
    
    def _generate_recommendations(
        self,
        analysis: Dict[str, Any],
        requirements: List[LegalRequirement]
    ) -> List[str]:
        """Generate recommended actions based on compliance analysis"""
        
        recommendations = []
        
        # Handle expired documents
        for doc_name in analysis["expired_documents"]:
            req = next((r for r in requirements if r.required_document == doc_name), None)
            if req:
                recommendations.append(
                    f"URGENT: Renovar {doc_name} inmediatamente con {req.authority}"
                )
        
        # Handle missing documents
        for doc_name in analysis["missing_documents"]:
            req = next((r for r in requirements if r.required_document == doc_name), None)
            if req:
                recommendations.append(
                    f"Solicitar {doc_name} ante {req.authority} - Documento obligatorio"
                )
        
        # Handle expiring documents
        for doc_info in analysis["soon_to_expire_documents"]:
            days = doc_info["days_remaining"]
            if days <= 15:
                recommendations.append(
                    f"URGENTE: Iniciar renovación de {doc_info['document']} ({days} días restantes)"
                )
            else:
                recommendations.append(
                    f"Programar renovación de {doc_info['document']} ({days} días restantes)"
                )
        
        # Handle non-compliant documents
        for doc_info in analysis["non_compliant_documents"]:
            recommendations.append(
                f"Revisar {doc_info['document']}: {', '.join(doc_info['issues'])}"
            )
        
        # Add general recommendations
        if not recommendations:
            recommendations.append("Mantener documentación actualizada y monitorear fechas de vencimiento")
        
        return recommendations
    
    def _create_empty_result(self, branch: Branch) -> ComplianceResult:
        """Create an empty compliance result when no requirements are found"""
        return ComplianceResult(
            branch_id=branch.branch_id,
            branch_name=branch.branch_name,
            state=branch.state,
            municipality=branch.municipality,
            compliance_score=0.0,
            missing_documents=[],
            expired_documents=[],
            soon_to_expire_documents=[],
            valid_documents=[],
            non_compliant_documents=[],
            legal_risk_level=LegalRiskLevel.LOW,
            recommended_actions=["Cargar matriz legal para esta ubicación"]
        )


# Example usage
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create sample legal requirements
    legal_matrix = [
        LegalRequirement(
            requirement_id="REQ-CDMX-001",
            state="Ciudad de México",
            municipality="Cuauhtémoc",
            required_document="Licencia de Funcionamiento",
            legal_category="operational",
            renewal_period=365,
            authority="Secretaría de Desarrollo Económico",
            mandatory=True,
            risk_level=LegalRiskLevel.HIGH,
            legal_reference="Ley de Establecimientos Mercantiles CDMX",
            description="Licencia requerida para operar establecimiento mercantil"
        ),
        LegalRequirement(
            requirement_id="REQ-CDMX-002",
            state="Ciudad de México",
            municipality="Cuauhtémoc",
            required_document="Certificado Sanitario",
            legal_category="health",
            renewal_period=365,
            authority="Secretaría de Salud",
            mandatory=True,
            risk_level=LegalRiskLevel.CRITICAL,
            legal_reference="Ley General de Salud",
            description="Certificado de condiciones sanitarias del establecimiento"
        ),
        LegalRequirement(
            requirement_id="REQ-CDMX-003",
            state="Ciudad de México",
            municipality="Cuauhtémoc",
            required_document="Permiso de Protección Civil",
            legal_category="safety",
            renewal_period=365,
            authority="Protección Civil",
            mandatory=True,
            risk_level=LegalRiskLevel.HIGH,
            legal_reference="Ley de Protección Civil CDMX",
            description="Permiso de medidas de seguridad y protección civil"
        )
    ]
    
    # Create agent
    agent = RegulatoryValidationAgent(legal_matrix)
    
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
    from datetime import timedelta
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
    
    # Validate compliance
    print("\n=== Branch Compliance Validation ===")
    result = agent.validate_branch_compliance(branch, documents)
    print(f"Branch: {result.branch_name}")
    print(f"Compliance Score: {result.compliance_score}%")
    print(f"Risk Level: {result.legal_risk_level.value}")
    print(f"\nMissing Documents: {result.missing_documents}")
    print(f"Expired Documents: {result.expired_documents}")
    print(f"Valid Documents: {result.valid_documents}")
    print(f"\nRecommended Actions:")
    for action in result.recommended_actions:
        print(f"  - {action}")

# Made with Bob