from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


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
    def from_config(
        cls,
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: int | None = None,
        enabled: bool = False,
    ) -> "VLLMClient":
        return cls(
            base_url=(base_url or "http://localhost:8000/v1").rstrip("/"),
            model=model or "amd-hackathon-model",
            api_key=api_key or "EMPTY",
            timeout_seconds=timeout_seconds or 20,
            enabled=enabled,
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
            return self.chat(prompt, max_tokens=220, temperature=0.2)
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
            return None

    def ask_intake_question(self, collected: dict[str, Any], missing: list[str]) -> str | None:
        if not self.enabled:
            return None
        prompt = (
            "You are running an insurance operations CLI. Ask exactly one short, natural question "
            "to collect the next missing item. Do not show numbered options. Do not explain features.\n\n"
            f"Collected so far: {json.dumps(collected, indent=2)}\n"
            f"Missing fields: {json.dumps(missing)}"
        )
        try:
            return self.chat(
                prompt,
                system="You are a concise insurance assistant that asks one question at a time.",
                max_tokens=80,
                temperature=0.3,
            )
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
            return None

    def answer_clarification(self, user_text: str, collected: dict[str, Any], missing: list[str]) -> str | None:
        if not self.enabled:
            return None
        prompt = (
            "The user asked a clarification question during an insurance CLI intake. "
            "Answer briefly and helpfully using only the supported capabilities below. "
            "Do not invent unsupported workflows. End by asking one natural follow-up question "
            "for the next missing field.\n\n"
            "Supported customer types: business, individual.\n"
            "Supported workflows: find new insurance, validate claim documents, complete KYC/KYB validation.\n"
            "Business new insurance categories: property, employee life, employee health, professional liability.\n"
            "Individual new insurance categories: health, life, motor, travel, home, personal accident.\n"
            "Business claim types: property damage, employee health, employee life, professional liability.\n"
            "Individual claim types: health, life, motor, travel, home, personal accident.\n"
            "For document validation, users provide local file paths for PDFs, images, or TXT files.\n\n"
            f"Collected so far: {json.dumps(collected, indent=2)}\n"
            f"Missing fields: {json.dumps(missing)}\n"
            f"User question: {user_text}"
        )
        try:
            return self.chat(
                prompt,
                system="You answer clarification questions in a concise insurance operations CLI.",
                max_tokens=180,
                temperature=0.2,
            )
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
            return None

    def extract_intake(self, transcript: list[dict[str, str]], current: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        prompt = (
            "Extract structured insurance workflow intake from the transcript. Return JSON only. "
            "Do not include markdown. Preserve existing values unless the user clearly changes them.\n\n"
            "Allowed customer_type values: business, individual.\n"
            "Allowed workflow_type values: new_insurance, claim_validation, kyc_validation, kyb_validation.\n"
            "Business insurance categories: property, employee_life, employee_health, professional_liability.\n"
            "Individual insurance categories: health, life, motor, travel, home, personal_accident.\n"
            "Business claim types: property_damage, employee_health, employee_life, professional_liability.\n"
            "Individual claim types: health, life, motor, travel, home, personal_accident.\n"
            "For document workflows, collect file_paths as a JSON array of strings.\n"
            "For product discovery, collect user_inputs as a JSON object of any business/customer details.\n"
            "Set ready_to_run true only when the user says to run, submit, start, validate, proceed, or has provided file paths for a document workflow.\n\n"
            "Return this JSON shape:\n"
            "{"
            "\"customer_type\": null,"
            "\"workflow_type\": null,"
            "\"insurance_category\": null,"
            "\"case_type\": null,"
            "\"file_paths\": [],"
            "\"user_inputs\": {},"
            "\"ready_to_run\": false"
            "}\n\n"
            f"Existing values: {json.dumps(current, indent=2)}\n"
            f"Transcript: {json.dumps(transcript, indent=2)}"
        )
        try:
            content = self.chat(
                prompt,
                system="You are a precise JSON extraction engine for an insurance CLI.",
                max_tokens=420,
                temperature=0.0,
            )
            return _extract_json_object(content)
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
            return None

    def chat(
        self,
        prompt: str,
        *,
        system: str = "You explain insurance workflow results clearly while preserving deterministic rule outcomes.",
        max_tokens: int = 220,
        temperature: float = 0.2,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system,
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
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


def _extract_json_object(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    parsed = json.loads(text[start : end + 1])
    return parsed if isinstance(parsed, dict) else None
