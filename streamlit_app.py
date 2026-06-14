from __future__ import annotations

import json
from pathlib import Path
import re
from uuid import uuid4

import streamlit as st

from cli.llm_chat import (
    REQUIRED_INDIVIDUAL_USER_FIELDS,
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
    _render_user_details_form()
    _render_option_cards()
    _render_document_uploader()
    _render_policy_application_form()
    _render_kyc_review()
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
        st.session_state.show_options = _question_needs_options(st.session_state.collected)


def _reset_conversation() -> None:
    st.session_state.collected = _empty_intake()
    st.session_state.transcript = []
    st.session_state.messages = []
    st.session_state.report = None
    st.session_state.pending_policy_report = None
    st.session_state.policy_application_approved = False
    st.session_state.pending_kyc_report = None
    st.session_state.pending_user_text = None
    st.session_state.selected_option = None
    st.session_state.show_options = False
    st.session_state.awaiting_document_followup = False
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
        elif _is_individual_kyc_report(result["report"]):
            st.session_state.pending_kyc_report = result["report"]
            st.session_state.messages.append({"role": "assistant", "content": _kyc_review_summary(result["report"])})
            st.session_state.awaiting_document_followup = not _kyc_details_align(result["report"].json_report)
        elif _should_continue_document_workflow(result["report"]):
            st.session_state.collected = _prepare_followup_intake(st.session_state.collected, result["report"])
            st.session_state.transcript = []
            st.session_state.messages.append({"role": "assistant", "content": _followup_prompt(result["report"])})
        else:
            st.session_state.collected = _empty_intake()
            st.session_state.transcript = []
            st.session_state.selected_option = None
            st.session_state.messages.append({"role": "assistant", "content": "What would you like to process next?"})
    elif not result["assistant_messages"]:
        question = next_assistant_question(st.session_state.orchestrator, st.session_state.collected)
        if question:
            st.session_state.messages.append({"role": "assistant", "content": question})
            st.session_state.show_options = _question_needs_options(st.session_state.collected)
    st.rerun()


def _render_option_cards() -> None:
    if not st.session_state.get("show_options"):
        return
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
    if (
        "document file paths" not in missing
        and "incident description" not in missing
        and not st.session_state.get("awaiting_document_followup")
    ):
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
                existing = st.session_state.collected.get("file_paths") or []
                st.session_state.collected["file_paths"] = [*existing, *paths]
                st.session_state.awaiting_document_followup = False
            st.session_state.collected = _normalize_intake(st.session_state.collected)
            uploaded_text = "Uploaded documents:\n" + "\n".join(st.session_state.collected["file_paths"])
            if st.session_state.collected.get("incident_description"):
                uploaded_text += f"\n\nIncident description: {st.session_state.collected['incident_description']}"
            st.session_state.messages.append({"role": "user", "content": uploaded_text})
            report = run_ready_workflow(st.session_state.orchestrator, st.session_state.collected)
            if report:
                st.session_state.report = report
                st.session_state.messages.append({"role": "assistant", "content": _report_summary(report)})
                if _is_individual_kyc_report(report):
                    st.session_state.pending_kyc_report = report
                    st.session_state.messages.append({"role": "assistant", "content": _kyc_review_summary(report)})
                    st.session_state.awaiting_document_followup = not _kyc_details_align(report.json_report)
                elif _should_continue_document_workflow(report):
                    st.session_state.collected = _prepare_followup_intake(st.session_state.collected, report)
                    st.session_state.transcript = []
                    st.session_state.messages.append({"role": "assistant", "content": _followup_prompt(report)})
                else:
                    st.session_state.collected = _empty_intake()
                    st.session_state.transcript = []
                    st.session_state.messages.append({"role": "assistant", "content": "What would you like to process next?"})
            else:
                question = next_assistant_question(st.session_state.orchestrator, st.session_state.collected)
                st.session_state.messages.append({"role": "assistant", "content": question})
                st.session_state.show_options = _question_needs_options(st.session_state.collected)
            st.rerun()


def _render_user_details_form() -> None:
    if "user details" not in _missing_fields(st.session_state.collected):
        return
    if st.session_state.collected.get("customer_type") != "individual" or not st.session_state.collected.get("workflow_type"):
        return

    current = st.session_state.collected.get("user_inputs") or {}
    with st.expander("User details", expanded=True):
        with st.form("individual_user_details_form"):
            name = st.text_input("Name", value=current.get("name", ""))
            date_of_birth = st.text_input("Date of birth", value=current.get("date_of_birth", ""), placeholder="DD/MM/YYYY")
            address = st.text_area("Address", value=current.get("address", ""))
            phone_number = st.text_input("Phone number", value=current.get("phone_number", ""))
            job = st.text_input("Job", value=current.get("job", ""))
            annual_income = st.text_input("Annual income", value=current.get("annual_income", ""))
            submitted = st.form_submit_button("Continue", type="primary")

        if not submitted:
            return

        details = {
            **current,
            "name": name.strip(),
            "date_of_birth": date_of_birth.strip(),
            "address": address.strip(),
            "phone_number": phone_number.strip(),
            "job": job.strip(),
            "annual_income": annual_income.strip(),
        }
        validation = _validate_application_details(details)
        if not validation["is_valid"]:
            st.error("Please correct: " + "; ".join(validation["issues"]))
            return

        st.session_state.collected["user_inputs"] = validation.get("normalized_details") or details
        st.session_state.messages.append({"role": "user", "content": "Submitted user details."})
        question = next_assistant_question(st.session_state.orchestrator, st.session_state.collected)
        if question:
            st.session_state.messages.append({"role": "assistant", "content": question})
            st.session_state.show_options = _question_needs_options(st.session_state.collected)
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
                if st.button("Approve and continue to KYC", type="primary", use_container_width=True):
                    st.session_state.policy_application_approved = True
                    details = {
                        **(payload.get("user_inputs") or {}),
                        "recommended_policy_ids": [item["scheme_id"] for item in payload["recommendations"]],
                    }
                    st.session_state.pending_policy_report = None
                    st.session_state.policy_application_approved = False
                    st.session_state.collected = {
                        **_empty_intake(),
                        "customer_type": "individual",
                        "workflow_type": "kyc_validation",
                        "case_type": "kyc",
                        "user_inputs": details,
                        "ready_to_run": False,
                    }
                    st.session_state.transcript = []
                    st.session_state.messages.append({"role": "user", "content": "Approved policy recommendation."})
                    st.session_state.messages.append({"role": "assistant", "content": "Please upload PAN card and Aadhaar card PDF or image files for KYC verification."})
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


def _render_kyc_review() -> None:
    report = st.session_state.get("pending_kyc_report")
    if not report:
        return
    payload = report.json_report
    with st.expander("KYC details review", expanded=True):
        by_document = payload.get("extracted_by_document") or {}
        if by_document:
            for document_type, fields in by_document.items():
                st.markdown(f"**{_display_label(document_type).title()}**")
                st.json(fields)
        else:
            st.info("No KYC fields were parsed from the uploaded documents.")

        st.markdown("**Summary**")
        st.write(_kyc_review_summary(report))
        _render_document_debug(payload)

        can_approve = _kyc_details_align(payload)
        if not can_approve:
            st.warning("Some KYC details are missing or inconsistent. Upload corrected documents before approval.")
            return

        if st.button("Approve and store KYC JSON", type="primary", use_container_width=True):
            stored_path = _store_kyc_json(payload)
            st.session_state.messages.append({"role": "assistant", "content": f"KYC details approved and stored as JSON: `{stored_path}`."})
            st.session_state.pending_kyc_report = None
            st.session_state.collected = _empty_intake()
            st.session_state.transcript = []
            st.session_state.awaiting_document_followup = False
            st.session_state.messages.append({"role": "assistant", "content": "What would you like to process next?"})
            st.rerun()


def _handle_chat_input() -> None:
    user_text = st.chat_input("Message the assistant")
    if user_text:
        _submit_user_text(user_text)


def _submit_user_text(user_text: str) -> None:
    st.session_state.messages.append({"role": "user", "content": user_text})
    st.session_state.pending_user_text = user_text
    st.session_state.selected_option = None
    st.session_state.show_options = False
    st.rerun()


def _current_options() -> list[dict[str, str]]:
    missing = _missing_fields(st.session_state.collected)
    customer_type = st.session_state.collected.get("customer_type")
    workflow_type = st.session_state.collected.get("workflow_type")

    if "user details" in missing:
        return []
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
    if payload.get("customer_type") == "individual" and payload.get("workflow_type") == "kyc_validation":
        return "KYC documents have been parsed. Please review the extracted details before approval."
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


def _is_individual_kyc_report(report) -> bool:
    payload = report.json_report
    return report.report_type == "kyc_validation" and payload.get("customer_type") == "individual"


def _is_individual_claim_intake(collected: dict) -> bool:
    return collected.get("customer_type") == "individual" and collected.get("workflow_type") == "claim_validation"


def _is_individual_kyc_intake(collected: dict) -> bool:
    return collected.get("customer_type") == "individual" and collected.get("workflow_type") == "kyc_validation"


def _should_continue_document_workflow(report) -> bool:
    payload = report.json_report
    return (
        payload.get("customer_type") == "individual"
        and payload.get("workflow_type") in {"claim_validation", "kyc_validation", "kyb_validation"}
        and payload.get("status") != "Ready for Submission"
    )


def _prepare_followup_intake(collected: dict, report) -> dict:
    payload = report.json_report
    updated = dict(collected)
    updated["customer_type"] = payload.get("customer_type") or updated.get("customer_type")
    updated["workflow_type"] = payload.get("workflow_type") or updated.get("workflow_type")
    updated["case_type"] = payload.get("case_type") or updated.get("case_type")
    updated["ready_to_run"] = False
    if payload.get("missing_documents"):
        st.session_state.awaiting_document_followup = True
    return updated


def _followup_prompt(report) -> str:
    payload = report.json_report
    missing = payload.get("missing_documents") or []
    issues = payload.get("validation_issues") or []
    if missing:
        return "Please upload the missing documents: " + ", ".join(missing) + "."
    if issues:
        first_issue = issues[0].get("message", "Some details need correction")
        return f"{first_issue}. Please provide corrected documents or details."
    return "Please provide the requested correction so I can continue this workflow."


def _question_needs_options(collected: dict) -> bool:
    missing = _missing_fields(collected)
    if "user details" in missing:
        return False
    return any(
        item in missing
        for item in [
            "customer_type",
            "workflow_type",
            "insurance_category",
            "claim_type",
            "confirmation to run product discovery",
        ]
    )


def _kyc_review_summary(report) -> str:
    payload = report.json_report
    if _documents_uploaded_but_unparsed(payload):
        return (
            "The document was uploaded, but no readable KYC fields were extracted. "
            "Use a clearer image or run the app with a vision-capable model such as Gemma 4 so PAN/Aadhaar images can be parsed directly."
        )
    llm_summary = st.session_state.orchestrator.llm_client.summarize_kyc_fields(
        {
            "status": payload.get("status"),
            "user_inputs": payload.get("user_inputs"),
            "extracted_by_document": payload.get("extracted_by_document"),
            "extracted_key_fields": payload.get("extracted_key_fields"),
            "validation_issues": payload.get("validation_issues"),
        }
    )
    if llm_summary:
        return llm_summary

    fields = payload.get("extracted_key_fields") or {}
    issues = payload.get("validation_issues") or []
    field_text = ", ".join(f"{key}: {value}" for key, value in fields.items()) or "no fields parsed"
    if _kyc_details_align(payload):
        return f"Parsed KYC fields: {field_text}. The available details are consistent and can be approved."
    issue_text = "; ".join(issue.get("message", "issue found") for issue in issues) or "missing required details"
    return f"Parsed KYC fields: {field_text}. Review needed: {issue_text}."


def _documents_uploaded_but_unparsed(payload: dict) -> bool:
    if payload.get("document_debug") and not payload.get("extracted_key_fields"):
        return True
    trace = payload.get("trace") or []
    parsed_steps = [item for item in trace if item.get("agent") == "Document Intake Agent"]
    parsed_count = 0
    if parsed_steps:
        parsed_count = int(parsed_steps[-1].get("details", {}).get("count") or 0)
    return parsed_count > 0 and not payload.get("extracted_key_fields")


def _render_document_debug(payload: dict) -> None:
    debug_rows = payload.get("document_debug") or []
    if not debug_rows:
        return
    with st.expander("Extraction diagnostics", expanded=False):
        for row in debug_rows:
            st.markdown(f"**{row.get('file_name', 'Uploaded document')}**")
            metric_cols = st.columns(4)
            metric_cols[0].metric("Method", row.get("extraction_method") or "unknown")
            metric_cols[1].metric("Text chars", row.get("text_length") or 0)
            metric_cols[2].metric("OCR tries", row.get("ocr_attempt_count") or 0)
            metric_cols[3].metric("Vision", "yes" if row.get("vision_fallback_succeeded") else "no")
            if row.get("ocr_best_attempt"):
                st.caption(f"OCR best: {row['ocr_best_attempt']}")
            if row.get("text_preview"):
                st.code(row["text_preview"], language="text")
            warnings = row.get("warnings") or []
            if warnings:
                st.warning("; ".join(str(item) for item in warnings))


def _kyc_details_align(payload: dict) -> bool:
    if payload.get("missing_documents"):
        return False
    serious_issues = [
        issue
        for issue in payload.get("validation_issues", [])
        if issue.get("severity") in {"medium", "high"} or "mismatch" in issue.get("message", "").lower()
    ]
    return not serious_issues


def _store_kyc_json(payload: dict) -> str:
    output_dir = Path("outputs/kyc_profiles")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_id = payload.get("report_id") or uuid4().hex[:10]
    target = output_dir / f"{report_id}.json"
    stored_payload = {
        "report_id": payload.get("report_id"),
        "customer_type": payload.get("customer_type"),
        "approved": True,
        "user_inputs": payload.get("user_inputs") or {},
        "extracted_by_document": payload.get("extracted_by_document") or {},
        "extracted_key_fields": payload.get("extracted_key_fields") or {},
        "summary": _kyc_review_summary(st.session_state.pending_kyc_report),
    }
    target.write_text(json.dumps(stored_payload, indent=2), encoding="utf-8")
    return str(target)


def _validate_application_details(details: dict) -> dict:
    local_issues = _local_user_detail_issues(details)
    if local_issues:
        return {"is_valid": False, "issues": local_issues, "normalized_details": details}

    llm_result = st.session_state.orchestrator.llm_client.validate_application_details(details)
    if isinstance(llm_result, dict) and "is_valid" in llm_result:
        return {
            "is_valid": bool(llm_result.get("is_valid")),
            "issues": [str(issue) for issue in llm_result.get("issues") or []],
            "normalized_details": llm_result.get("normalized_details") or details,
        }

    return {"is_valid": True, "issues": [], "normalized_details": details}


def _local_user_detail_issues(details: dict) -> list[str]:
    issues = []
    for field in REQUIRED_INDIVIDUAL_USER_FIELDS:
        if not str(details.get(field) or "").strip():
            issues.append(f"{_display_label(field)} is required")
    if details.get("phone_number") and not _valid_phone(str(details.get("phone_number") or "")):
        issues.append("phone number should be 10 to 15 digits")
    if details.get("annual_income") and _income_value(details.get("annual_income")) <= 0:
        issues.append("annual income should be greater than zero")
    return issues


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
