from __future__ import annotations

import argparse
from pathlib import Path

from cli.llm_chat import run_llm_interactive
from orchestrator.workflow import WorkflowOrchestrator
from schemas.messages import DocumentPacketMessage, ProductDiscoveryMessage


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic Insurance Operations Assistant")
    parser.add_argument("--demo", choices=["all", "1", "2", "3", "4", "5"], help="Run scripted demo scenario")
    parser.add_argument("--use-llm", action="store_true", help="Use vLLM/OpenAI-compatible endpoint")
    parser.add_argument("--vllm-base-url", default="http://localhost:8000/v1", help="vLLM OpenAI-compatible base URL")
    parser.add_argument("--vllm-model", default="amd-hackathon-model", help="vLLM served model name")
    parser.add_argument("--vllm-api-key", default="EMPTY", help="API key for OpenAI-compatible vLLM endpoint")
    parser.add_argument("--vllm-timeout-seconds", type=int, default=20, help="vLLM request timeout")
    args = parser.parse_args()
    orchestrator = WorkflowOrchestrator(
        use_llm=args.use_llm or args.demo is None,
        vllm_base_url=args.vllm_base_url,
        vllm_model=args.vllm_model,
        vllm_api_key=args.vllm_api_key,
        vllm_timeout_seconds=args.vllm_timeout_seconds,
    )
    if args.demo:
        run_demo(orchestrator, args.demo)
    else:
        run_interactive(orchestrator)


def run_interactive(orchestrator: WorkflowOrchestrator) -> None:
    run_llm_interactive(orchestrator, print_cli_summary)


def run_demo(orchestrator: WorkflowOrchestrator, selected: str) -> None:
    scenarios = {
        "1": lambda: orchestrator.run_product_discovery(
            ProductDiscoveryMessage(
                session_id=orchestrator.new_session_id(),
                customer_type="business",
                insurance_category="property",
                user_inputs={"company_name": "Acme Components Pvt Ltd", "employees": "48"},
            )
        ),
        "2": lambda: orchestrator.run_document_validation(
            _packet(orchestrator, "business", "claim_validation", "property_damage", "demo_data/business_property_claim")
        ),
        "3": lambda: orchestrator.run_document_validation(
            _packet(orchestrator, "individual", "claim_validation", "health", "demo_data/individual_health_claim")
        ),
        "4": lambda: orchestrator.run_document_validation(
            _packet(orchestrator, "business", "kyb_validation", "kyb", "demo_data/business_kyb")
        ),
        "5": lambda: orchestrator.run_document_validation(
            _packet(orchestrator, "individual", "kyc_validation", "kyc", "demo_data/individual_kyc_mismatch")
        ),
    }
    keys = list(scenarios) if selected == "all" else [selected]
    for key in keys:
        print(f"\n=== Demo {key} ===")
        report = scenarios[key]()
        print_cli_summary(report)


def _packet(orchestrator: WorkflowOrchestrator, customer_type: str, workflow_type: str, case_type: str, folder: str) -> DocumentPacketMessage:
    paths = sorted(str(path) for path in Path(folder).glob("*.txt"))
    return DocumentPacketMessage(
        session_id=orchestrator.new_session_id(),
        customer_type=customer_type,
        workflow_type=workflow_type,
        case_type=case_type,
        file_paths=paths,
    )


def print_cli_summary(report) -> None:
    payload = report.json_report
    print(f"Report ID: {report.report_id}")
    if report.report_type == "new_insurance":
        print(f"Recommendations: {len(payload['recommendations'])}")
        for item in payload["recommendations"]:
            print(f"- {item['scheme_name']}: {item['recommended_next_step']}")
    else:
        print(f"Status: {payload['status']}")
        print(f"Human review required: {payload['human_review_required']}")
        print(f"Missing documents: {', '.join(payload['missing_documents']) or 'None'}")
        print(f"Next action: {payload['next_action']}")
    print(f"Saved JSON/Markdown report under outputs/reports/{report.report_id}.*")


if __name__ == "__main__":
    main()
