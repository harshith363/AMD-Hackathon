from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from llm import VLLMClient
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
            "evidence": extraction.evidence,
            "next_action": validation.next_action,
            "trace": trace.to_list(),
        }
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
