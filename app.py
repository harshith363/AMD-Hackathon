from __future__ import annotations

import argparse
from pathlib import Path

from cli.prompts import (
    BUSINESS_CLAIM_TYPES,
    BUSINESS_INSURANCE_CATEGORIES,
    INDIVIDUAL_CLAIM_TYPES,
    INDIVIDUAL_INSURANCE_CATEGORIES,
    choose,
    collect_file_paths,
    collect_key_values,
)
from orchestrator.workflow import WorkflowOrchestrator
from schemas.messages import DocumentPacketMessage, ProductDiscoveryMessage


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic Insurance Operations Assistant")
    parser.add_argument("--demo", choices=["all", "1", "2", "3", "4", "5"], help="Run scripted demo scenario")
    parser.add_argument("--use-llm", action="store_true", help="Use vLLM/OpenAI-compatible endpoint for report explanations")
    args = parser.parse_args()
    orchestrator = WorkflowOrchestrator(use_llm=args.use_llm)
    if args.demo:
        run_demo(orchestrator, args.demo)
    else:
        run_interactive(orchestrator)


def run_interactive(orchestrator: WorkflowOrchestrator) -> None:
    while True:
        customer_type = choose("Select user type", {"1": "business", "2": "individual", "3": "exit"})
        if customer_type == "exit":
            return
        if customer_type == "business":
            workflow = choose(
                "Business options",
                {"1": "new_insurance", "2": "claim_validation", "3": "kyb_validation", "4": "exit"},
            )
        else:
            workflow = choose(
                "Individual options",
                {"1": "new_insurance", "2": "claim_validation", "3": "kyc_validation", "4": "exit"},
            )
        if workflow == "exit":
            continue
        if workflow == "new_insurance":
            categories = BUSINESS_INSURANCE_CATEGORIES if customer_type == "business" else INDIVIDUAL_INSURANCE_CATEGORIES
            category = choose("Select insurance category", categories)
            details = collect_key_values("Collecting basic details for product discovery.")
            report = orchestrator.run_product_discovery(
                ProductDiscoveryMessage(
                    session_id=orchestrator.new_session_id(),
                    customer_type=customer_type,
                    insurance_category=category,
                    user_inputs=details,
                )
            )
        else:
            if workflow == "claim_validation":
                claim_types = BUSINESS_CLAIM_TYPES if customer_type == "business" else INDIVIDUAL_CLAIM_TYPES
                case_type = choose("Select claim type", claim_types)
            else:
                case_type = "kyb" if customer_type == "business" else "kyc"
            paths = collect_file_paths()
            report = orchestrator.run_document_validation(
                DocumentPacketMessage(
                    session_id=orchestrator.new_session_id(),
                    customer_type=customer_type,
                    workflow_type=workflow,
                    case_type=case_type,
                    file_paths=paths,
                )
            )
        print_cli_summary(report)


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
