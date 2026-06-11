from __future__ import annotations

import re
from typing import Any

from orchestrator.trace import WorkflowTrace
from rules.claim_rules import CLAIM_RULES
from rules.kyc_rules import KYC_RULES
from schemas.messages import ClassifiedDocumentMessage, ExtractionResultMessage, ReconciliationMessage, ValidationResultMessage


class ValidationAgent:
    name = "Validation Agent"

    def validate(
        self,
        customer_type: str,
        workflow_type: str,
        case_type: str,
        classified: ClassifiedDocumentMessage,
        extraction: ExtractionResultMessage,
        reconciliation: ReconciliationMessage,
        trace: WorkflowTrace,
    ) -> ValidationResultMessage:
        rule = _select_rule(customer_type, workflow_type, case_type)
        received_types = {doc.get("document_type") for doc in classified.documents}
        missing_documents = [doc for doc in rule["required_documents"] if doc not in received_types]
        issues: list[dict[str, Any]] = []
        issues.extend(reconciliation.inconsistencies)

        canonical = extraction.extracted_fields.get("canonical", {})
        for field_name in rule.get("field_checks", []):
            if field_name not in canonical:
                issues.append({"severity": "low", "field": field_name, "message": f"Missing key field: {field_name}"})

        _append_format_issues(canonical, issues)
        status, human_review_required, next_action = _decide_status(missing_documents, issues)
        confidence = _adjust_confidence(extraction.confidence, missing_documents, issues)
        trace.add(self.name, "validated_case", {"status": status, "missing_documents": missing_documents, "issues": len(issues)})
        return ValidationResultMessage(
            session_id=classified.session_id,
            status=status,
            human_review_required=human_review_required,
            confidence=confidence,
            missing_documents=missing_documents,
            issues=issues,
            next_action=next_action,
        )


def _select_rule(customer_type: str, workflow_type: str, case_type: str) -> dict[str, Any]:
    if workflow_type == "claim_validation":
        return CLAIM_RULES[customer_type][case_type]
    return KYC_RULES["business" if workflow_type == "kyb_validation" else "individual"]


def _append_format_issues(canonical: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    pan = canonical.get("pan_number")
    if pan and not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
        issues.append({"severity": "medium", "field": "pan_number", "message": "PAN format is invalid"})
    gstin = canonical.get("gstin")
    if gstin and not re.fullmatch(r"[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]", gstin):
        issues.append({"severity": "medium", "field": "gstin", "message": "GSTIN format is invalid"})


def _decide_status(missing_documents: list[str], issues: list[dict[str, Any]]) -> tuple[str, bool, str]:
    if any(issue.get("severity") == "high" for issue in issues):
        return "Human Review Required", True, "Escalate to a human reviewer with extracted evidence."
    if missing_documents:
        return "Needs Additional Documents", False, "Request the missing mandatory documents from the customer."
    if any(issue.get("severity") == "medium" for issue in issues):
        return "Needs Correction", False, "Ask the customer to correct inconsistent or invalid details."
    if not issues:
        return "Ready for Submission", False, "Submit the case to the insurer workflow."
    return "Human Review Required", True, "Escalate because validation did not reach a deterministic pass."


def _adjust_confidence(base: float, missing_documents: list[str], issues: list[dict[str, Any]]) -> float:
    penalty = (len(missing_documents) * 0.08) + (len(issues) * 0.04)
    return round(max(0.1, min(0.99, base - penalty)), 2)
