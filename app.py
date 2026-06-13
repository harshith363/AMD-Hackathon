from __future__ import annotations

import argparse

from cli.llm_chat import run_llm_interactive
from orchestrator.workflow import WorkflowOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic Insurance Operations Assistant")
    parser.add_argument("--use-llm", action="store_true", help="Use vLLM/OpenAI-compatible endpoint")
    parser.add_argument("--vllm-base-url", default="http://localhost:8000/v1", help="vLLM OpenAI-compatible base URL")
    parser.add_argument("--vllm-model", default="amd-hackathon-model", help="vLLM served model name")
    parser.add_argument("--vllm-api-key", default="EMPTY", help="API key for OpenAI-compatible vLLM endpoint")
    parser.add_argument("--vllm-timeout-seconds", type=int, default=20, help="vLLM request timeout")
    args = parser.parse_args()
    orchestrator = WorkflowOrchestrator(
        use_llm=args.use_llm,
        vllm_base_url=args.vllm_base_url,
        vllm_model=args.vllm_model,
        vllm_api_key=args.vllm_api_key,
        vllm_timeout_seconds=args.vllm_timeout_seconds,
    )
    run_interactive(orchestrator)


def run_interactive(orchestrator: WorkflowOrchestrator) -> None:
    run_llm_interactive(orchestrator, print_cli_summary)


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
