from __future__ import annotations

from collections import defaultdict
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
                grouped[_normalize(item["value"])].append(item["document_type"])
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


def _normalize(value: str) -> str:
    return " ".join(value.lower().replace(".", "").replace(",", "").split())
