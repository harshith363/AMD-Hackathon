from __future__ import annotations

import json
from pathlib import Path
import re
from uuid import uuid4

import streamlit as st

from cli.llm_chat import (
    REQUIRED_BUSINESS_USER_FIELDS,
    REQUIRED_INDIVIDUAL_USER_FIELDS,
    _empty_intake,
    _missing_fields,
    _normalize_intake,
    next_assistant_question,
    process_user_message,
    run_ready_workflow,
)
from domain_tools import get_claim_types, get_insurance_categories, get_required_documents, get_supported_workflows
from orchestrator.workflow import WorkflowOrchestrator

DEFAULT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_MODEL = "mistralai/Ministral-3-14B-Instruct-2512"
DEFAULT_API_KEY = "EMPTY"
DEFAULT_TIMEOUT = 20


def main() -> None:
    st.set_page_config(page_title="Insurance Operations Assistant", layout="centered")
    _inject_styles()
    _ensure_state()

    st.markdown("<main class='chat-shell'>", unsafe_allow_html=True)
    _render_header()
    _render_demo_shortcuts()
    _render_chat()
    _process_pending_message()
    _render_user_details_form()
    _render_option_cards()
    _render_document_uploader()
    _render_claim_review()
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
    st.session_state.identity_uploads = {}
    st.session_state.claim_uploads = {}
    st.session_state.claim_decisions = {}


def _render_header() -> None:
    top_left, top_right = st.columns([0.8, 0.2], vertical_alignment="center")
    with top_left:
        st.markdown(
            """
            <section class="hero">
              <h1>AI Insurance Compliance Desk</h1>
              <p>Validate claim compliance and complete AI-assisted KYC/KYB, with lightweight policy onboarding as an add-on.</p>
            </section>
            """,
            unsafe_allow_html=True,
        )
    with top_right:
        if st.button("Reset", use_container_width=True):
            _reset_conversation()
            st.rerun()


def _render_demo_shortcuts() -> None:
    with st.expander("Demo shortcuts", expanded=False):
        st.caption("Use these sample flows for a reliable hackathon demo.")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Sample Individual KYC", use_container_width=True):
                _run_sample_individual_kyc()
                st.rerun()
        with col2:
            if st.button("Sample Business KYB", use_container_width=True):
                _run_sample_business_kyb()
                st.rerun()
        with col3:
            if st.button("Sample Property Claim", use_container_width=True):
                _run_sample_property_claim()
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
    if st.session_state.get("pending_policy_report"):
        if _policy_approval_requested(pending):
            _start_identity_workflow_from_policy(st.session_state.pending_policy_report)
        else:
            st.session_state.messages.append({"role": "assistant", "content": _answer_policy_question(st.session_state.pending_policy_report, pending)})
        st.rerun()
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
        if _is_policy_report(result["report"]):
            st.session_state.pending_policy_report = result["report"]
            st.session_state.policy_application_approved = False
            st.session_state.messages.append({"role": "assistant", "content": _policy_approval_prompt(result["report"])})
        elif _is_identity_report(result["report"]):
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
        with columns[index % len(columns)]:
            if st.button(option["label"], key=f"option_{option['value']}", use_container_width=True):
                _select_option(option["value"])


def _render_document_uploader() -> None:
    missing = _missing_fields(st.session_state.collected)
    if _is_identity_intake(st.session_state.collected):
        if st.session_state.get("pending_kyc_report"):
            return
        _render_identity_document_uploader()
        return
    if _is_claim_intake(st.session_state.collected):
        _render_claim_document_uploader()
        return
    if (
        "document file paths" not in missing
        and "incident description" not in missing
        and not st.session_state.get("awaiting_document_followup")
    ):
        return
    with st.expander("Upload documents", expanded=True):
        if _is_individual_kyc_intake(st.session_state.collected):
            st.caption("Upload PAN card and Aadhaar card as PDF or image files.")
        if _is_business_kyb_intake(st.session_state.collected):
            st.caption("Upload company PAN, GST certificate, incorporation, board resolution, address, signatory, ownership, and bank proof documents.")
        if _is_claim_intake(st.session_state.collected):
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
        if _is_claim_intake(st.session_state.collected):
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
                if _is_identity_report(report):
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


def _render_claim_document_uploader() -> None:
    missing = _missing_fields(st.session_state.collected)
    if "claim_type" in missing:
        return
    customer_type = st.session_state.collected.get("customer_type")
    case_type = st.session_state.collected.get("case_type")
    required_documents = get_required_documents(customer_type, "claim_validation", case_type)["required_documents"]
    uploads = st.session_state.setdefault("claim_uploads", {})

    with st.expander("Claim compliance checklist", expanded=True):
        st.markdown(_claim_compliance_rules(customer_type, case_type, required_documents))
        _render_claim_details_inputs(customer_type, case_type)
        st.session_state.collected["incident_description"] = st.text_area(
            "Incident description",
            value=st.session_state.collected.get("incident_description") or "",
            placeholder="Describe what happened, when it happened, and the loss/treatment involved.",
        ).strip()

        staged_files = {}
        for doc_type in required_documents:
            label = _display_label(doc_type).title()
            existing_path = uploads.get(doc_type)
            if existing_path:
                st.success(f"{label} uploaded: `{Path(existing_path).name}`")
            uploaded_file = st.file_uploader(
                f"Upload {label}",
                type=["txt", "pdf", "png", "jpg", "jpeg", "tiff", "bmp", "webp"],
                key=f"claim_upload_{doc_type}",
            )
            if uploaded_file is not None:
                staged_files[doc_type] = uploaded_file

        missing_docs = [doc_type for doc_type in required_documents if not uploads.get(doc_type) and doc_type not in staged_files]
        if not _has_required_claim_details(customer_type, st.session_state.collected.get("user_inputs") or {}):
            st.info("Add the claim details before analysis.")
            return
        if missing_docs:
            st.info("Upload all required claim documents before analysis: " + ", ".join(_display_label(item) for item in missing_docs) + ".")
            return
        if not st.session_state.collected.get("incident_description"):
            st.info("Add the incident description before analysis.")
            return

        if st.button("Upload and analyze claim documents", type="primary", use_container_width=True):
            for doc_type, uploaded_file in staged_files.items():
                uploads[doc_type] = _save_uploaded_file_for_doc(uploaded_file, doc_type)
            st.session_state.collected["file_paths"] = [uploads[doc_type] for doc_type in required_documents]
            st.session_state.collected["expected_document_types"] = list(required_documents)
            st.session_state.collected["prefer_vision"] = any(
                Path(uploads[doc_type]).suffix.lower() in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}
                for doc_type in required_documents
            )
            st.session_state.collected = _normalize_intake(st.session_state.collected)
            st.session_state.messages.append({"role": "user", "content": "Uploaded all required claim documents and requested compliance analysis."})
            report = run_ready_workflow(st.session_state.orchestrator, st.session_state.collected)
            if report:
                _handle_report(report)
            st.rerun()


