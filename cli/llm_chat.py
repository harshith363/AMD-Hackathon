from __future__ import annotations

from typing import Any

from orchestrator.workflow import WorkflowOrchestrator
from schemas.messages import DocumentPacketMessage, ProductDiscoveryMessage


def run_llm_interactive(orchestrator: WorkflowOrchestrator, print_summary) -> None:
    client = orchestrator.llm_client
    if not client.enabled:
        print("Interactive mode requires a vLLM/OpenAI-compatible endpoint.")
        print("Run with --use-llm and pass --vllm-base-url plus --vllm-model.")
        return

    print("Insurance Operations Assistant")
    print("Tell me what you need. You can mention business/individual, the workflow, details, and document paths naturally.")
    collected: dict[str, Any] = _empty_intake()
    transcript: list[dict[str, str]] = []

    while True:
        missing = _missing_fields(collected)
        if not missing and collected.get("ready_to_run"):
            report = _run_collected_workflow(orchestrator, collected)
            print_summary(report)
            collected = _empty_intake()
            transcript = []
            print()
            print("What would you like to process next?")
            continue

        question = client.ask_intake_question(collected, missing) or _fallback_question(missing)
        print(f"\nAssistant: {question}")
        user_text = input("You: ").strip()
        if user_text.lower() in {"exit", "quit", "bye"}:
            return
        if _is_clarification_question(user_text, missing):
            answer = _answer_clarification(client, user_text, collected, missing)
            print(f"Assistant: {answer}")
            continue
        transcript.append({"role": "user", "content": user_text})
        extracted = client.extract_intake(transcript, collected)
        if not extracted:
            print("Assistant: I could not parse that cleanly. Please rephrase with the case type, workflow, or file paths.")
            continue
        collected = _merge_intake(collected, extracted)
        collected = _normalize_intake(collected)


def _empty_intake() -> dict[str, Any]:
    return {
        "customer_type": None,
        "workflow_type": None,
        "insurance_category": None,
        "case_type": None,
        "file_paths": [],
        "user_inputs": {},
        "ready_to_run": False,
    }


def _missing_fields(collected: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not collected.get("customer_type"):
        missing.append("customer_type")
    if not collected.get("workflow_type"):
        missing.append("workflow_type")
    workflow = collected.get("workflow_type")
    if workflow == "new_insurance":
        if not collected.get("insurance_category"):
            missing.append("insurance_category")
        if not collected.get("user_inputs"):
            missing.append("basic customer or business details")
        if not collected.get("ready_to_run"):
            missing.append("confirmation to run product discovery")
    elif workflow in {"claim_validation", "kyc_validation", "kyb_validation"}:
        if workflow == "claim_validation" and not collected.get("case_type"):
            missing.append("claim_type")
        if not collected.get("file_paths"):
            missing.append("document file paths")
    return missing


def _merge_intake(current: dict[str, Any], extracted: dict[str, Any]) -> dict[str, Any]:
    merged = dict(current)
    for key in ["customer_type", "workflow_type", "insurance_category", "case_type"]:
        if extracted.get(key):
            merged[key] = extracted[key]
    if extracted.get("file_paths"):
        merged["file_paths"] = extracted["file_paths"]
    if isinstance(extracted.get("user_inputs"), dict):
        merged["user_inputs"] = {**merged.get("user_inputs", {}), **extracted["user_inputs"]}
    if extracted.get("ready_to_run"):
        merged["ready_to_run"] = True
    return merged


def _normalize_intake(collected: dict[str, Any]) -> dict[str, Any]:
    if collected.get("customer_type") == "business" and collected.get("workflow_type") == "kyc_validation":
        collected["workflow_type"] = "kyb_validation"
    if collected.get("customer_type") == "individual" and collected.get("workflow_type") == "kyb_validation":
        collected["workflow_type"] = "kyc_validation"
    if collected.get("workflow_type") in {"kyc_validation", "kyb_validation"}:
        collected["case_type"] = "kyc" if collected["workflow_type"] == "kyc_validation" else "kyb"
    if collected.get("file_paths"):
        collected["ready_to_run"] = True
    return collected


def _run_collected_workflow(orchestrator: WorkflowOrchestrator, collected: dict[str, Any]):
    if collected["workflow_type"] == "new_insurance":
        return orchestrator.run_product_discovery(
            ProductDiscoveryMessage(
                session_id=orchestrator.new_session_id(),
                customer_type=collected["customer_type"],
                insurance_category=collected["insurance_category"],
                user_inputs=collected["user_inputs"],
            )
        )
    return orchestrator.run_document_validation(
        DocumentPacketMessage(
            session_id=orchestrator.new_session_id(),
            customer_type=collected["customer_type"],
            workflow_type=collected["workflow_type"],
            case_type=collected["case_type"],
            file_paths=collected["file_paths"],
        )
    )


def _fallback_question(missing: list[str]) -> str:
    if not missing:
        return "Say run when you want me to process this."
    return f"Please share the {missing[0].replace('_', ' ')}."


def _is_clarification_question(user_text: str, missing: list[str]) -> bool:
    normalized = user_text.lower().strip()
    if "?" in normalized:
        return True
    clarification_phrases = [
        "what options",
        "what can you",
        "what do you",
        "help",
        "examples",
        "show options",
        "list options",
        "available options",
        "which options",
        "what workflows",
        "what categories",
        "what documents",
    ]
    return any(phrase in normalized for phrase in clarification_phrases) and bool(missing)


def _answer_clarification(client, user_text: str, collected: dict[str, Any], missing: list[str]) -> str:
    deterministic = _deterministic_clarification(user_text, collected, missing)
    if deterministic:
        return deterministic
    return client.answer_clarification(user_text, collected, missing) or _fallback_question(missing)


def _deterministic_clarification(user_text: str, collected: dict[str, Any], missing: list[str]) -> str | None:
    normalized = user_text.lower()
    customer_type = collected.get("customer_type")
    workflow = collected.get("workflow_type")

    if "option" in normalized or "workflow" in normalized or "what can" in normalized or "help" in normalized:
        if not workflow:
            return (
                "I can help you find new insurance, validate claim documents, or complete KYC/KYB validation. "
                "Which one would you like to do?"
            )
        if workflow == "new_insurance":
            if customer_type == "business":
                return (
                    "For a business, I can search property, employee life, employee health, or professional liability insurance. "
                    "Which category should I use?"
                )
            if customer_type == "individual":
                return (
                    "For an individual, I can search health, life, motor, travel, home, or personal accident insurance. "
                    "Which category should I use?"
                )
        if workflow == "claim_validation":
            if customer_type == "business":
                return (
                    "For business claims, I can validate property damage, employee health, employee life, or professional liability claims. "
                    "Which claim type is this?"
                )
            if customer_type == "individual":
                return (
                    "For individual claims, I can validate health, life, motor, travel, home, or personal accident claims. "
                    "Which claim type is this?"
                )

    if "document" in normalized:
        if workflow in {"claim_validation", "kyc_validation", "kyb_validation"}:
            return (
                "Please provide local file paths to the documents. I can process TXT files now and will use PDF/image extraction when those tools are available. "
                "What file paths should I validate?"
            )

    if "categor" in normalized and workflow == "new_insurance":
        if customer_type == "business":
            return "Business insurance categories are property, employee life, employee health, and professional liability. Which one do you want?"
        if customer_type == "individual":
            return "Individual insurance categories are health, life, motor, travel, home, and personal accident. Which one do you want?"

    return None
