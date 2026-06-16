from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
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
            "documents. Keep it suitable for a hackathon application.\n\n"
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

    def answer_with_tool_result(
        self,
        user_text: str,
        collected: dict[str, Any],
        missing: list[str],
        tool_result: dict[str, Any],
    ) -> str | None:
        if not self.enabled:
            return None
        prompt = (
            "The user asked a clarification question during insurance workflow intake. "
            "Answer using only the provided tool result. Do not invent options that are not in the tool result. "
            "Keep it concise and end with one natural follow-up question for the next missing field.\n\n"
            f"Collected so far: {json.dumps(collected, indent=2)}\n"
            f"Missing fields: {json.dumps(missing)}\n"
            f"User question: {user_text}\n"
            f"Tool result: {json.dumps(tool_result, indent=2)}"
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

    def extract_intake(
        self,
        transcript: list[dict[str, str]],
        current: dict[str, Any],
        domain_context: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        prompt = (
            "Extract structured insurance workflow intake from the transcript. Return JSON only. "
            "Do not include markdown. Preserve existing values unless the user clearly changes them.\n\n"
            "Use the domain context for allowed workflow types, insurance categories, and claim types. "
            "Do not invent values outside the domain context.\n"
            "For document workflows, collect file_paths as a JSON array of strings. "
            "For claim workflows, collect incident_description when the user describes what happened.\n"
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
            "\"incident_description\": null,"
            "\"ready_to_run\": false"
            "}\n\n"
            f"Existing values: {json.dumps(current, indent=2)}\n"
            f"Domain context: {json.dumps(domain_context, indent=2)}\n"
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

    def validate_application_details(self, details: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        prompt = (
            "Validate these individual insurance application details. Return JSON only with keys "
            "is_valid, issues, and normalized_details. Check that name, date_of_birth, address, "
            "phone_number, job, and annual_income are plausible and present. Do not reject just "
            "because the details are brief.\n\n"
            f"Details: {json.dumps(details, indent=2)}"
        )
        try:
            content = self.chat(
                prompt,
                system="You validate insurance application details and return compact JSON only.",
                max_tokens=260,
                temperature=0.0,
            )
            return _extract_json_object(content)
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
            return None

    def verify_identity_consistency(self, user_details: dict[str, Any], extracted_fields: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        prompt = (
            "Compare user-provided details with fields extracted from PAN/Aadhaar/identity documents. "
            "The match does not need to be exact, but it must be consistent. Return JSON only with "
            "keys is_consistent, match_level, issues, and confidence. Use match_level='consistent' when "
            "details agree, 'partial' when there is some overlap or a plausible near match that should be "
            "reviewed by a human, and 'clear_mismatch' when the values are completely different and corrected "
            "documents should be requested. Treat abbreviations, casing, and minor spelling differences as acceptable.\n\n"
            f"User details: {json.dumps(user_details, indent=2)}\n"
            f"Extracted fields: {json.dumps(extracted_fields, indent=2)}"
        )
        try:
            content = self.chat(
                prompt,
                system="You verify KYC consistency and return compact JSON only.",
                max_tokens=260,
                temperature=0.0,
            )
            return _extract_json_object(content)
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
            return None

    def summarize_kyc_fields(self, payload: dict[str, Any]) -> str | None:
        if not self.enabled:
            return None
        prompt = (
            "Write a very precise KYC field summary for the user. Mention fields parsed from each document, "
            "then state whether the details appear aligned. Do not add legal advice or extra workflow steps. "
            "Keep it under 120 words.\n\n"
            f"{json.dumps(payload, indent=2)}"
        )
        try:
            return self.chat(
                prompt,
                system="You summarize parsed KYC fields precisely and concisely.",
                max_tokens=180,
                temperature=0.0,
            )
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
            return None

    def extract_document_fields_from_file(self, path: Path) -> dict[str, Any] | None:
        if not self.enabled or not path.exists():
            return None
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if not (mime_type.startswith("image/") or mime_type == "application/pdf"):
            return None
        data_url = f"data:{mime_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
        prompt = (
            "Parse this Indian insurance/KYC document. Return JSON only. If a field is not visible, use null. "
            "Use document_type as one of pan, identity_proof, address_proof, bank_proof, claim_form, "
            "policy_copy, hospital_bill, discharge_summary, unknown. Extract these fields where visible: "
            "customer_name, date_of_birth, pan_number, aadhaar_number, address, phone_number, "
            "policy_number, patient_name, insured_name, claim_amount, incident_date.\n\n"
            "Return shape: {\"document_type\":\"unknown\",\"fields\":{},\"summary\":\"\"}. "
            "Every value inside fields must be a string or null, never an object or array."
        )
        try:
            content = self.chat_multimodal(
                prompt,
                data_url,
                system="You are a precise document parsing engine. Return JSON only.",
                max_tokens=420,
                temperature=0.0,
            )
            parsed = _extract_json_object(content)
            return parsed if isinstance(parsed, dict) else None
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

    def chat_multimodal(
        self,
        prompt: str,
        data_url: str,
        *,
        system: str,
        max_tokens: int = 420,
        temperature: float = 0.0,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_url}},
                        {"type": "text", "text": prompt},
                    ],
                },
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
