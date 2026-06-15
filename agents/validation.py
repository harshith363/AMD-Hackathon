from __future__ import annotations

from datetime import datetime
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
        *,
        user_inputs: dict[str, Any] | None = None,
        incident_description: str | None = None,
        llm_client: Any | None = None,
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
        if customer_type == "individual" and workflow_type == "claim_validation":
            _append_claim_description_issues(incident_description, canonical, issues)
        if customer_type == "individual" and workflow_type == "kyc_validation" and user_inputs:
            _append_kyc_user_detail_issues(user_inputs, canonical, issues, llm_client)
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


def _append_claim_description_issues(
    incident_description: str | None,
    canonical: dict[str, Any],
    issues: list[dict[str, Any]],
) -> None:
    description = (incident_description or "").strip()
    if not description:
        issues.append({"severity": "medium", "field": "incident_description", "message": "Incident description is required"})
        return
    if len(description.split()) < 5:
        issues.append({"severity": "low", "field": "incident_description", "message": "Incident description is too brief for claim review"})
    incident_date = canonical.get("incident_date")
    if incident_date and incident_date not in description:
        issues.append(
            {
                "severity": "low",
                "field": "incident_description",
                "message": "Incident description does not mention the extracted incident date",
            }
        )


def _append_kyc_user_detail_issues(
    user_inputs: dict[str, Any],
    canonical: dict[str, Any],
    issues: list[dict[str, Any]],
    llm_client: Any | None,
) -> None:
    verification = None
    if llm_client is not None:
        verification = llm_client.verify_identity_consistency(user_inputs, canonical)
    if isinstance(verification, dict):
        if verification.get("is_consistent") is False:
            for issue in verification.get("issues") or ["User details are not consistent with KYC documents"]:
                issues.append({"severity": "medium", "field": "user_details", "message": str(issue)})
        return

    comparisons = {
        "address": "address",
        "name": "customer_name",
        "date_of_birth": "date_of_birth",
        "pan_number": "pan_number",
        "aadhaar_number": "aadhaar_number",
        "phone_number": "phone_number",
    }
    for user_key, extracted_key in comparisons.items():
        user_value = user_inputs.get(user_key)
        extracted_value = canonical.get(extracted_key)
        if user_value and extracted_value and not _consistent_kyc_value(user_key, user_value, extracted_value):
            issues.append(
                {
                    "severity": "medium",
                    "field": user_key,
                    "message": f"{user_key} is not consistent with extracted KYC document details",
                }
            )


def _consistent_kyc_value(field_name: str, left: Any, right: Any) -> bool:
    if field_name == "date_of_birth":
        left_date = _normalize_date(left)
        right_date = _normalize_date(right)
        if left_date and right_date:
            return left_date == right_date
    if field_name in {"pan_number", "aadhaar_number", "phone_number"}:
        return _normalize_identifier(field_name, left) == _normalize_identifier(field_name, right)
    return _consistent_text(_flatten_user_value(left), _flatten_user_value(right))


def _normalize_date(value: Any) -> str | None:
    text = str(value).strip()
    for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def _normalize_identifier(field_name: str, value: Any) -> str:
    text = str(value)
    if field_name == "pan_number":
        return re.sub(r"[^A-Z0-9]", "", text.upper())
    return re.sub(r"\D", "", text)


def _flatten_user_value(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(str(item) for item in value.values() if item)
    if isinstance(value, list):
        return " ".join(str(item) for item in value if item)
    return str(value)


def _consistent_text(left: str, right: str) -> bool:
    left_norm = set(_normalize_for_match(left).split())
    right_norm = set(_normalize_for_match(right).split())
    if not left_norm or not right_norm:
        return False
    overlap = left_norm & right_norm
    return bool(overlap) and len(overlap) / min(len(left_norm), len(right_norm)) >= 0.5


def _normalize_for_match(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", value.lower()).strip()


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
