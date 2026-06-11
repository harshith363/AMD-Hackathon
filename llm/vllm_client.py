from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from config import load_dotenv


@dataclass
class VLLMClient:
    """Small OpenAI-compatible client for vLLM servers.

    vLLM commonly exposes an OpenAI-compatible API at /v1/chat/completions.
    This client intentionally uses the Python standard library so the project
    remains easy to run inside AMD Jupyter notebook cloud images.
    """

    base_url: str = "http://localhost:8000/v1"
    model: str = "amd-hackathon-model"
    api_key: str = "EMPTY"
    timeout_seconds: int = 20
    enabled: bool = False

    @classmethod
    def from_env(cls, enabled: bool | None = None) -> "VLLMClient":
        load_dotenv()
        env_enabled = os.getenv("INSURANCE_USE_LLM", "").lower() in {"1", "true", "yes", "on"}
        return cls(
            base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1").rstrip("/"),
            model=os.getenv("VLLM_MODEL", "amd-hackathon-model"),
            api_key=os.getenv("VLLM_API_KEY", "EMPTY"),
            timeout_seconds=int(os.getenv("VLLM_TIMEOUT_SECONDS", "20")),
            enabled=env_enabled if enabled is None else enabled,
        )

    def explain_report(self, report: dict[str, Any]) -> str | None:
        if not self.enabled:
            return None
        prompt = (
            "Write a concise insurance operations explanation for this validation or "
            "recommendation report. Do not change the deterministic status or missing "
            "documents. Keep it suitable for a hackathon CLI demo.\n\n"
            f"{json.dumps(_compact_report(report), indent=2)}"
        )
        try:
            return self.chat(prompt)
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
            return None

    def chat(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You explain insurance workflow results clearly while preserving deterministic rule outcomes.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 220,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()


def _compact_report(report: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "workflow_type",
        "customer_type",
        "case_type",
        "status",
        "confidence",
        "human_review_required",
        "missing_documents",
        "validation_issues",
        "next_action",
        "recommendations",
    ]
    return {key: report[key] for key in keys if key in report}
