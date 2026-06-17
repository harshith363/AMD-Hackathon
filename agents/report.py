from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from llm import VLLMClient
from mcp_server.client import get_claim_compliance_rules
from orchestrator.trace import WorkflowTrace
from schemas.messages import ExtractionResultMessage, ReportMessage, ValidationResultMessage


class ReportAgent:
    name = "Report Agent"

    def __init__(self, llm_client: VLLMClient | None = None) -> None:
        self.llm_client = llm_client or VLLMClient.from_config()

    def validation_report(
        self,
        customer_type: str,
        workflow_type: str,
        case_type: str,
        validation: ValidationResultMessage,
        extraction: ExtractionResultMessage,
        trace: WorkflowTrace,
        *,
        user_inputs: dict[str, Any] | None = None,
        incident_description: str | None = None,
    ) -> ReportMessage:
        report_id = f"RPT-{uuid4().hex[:10].upper()}"
        json_report: dict[str, Any] = {
            "report_id": report_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "workflow_type": workflow_type,
            "customer_type": customer_type,
            "case_type": case_type,
            "status": validation.status,
            "confidence": validation.confidence,
            "human_review_required": validation.human_review_required,
            "missing_documents": validation.missing_documents,
            "validation_issues": validation.issues,
            "extracted_key_fields": extraction.extracted_fields.get("canonical", {}),
            "extracted_by_document": _group_extracted_fields_by_document(extraction.extracted_fields.get("by_field", {})),
            "document_debug": _document_debug_from_trace(trace),
            "user_inputs": user_inputs or {},
            "incident_description": incident_description,
            "evidence": extraction.evidence,
            "next_action": validation.next_action,
            "trace": trace.to_list(),
        }
        if workflow_type == "claim_validation":
            json_report["claim_document_summary"] = _claim_document_summary(
                self.llm_client,
                json_report,
                _documents_from_trace(trace),
                get_claim_compliance_rules(customer_type, case_type),
            )
        llm_explanation = self.llm_client.explain_report(json_report)
        if llm_explanation:
            json_report["llm_explanation"] = llm_explanation
        markdown = _markdown_validation_report(json_report)
        trace.add(self.name, "generated_validation_report", {"report_id": report_id})
        return ReportMessage(
            session_id=validation.session_id,
            report_id=report_id,
            report_type=workflow_type,
            json_report=json_report,
            markdown_report=markdown,
        )

    def product_report(self, recommendation_message, trace: WorkflowTrace) -> ReportMessage:
        report_id = f"REC-{uuid4().hex[:10].upper()}"
        json_report = {
            "report_id": report_id,
            "workflow_type": "new_insurance",
            "customer_type": recommendation_message.customer_type,
            "category": recommendation_message.insurance_category,
            "user_inputs": recommendation_message.user_inputs,
            "recommendations": recommendation_message.recommendations,
            "trace": trace.to_list(),
        }
        llm_explanation = self.llm_client.explain_report(json_report)
        if llm_explanation:
            json_report["llm_explanation"] = llm_explanation
        markdown = _markdown_product_report(json_report)
        trace.add(self.name, "generated_product_report", {"report_id": report_id})
        return ReportMessage(
            session_id=recommendation_message.session_id,
            report_id=report_id,
            report_type="new_insurance",
            json_report=json_report,
            markdown_report=markdown,
        )


def _markdown_validation_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Validation Report {report['report_id']}",
        "",
        f"- Workflow: {report['workflow_type']}",
        f"- Customer type: {report['customer_type']}",
        f"- Case type: {report['case_type']}",
        f"- Status: {report['status']}",
        f"- Confidence: {report['confidence']}",
        f"- Human review required: {report['human_review_required']}",
        f"- Next action: {report['next_action']}",
        "",
    ]
    if report.get("incident_description"):
        lines.extend(["## Incident Description", report["incident_description"], ""])
    if report.get("llm_explanation"):
        lines.extend(["## LLM Explanation", report["llm_explanation"], ""])
    lines.append("## Missing Documents")
    lines.extend([f"- {item}" for item in report["missing_documents"]] or ["- None"])
    lines.append("")
    lines.append("## Issues")
    lines.extend([f"- [{item.get('severity')}] {item.get('message')}" for item in report["validation_issues"]] or ["- None"])
    lines.append("")
    lines.append("## Extracted Key Fields")
    lines.extend([f"- {key}: {value}" for key, value in report["extracted_key_fields"].items()] or ["- None"])
    return "\n".join(lines)