def _render_claim_details_inputs(customer_type: str | None, case_type: str | None) -> None:
    current = st.session_state.collected.get("user_inputs") or {}
    updated = dict(current)
    st.markdown("**Claim details**")
    if customer_type == "business":
        updated["company_name"] = st.text_input("Company name", value=current.get("company_name", "")).strip()
    else:
        updated["patient_name"] = st.text_input("Patient name", value=current.get("patient_name", "")).strip()
    updated["policy_number"] = st.text_input("Policy number", value=current.get("policy_number", "")).strip()
    cols = st.columns(2)
    with cols[0]:
        updated["incident_date"] = st.text_input("Incident date", value=current.get("incident_date", ""), placeholder="DD/MM/YYYY").strip()
    with cols[1]:
        updated["claim_amount"] = st.text_input("Claim amount", value=current.get("claim_amount", ""), placeholder="Example: 450000").strip()
    if case_type:
        updated["claim_type"] = case_type
    st.session_state.collected["user_inputs"] = updated


def _render_user_details_form() -> None:
    if _is_claim_intake(st.session_state.collected):
        return
    missing = _missing_fields(st.session_state.collected)
    if "user details" not in missing and "business details" not in missing:
        return
    customer_type = st.session_state.collected.get("customer_type")
    if customer_type not in {"individual", "business"} or not st.session_state.collected.get("workflow_type"):
        return

    current = st.session_state.collected.get("user_inputs") or {}
    title = "Business details" if customer_type == "business" else "User details"
    with st.expander(title, expanded=True):
        with st.form(f"{customer_type}_user_details_form"):
            if customer_type == "business":
                details, submitted = _business_details_inputs(current)
            else:
                details, submitted = _individual_details_inputs(current)

        if not submitted:
            return

        validation = _validate_application_details(details, customer_type)
        if not validation["is_valid"]:
            st.error("Please correct: " + "; ".join(validation["issues"]))
            return

        st.session_state.collected["user_inputs"] = validation.get("normalized_details") or details
        st.session_state.messages.append({"role": "user", "content": f"Submitted {title.lower()}."})
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
        best_policy = _best_policy(payload)
        st.caption("Recommended policies")
        if best_policy:
            st.markdown(_best_policy_box(best_policy, payload), unsafe_allow_html=True)
        for item in payload["recommendations"]:
            with st.expander(item["scheme_name"], expanded=item == best_policy):
                st.markdown(_policy_detail_markdown(item, item == best_policy))

        with st.form("policy_question_form"):
            question = st.text_input("Ask about these policies", placeholder="Example: why is this better for me?")
            asked = st.form_submit_button("Ask")
        if asked and question.strip():
            st.session_state.messages.append({"role": "user", "content": question.strip()})
            st.session_state.messages.append({"role": "assistant", "content": _answer_policy_question(report, question.strip())})
            st.rerun()

        if not st.session_state.policy_application_approved:
            approve_col, decline_col = st.columns(2)
            with approve_col:
                identity_label = "KYB" if payload.get("customer_type") == "business" else "KYC"
                if st.button(f"Approve and continue to {identity_label}", type="primary", use_container_width=True):
                    _start_identity_workflow_from_policy(report)
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


def _individual_details_inputs(current: dict) -> tuple[dict, bool]:
    name = st.text_input("Name", value=current.get("name", ""))
    date_of_birth = st.text_input("Date of birth", value=current.get("date_of_birth", ""), placeholder="DD/MM/YYYY")
    address = st.text_area("Address", value=current.get("address", ""))
    phone_number = st.text_input("Phone number", value=current.get("phone_number", ""))
    job = st.text_input("Job", value=current.get("job", ""))
    annual_income = st.text_input("Annual income", value=current.get("annual_income", ""))
    submitted = st.form_submit_button("Continue", type="primary")
    return (
        {
            **current,
            "name": name.strip(),
            "date_of_birth": date_of_birth.strip(),
            "address": address.strip(),
            "phone_number": phone_number.strip(),
            "job": job.strip(),
            "annual_income": annual_income.strip(),
        },
        submitted,
    )


def _business_details_inputs(current: dict) -> tuple[dict, bool]:
    company_name = st.text_input("Company name", value=current.get("company_name", ""))
    business_type = st.text_input("Business type", value=current.get("business_type", ""), placeholder="Manufacturing, retail, services...")
    registered_address = st.text_area("Registered address", value=current.get("registered_address", ""))
    contact_person = st.text_input("Contact person", value=current.get("contact_person", ""))
    contact_phone = st.text_input("Contact phone", value=current.get("contact_phone", ""))
    annual_turnover = st.text_input("Annual turnover", value=current.get("annual_turnover", ""))
    employee_count = st.text_input("Employee count", value=current.get("employee_count", ""))
    submitted = st.form_submit_button("Continue", type="primary")
    return (
        {
            **current,
            "company_name": company_name.strip(),
            "business_type": business_type.strip(),
            "registered_address": registered_address.strip(),
            "contact_person": contact_person.strip(),
            "contact_phone": contact_phone.strip(),
            "annual_turnover": annual_turnover.strip(),
            "employee_count": employee_count.strip(),
        },
        submitted,
    )


def _render_identity_document_uploader() -> None:
    customer_type = st.session_state.collected.get("customer_type")
    identity_label = "KYB" if customer_type == "business" else "KYC"
    required_documents = _required_identity_documents(customer_type)
    uploads = st.session_state.setdefault("identity_uploads", {})

    with st.expander(f"{identity_label} document checklist", expanded=True):
        st.markdown(_identity_compliance_rules(customer_type))
        staged_files = {}
        for doc_type in required_documents:
            label = _display_label(doc_type).title()
            existing_path = uploads.get(doc_type)
            if existing_path:
                st.success(f"{label} uploaded: `{Path(existing_path).name}`")
            uploaded_file = st.file_uploader(
                f"Upload {label}",
                type=["txt", "pdf", "png", "jpg", "jpeg", "tiff", "bmp", "webp"],
                key=f"identity_upload_{doc_type}",
            )
            if uploaded_file is not None:
                staged_files[doc_type] = uploaded_file

        missing_docs = [doc_type for doc_type in required_documents if not uploads.get(doc_type) and doc_type not in staged_files]
        if missing_docs:
            st.info("Upload all required documents before validation: " + ", ".join(_display_label(item) for item in missing_docs) + ".")
            return

        if st.button(f"Upload and analyze {identity_label} documents", type="primary", use_container_width=True):
            for doc_type, uploaded_file in staged_files.items():
                uploads[doc_type] = _save_uploaded_file_for_doc(uploaded_file, doc_type)
            _run_identity_validation(customer_type, payload_user_inputs=st.session_state.collected.get("user_inputs") or {})
            st.rerun()


