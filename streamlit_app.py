from __future__ import annotations

from pathlib import Path
import re
from uuid import uuid4

import streamlit as st

from cli.llm_chat import (
    _empty_intake,
    _missing_fields,
    _normalize_intake,
    next_assistant_question,
    process_user_message,
    run_ready_workflow,
)
from domain_tools import get_claim_types, get_insurance_categories, get_supported_workflows
from orchestrator.workflow import WorkflowOrchestrator

DEFAULT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_MODEL = "Qwen/Qwen2.5-32B-Instruct"
DEFAULT_API_KEY = "EMPTY"
DEFAULT_TIMEOUT = 20


def main() -> None:
    st.set_page_config(page_title="Insurance Operations Assistant", layout="centered")
    _inject_styles()
    _ensure_state()

    st.markdown("<main class='chat-shell'>", unsafe_allow_html=True)
    _render_header()
    _render_chat()
    _process_pending_message()
    _render_option_cards()
    _render_document_uploader()
    _render_report()
    _render_policy_application_form()
    _handle_chat_input()
    st.markdown("</main>", unsafe_allow_html=True)


def _ensure_state() -> None:
    if "orchestrator" not in st.session_state:
        st.session_state.orchestrator = WorkflowOrchestrator(
            use_llm=True,
            vllm_base_url=DEFAULT_BASE_URL,
            vllm_model=DEFAULT_MODEL,
            vllm_api_key=DEFAULT_API_KEY,
            vllm_timeout_seconds=DEFAULT_TIMEOUT,
        )
    if "collected" not in st.session_state:
        _reset_conversation()
    if not st.session_state.messages:
        question = next_assistant_question(st.session_state.orchestrator, st.session_state.collected)
        st.session_state.messages.append({"role": "assistant", "content": question})


def _reset_conversation() -> None:
    st.session_state.collected = _empty_intake()
    st.session_state.transcript = []
    st.session_state.messages = []
    st.session_state.report = None
    st.session_state.pending_policy_report = None
    st.session_state.policy_application_approved = False
    st.session_state.pending_user_text = None
    st.session_state.selected_option = None
    st.session_state.upload_session_id = uuid4().hex[:10]


def _render_header() -> None:
    top_left, top_right = st.columns([0.8, 0.2], vertical_alignment="center")
    with top_left:
        st.markdown(
            """
            <section class="hero">
              <h1>Insurance Operations Assistant</h1>
              <p>Tell me what you need: find a policy, validate claim documents, or complete KYC/KYB.</p>
            </section>
            """,
            unsafe_allow_html=True,
        )
    with top_right:
        if st.button("Reset", use_container_width=True):
            _reset_conversation()
            st.rerun()