def _group_extracted_fields_by_document(by_field: dict[str, Any]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for field_name, values in by_field.items():
        for item in values:
            document_type = item.get("document_type", "unknown")
            grouped.setdefault(document_type, {})[field_name] = item.get("value")
    return grouped


def _document_debug_from_trace(trace: WorkflowTrace) -> list[dict[str, Any]]:
    for item in reversed(trace.to_list()):
        if item.get("agent") == "Document Intake Agent" and item.get("action") == "parsed_documents":
            return (item.get("detail") or item.get("details") or {}).get("documents", [])
    return []


def _documents_from_trace(trace: WorkflowTrace) -> list[dict[str, Any]]:
    for item in reversed(trace.to_list()):
        if item.get("agent") == "Document Intake Agent" and item.get("action") == "parsed_documents":
            return (item.get("detail") or item.get("details") or {}).get("documents", [])
    return []


def _claim_document_summary(
    llm_client: VLLMClient,
    report: dict[str, Any],
    documents: list[dict[str, Any]],
    compliance_rules: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "claim_details": report.get("user_inputs") or {},
        "incident_description": report.get("incident_description"),
        "extracted_by_document": report.get("extracted_by_document") or {},
        "document_previews": [
            {
                "document_type": item.get("document_type"),
                "file_name": item.get("file_name"),
                "text_preview": item.get("text_preview"),
                "extraction_method": item.get("extraction_method"),
            }
            for item in documents
            if item.get("document_type") in {"incident_report", "forensic_report", "loss_estimate", "repair_estimate", "hospital_bill", "discharge_summary"}
        ],
        "compliance_rules_from_mcp": compliance_rules,
    }
    llm_summary = llm_client.summarize_claim_documents(payload)
    if isinstance(llm_summary, dict):
        llm_summary["source"] = "llm_with_mcp_rules"
        return llm_summary
    return _fallback_claim_document_summary(report, compliance_rules)


def _fallback_claim_document_summary(report: dict[str, Any], compliance_rules: dict[str, Any]) -> dict[str, Any]:
    details = report.get("user_inputs") or {}
    extracted = report.get("extracted_key_fields") or {}
    incident_description = report.get("incident_description") or "No incident description was provided."
    claimant = details.get("company_name") or details.get("patient_name") or extracted.get("company_name") or extracted.get("patient_name") or "The claimant"
    policy_number = details.get("policy_number") or extracted.get("policy_number") or "the submitted policy"
    claim_amount = details.get("claim_amount") or extracted.get("claim_amount") or "not clearly extracted"
    return {
        "source": "deterministic_fallback",
        "event_summary": f"{claimant} reported an event under policy {policy_number}. {incident_description}",
        "timeline": f"Incident date: {details.get('incident_date') or extracted.get('incident_date') or 'not clearly extracted'}",
        "likely_cause": "Requires review of incident/forensic narrative." if report.get("case_type") == "cybersecurity" else "Based on submitted incident narrative.",
        "affected_assets_or_treatment": "Claim amount: INR " + str(claim_amount),
        "evidence_reviewed": ", ".join(compliance_rules.get("required_documents") or []) or "Uploaded claim documents",
        "coverage_reasoning": "Compared submitted document types and extracted fields against the MCP claim rule pack.",
        "missing_or_unclear_information": ", ".join(report.get("missing_documents") or []) or "No required document gaps detected.",
    }


def _markdown_product_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Product Recommendations {report['report_id']}",
        "",
        f"- Customer type: {report['customer_type']}",
        f"- Category: {report['category']}",
        "",
    ]
    if report.get("llm_explanation"):
        lines.extend(["## LLM Explanation", report["llm_explanation"], ""])
    for product in report["recommendations"]:
        lines.extend(
            [
                f"## {product['scheme_name']}",
                f"- Scheme ID: {product['scheme_id']}",
                f"- Eligibility: {product['eligibility']}",
                f"- Coverage: {', '.join(product['coverage_highlights'])}",
                f"- Required documents: {', '.join(product['required_documents'])}",
                f"- Recommended next step: {product['recommended_next_step']}",
                "",
            ]
        )
    if not report["recommendations"]:
        lines.append("No matching schemes found.")
    return "\n".join(lines)
