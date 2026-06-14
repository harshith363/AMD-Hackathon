from __future__ import annotations

from document_processing.intake import parse_document
from orchestrator.trace import WorkflowTrace
from schemas.messages import DocumentPacketMessage, ParsedDocumentMessage


class DocumentIntakeAgent:
    name = "Document Intake Agent"

    def parse(self, message: DocumentPacketMessage, trace: WorkflowTrace, llm_client=None) -> ParsedDocumentMessage:
        vision_extractor = getattr(llm_client, "extract_document_fields_from_file", None)
        prefer_vision = message.customer_type == "individual" and message.workflow_type == "kyc_validation"
        documents = [
            parse_document(path, vision_extractor=vision_extractor, prefer_vision=prefer_vision)
            for path in message.file_paths
        ]
        trace.add(
            self.name,
            "parsed_documents",
            {
                "count": len(documents),
                "ocr_used": [d["ocr_used"] for d in documents],
                "vision_preferred": prefer_vision,
                "vision_fallback": [d.get("vision_fallback_succeeded", False) for d in documents],
                "documents": [_document_debug_summary(document) for document in documents],
            },
        )
        return ParsedDocumentMessage(session_id=message.session_id, documents=documents)


def _document_debug_summary(document):
    debug = document.get("debug", {})
    ocr_debug = debug.get("ocr", {})
    attempts = ocr_debug.get("attempts", [])
    return {
        "file_name": document.get("file_name"),
        "exists": document.get("exists"),
        "document_type": document.get("document_type"),
        "extraction_method": document.get("extraction_method"),
        "confidence": document.get("confidence"),
        "text_length": debug.get("text_length"),
        "text_preview": debug.get("text_preview"),
        "file_size_bytes": debug.get("file_size_bytes"),
        "tesseract_path": ocr_debug.get("tesseract_path"),
        "ocr_attempt_count": len(attempts),
        "ocr_best_attempt": ocr_debug.get("best_attempt"),
        "preprocessing_available": ocr_debug.get("preprocessing_available"),
        "vision_fallback_attempted": debug.get("vision_fallback_attempted", document.get("vision_fallback_attempted", False)),
        "vision_fallback_succeeded": debug.get("vision_fallback_succeeded", document.get("vision_fallback_succeeded", False)),
        "vision_preferred": debug.get("vision_preferred", False),
        "vision_latency_ms": debug.get("vision_latency_ms"),
        "warnings": [*debug.get("warnings", []), *ocr_debug.get("warnings", [])],
    }
