from __future__ import annotations

from app import _packet
from orchestrator.workflow import WorkflowOrchestrator
from schemas.messages import ProductDiscoveryMessage


def run_demo(
    demo_id: str = "all",
    use_llm: bool = False,
    vllm_base_url: str = "http://localhost:8000/v1",
    vllm_model: str = "amd-hackathon-model",
    vllm_api_key: str = "EMPTY",
    vllm_timeout_seconds: int = 20,
):
    """Notebook-friendly demo entrypoint.

    Example:
        from notebook_demo import run_demo
        reports = run_demo("all", use_llm=False)
    """

    orchestrator = WorkflowOrchestrator(
        use_llm=use_llm,
        vllm_base_url=vllm_base_url,
        vllm_model=vllm_model,
        vllm_api_key=vllm_api_key,
        vllm_timeout_seconds=vllm_timeout_seconds,
    )
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
    selected = list(scenarios) if demo_id == "all" else [demo_id]
    reports = []
    for key in selected:
        report = scenarios[key]()
        reports.append(report)
        _print_notebook_summary(key, report)
    return reports


def _print_notebook_summary(demo_id: str, report) -> None:
    payload = report.json_report
    print(f"Demo {demo_id}: {report.report_id}")
    if report.report_type == "new_insurance":
        print(f"Recommendations: {len(payload['recommendations'])}")
        for item in payload["recommendations"]:
            print(f"- {item['scheme_name']}")
    else:
        print(f"Status: {payload['status']}")
        print(f"Missing documents: {', '.join(payload['missing_documents']) or 'None'}")
        print(f"Next action: {payload['next_action']}")
    if payload.get("llm_explanation"):
        print(f"LLM explanation: {payload['llm_explanation']}")
    print()