def _render_kyc_review() -> None:
    report = st.session_state.get("pending_kyc_report")
    if not report:
        return
    payload = report.json_report
    identity_label = "KYB" if payload.get("customer_type") == "business" else "KYC"
    with st.expander(f"{identity_label} details review", expanded=True):
        by_document = payload.get("extracted_by_document") or {}
        if by_document:
            for document_type, fields in by_document.items():
                fields = _identity_display_fields(payload, fields)
                if not fields:
                    continue
                st.markdown(f"**{_display_label(document_type).title()}**")
                st.json(fields)
        else:
            st.info(f"No {identity_label} fields were parsed from the uploaded documents.")

        st.markdown("**Summary**")
        st.write(_kyc_review_summary(report))
        _render_document_debug(payload)

        can_approve = _kyc_details_align(payload)
        if not can_approve:
            if _requires_human_review_without_reupload(payload):
                st.warning(
                    f"The {identity_label} details show partial consistency. You can proceed, but an agent may contact the user for additional information."
                )
                _render_identity_review_findings(payload)
                _render_manual_processing_proceed(payload, identity_label)
                return
            st.warning(f"Some {identity_label} details need another look. You can re-upload only the exact document that needs correction below.")
            _render_identity_review_findings(payload)
            _render_identity_reupload_controls(payload)
            st.warning("For demo/manual processing, you can proceed without re-uploading. This does not mark the documents as fully valid.")
            _render_manual_processing_proceed(payload, identity_label)
            return

        if st.button(f"Approve and store {identity_label} JSON", type="primary", use_container_width=True):
            stored_path = _store_kyc_json(payload, approved=True)
            st.session_state.messages.append({"role": "assistant", "content": f"{identity_label} details approved and stored as JSON: `{stored_path}`."})
            st.session_state.pending_kyc_report = None
            st.session_state.collected = _empty_intake()
            st.session_state.transcript = []
            st.session_state.awaiting_document_followup = False
            st.session_state.messages.append({"role": "assistant", "content": "What would you like to process next?"})
            st.rerun()


def _render_identity_reupload_controls(payload: dict) -> None:
    customer_type = payload.get("customer_type")
    identity_label = "KYB" if customer_type == "business" else "KYC"
    target_docs = _docs_to_reupload(payload)
    if not target_docs:
        target_docs = _required_identity_documents(customer_type)
    st.markdown("**Upload corrected document**")
    st.caption("Choose the corrected file, then press the button to upload and analyze it.")
    staged_files = {}
    for doc_type in target_docs:
        uploaded_file = st.file_uploader(
            f"Re-upload {_display_label(doc_type).title()}",
            type=["txt", "pdf", "png", "jpg", "jpeg", "tiff", "bmp", "webp"],
            key=f"reupload_{doc_type}",
        )
        if uploaded_file is not None:
            staged_files[doc_type] = uploaded_file

    if staged_files and st.button(f"Upload correction and analyze {identity_label}", type="primary", use_container_width=True):
        for doc_type, uploaded_file in staged_files.items():
            st.session_state.identity_uploads[doc_type] = _save_uploaded_file_for_doc(uploaded_file, doc_type)
        _run_identity_validation(customer_type, payload_user_inputs=payload.get("user_inputs") or {}, correction=True)
        st.rerun()


def _render_manual_processing_proceed(payload: dict, identity_label: str) -> None:
    st.markdown("**Manual processing warning**")
    st.caption(
        "The uploaded documents are not completely valid. Proceeding may require the user to provide additional information when an agent contacts them."
    )
    acknowledged = st.checkbox(
        "I understand this case may need manual processing and follow-up information.",
        key=f"manual_processing_ack_{payload.get('report_id')}",
    )
    if acknowledged and st.button(f"Proceed with manual {identity_label} processing", type="primary", use_container_width=True):
        stored_path = _store_kyc_json(payload, approved=False)
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": (
                    f"{identity_label} documents were accepted for manual processing and stored as JSON: `{stored_path}`. "
                    "An agent may request additional information before final approval."
                ),
            }
        )
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


def _select_option(value: str) -> None:
    missing = _missing_fields(st.session_state.collected)
    st.session_state.selected_option = None
    st.session_state.show_options = False
    if "customer_type" in missing:
        st.session_state.collected["customer_type"] = value
    elif "workflow_type" in missing:
        st.session_state.collected["workflow_type"] = value
    elif "insurance_category" in missing:
        st.session_state.collected["insurance_category"] = value
    elif "claim_type" in missing:
        st.session_state.collected["case_type"] = value
    else:
        _submit_user_text(_option_user_text(value))
        return

    st.session_state.collected = _normalize_intake(st.session_state.collected)
    st.session_state.messages.append({"role": "user", "content": _option_user_text(value)})
    report = run_ready_workflow(st.session_state.orchestrator, st.session_state.collected)
    if report:
        _handle_report(report)
    else:
        question = next_assistant_question(st.session_state.orchestrator, st.session_state.collected)
        if question:
            st.session_state.messages.append({"role": "assistant", "content": question})
            st.session_state.show_options = _question_needs_options(st.session_state.collected)
    st.rerun()


def _handle_report(report) -> None:
    st.session_state.report = report
    st.session_state.messages.append({"role": "assistant", "content": _report_summary(report)})
    if _is_policy_report(report):
        st.session_state.pending_policy_report = report
        st.session_state.policy_application_approved = False
        st.session_state.messages.append({"role": "assistant", "content": _policy_approval_prompt(report)})
    elif _is_identity_report(report):
        st.session_state.pending_kyc_report = report
        st.session_state.messages.append({"role": "assistant", "content": _kyc_review_summary(report)})
        st.session_state.awaiting_document_followup = not _kyc_details_align(report.json_report)
    elif _is_claim_report(report):
        st.session_state.collected = _empty_intake()
        st.session_state.transcript = []
        st.session_state.selected_option = None
        st.session_state.show_options = False
        st.session_state.awaiting_document_followup = False
        st.session_state.claim_uploads = {}
        st.session_state.upload_session_id = uuid4().hex[:10]
        st.session_state.messages.append({"role": "assistant", "content": "Review the claim result below, then submit it or route it for manual approval."})
    elif _should_continue_document_workflow(report):
        st.session_state.collected = _prepare_followup_intake(st.session_state.collected, report)
        st.session_state.transcript = []
        st.session_state.messages.append({"role": "assistant", "content": _followup_prompt(report)})
    else:
        st.session_state.collected = _empty_intake()
        st.session_state.transcript = []
        st.session_state.selected_option = None
        st.session_state.messages.append({"role": "assistant", "content": "What would you like to process next?"})


