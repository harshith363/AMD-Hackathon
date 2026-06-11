from __future__ import annotations

from document_processing.extraction import extract_fields
from orchestrator.trace import WorkflowTrace
from schemas.messages import ClassifiedDocumentMessage, ExtractionResultMessage


class ExtractionAgent:
    name = "Extraction Agent"

    def extract(self, message: ClassifiedDocumentMessage, trace: WorkflowTrace) -> ExtractionResultMessage:
        extracted_fields, evidence, confidence = extract_fields(message.documents)
        trace.add(self.name, "extracted_fields", {"fields": sorted(extracted_fields.get("canonical", {}).keys())})
        return ExtractionResultMessage(
            session_id=message.session_id,
            extracted_fields=extracted_fields,
            evidence=evidence,
            confidence=confidence,
        )
