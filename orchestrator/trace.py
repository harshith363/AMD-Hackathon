from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class WorkflowTrace:
    session_id: str
    events: list[dict[str, Any]] = field(default_factory=list)

    def add(self, agent: str, action: str, detail: dict[str, Any] | None = None) -> None:
        self.events.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "agent": agent,
                "action": action,
                "detail": detail or {},
            }
        )

    def to_list(self) -> list[dict[str, Any]]:
        return list(self.events)