def _render_claim_review() -> None:
    report = st.session_state.get("report")
    if not report or not _is_claim_report(report):
        return

    payload = report.json_report
    status = payload.get("status", "Unknown")
    if status == "Ready for Submission":
        st.success("Claim validation complete. The documents look consistent and the claim is ready for submission.")
    elif payload.get("missing_documents"):
        st.warning("Claim validation found missing documents.")
    else:
        st.warning("Claim validation found details that need review or correction.")

    with st.expander("Claim validation result", expanded=True):
        top_cols = st.columns(3)
        top_cols[0].metric("Status", status)
        top_cols[1].metric("Confidence", payload.get("confidence", "n/a"))
        top_cols[2].metric("Human review", "Yes" if payload.get("human_review_required") else "No")

        st.markdown("**Incident summary**")
        st.info(_claim_incident_summary(payload))

        claim_doc_summary = payload.get("claim_document_summary") or {}
        if claim_doc_summary:
            st.markdown("**LLM document review**" if claim_doc_summary.get("source") == "llm_with_mcp_rules" else "**Document review summary**")
            st.info(_format_claim_document_summary(claim_doc_summary))

        st.markdown("**Coverage assessment**")
        coverage = _claim_coverage_assessment(payload)
        if coverage["covered"]:
            st.success(coverage["message"])
        elif coverage["manual_review"]:
            st.warning(coverage["message"])
        else:
            st.error(coverage["message"])

        missing = payload.get("missing_documents") or []
        if missing:
            st.markdown("**Missing documents**")
            for item in missing:
                st.error(_display_label(item).title())

        issues = payload.get("validation_issues") or []
        if issues:
            st.markdown("**Fields needing attention**")
            for issue in issues:
                field = _display_label(issue.get("field") or "details").title()
                message = issue.get("message") or "Needs review"
                severity = issue.get("severity", "review")
                values = issue.get("values") or {}
                detail = f"**{field}**: {message}"
                if values:
                    detail += " Values seen: " + ", ".join(str(value) for value in values.keys())
                if severity in {"high", "medium"}:
                    st.error(detail)
                else:
                    st.warning(detail)
        else:
            st.markdown("**Issues**")
            st.success("No mismatches or missing claim details were found.")

        extracted = payload.get("extracted_key_fields") or {}
        important_fields = ["company_name", "patient_name", "policy_number", "incident_date", "claim_amount"]
        shown_fields = {field: extracted.get(field) for field in important_fields if extracted.get(field)}
        if shown_fields:
            st.markdown("**Extracted claim details**")
            st.table(
                [
                    {"Field": _display_label(field).title(), "Value": value}
                    for field, value in shown_fields.items()
                ]
            )

        with st.expander("Documents parsed", expanded=False):
            by_document = payload.get("extracted_by_document") or {}
            if by_document:
                for doc_type, fields in by_document.items():
                    st.markdown(f"**{_display_label(doc_type).title()}**")
                    st.json(fields)
            else:
                st.info("No structured claim fields were extracted from the uploaded files.")

        _render_claim_manual_approval(payload)

        if st.button("Start another claim check", use_container_width=True):
            st.session_state.report = None
            st.session_state.collected = {
                **_empty_intake(),
                "workflow_type": "claim_validation",
            }
            st.session_state.transcript = []
            st.session_state.claim_uploads = {}
            st.session_state.upload_session_id = uuid4().hex[:10]
            st.session_state.messages.append({"role": "assistant", "content": "Sure. Is this claim for an individual or a business?"})
            st.session_state.show_options = True
            st.rerun()


def _current_options() -> list[dict[str, str]]:
    missing = _missing_fields(st.session_state.collected)
    customer_type = st.session_state.collected.get("customer_type")
    workflow_type = st.session_state.collected.get("workflow_type")

    if "user details" in missing or "business details" in missing:
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
    return []


def _claim_incident_summary(payload: dict) -> str:
    details = payload.get("user_inputs") or {}
    extracted = payload.get("extracted_key_fields") or {}
    name = details.get("company_name") or details.get("patient_name") or extracted.get("company_name") or extracted.get("patient_name") or "The claimant"
    policy_number = details.get("policy_number") or extracted.get("policy_number") or "the submitted policy"
    incident_date = details.get("incident_date") or extracted.get("incident_date")
    claim_amount = details.get("claim_amount") or extracted.get("claim_amount")
    description = payload.get("incident_description") or "No incident description was provided."
    pieces = [f"{name} submitted a { _display_label(payload.get('case_type') or 'claim') } claim under policy {policy_number}."]
    if incident_date:
        pieces.append(f"The incident date is {incident_date}.")
    if claim_amount:
        pieces.append(f"The claimed amount is INR {claim_amount}.")
    pieces.append(description)
    return " ".join(pieces)


def _claim_coverage_assessment(payload: dict) -> dict[str, object]:
    status = payload.get("status")
    case_type = payload.get("case_type")
    text = " ".join(
        str(item or "")
        for item in [
            payload.get("incident_description"),
            payload.get("user_inputs") or {},
            payload.get("extracted_key_fields") or {},
        ]
    ).lower()
    coverage_terms = {
        "health": ["hospital", "hospitalized", "treatment", "surgery", "appendicitis", "discharge", "bill"],
        "property_damage": ["fire", "damage", "repair", "stock", "electrical", "warehouse", "fixture", "rain"],
        "cybersecurity": ["ransomware", "malware", "breach", "vpn", "server", "forensic", "data", "incident response"],
    }
    keyword_match = any(term in text for term in coverage_terms.get(case_type, []))
    if status == "Ready for Submission" and keyword_match:
        return {
            "covered": True,
            "manual_review": False,
            "message": "The incident appears to fall within the selected policy coverage based on the uploaded documents and claim details.",
        }
    if status == "Ready for Submission":
        return {
            "covered": True,
            "manual_review": True,
            "message": "The documents are consistent and ready for submission. Coverage appears plausible, but the incident wording should be reviewed by a claims handler.",
        }
    if payload.get("missing_documents"):
        return {
            "covered": False,
            "manual_review": True,
            "message": "Coverage cannot be confirmed yet because required documents are missing. The claim can be routed for manual follow-up.",
        }
    return {
        "covered": False,
        "manual_review": True,
        "message": "Coverage cannot be automatically confirmed because some document fields do not match. The claim can still proceed through manual approval for demo or operations review.",
    }


def _format_claim_document_summary(summary: dict) -> str:
    lines = []
    labels = [
        ("event_summary", "Event"),
        ("timeline", "Timeline"),
        ("likely_cause", "Likely cause"),
        ("affected_assets_or_treatment", "Impact"),
        ("evidence_reviewed", "Evidence"),
        ("coverage_reasoning", "Coverage reasoning"),
        ("missing_or_unclear_information", "Missing or unclear"),
    ]
    for key, label in labels:
        value = summary.get(key)
        if value:
            lines.append(f"{label}: {value}")
    return "\n\n".join(lines) or "No claim document summary was generated."


def _render_claim_manual_approval(payload: dict) -> None:
    report_id = payload.get("report_id") or "claim"
    decision = st.session_state.setdefault("claim_decisions", {}).get(report_id)
    if decision:
        if decision.get("decision") == "submitted":
            st.success(f"Claim submitted successfully. Decision stored at `{decision.get('path')}`.")
        else:
            st.warning(f"Claim routed for manual approval. Decision stored at `{decision.get('path')}`.")
        return

    if payload.get("status") == "Ready for Submission":
        if st.button("Proceed with claim submission", type="primary", use_container_width=True):
            stored_path = _store_claim_decision(payload, decision="submitted")
            _mark_claim_decision(payload, "submitted", stored_path)
            st.session_state.messages.append({"role": "assistant", "content": f"Claim marked for submission and stored at `{stored_path}`."})
            st.rerun()
        return

    st.markdown("**Manual approval**")
    st.warning(
        "This claim is not fully auto-approved. You can proceed for manual approval, but a claims handler may ask for corrected documents or additional information."
    )
    acknowledged = st.checkbox(
        "I understand this claim needs manual processing.",
        key=f"claim_manual_ack_{payload.get('report_id')}",
    )
    if st.button("Proceed with manual approval", type="primary", use_container_width=True, disabled=not acknowledged):
        stored_path = _store_claim_decision(payload, decision="manual_approval")
        _mark_claim_decision(payload, "manual_approval", stored_path)
        st.session_state.messages.append({"role": "assistant", "content": f"Claim routed for manual approval and stored at `{stored_path}`."})
        st.rerun()


