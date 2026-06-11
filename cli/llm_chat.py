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
