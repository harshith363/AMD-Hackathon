from __future__ import annotations

from typing import Any

from domain_tools import (
    answer_capability_question,
    get_claim_types,
    get_insurance_categories,
    get_supported_workflows,
)
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
        question = next_assistant_question(orchestrator, collected)
        if not question:
            report = run_ready_workflow(orchestrator, collected)
            if report:
                print_summary(report)
                collected = _empty_intake()
                transcript = []
                print()
                print("What would you like to process next?")
                continue

        print(f"\nAssistant: {question}")
        user_text = input("You: ").strip()
        result = process_user_message(orchestrator, collected, transcript, user_text)
        if result["exit_requested"]:
            return
        for message in result["assistant_messages"]:
            print(f"Assistant: {message}")
        collected = result["collected"]
        transcript = result["transcript"]
        if result["report"]:
            print_summary(result["report"])
            collected = _empty_intake()
            transcript = []
            print()
            print("What would you like to process next?")


def next_assistant_question(orchestrator: WorkflowOrchestrator, collected: dict[str, Any]) -> str | None:
    missing = _missing_fields(collected)
    if not missing and collected.get("ready_to_run"):
        return None
    return orchestrator.llm_client.ask_intake_question(collected, missing) or _fallback_question(missing)


def process_user_message(
    orchestrator: WorkflowOrchestrator,
    collected: dict[str, Any],
    transcript: list[dict[str, str]],
    user_text: str,
) -> dict[str, Any]:
    client = orchestrator.llm_client
    if user_text.lower() in {"exit", "quit", "bye"}:
        return {
            "exit_requested": True,
            "assistant_messages": [],
            "collected": collected,
            "transcript": transcript,
            "report": None,
        }

    missing = _missing_fields(collected)
    if _is_clarification_question(user_text, missing):
        answer = _answer_clarification(client, user_text, collected, missing)
        return {
            "exit_requested": False,
            "assistant_messages": [answer],
            "collected": collected,
            "transcript": transcript,
            "report": None,
        }

    updated_transcript = [*transcript, {"role": "user", "content": user_text}]
    extracted = client.extract_intake(updated_transcript, collected, _domain_context(collected))
    if not extracted:
        return {
            "exit_requested": False,
            "assistant_messages": ["I could not parse that cleanly. Please rephrase with the case type, workflow, or file paths."],
            "collected": collected,
            "transcript": updated_transcript,
            "report": None,
        }

    updated_collected = _normalize_intake(_merge_intake(collected, extracted))
    report = run_ready_workflow(orchestrator, updated_collected)
    return {
        "exit_requested": False,
        "assistant_messages": [],
        "collected": updated_collected,
        "transcript": updated_transcript,
        "report": report,
    }


def run_ready_workflow(orchestrator: WorkflowOrchestrator, collected: dict[str, Any]):
    missing = _missing_fields(collected)
    if missing or not collected.get("ready_to_run"):
        return None
    return _run_collected_workflow(orchestrator, collected)


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
    if any(word in normalized.split() for word in ["options", "option", "help"]):
        return bool(missing)
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
    tool_result = answer_capability_question(user_text, collected, missing)
    return client.answer_with_tool_result(user_text, collected, missing, tool_result) or _format_tool_result(tool_result, missing)


def _domain_context(collected: dict[str, Any]) -> dict[str, Any]:
    customer_type = collected.get("customer_type")
    return {
        "supported_workflows": get_supported_workflows(customer_type),
        "insurance_categories": get_insurance_categories(customer_type),
        "claim_types": get_claim_types(customer_type),
    }


def _format_tool_result(tool_result: dict[str, Any], missing: list[str]) -> str:
    tool_name = tool_result.get("tool")
    if tool_name == "get_supported_workflows":
        labels = [item["label"] for item in tool_result["workflows"]]
        return f"I can help you {', '.join(labels)}. Which one would you like to do?"
    if tool_name == "get_insurance_categories":
        categories = tool_result["categories"]
        if isinstance(categories, dict):
            business = ", ".join(_display_label(item) for item in categories["business"])
            individual = ", ".join(_display_label(item) for item in categories["individual"])
            return f"Business categories: {business}. Individual categories: {individual}. Which category should I use?"
        return f"I can search these insurance categories: {', '.join(_display_label(item) for item in categories)}. Which category should I use?"
    if tool_name == "get_claim_types":
        claim_types = tool_result["claim_types"]
        if isinstance(claim_types, dict):
            business = ", ".join(_display_label(item) for item in claim_types["business"])
            individual = ", ".join(_display_label(item) for item in claim_types["individual"])
            return f"Business claim types: {business}. Individual claim types: {individual}. Which claim type is this?"
        return f"I can validate these claim types: {', '.join(_display_label(item) for item in claim_types)}. Which claim type is this?"
    if tool_name == "get_required_documents":
        documents = tool_result["required_documents"]
        if documents:
            return f"I need these documents: {', '.join(documents)}. Please provide the file paths."
        return "Please provide the document file paths you want me to validate."
    return _fallback_question(missing)


def _display_label(value: str) -> str:
    return value.replace("_", " ")