def _mark_claim_decision(payload: dict, decision: str, stored_path: str) -> None:
    report_id = payload.get("report_id") or "claim"
    st.session_state.setdefault("claim_decisions", {})[report_id] = {
        "decision": decision,
        "path": stored_path,
    }


def _store_claim_decision(payload: dict, *, decision: str) -> str:
    output_dir = Path("outputs/claim_decisions")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_id = payload.get("report_id") or uuid4().hex[:10]
    target = output_dir / f"{report_id}_{decision}.json"
    stored_payload = {
        "report_id": payload.get("report_id"),
        "decision": decision,
        "status": payload.get("status"),
        "customer_type": payload.get("customer_type"),
        "case_type": payload.get("case_type"),
        "incident_summary": _claim_incident_summary(payload),
        "coverage_assessment": _claim_coverage_assessment(payload),
        "missing_documents": payload.get("missing_documents") or [],
        "validation_issues": payload.get("validation_issues") or [],
        "extracted_key_fields": payload.get("extracted_key_fields") or {},
        "user_inputs": payload.get("user_inputs") or {},
    }
    target.write_text(json.dumps(stored_payload, indent=2), encoding="utf-8")
    return str(target)


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


def _run_sample_individual_kyc() -> None:
    _reset_conversation()
    st.session_state.messages.append({"role": "user", "content": "Run sample individual KYC verification."})
    st.session_state.identity_uploads = {
        path.stem: str(path)
        for path in Path("sample_data/individual_kyc_mismatch").glob("*.txt")
        if path.stem in {"pan", "identity_proof"}
    }
    report = st.session_state.orchestrator.run_document_validation(
        _sample_document_packet(
            "individual",
            "kyc_validation",
            "kyc",
            "sample_data/individual_kyc_mismatch",
            user_inputs={
                "name": "Rohan Mehta",
                "date_of_birth": "05/03/1992",
                "address": "77 Park Street Mumbai",
                "phone_number": "9876543210",
                "job": "Software Engineer",
                "annual_income": "1200000",
            },
        )
    )
    _handle_report(report)


def _run_sample_business_kyb() -> None:
    _reset_conversation()
    st.session_state.messages.append({"role": "user", "content": "Run sample business KYB verification."})
    st.session_state.identity_uploads = {
        path.stem: str(path)
        for path in Path("sample_data/business_kyb").glob("*.txt")
    }
    report = st.session_state.orchestrator.run_document_validation(
        _sample_document_packet(
            "business",
            "kyb_validation",
            "kyb",
            "sample_data/business_kyb",
            user_inputs={
                "company_name": "Acme Manufacturing Pvt Ltd",
                "business_type": "manufacturing",
                "registered_address": "12 Industrial Estate, Pune",
                "contact_person": "Nisha Rao",
                "contact_phone": "9876543210",
                "annual_turnover": "50000000",
                "employee_count": "120",
            },
        )
    )
    _handle_report(report)


def _run_sample_property_claim() -> None:
    _reset_conversation()
    required_documents = get_required_documents("business", "claim_validation", "property_damage")["required_documents"]
    sample_dir = Path("sample_data/demo_claim_property")
    st.session_state.claim_uploads = {
        doc_type: str(sample_dir / f"{doc_type}.txt")
        for doc_type in required_documents
    }
    st.session_state.collected = {
        **_empty_intake(),
        "customer_type": "business",
        "workflow_type": "claim_validation",
        "case_type": "property_damage",
        "user_inputs": {
            "company_name": "Acme Components Pvt Ltd",
            "policy_number": "BUS-PROP-7788",
            "incident_date": "14/05/2026",
            "claim_amount": "450000",
            "claim_type": "property_damage",
        },
        "incident_description": "On 14/05/2026 Acme Components Pvt Ltd reported fire damage to the stock room and electrical fixtures under policy BUS-PROP-7788 for INR 450000.",
        "ready_to_run": False,
    }
    st.session_state.messages.append({"role": "user", "content": "Load sample business property claim details and documents."})
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": "Sample claim details and documents are filled in. Click **Upload and analyze claim documents** when you want to run validation.",
        }
    )
    st.session_state.show_options = False


def _sample_document_packet(customer_type: str, workflow_type: str, case_type: str, folder: str, **kwargs):
    from schemas.messages import DocumentPacketMessage

    paths = sorted(str(path) for path in Path(folder).glob("*.txt"))
    return DocumentPacketMessage(
        session_id=st.session_state.orchestrator.new_session_id(),
        customer_type=customer_type,
        workflow_type=workflow_type,
        case_type=case_type,
        file_paths=paths,
        **kwargs,
    )


def _save_uploaded_file_for_doc(uploaded_file, doc_type: str) -> str:
    output_dir = Path("outputs/uploads") / st.session_state.upload_session_id
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", uploaded_file.name)
    target = output_dir / f"{doc_type}_{safe_name}"
    target.write_bytes(uploaded_file.getbuffer())
    return str(target)


def _claim_compliance_rules(customer_type: str | None, case_type: str | None, required_documents: list[str]) -> str:
    documents = ", ".join(_display_label(item) for item in required_documents)
    if customer_type == "business" and case_type == "cybersecurity":
        return (
            "**Compliance rules for cyber claim validation**\n\n"
            f"- Required documents: {documents}.\n"
            "- Incident date, policy number, breach/loss summary, forensic evidence, and loss estimate must be readable.\n"
            "- Upload police report if fraud, extortion, or a legal case is involved.\n"
            "- The business name and policy number should be consistent across documents."
        )
    if customer_type == "business":
        return (
            "**Compliance rules for business property claim validation**\n\n"
            f"- Required documents: {documents}.\n"
            "- Policy number, incident date, company name, and claim amount must be readable.\n"
            "- Upload police report if theft or a legal case is involved.\n"
            "- Damage report and repair estimate should describe the same incident."
        )
    return (
        "**Compliance rules for health claim validation**\n\n"
        f"- Required documents: {documents}.\n"
        "- Policy number, patient name, bill amount, and hospitalization details must be readable.\n"
        "- Hospital bill and discharge summary should refer to the same patient and treatment event."
    )