def _render_chat() -> None:
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def _process_pending_message() -> None:
    pending = st.session_state.get("pending_user_text")
    if not pending:
        return
    st.session_state.pending_user_text = None
    with st.spinner("Thinking..."):
        result = process_user_message(
            st.session_state.orchestrator,
            st.session_state.collected,
            st.session_state.transcript,
            pending,
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
        if _is_individual_policy_report(result["report"]):
            st.session_state.pending_policy_report = result["report"]
            st.session_state.policy_application_approved = False
            st.session_state.messages.append({"role": "assistant", "content": "Please review the recommended policy. If you approve it, I will collect application details and move to KYC."})
        else:
            st.session_state.collected = _empty_intake()
            st.session_state.transcript = []
            st.session_state.selected_option = None
            st.session_state.messages.append({"role": "assistant", "content": "What would you like to process next?"})
    elif not result["assistant_messages"]:
        question = next_assistant_question(st.session_state.orchestrator, st.session_state.collected)
        if question:
            st.session_state.messages.append({"role": "assistant", "content": question})
    st.rerun()


def _render_option_cards() -> None:
    options = _current_options()
    if not options:
        return

    st.markdown("#### Choose an option")
    columns = st.columns(min(4, len(options)))
    for index, option in enumerate(options):
        selected = st.session_state.get("selected_option") == option["value"]
        button_label = f"{'✓ ' if selected else ''}{option['label']}"
        with columns[index % len(columns)]:
            if st.button(button_label, key=f"option_{option['value']}", use_container_width=True):
                st.session_state.selected_option = option["value"]
                st.rerun()

    selected = st.session_state.get("selected_option")
    if selected:
        enter_col, hint_col = st.columns([0.24, 0.76], vertical_alignment="center")
        with enter_col:
            if st.button("Enter", type="primary", use_container_width=True):
                _submit_user_text(_option_user_text(selected))
        with hint_col:
            st.caption(f"Selected: {_display_label(selected)}")


def _render_document_uploader() -> None:
    missing = _missing_fields(st.session_state.collected)
    if "document file paths" not in missing and "incident description" not in missing:
        return
    with st.expander("Upload documents", expanded=True):
        if _is_individual_kyc_intake(st.session_state.collected):
            st.caption("Upload PAN card and Aadhaar card as PDF or image files.")
        if _is_individual_claim_intake(st.session_state.collected):
            st.session_state.collected["incident_description"] = st.text_area(
                "Incident description",
                value=st.session_state.collected.get("incident_description") or "",
                placeholder="Briefly describe what happened, when it happened, and the loss or treatment involved.",
            ).strip()
        uploaded_files = st.file_uploader(
            "Attach PDF, image, or TXT files",
            type=["txt", "pdf", "png", "jpg", "jpeg", "tiff", "bmp", "webp"],
            accept_multiple_files=True,
            label_visibility="collapsed",
        )
        existing_paths = st.session_state.collected.get("file_paths") or []
        ready_for_submit = bool(uploaded_files or existing_paths)
        if _is_individual_claim_intake(st.session_state.collected):
            ready_for_submit = ready_for_submit and bool(st.session_state.collected.get("incident_description"))
        if ready_for_submit and st.button("Use uploaded files", type="primary"):
            if uploaded_files:
                paths = _save_uploaded_files(uploaded_files)
                st.session_state.collected["file_paths"] = paths
            st.session_state.collected = _normalize_intake(st.session_state.collected)
            uploaded_text = "Uploaded documents:\n" + "\n".join(st.session_state.collected["file_paths"])
            if st.session_state.collected.get("incident_description"):
                uploaded_text += f"\n\nIncident description: {st.session_state.collected['incident_description']}"
            st.session_state.messages.append({"role": "user", "content": uploaded_text})
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


def _render_policy_application_form() -> None:
    report = st.session_state.get("pending_policy_report")
    if not report:
        return
    with st.expander("Policy application", expanded=True):
        payload = report.json_report
        st.caption("Recommended policies")
        for item in payload["recommendations"]:
            st.markdown(f"**{item['scheme_name']}**")
            st.write(item["recommended_next_step"])

        if not st.session_state.policy_application_approved:
            approve_col, decline_col = st.columns(2)
            with approve_col:
                if st.button("Approve recommendation", type="primary", use_container_width=True):
                    st.session_state.policy_application_approved = True
                    st.rerun()
            with decline_col:
                if st.button("Do not proceed", use_container_width=True):
                    st.session_state.pending_policy_report = None
                    st.session_state.policy_application_approved = False
                    st.session_state.collected = _empty_intake()
                    st.session_state.transcript = []
                    st.session_state.messages.append({"role": "assistant", "content": "No problem. What would you like to process next?"})
                    st.rerun()
            return

        with st.form("individual_policy_application_form"):
            address = st.text_area("Address")
            phone_number = st.text_input("Phone number")
            job = st.text_input("Job")
            annual_income = st.text_input("Annual income")
            submitted = st.form_submit_button("Validate and continue to KYC", type="primary")

        if not submitted:
            return

        details = {
            **payload.get("user_inputs", {}),
            "address": address.strip(),
            "phone_number": phone_number.strip(),
            "job": job.strip(),
            "annual_income": annual_income.strip(),
            "recommended_policy_ids": [item["scheme_id"] for item in payload["recommendations"]],
        }
        validation = _validate_application_details(details)
        if not validation["is_valid"]:
            st.error("Please correct: " + "; ".join(validation["issues"]))
            return

        st.session_state.pending_policy_report = None
        st.session_state.policy_application_approved = False
        st.session_state.collected = {
            **_empty_intake(),
            "customer_type": "individual",
            "workflow_type": "kyc_validation",
            "case_type": "kyc",
            "user_inputs": validation.get("normalized_details") or details,
            "ready_to_run": False,
        }
        st.session_state.transcript = []
        st.session_state.messages.append({"role": "user", "content": "Approved policy recommendation and submitted application details."})
        st.session_state.messages.append({"role": "assistant", "content": "Application details look usable. Please upload PAN card and Aadhaar card PDF or image files for KYC verification."})
        st.rerun()


def _render_report() -> None:
    report = st.session_state.report
    if not report:
        return
    with st.expander("Latest report", expanded=True):
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
                st.dataframe(payload["validation_issues"], use_container_width=True)

        with st.expander("Markdown"):
            st.markdown(report.markdown_report)
        with st.expander("JSON"):
            st.json(payload)


def _handle_chat_input() -> None:
    user_text = st.chat_input("Message the assistant")
    if user_text:
        _submit_user_text(user_text)


def _submit_user_text(user_text: str) -> None:
    st.session_state.messages.append({"role": "user", "content": user_text})
    st.session_state.pending_user_text = user_text
    st.session_state.selected_option = None
    st.rerun()


def _current_options() -> list[dict[str, str]]:
    missing = _missing_fields(st.session_state.collected)
    customer_type = st.session_state.collected.get("customer_type")
    workflow_type = st.session_state.collected.get("workflow_type")

    if "customer_type" in missing:
        return [
            {"label": "Individual", "value": "individual"},
            {"label": "Business", "value": "business"},
        ]
    if "workflow_type" in missing:
        return [
            {"label": item["label"].title(), "value": item["workflow_type"]}
            for item in get_supported_workflows(customer_type)["workflows"]
        ]
    if "insurance_category" in missing:
        categories = get_insurance_categories(customer_type)["categories"]
        if isinstance(categories, dict):
            categories = categories.get(customer_type or "individual", [])
        return [{"label": _display_label(value).title(), "value": value} for value in categories]
    if "claim_type" in missing:
        claim_types = get_claim_types(customer_type)["claim_types"]
        if isinstance(claim_types, dict):
            claim_types = claim_types.get(customer_type or "individual", [])
        return [{"label": _display_label(value).title(), "value": value} for value in claim_types]
    if "confirmation to run product discovery" in missing:
        return [
            {"label": "Run Product Discovery", "value": "yes"},
            {"label": "Add More Details", "value": "add more details"},
        ]
    return []


def _option_user_text(value: str) -> str:
    if value == "new_insurance":
        return "I want a new policy"
    if value == "claim_validation":
        return "I want to validate claim documents"
    if value == "kyc_validation":
        return "I want to complete KYC validation"
    if value == "kyb_validation":
        return "I want to complete KYB validation"
    return _display_label(value)


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
    if (
        payload.get("customer_type") == "individual"
        and payload.get("workflow_type") == "claim_validation"
        and payload.get("status") == "Ready for Submission"
    ):
        return "Claim validation is complete. Everything looks fine, and the claim has been generated."
    return f"Validation complete. Status: {payload['status']}. Missing documents: {missing}."


def _is_individual_policy_report(report) -> bool:
    payload = report.json_report
    return report.report_type == "new_insurance" and payload.get("customer_type") == "individual"


def _is_individual_claim_intake(collected: dict) -> bool:
    return collected.get("customer_type") == "individual" and collected.get("workflow_type") == "claim_validation"


def _is_individual_kyc_intake(collected: dict) -> bool:
    return collected.get("customer_type") == "individual" and collected.get("workflow_type") == "kyc_validation"


def _validate_application_details(details: dict) -> dict:
    llm_result = st.session_state.orchestrator.llm_client.validate_application_details(details)
    if isinstance(llm_result, dict) and "is_valid" in llm_result:
        return {
            "is_valid": bool(llm_result.get("is_valid")),
            "issues": [str(issue) for issue in llm_result.get("issues") or []],
            "normalized_details": llm_result.get("normalized_details") or details,
        }

    issues = []
    if not details.get("address"):
        issues.append("address is required")
    if not _valid_phone(str(details.get("phone_number") or "")):
        issues.append("phone number should be 10 to 15 digits")
    if not details.get("job"):
        issues.append("job is required")
    if _income_value(details.get("annual_income")) <= 0:
        issues.append("annual income should be greater than zero")
    return {"is_valid": not issues, "issues": issues, "normalized_details": details}


def _valid_phone(value: str) -> bool:
    digits = re.sub(r"\D+", "", value)
    return 10 <= len(digits) <= 15


def _income_value(value) -> int:
    digits = re.sub(r"\D+", "", str(value or ""))
    return int(digits) if digits else 0


def _display_label(value: str) -> str:
    return value.replace("_", " ")


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 860px;
            padding-top: 2.2rem;
            padding-bottom: 6rem;
        }
        .hero {
            text-align: center;
            margin: 0 auto 1.4rem auto;
        }
        .hero h1 {
            font-size: 2.1rem;
            margin-bottom: 0.35rem;
            letter-spacing: 0;
        }
        .hero p {
            color: #5f6368;
            font-size: 1rem;
            margin: 0 auto;
            max-width: 620px;
        }
        div[data-testid="stChatMessage"] {
            border-radius: 8px;
        }
        div[data-testid="stButton"] button {
            min-height: 3.2rem;
            border-radius: 8px;
            white-space: normal;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
