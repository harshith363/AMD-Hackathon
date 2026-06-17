from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rules.claim_rules import CLAIM_RULES

CATALOG_PATH = Path(__file__).with_name("insurance_catalog.json")


def _load_catalog() -> list[dict[str, Any]]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def get_business_insurance_schemes(category: str, user_inputs: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _filter_schemes("business", category)


def get_individual_insurance_schemes(category: str, user_inputs: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _filter_schemes("individual", category)


def get_claim_compliance_rules(customer_type: str, claim_type: str) -> dict[str, Any]:
    return CLAIM_RULES.get(customer_type, {}).get(claim_type, {})


def _filter_schemes(customer_type: str, category: str) -> list[dict[str, Any]]:
    normalized = category.lower().replace(" insurance", "").replace(" ", "_")
    matches = [
        product
        for product in _load_catalog()
        if product["customer_type"] == customer_type and product["category"] == normalized
    ]
    return matches