def _run_identity_validation(customer_type: str | None, *, payload_user_inputs: dict, correction: bool = False) -> None:
    identity_label = "KYB" if customer_type == "business" else "KYC"
    required_documents = _required_identity_documents(customer_type)
    uploads = st.session_state.get("identity_uploads") or {}
    missing_docs = [doc_type for doc_type in required_documents if not uploads.get(doc_type)]
    if missing_docs:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "I still need these documents before analysis: "
                + ", ".join(_display_label(item) for item in missing_docs)
                + ".",
            }
        )
        return

    st.session_state.collected = {
        **_empty_intake(),
        "customer_type": customer_type,
        "workflow_type": "kyb_validation" if customer_type == "business" else "kyc_validation",
        "case_type": "kyb" if customer_type == "business" else "kyc",
        "user_inputs": payload_user_inputs,
        "file_paths": [uploads[doc_type] for doc_type in required_documents],
        "expected_document_types": list(required_documents),
        "prefer_vision": any(
            Path(uploads[doc_type]).suffix.lower() in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}
            for doc_type in required_documents
        ),
        "ready_to_run": True,
    }
    st.session_state.collected = _normalize_intake(st.session_state.collected)
    user_message = f"Uploaded corrected {identity_label} document and requested analysis." if correction else f"Uploaded all required {identity_label} documents and requested analysis."
    st.session_state.messages.append({"role": "user", "content": user_message})
    report = run_ready_workflow(st.session_state.orchestrator, st.session_state.collected)
    if report:
        st.session_state.report = report
        st.session_state.pending_kyc_report = report
        st.session_state.messages.append({"role": "assistant", "content": _report_summary(report)})
        st.session_state.messages.append({"role": "assistant", "content": _kyc_review_summary(report)})
        st.session_state.awaiting_document_followup = not _kyc_details_align(report.json_report)


def _required_identity_documents(customer_type: str | None) -> list[str]:
    workflow_type = "kyb_validation" if customer_type == "business" else "kyc_validation"
    case_type = "kyb" if customer_type == "business" else "kyc"
    return get_required_documents(customer_type, workflow_type, case_type)["required_documents"]


def _identity_compliance_rules(customer_type: str | None) -> str:
    if customer_type == "business":
        return (
            "**Compliance rules for KYB upload**\n\n"
            "- Upload one file for every listed business verification document.\n"
            "- Company name, PAN/GSTIN, registered address, authorized signatory, ownership, and bank details must be readable.\n"
            "- Documents should belong to the same legal entity and current bank account.\n"
            "- If a discrepancy is found, re-upload only the exact document named in the review."
        )
    return (
        "**Compliance rules for KYC upload**\n\n"
        "- Upload one file for PAN and one file for identity proof.\n"
        "- Name, date of birth, Aadhaar/identity number, address, and phone details must be readable where present.\n"
        "- User-entered details should match the uploaded documents.\n"
        "- If a discrepancy is found, re-upload only the exact document named in the review."
    )


def _best_policy(payload: dict) -> dict | None:
    recommendations = payload.get("recommendations") or []
    if not recommendations:
        return None
    user_inputs = payload.get("user_inputs") or {}
    return max(recommendations, key=lambda item: _policy_score(item, user_inputs))


def _policy_score(policy: dict, user_inputs: dict) -> int:
    score = len(policy.get("coverage_highlights") or []) * 3
    eligibility = policy.get("eligibility") or {}
    lowered_inputs = " ".join(str(value).lower() for value in user_inputs.values())
    for value in eligibility.values():
        if isinstance(value, str) and value.lower() in lowered_inputs:
            score += 4
        elif value is True:
            score += 1
    if policy.get("required_documents"):
        score += 1
    return score


def _best_policy_box(policy: dict, payload: dict) -> str:
    reason = _policy_reason(policy, payload.get("user_inputs") or {})
    return f"""
    <div class="best-policy-box">
      <div class="best-policy-label">Best match</div>
      <h3>{policy["scheme_name"]}</h3>
      <p>{policy.get("description", "")}</p>
      <p><strong>Why this one:</strong> {reason}</p>
    </div>
    """


def _policy_detail_markdown(policy: dict, is_best: bool = False) -> str:
    highlights = "\n".join(f"- {item}" for item in policy.get("coverage_highlights") or []) or "- Not specified"
    documents = "\n".join(f"- {_display_label(item)}" for item in policy.get("required_documents") or []) or "- Not specified"
    eligibility = "\n".join(f"- {_display_label(str(key))}: {value}" for key, value in (policy.get("eligibility") or {}).items()) or "- Standard underwriting applies"
    best_line = "\n**Recommended choice:** This is the strongest fit based on the submitted details.\n" if is_best else ""
    return (
        f"{best_line}\n"
        f"**Policy ID:** `{policy.get('scheme_id')}`\n\n"
        f"**Description:** {policy.get('description')}\n\n"
        f"**Coverage highlights**\n{highlights}\n\n"
        f"**Eligibility signals**\n{eligibility}\n\n"
        f"**Documents needed for application**\n{documents}\n\n"
        f"**Next step:** {policy.get('recommended_next_step')}"
    )


def _policy_reason(policy: dict, user_inputs: dict) -> str:
    highlights = policy.get("coverage_highlights") or []
    category_context = ", ".join(highlights[:3]).lower()
    if user_inputs:
        return f"it matches the requested insurance type and gives strong coverage around {category_context}, with documents that fit the details already collected."
    return f"it provides the broadest useful coverage in this category, especially around {category_context}."


def _answer_policy_question(report, question: str) -> str:
    payload = report.json_report
    best_policy = _best_policy(payload)
    recommendations = payload.get("recommendations") or []
    normalized = question.lower()
    if not recommendations:
        return "I could not find matching policies for this category. Try another insurance type or update the details."
    if "why" in normalized or "best" in normalized or "recommend" in normalized:
        return f"I recommend **{best_policy['scheme_name']}** because {_policy_reason(best_policy, payload.get('user_inputs') or {})}"
    if "document" in normalized:
        docs = best_policy.get("required_documents") or []
        return "For the recommended policy, the application documents are: " + ", ".join(_display_label(doc) for doc in docs) + "."
    if "cover" in normalized or "coverage" in normalized:
        return f"**{best_policy['scheme_name']}** covers: " + ", ".join(best_policy.get("coverage_highlights") or []) + "."
    if "eligib" in normalized:
        eligibility = best_policy.get("eligibility") or {}
        return "Eligibility signals for the recommended policy: " + ", ".join(f"{_display_label(str(key))}: {value}" for key, value in eligibility.items()) + "."
    return (
        f"The best fit is **{best_policy['scheme_name']}**. "
        f"{best_policy.get('description')} Next step: {best_policy.get('recommended_next_step')}"
    )


def _policy_approval_requested(text: str) -> bool:
    normalized = text.lower().strip()
    return any(phrase in normalized for phrase in ["approve", "proceed", "continue", "looks good", "go ahead"])


def _start_identity_workflow_from_policy(report) -> None:
    payload = report.json_report
    customer_type = payload.get("customer_type") or "individual"
    identity_workflow = "kyb_validation" if customer_type == "business" else "kyc_validation"
    identity_case = "kyb" if customer_type == "business" else "kyc"
    best_policy = _best_policy(payload)
    details = {
        **(payload.get("user_inputs") or {}),
        "recommended_policy_ids": [item["scheme_id"] for item in payload.get("recommendations") or []],
        "selected_policy_id": best_policy.get("scheme_id") if best_policy else None,
    }
    st.session_state.pending_policy_report = None
    st.session_state.policy_application_approved = False
    st.session_state.identity_uploads = {}
    st.session_state.collected = {
        **_empty_intake(),
        "customer_type": customer_type,
        "workflow_type": identity_workflow,
        "case_type": identity_case,
        "user_inputs": details,
        "ready_to_run": False,
    }
    st.session_state.transcript = []
    st.session_state.messages.append({"role": "user", "content": "Approved policy recommendation."})
    st.session_state.messages.append({"role": "assistant", "content": _identity_upload_prompt(customer_type)})


