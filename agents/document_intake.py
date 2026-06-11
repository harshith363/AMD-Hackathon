from __future__ import annotations

from document_processing.intake import parse_document
from orchestrator.trace import WorkflowTrace
from schemas.messages import DocumentPacketMessage, ParsedDocumentMessage


class DocumentIntakeAgent:
    name = "Document Intake Agent"

    def parse(self, message: DocumentPacketMessage, trace: WorkflowTrace) -> ParsedDocumentMessage:
        documents = [parse_document(path) for path in message.file_paths]
        trace.add(self.name, "parsed_documents", {"count": len(documents), "ocr_used": [d["ocr_used"] for d in documents]})
        return ParsedDocumentMessage(session_id=message.session_id, documents=documents)
