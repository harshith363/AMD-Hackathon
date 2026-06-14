from __future__ import annotations

from typing import Any

DOCUMENT_HINTS = {
    "claim_form": ["claim form", "claim amount", "incident date"],
    "policy_copy": ["policy number", "sum insured", "policy copy"],
    "incident_report": ["incident report", "damage description"],
    "repair_estimate": ["repair estimate", "estimated repair"],
    "hospital_bill": ["hospital bill", "invoice", "total bill"],
    "discharge_summary": ["discharge summary", "admission date", "discharge date"],
    "death_certificate": ["death certificate", "date of death"],
    "employee_id_proof": ["employee id", "employee code"],
    "nominee_id_proof": ["nominee", "identity proof"],
    "legal_notice": ["legal notice", "plaintiff", "notice"],
    "client_contract": ["client contract", "agreement"],
    "incident_summary": ["incident summary", "professional service"],
    "registration_certificate": ["registration certificate", "vehicle number"],
    "driving_license": ["driving license", "license number"],
    "ticket_or_itinerary": ["ticket", "itinerary", "pnr"],
    "expense_receipts": ["receipt", "expense"],
    "medical_report": ["medical report", "diagnosis"],
    "identity_proof": ["aadhaar", "passport", "identity proof", "date of birth"],
    "pan": ["permanent account number", "pan number"],
    "address_proof": ["address proof", "residential address"],
    "bank_proof": ["bank account", "ifsc", "account holder"],
    "certificate_of_incorporation": ["certificate of incorporation", "cin"],
    "company_pan": ["company pan", "permanent account number"],
    "gst_certificate": ["gstin", "gst certificate"],
    "registered_address_proof": ["registered address proof", "registered address"],
    "board_resolution": ["board resolution", "authorized signatory"],
    "authorized_signatory_id_proof": ["authorized signatory", "identity proof"],
    "authorized_signatory_address_proof": ["authorized signatory", "address proof"],
    "beneficial_ownership_declaration": ["beneficial ownership", "beneficial owner"],
    "bank_account_proof": ["bank account", "account holder", "current account"],
}


def classify_document(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("extraction_method") == "vision_llm" and document.get("document_type") != "unknown":
        document["confidence"] = max(float(document.get("confidence", 0.5)), 0.88)
        return document
    text = document.get("extracted_text", "").lower()
    file_name = document.get("file_name", "").lower().replace("-", "_").replace(" ", "_")
    file_stem = file_name.rsplit(".", 1)[0]
    scores: dict[str, int] = {}
    for doc_type, hints in DOCUMENT_HINTS.items():
        score = sum(1 for hint in hints if hint in text or hint.replace(" ", "_") in file_name)
        if doc_type == file_stem:
            score += 10
        if doc_type in file_name:
            score += 3
        if score:
            scores[doc_type] = score
    if scores:
        document["document_type"] = max(scores, key=scores.get)
        document["confidence"] = max(float(document.get("confidence", 0.5)), min(0.99, 0.55 + (max(scores.values()) * 0.1)))
    return document