def _report_summary(report) -> str:
    payload = report.json_report
    if report.report_type == "new_insurance":
        names = ", ".join(item["scheme_name"] for item in payload["recommendations"]) or "no matching schemes"
        return f"Product discovery is complete. Recommended schemes: {names}."
    if payload.get("customer_type") == "individual" and payload.get("workflow_type") == "kyc_validation":
        return "KYC documents have been parsed. Please review the extracted details before approval."
    if payload.get("customer_type") == "business" and payload.get("workflow_type") == "kyb_validation":
        return "KYB documents have been parsed. Please review the extracted business details before approval."
    missing = ", ".join(payload["missing_documents"]) or "none"
    if (
        payload.get("customer_type") == "individual"
        and payload.get("workflow_type") == "claim_validation"
        and payload.get("status") == "Ready for Submission"
    ):
        return "Claim validation is complete. The uploaded documents are consistent and the claim is ready for submission."
    if payload.get("workflow_type") == "claim_validation":
        issue_count = len(payload.get("validation_issues") or [])
        status = payload.get("status", "Unknown")
        coverage = _claim_coverage_assessment(payload)["message"]
        if status == "Ready for Submission":
            return f"Claim validation is complete. The uploaded documents are consistent and the claim is ready for submission. {coverage}"
        if payload.get("missing_documents"):
            return f"Claim validation is complete. Status: {status}. Missing documents: {missing}. {coverage}"
        return f"Claim validation is complete. Status: {status}. Fields needing attention: {issue_count}. {coverage}"
    return f"Validation complete. Status: {payload['status']}. Missing documents: {missing}."


def _is_policy_report(report) -> bool:
    payload = report.json_report
    return report.report_type == "new_insurance" and payload.get("customer_type") in {"individual", "business"}


def _policy_approval_prompt(report) -> str:
    payload = report.json_report
    identity_label = "KYB" if payload.get("customer_type") == "business" else "KYC"
    return f"Please review the recommended policy. If you approve it, I will continue to {identity_label} verification."


def _is_identity_report(report) -> bool:
    payload = report.json_report
    return (
        report.report_type in {"kyc_validation", "kyb_validation"}
        and payload.get("customer_type") in {"individual", "business"}
    )


def _is_claim_report(report) -> bool:
    payload = report.json_report
    return report.report_type == "claim_validation" and payload.get("workflow_type") == "claim_validation"


def _is_claim_intake(collected: dict) -> bool:
    return collected.get("workflow_type") == "claim_validation"


def _is_individual_kyc_intake(collected: dict) -> bool:
    return collected.get("customer_type") == "individual" and collected.get("workflow_type") == "kyc_validation"


def _is_business_kyb_intake(collected: dict) -> bool:
    return collected.get("customer_type") == "business" and collected.get("workflow_type") == "kyb_validation"


def _is_identity_intake(collected: dict) -> bool:
    return _is_individual_kyc_intake(collected) or _is_business_kyb_intake(collected)


def _identity_upload_prompt(customer_type: str) -> str:
    if customer_type == "business":
        return (
            "Please upload business KYB documents: incorporation certificate, company PAN, GST certificate, "
            "registered address proof, board resolution, authorized signatory ID/address proof, beneficial ownership declaration, and bank proof."
        )
    return "Please upload PAN card and Aadhaar card PDF or image files for KYC verification."


