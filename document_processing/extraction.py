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


def extract_fields(documents: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], float]:
    extracted: dict[str, list[dict[str, str]]] = {}
    evidence: dict[str, list[dict[str, str]]] = {}
    confidences: list[float] = []
    for document in documents:
        text = document.get("extracted_text", "")
        doc_type = document.get("document_type", "unknown")
        confidences.append(float(document.get("confidence", 0.4)))
        for field_name, pattern in FIELD_PATTERNS.items():
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if not match:
                continue
            value = _clean(match.group(1))
            extracted.setdefault(field_name, []).append({"value": value, "document_type": doc_type})
            evidence.setdefault(field_name, []).append({"document_type": doc_type, "snippet": match.group(0)[:160]})

    canonical = {
        field_name: values[0]["value"]
        for field_name, values in extracted.items()
        if values
    }
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return {"canonical": canonical, "by_field": extracted}, evidence, round(confidence, 2)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" .,\n\t")
