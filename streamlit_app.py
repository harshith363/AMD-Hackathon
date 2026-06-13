from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import streamlit as st

from cli.llm_chat import (
    _empty_intake,
    _normalize_intake,
    next_assistant_question,
    process_user_message,
    run_ready_workflow,
)
from orchestrator.workflow import WorkflowOrchestrator

DEFAULT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_MODEL = "Qwen/Qwen2.5-32B-Instruct"
DEFAULT_API_KEY = "EMPTY"


def main() -> None:
    st.set_page_config(page_title="Insurance Operations Assistant", layout="wide")
    st.title("Insurance Operations Assistant")

    config = _sidebar_config()
    _ensure_state(config)

    left, right = st.columns([0.62, 0.38], gap="large")
    with left:
        _render_chat()
        _handle_chat_input()
    with right:
        _render_controls()
        _render_report()


def _sidebar_config() -> dict:
    with st.sidebar:
        st.header("vLLM")
        base_url = st.text_input("Base URL", value=DEFAULT_BASE_URL)
        model = st.text_input("Model", value=DEFAULT_MODEL)
        api_key = st.text_input("API key", value=DEFAULT_API_KEY, type="password")
        timeout = st.number_input("Timeout seconds", min_value=5, max_value=120, value=20, step=5)
        if st.button("Reset conversation", use_container_width=True):
            _reset_conversation()
            st.rerun()
    return {
        "base_url": base_url,
        "model": model,
        "api_key": api_key,
        "timeout": int(timeout),
    }


def _ensure_state(config: dict) -> None:
    config_key = tuple(config.values())
    if st.session_state.get("config_key") != config_key:
        st.session_state.config_key = config_key
        st.session_state.orchestrator = WorkflowOrchestrator(
            use_llm=True,
            vllm_base_url=config["base_url"],
            vllm_model=config["model"],
            vllm_api_key=config["api_key"],
            vllm_timeout_seconds=config["timeout"],
        )
        _reset_conversation()

    if "upload_session_id" not in st.session_state:
        st.session_state.upload_session_id = uuid4().hex[:10]
    if not st.session_state.messages:
        question = next_assistant_question(st.session_state.orchestrator, st.session_state.collected)
        st.session_state.messages.append({"role": "assistant", "content": question})


def _reset_conversation() -> None:
    st.session_state.collected = _empty_intake()
    st.session_state.transcript = []
    st.session_state.messages = []
    st.session_state.report = None
    st.session_state.upload_session_id = uuid4().hex[:10]


def _render_chat() -> None:
    st.subheader("Chat")
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def _handle_chat_input() -> None:
    user_text = st.chat_input("Type a response, ask for options, or provide document paths")
    if not user_text:
        return

    st.session_state.messages.append({"role": "user", "content": user_text})
    result = process_user_message(
        st.session_state.orchestrator,
        st.session_state.collected,
        st.session_state.transcript,
        user_text,
    )
    if result["exit_requested"]:
        _reset_conversation()
        st.rerun()

    st.session_state.collected = result["collected"]
    st.session_state.transcript = result["transcript"]
    for message in result["assistant_messages"]:
        st.session_state.messages.append({"role": "assistant", "content": message})

    if result["report"]:
        st.session_state.report = result["report"]
        st.session_state.messages.append({"role": "assistant", "content": _report_summary(result["report"])})
        st.session_state.collected = _empty_intake()
        st.session_state.transcript = []
        st.session_state.messages.append({"role": "assistant", "content": "What would you like to process next?"})
    elif not result["assistant_messages"]:
        question = next_assistant_question(st.session_state.orchestrator, st.session_state.collected)
        if question:
            st.session_state.messages.append({"role": "assistant", "content": question})
    st.rerun()


def _render_controls() -> None:
    st.subheader("Documents")
    uploaded_files = st.file_uploader(
        "Upload PDF, image, or TXT documents",
        type=["txt", "pdf", "png", "jpg", "jpeg", "tiff", "bmp", "webp"],
        accept_multiple_files=True,
    )
    if uploaded_files and st.button("Attach uploaded documents", use_container_width=True):
        paths = _save_uploaded_files(uploaded_files)
        st.session_state.collected["file_paths"] = paths
        st.session_state.collected = _normalize_intake(st.session_state.collected)
        st.session_state.messages.append({"role": "user", "content": "Uploaded documents:\n" + "\n".join(paths)})
        report = run_ready_workflow(st.session_state.orchestrator, st.session_state.collected)
        if report:
            st.session_state.report = report
            st.session_state.messages.append({"role": "assistant", "content": _report_summary(report)})
            st.session_state.collected = _empty_intake()
            st.session_state.transcript = []
            st.session_state.messages.append({"role": "assistant", "content": "What would you like to process next?"})
        else:
            question = next_assistant_question(st.session_state.orchestrator, st.session_state.collected)
            st.session_state.messages.append({"role": "assistant", "content": question})
        st.rerun()

    with st.expander("Current structured intake", expanded=False):
        st.json(st.session_state.collected)


def _render_report() -> None:
    st.subheader("Latest Report")
    report = st.session_state.report
    if not report:
        st.info("Run a workflow to see the report here.")
        return

    payload = report.json_report
    st.caption(f"Report ID: {report.report_id}")
    if report.report_type == "new_insurance":
        st.metric("Recommendations", len(payload["recommendations"]))
        for item in payload["recommendations"]:
            st.markdown(f"**{item['scheme_name']}**")
            st.write(item["recommended_next_step"])
    else:
        st.metric("Status", payload["status"])
        st.write(f"Human review required: `{payload['human_review_required']}`")
        st.write("Missing documents:", payload["missing_documents"] or "None")
        st.write("Next action:", payload["next_action"])
        if payload["validation_issues"]:
            st.write("Validation issues")
            st.dataframe(payload["validation_issues"], use_container_width=True)

    with st.expander("Markdown report", expanded=True):
        st.markdown(report.markdown_report)
    with st.expander("JSON report", expanded=False):
        st.json(payload)


def _save_uploaded_files(uploaded_files) -> list[str]:
    output_dir = Path("outputs/uploads") / st.session_state.upload_session_id
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for uploaded_file in uploaded_files:
        target = output_dir / uploaded_file.name
        target.write_bytes(uploaded_file.getbuffer())
        paths.append(str(target))
    return paths


def _report_summary(report) -> str:
    payload = report.json_report
    if report.report_type == "new_insurance":
        names = ", ".join(item["scheme_name"] for item in payload["recommendations"]) or "no matching schemes"
        return f"Product discovery is complete. Recommended schemes: {names}."
    missing = ", ".join(payload["missing_documents"]) or "none"
    return f"Validation complete. Status: {payload['status']}. Missing documents: {missing}."


if __name__ == "__main__":
    main()