def _should_continue_document_workflow(report) -> bool:
    payload = report.json_report
    if payload.get("workflow_type") == "claim_validation":
        return False
    return (
        payload.get("customer_type") in {"individual", "business"}
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
    if "user details" in missing or "business details" in missing:
        return False
    return any(
        item in missing
        for item in [
            "customer_type",
            "workflow_type",
            "insurance_category",
            "claim_type",
        ]
    )


def _kyc_review_summary(report) -> str:
    payload = report.json_report
    identity_label = "KYB" if payload.get("customer_type") == "business" else "KYC"
    if _documents_uploaded_but_unparsed(payload):
        return (
            f"The document was uploaded, but no readable {identity_label} fields were extracted. "
            "Use clearer images or run the app with a vision-capable model such as Gemma 4 so identity documents can be parsed directly."
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

    fields = _identity_display_fields(payload, payload.get("extracted_key_fields") or {})
    issues = payload.get("validation_issues") or []
    missing = payload.get("missing_documents") or []
    field_text = ", ".join(f"{_display_label(key)}: {value}" for key, value in fields.items()) or "no fields parsed yet"
    if _kyc_details_align(payload):
        return f"Good news, the {identity_label} check looks consistent. I found these details: {field_text}. You can approve and store the verified JSON."
    if _requires_human_review_without_reupload(payload):
        issue_text = "; ".join(issue.get("message", "needs review") for issue in issues) or "some details are only partially consistent"
        return f"I parsed these {identity_label} details: {field_text}. Some details look partially consistent, so I marked this for human review instead of asking for another upload: {issue_text}."
    issue_text = "; ".join(issue.get("message", "issue found") for issue in issues)
    missing_text = ", ".join(_display_label(item) for item in missing)
    review_parts = []
    if missing_text:
        review_parts.append(f"missing documents: {missing_text}")
    if issue_text:
        review_parts.append(f"details to correct: {issue_text}")
    return f"I parsed these {identity_label} details: {field_text}. I need a corrected upload because " + "; ".join(review_parts or ["some required details could not be verified"]) + "."


def _identity_display_fields(payload: dict, fields: dict) -> dict:
    customer_type = payload.get("customer_type")
    if customer_type == "business":
        allowed = {"company_name", "pan_number", "gstin", "registered_address", "authorized_signatory", "bank_account_holder"}
    else:
        allowed = {"customer_name", "date_of_birth", "pan_number", "aadhaar_number", "address"}
    return {key: value for key, value in fields.items() if key in allowed}


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


def _render_identity_review_findings(payload: dict) -> None:
    mismatches = _identity_mismatch_issues(payload)
    unavailable = _identity_unavailable_info(payload)

    if mismatches:
        st.markdown("**Fields needing attention**")
        for issue in mismatches:
            field = _display_label(issue.get("field") or "details")
            severity = issue.get("severity", "review")
            message = issue.get("message", "Needs review")
            if severity == "high":
                st.error(f"**{field.title()}**: {message}")
            else:
                st.warning(f"**{field.title()}**: {message}")

    if unavailable:
        st.markdown("**Information not fully captured**")
        for item in unavailable:
            st.info(item)


def _identity_mismatch_issues(payload: dict) -> list[dict]:
    return [
        issue
        for issue in payload.get("validation_issues") or []
        if issue.get("severity") in {"review", "medium", "high"} or "mismatch" in issue.get("message", "").lower()
    ]


def _identity_unavailable_info(payload: dict) -> list[str]:
    unavailable = []
    missing_documents = payload.get("missing_documents") or []
    if missing_documents:
        unavailable.append("Missing documents: " + ", ".join(_display_label(item) for item in missing_documents) + ".")

    for issue in payload.get("validation_issues") or []:
        if str(issue.get("message", "")).lower().startswith("missing key field"):
            unavailable.append(_display_label(issue.get("field", "field")).title() + " could not be extracted clearly.")

    if _documents_uploaded_but_unparsed(payload):
        unavailable.append("The uploaded file was received, but no readable identity fields could be extracted.")

    return unavailable


def _kyc_details_align(payload: dict) -> bool:
    if payload.get("missing_documents"):
        return False
    if payload.get("status") == "Human Review Required":
        return False
    serious_issues = [
        issue
        for issue in payload.get("validation_issues", [])
        if issue.get("severity") in {"medium", "high"} or "mismatch" in issue.get("message", "").lower()
    ]
    return not serious_issues


def _requires_human_review_without_reupload(payload: dict) -> bool:
    if payload.get("missing_documents"):
        return False
    issues = payload.get("validation_issues") or []
    if any(issue.get("severity") == "high" for issue in issues):
        return False
    return payload.get("status") == "Human Review Required" or any(issue.get("severity") == "review" for issue in issues)


def _docs_to_reupload(payload: dict) -> list[str]:
    required = _required_identity_documents(payload.get("customer_type"))
    docs = [doc for doc in payload.get("missing_documents") or [] if doc in required]
    field_to_docs = _identity_field_document_map(payload.get("customer_type"))
    for issue in payload.get("validation_issues") or []:
        if issue.get("severity") == "review":
            continue
        field = issue.get("field")
        docs.extend(field_to_docs.get(field, []))
        message = issue.get("message", "").lower()
        for doc_type in required:
            if doc_type.replace("_", " ") in message or doc_type in message:
                docs.append(doc_type)
    ordered_unique = []
    for doc_type in docs:
        if doc_type in required and doc_type not in ordered_unique:
            ordered_unique.append(doc_type)
    return ordered_unique


def _identity_field_document_map(customer_type: str | None) -> dict[str, list[str]]:
    if customer_type == "business":
        return {
            "company_name": ["certificate_of_incorporation", "company_pan", "gst_certificate"],
            "pan_number": ["company_pan"],
            "gstin": ["gst_certificate"],
            "registered_address": ["registered_address_proof"],
            "authorized_signatory": ["board_resolution", "authorized_signatory_id_proof"],
            "bank_account_holder": ["bank_account_proof"],
            "user_details": ["certificate_of_incorporation", "registered_address_proof"],
        }
    return {
        "customer_name": ["pan", "identity_proof"],
        "name": ["pan", "identity_proof"],
        "date_of_birth": ["identity_proof", "pan"],
        "pan_number": ["pan"],
        "aadhaar_number": ["identity_proof"],
        "address": ["identity_proof"],
        "phone_number": ["identity_proof"],
        "user_details": ["pan", "identity_proof"],
    }


def _store_kyc_json(payload: dict, *, approved: bool) -> str:
    output_dir = Path("outputs/kyb_profiles" if payload.get("customer_type") == "business" else "outputs/kyc_profiles")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_id = payload.get("report_id") or uuid4().hex[:10]
    target = output_dir / f"{report_id}.json"
    stored_payload = {
        "report_id": payload.get("report_id"),
        "customer_type": payload.get("customer_type"),
        "approved": approved,
        "status": payload.get("status"),
        "human_review_required": payload.get("human_review_required"),
        "user_inputs": payload.get("user_inputs") or {},
        "extracted_by_document": payload.get("extracted_by_document") or {},
        "extracted_key_fields": payload.get("extracted_key_fields") or {},
        "validation_issues": payload.get("validation_issues") or [],
        "missing_documents": payload.get("missing_documents") or [],
        "summary": _kyc_review_summary(st.session_state.pending_kyc_report),
    }
    target.write_text(json.dumps(stored_payload, indent=2), encoding="utf-8")
    return str(target)


def _validate_application_details(details: dict, customer_type: str) -> dict:
    local_issues = _local_user_detail_issues(details, customer_type)
    if local_issues:
        return {"is_valid": False, "issues": local_issues, "normalized_details": details}

    if customer_type == "business":
        return {"is_valid": True, "issues": [], "normalized_details": details}

    llm_result = st.session_state.orchestrator.llm_client.validate_application_details(details)
    if isinstance(llm_result, dict) and "is_valid" in llm_result:
        return {
            "is_valid": bool(llm_result.get("is_valid")),
            "issues": [str(issue) for issue in llm_result.get("issues") or []],
            "normalized_details": llm_result.get("normalized_details") or details,
        }

    return {"is_valid": True, "issues": [], "normalized_details": details}


def _local_user_detail_issues(details: dict, customer_type: str) -> list[str]:
    issues = []
    required_fields = REQUIRED_BUSINESS_USER_FIELDS if customer_type == "business" else REQUIRED_INDIVIDUAL_USER_FIELDS
    for field in required_fields:
        if not str(details.get(field) or "").strip():
            issues.append(f"{_display_label(field)} is required")
    phone_field = "contact_phone" if customer_type == "business" else "phone_number"
    if details.get(phone_field) and not _valid_phone(str(details.get(phone_field) or "")):
        issues.append(f"{_display_label(phone_field)} should be 10 to 15 digits")
    if customer_type == "individual" and details.get("annual_income") and _income_value(details.get("annual_income")) <= 0:
        issues.append("annual income should be greater than zero")
    if customer_type == "business" and details.get("annual_turnover") and _income_value(details.get("annual_turnover")) <= 0:
        issues.append("annual turnover should be greater than zero")
    if customer_type == "business" and details.get("employee_count") and _income_value(details.get("employee_count")) <= 0:
        issues.append("employee count should be greater than zero")
    return issues


def _has_required_claim_details(customer_type: str | None, details: dict) -> bool:
    required = ["policy_number", "incident_date", "claim_amount"]
    required.append("company_name" if customer_type == "business" else "patient_name")
    return all(str(details.get(field) or "").strip() for field in required)


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
        .best-policy-box {
            border: 1px solid #7bb7ff;
            background: #eaf4ff;
            border-radius: 8px;
            padding: 1rem 1.1rem;
            margin: 0.4rem 0 1rem 0;
            color: #12324f;
        }
        .best-policy-box h3 {
            margin: 0.2rem 0 0.45rem 0;
            font-size: 1.15rem;
            letter-spacing: 0;
        }
        .best-policy-box p {
            margin: 0.35rem 0;
        }
        .best-policy-label {
            display: inline-block;
            font-size: 0.78rem;
            font-weight: 700;
            color: #075ca8;
            text-transform: uppercase;
            letter-spacing: 0;
        }
        div[data-testid="stButton"] button {
            min-height: 3.2rem;
            border-radius: 8px;
            white-space: normal;
        }
        div[class*="st-key-option_"] button {
            min-height: 2.4rem;
            border-radius: 999px;
            padding: 0.35rem 0.85rem;
            font-size: 0.92rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
