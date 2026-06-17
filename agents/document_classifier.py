from __future__ import annotations

from document_processing.classifier import classify_document
from orchestrator.trace import WorkflowTrace
from schemas.messages import ClassifiedDocumentMessage, ParsedDocumentMessage


class DocumentClassifierAgent:
    name = "Document Classifier Agent"

    def classify(self, message: ParsedDocumentMessage, trace: WorkflowTrace) -> ClassifiedDocumentMessage:
        documents = [_classify_or_trust_upload_slot(document) for document in message.documents]
        trace.add(self.name, "classified_documents", {"types": [d.get("document_type") for d in documents]})
        return ClassifiedDocumentMessage(session_id=message.session_id, documents=documents)


def _classify_or_trust_upload_slot(document: dict) -> dict:
    copied = dict(document)
    if copied.get("document_type_source") == "upload_slot":
        copied["confidence"] = max(float(copied.get("confidence", 0.5)), 0.9)
        return copied
    return classify_document(copied)
