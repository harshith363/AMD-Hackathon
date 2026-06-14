from __future__ import annotations

import re
from typing import Any

FIELD_PATTERNS = {
    "policy_number": r"(?:policy number|policy no)\s*[:\-]\s*([A-Z0-9\-\/]+)",
    "claim_amount": r"(?:claim amount|total bill|estimated repair|amount)\s*[:\-]\s*(?:INR|Rs\.?)?\s*([0-9,]+)",
    "incident_date": r"(?:incident date|loss date)\s*[:\-]\s*([0-9]{2}[\/\-][0-9]{2}[\/\-][0-9]{4})",
    "customer_name": r"(?:customer name|name)\s*[:\-]\s*([A-Za-z .]+)",
    "patient_name": r"(?:patient name|customer name|name)\s*[:\-]\s*([A-Za-z .]+)",
    "insured_name": r"(?:insured name|customer name|name)\s*[:\-]\s*([A-Za-z .]+)",
    "employee_name": r"(?:employee name|name)\s*[:\-]\s*([A-Za-z .]+)",
    "company_name": r"(?:company name|account holder|insured company)\s*[:\-]\s*([A-Za-z0-9 &.,]+)",
    "pan_number": r"(?:pan number|pan)\s*[:\-]\s*([A-Z]{5}[0-9]{4}[A-Z])",
    "aadhaar_number": r"(?:aadhaar number|aadhar number|aadhaar|aadhar)\s*[:\-]\s*([0-9]{4}\s?[0-9]{4}\s?[0-9]{4})",
    "phone_number": r"(?:phone number|mobile number|phone|mobile)\s*[:\-]\s*(\+?[0-9][0-9 \-]{8,18})",
    "gstin": r"(?:gstin|gst number)\s*[:\-]\s*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])",
    "registered_address": r"(?:registered address|address)\s*[:\-]\s*([A-Za-z0-9 ,.\-/]+)",
    "address": r"(?:residential address|address)\s*[:\-]\s*([A-Za-z0-9 ,.\-/]+)",
    "date_of_birth": r"(?:date of birth|dob)\s*[:\-]\s*([0-9]{2}[\/\-][0-9]{2}[\/\-][0-9]{4})",
    "date_of_death": r"(?:date of death)\s*[:\-]\s*([0-9]{2}[\/\-][0-9]{2}[\/\-][0-9]{4})",
    "authorized_signatory": r"(?:authorized signatory|authorised signatory)\s*[:\-]\s*([A-Za-z .]+)",
    "bank_account_holder": r"(?:account holder|bank account holder)\s*[:\-]\s*([A-Za-z0-9 &.,]+)",
    "vehicle_number": r"(?:vehicle number|registration number)\s*[:\-]\s*([A-Z0-9\-]+)",
    "travel_date": r"(?:travel date|departure date)\s*[:\-]\s*([0-9]{2}[\/\-][0-9]{2}[\/\-][0-9]{4})",
}

VISION_FIELD_NAMES = set(FIELD_PATTERNS)

FALLBACK_FIELD_PATTERNS = {
    "pan_number": [
        r"\b([A-Z]{5}\s*[0-9]{4}\s*[A-Z])\b",
    ],
    "aadhaar_number": [
        r"\b([0-9]{4}[ \t]+[0-9]{4}[ \t]+[0-9]{4})\b",
        r"\b([0-9]{12})\b",
    ],
    "phone_number": [
        r"(?:phone number|mobile number|phone|mobile)\s*[:\-]?\s*(?:\+91[\s-]?)?([6-9][0-9][0-9\s-]{8,14})\b",
    ],
    "date_of_birth": [
        r"(?:date of birth|dob|birth)\s*[:\-]?\s*([0-9]{2}[\/\-][0-9]{2}[\/\-][0-9]{4})",
        r"(?:date of birth|dob|birth)\s*[:\-]?\s*([0-9]{4}[\/\-][0-9]{2}[\/\-][0-9]{2})",
    ],
    "customer_name": [
        r"(?:customer name|name)\s*[:\-]?\s*([A-Za-z][A-Za-z .]{2,80})",
    ],
    "address": [
        r"(?:residential address|address)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9 ,.\-/\n]{5,180})",
    ],
}


def extract_fields(documents: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], float]:
    extracted: dict[str, list[dict[str, str]]] = {}
    evidence: dict[str, list[dict[str, str]]] = {}
    confidences: list[float] = []
    for document in documents:
        text = document.get("extracted_text", "")
        doc_type = document.get("document_type", "unknown")
        confidences.append(float(document.get("confidence", 0.4)))
        for field_name, value in _structured_fields(document).items():
            _add_field(extracted, evidence, field_name, value, doc_type, "vision_extracted_fields")
        for field_name, pattern in FIELD_PATTERNS.items():
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            value = _clean(match.group(1))
            _add_field(extracted, evidence, field_name, value, doc_type, match.group(0)[:160])
        for field_name, patterns in FALLBACK_FIELD_PATTERNS.items():
            if field_name in extracted:
                continue
            for pattern in patterns:
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if not match:
                    continue
                value = _clean_value(field_name, match.group(1))
                if value:
                    _add_field(extracted, evidence, field_name, value, doc_type, match.group(0)[:160])
                    break

    canonical = {
        field_name: values[0]["value"]
        for field_name, values in extracted.items()
        if values
    }
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return {"canonical": canonical, "by_field": extracted}, evidence, round(confidence, 2)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" .,\n\t")


def _structured_fields(document: dict[str, Any]) -> dict[str, str]:
    fields = document.get("vision_extracted_fields") or {}
    if not isinstance(fields, dict):
        return {}
    cleaned: dict[str, str] = {}
    for field_name, value in fields.items():
        if field_name not in VISION_FIELD_NAMES or value in {None, ""}:
            continue
        cleaned_value = _clean_value(field_name, str(value))
        if cleaned_value:
            cleaned[field_name] = cleaned_value
    return cleaned


def _clean_value(field_name: str, value: str) -> str:
    cleaned = _clean(value)
    if field_name == "pan_number":
        return re.sub(r"[^A-Z0-9]", "", cleaned.upper())
    if field_name in {"aadhaar_number", "phone_number"}:
        digits = re.sub(r"\D", "", cleaned)
        if field_name == "aadhaar_number" and len(digits) == 12:
            return f"{digits[:4]} {digits[4:8]} {digits[8:]}"
        if field_name == "phone_number" and len(digits) >= 10:
            return digits[-10:]
    return cleaned


def _add_field(
    extracted: dict[str, list[dict[str, str]]],
    evidence: dict[str, list[dict[str, str]]],
    field_name: str,
    value: str,
    document_type: str,
    snippet: str,
) -> None:
    if any(item["value"] == value and item["document_type"] == document_type for item in extracted.get(field_name, [])):
        return
    extracted.setdefault(field_name, []).append({"value": value, "document_type": document_type})
    evidence.setdefault(field_name, []).append({"document_type": document_type, "snippet": snippet})
