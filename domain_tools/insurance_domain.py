from __future__ import annotations

from typing import Any

from mcp_server.client import get_business_insurance_schemes, get_individual_insurance_schemes
from rules.claim_rules import CLAIM_RULES
from rules.kyc_rules import KYC_RULES

WORKFLOWS = [
    {
        "workflow_type": "new_insurance",
        "label": "find new insurance",
        "description": "Search the product catalogue and recommend matching insurance schemes.",
    },
    {
        "workflow_type": "claim_validation",
        "label": "validate claim documents",
        "description": "Parse uploaded documents, classify them, extract fields, and validate claim requirements.",
    },
    {
        "workflow_type": "kyc_validation",
        "label": "complete KYC validation",
        "description": "Validate individual identity, address, PAN, and bank proof documents.",
        "customer_type": "individual",
    },
    {
        "workflow_type": "kyb_validation",
        "label": "complete KYB validation",
        "description": "Validate business registration, tax, signatory, ownership, address, and bank documents.",
        "customer_type": "business",
    },
]


def get_supported_workflows(customer_type: str | None = None) -> dict[str, Any]:
    workflows = [
        workflow
        for workflow in WORKFLOWS
        if workflow.get("customer_type") in {None, customer_type}
    ]
    return {"tool": "get_supported_workflows", "customer_type": customer_type, "workflows": workflows}


def get_insurance_categories(customer_type: str | None) -> dict[str, Any]:
    if customer_type == "business":
        categories = _catalog_categories("business")
    elif customer_type == "individual":
        categories = _catalog_categories("individual")
    else:
        categories = {"business": _catalog_categories("business"), "individual": _catalog_categories("individual")}
    return {"tool": "get_insurance_categories", "customer_type": customer_type, "categories": categories}


def get_claim_types(customer_type: str | None) -> dict[str, Any]:
    if customer_type in CLAIM_RULES:
        claim_types: Any = sorted(CLAIM_RULES[customer_type].keys())
    else:
        claim_types = {key: sorted(value.keys()) for key, value in CLAIM_RULES.items()}
    return {"tool": "get_claim_types", "customer_type": customer_type, "claim_types": claim_types}


def get_required_documents(customer_type: str | None, workflow_type: str | None, case_type: str | None = None) -> dict[str, Any]:
    if workflow_type == "claim_validation" and customer_type in CLAIM_RULES and case_type in CLAIM_RULES[customer_type]:
        required = CLAIM_RULES[customer_type][case_type]["required_documents"]
    elif workflow_type == "kyc_validation":
        required = KYC_RULES["individual"]["required_documents"]
    elif workflow_type == "kyb_validation":
        required = KYC_RULES["business"]["required_documents"]
    else:
        required = []
    return {
        "tool": "get_required_documents",
        "customer_type": customer_type,
        "workflow_type": workflow_type,
        "case_type": case_type,
        "required_documents": required,
        "supported_file_inputs": ["txt", "pdf", "png", "jpg", "jpeg", "tiff", "bmp", "webp"],
    }


def get_product_catalog_options(customer_type: str | None, category: str | None = None) -> dict[str, Any]:
    if customer_type == "business":
        schemes = get_business_insurance_schemes(category or "", {})
    elif customer_type == "individual":
        schemes = get_individual_insurance_schemes(category or "", {})
    else:
        schemes = []
    return {
        "tool": "get_product_catalog_options",
        "customer_type": customer_type,
        "category": category,
        "schemes": schemes,
    }


def answer_capability_question(user_text: str, collected: dict[str, Any], missing: list[str]) -> dict[str, Any]:
    normalized = user_text.lower()
    customer_type = collected.get("customer_type")
    workflow_type = collected.get("workflow_type")
    case_type = collected.get("case_type")

    if "document" in normalized or "file" in normalized:
        return get_required_documents(customer_type, workflow_type, case_type)
    if "claim" in normalized and (workflow_type == "claim_validation" or "claim_type" in missing):
        return get_claim_types(customer_type)
    if "categor" in normalized or workflow_type == "new_insurance" and any(item in missing for item in ["insurance_category", "basic customer or business details"]):
        return get_insurance_categories(customer_type)
    if "option" in normalized or "workflow" in normalized or "what can" in normalized or "help" in normalized:
        if not workflow_type or "workflow_type" in missing:
            return get_supported_workflows(customer_type)
        if workflow_type == "new_insurance":
            return get_insurance_categories(customer_type)
        if workflow_type == "claim_validation":
            return get_claim_types(customer_type)
        return get_required_documents(customer_type, workflow_type, case_type)
    return get_supported_workflows(customer_type)


def _catalog_categories(customer_type: str) -> list[str]:
    getter = get_business_insurance_schemes if customer_type == "business" else get_individual_insurance_schemes
    categories = []
    # The catalogue client filters by category, so derive supported categories
    # from known product data through the catalogue file used by that client.
    from mcp_server.client import _load_catalog

    for product in _load_catalog():
        if product["customer_type"] == customer_type:
            categories.append(product["category"])
    return sorted(set(categories))
