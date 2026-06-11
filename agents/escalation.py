from __future__ import annotations

from orchestrator.trace import WorkflowTrace
from schemas.messages import ValidationResultMessage


class EscalationAgent:
    name = "Escalation Agent"

    def decide(self, message: ValidationResultMessage, trace: WorkflowTrace) -> ValidationResultMessage:
        trace.add(self.name, "decided_escalation", {"human_review_required": message.human_review_required})
        return message
