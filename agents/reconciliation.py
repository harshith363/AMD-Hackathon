from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from orchestrator.trace import WorkflowTrace
from schemas.messages import ExtractionResultMessage, ReconciliationMessage


class ReconciliationAgent:
    name = "Reconciliation Agent"

    def reconcile(self, message: ExtractionResultMessage, trace: WorkflowTrace) -> ReconciliationMessage:
        inconsistencies: list[dict[str, Any]] = []
        canonical_fields = message.extracted_fields.get("canonical", {})
        for field_name, values in message.extracted_fields.get("by_field", {}).items():
            grouped = defaultdict(list)
            for item in values:
                grouped[_normalize(field_name, item["value"])].append(item["document_type"])
            if len(grouped) > 1:
                inconsistencies.append(
                    {
                        "severity": "medium",
                        "field": field_name,
                        "message": f"{field_name} mismatch across documents",
                        "values": dict(grouped),
                    }
                )
        trace.add(self.name, "reconciled_fields", {"inconsistency_count": len(inconsistencies)})
        return ReconciliationMessage(
            session_id=message.session_id,
            inconsistencies=inconsistencies,
            canonical_fields=canonical_fields,
        )


def _normalize(field_name: str, value: str) -> str:
    if field_name in {"aadhaar_number", "phone_number"}:
        return re.sub(r"\D", "", value)
    if field_name in {"pan_number", "gstin"}:
        return re.sub(r"[^A-Z0-9]", "", value.upper())
    return " ".join(value.lower().replace(".", "").replace(",", "").split())
