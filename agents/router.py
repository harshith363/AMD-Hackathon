from __future__ import annotations

from orchestrator.trace import WorkflowTrace
from schemas.messages import UserIntentMessage


class RouterAgent:
    name = "Router Agent"

    def route(self, message: UserIntentMessage, trace: WorkflowTrace) -> UserIntentMessage:
        trace.add(self.name, "routed_intent", message.to_dict())
        return message
