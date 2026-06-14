from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from agents.database import DatabaseAgent
from agents.document_classifier import DocumentClassifierAgent
from agents.document_intake import DocumentIntakeAgent
from agents.escalation import EscalationAgent
from agents.extraction import ExtractionAgent
from agents.product_discovery import ProductDiscoveryAgent
from agents.reconciliation import ReconciliationAgent
from agents.report import ReportAgent
from agents.router import RouterAgent
from agents.validation import ValidationAgent
from llm import VLLMClient
from orchestrator.trace import WorkflowTrace
from schemas.messages import DocumentPacketMessage, ProductDiscoveryMessage, UserIntentMessage


class WorkflowOrchestrator:
    def __init__(
        self,
        use_llm: bool | None = None,
        *,
        vllm_base_url: str | None = None,
        vllm_model: str | None = None,
        vllm_api_key: str | None = None,
        vllm_timeout_seconds: int | None = None,
    ) -> None:
        self.llm_client = VLLMClient.from_config(
            base_url=vllm_base_url,
            model=vllm_model,
            api_key=vllm_api_key,
            timeout_seconds=vllm_timeout_seconds,
            enabled=bool(use_llm),
        )
        self.router = RouterAgent()
        self.product_discovery = ProductDiscoveryAgent()
        self.document_intake = DocumentIntakeAgent()
        self.document_classifier = DocumentClassifierAgent()
        self.extraction = ExtractionAgent()
        self.reconciliation = ReconciliationAgent()
        self.validation = ValidationAgent()
        self.escalation = EscalationAgent()
        self.report = ReportAgent(self.llm_client)
        self.database = DatabaseAgent()

    def run_product_discovery(self, message: ProductDiscoveryMessage):
        intent = UserIntentMessage(
            session_id=message.session_id,
            customer_type=message.customer_type,
            intent="new_insurance",
            raw_input=message.insurance_category,
        )
        trace = WorkflowTrace(message.session_id)
        self.router.route(intent, trace)
        recommendations = self.product_discovery.recommend(message, trace)
        report = self.report.product_report(recommendations, trace)
        self.database.save_report(message.session_id, report)
        self._write_report(report)
        return report

    def run_document_validation(self, message: DocumentPacketMessage):
        intent_name = "kyc_validation" if message.workflow_type == "kyc_validation" else message.workflow_type
        intent = UserIntentMessage(
            session_id=message.session_id,
            customer_type=message.customer_type,
            intent=intent_name,
            raw_input=message.case_type,
        )
        trace = WorkflowTrace(message.session_id)
        self.router.route(intent, trace)
        parsed = self.document_intake.parse(message, trace)
        classified = self.document_classifier.classify(parsed, trace)
        extracted = self.extraction.extract(classified, trace)
        reconciled = self.reconciliation.reconcile(extracted, trace)
        validation = self.validation.validate(
            message.customer_type,
            message.workflow_type,
            message.case_type,
            classified,
            extracted,
            reconciled,
            trace,
            user_inputs=message.user_inputs,
            incident_description=message.incident_description,
            llm_client=self.llm_client,
        )
        validation = self.escalation.decide(validation, trace)
        report = self.report.validation_report(
            message.customer_type,
            message.workflow_type,
            message.case_type,
            validation,
            extracted,
            trace,
            user_inputs=message.user_inputs,
            incident_description=message.incident_description,
        )
        self.database.save_report(message.session_id, report)
        self._write_report(report)
        return report

    @staticmethod
    def new_session_id() -> str:
        return f"SES-{uuid4().hex[:10].upper()}"

    @staticmethod
    def _write_report(report) -> None:
        output_dir = Path("outputs/reports")
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"{report.report_id}.json").write_text(json.dumps(report.json_report, indent=2), encoding="utf-8")
        (output_dir / f"{report.report_id}.md").write_text(report.markdown_report, encoding="utf-8")
