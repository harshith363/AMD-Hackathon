from __future__ import annotations

from document_processing.classifier import classify_document
from orchestrator.trace import WorkflowTrace
from schemas.messages import ClassifiedDocumentMessage, ParsedDocumentMessage


class DocumentClassifierAgent:
    name = "Document Classifier Agent"

    def classify(self, message: ParsedDocumentMessage, trace: WorkflowTrace) -> ClassifiedDocumentMessage:
        documents = [classify_document(dict(document)) for document in message.documents]
        trace.add(self.name, "classified_documents", {"types": [d.get("document_type") for d in documents]})
        return ClassifiedDocumentMessage(session_id=message.session_id, documents=documents)
