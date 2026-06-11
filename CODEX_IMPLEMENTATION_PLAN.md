# Codex Build Brief: Agentic Insurance Operations Assistant

## 1. Goal

Build a CLI-based agentic insurance assistant for a hackathon demo.

The assistant should support two user types:

1. Business user
2. Individual user

For each user type, the assistant should support three core workflows:

1. Find new insurance using a mock MCP product catalogue
2. Validate claim documents using document extraction and compliance rules
3. Validate KYC/KYB documents using consistency checks and structured reporting

The solution should be built as an agentic workflow, not as a monolithic chatbot.

---

## 2. Core Principle

The CLI is only the interface.

All business logic must be handled by agents that communicate through structured messages.

The desired architecture is:

```text
CLI
  -> Router Agent
  -> Structured Message
  -> Workflow Orchestrator
  -> Specialized Agents
  -> Structured Report
  -> Database / CLI Response
```

---

## 3. Required Capabilities

## 3.1 Business User

When the user selects `Business`, show these options:

```text
1. Find new insurance
2. Validate claim documents
3. Complete KYB/KYC validation
4. Exit
```

### Business: New Insurance

Supported categories:

1. Property insurance
2. Employee life insurance
3. Employee health insurance
4. Professional liability insurance

Expected flow:

```text
Business user
  -> selects new insurance
  -> selects category
  -> chatbot collects basic business details
  -> Product Discovery Agent calls mock MCP catalogue
  -> assistant returns recommended schemes
```

The mock MCP catalogue should return:

- scheme name
- category
- eligibility
- coverage highlights
- required documents
- recommended next step

### Business: Claim Validation

Supported claim types:

1. Property damage claim
2. Employee health claim
3. Employee life claim
4. Professional liability claim

Expected flow:

```text
Business user
  -> selects claim validation
  -> selects claim type
  -> uploads PDF/image documents using file paths
  -> Document Intake Agent parses PDFs and OCRs images/scanned PDFs
  -> Document Classifier Agent identifies document types
  -> Extraction Agent extracts key fields
  -> Validation Agent checks required documents and rules
  -> Report Agent generates validation report
```

The report should say:

- claim type
- documents received
- missing documents
- failed rules
- inconsistencies
- status
- human review required or not
- next action

### Business: KYB/KYC Validation

Required business documents:

- certificate of incorporation
- company PAN
- GST certificate
- registered address proof
- board resolution
- authorized signatory ID proof
- authorized signatory address proof
- beneficial ownership declaration
- bank account proof

Expected checks:

- company name consistency
- PAN consistency
- GSTIN format validity
- registered address consistency
- authorized signatory presence
- board resolution authorizes signatory
- beneficial ownership declaration present
- bank account holder matches company name
- mandatory documents present

---

## 3.2 Individual User

When the user selects `Individual`, show these options:

```text
1. Find new insurance
2. Validate claim documents
3. Complete KYC validation
4. Exit
```

### Individual: New Insurance

Supported categories:

1. Health insurance
2. Life insurance
3. Motor insurance
4. Travel insurance
5. Home insurance
6. Personal accident insurance

Expected flow:

```text
Individual user
  -> selects new insurance
  -> selects category
  -> chatbot collects basic user details
  -> Product Discovery Agent calls mock MCP catalogue
  -> assistant returns recommended schemes
```

### Individual: Claim Validation

Supported claim types:

1. Health claim
2. Life claim
3. Motor claim
4. Travel claim
5. Home insurance claim
6. Personal accident claim

Expected flow:

```text
Individual user
  -> selects claim validation
  -> selects claim type
  -> uploads PDF/image documents using file paths
  -> system parses and OCRs documents
  -> system classifies documents
  -> system extracts key fields
  -> system validates documents against claim rules
  -> system generates validation report
```

### Individual: KYC Validation

Required documents:

- PAN
- Aadhaar or passport
- address proof
- bank proof

Expected checks:

- name consistency
- date of birth consistency
- address consistency
- PAN format validity
- bank account holder matches customer
- mandatory documents present

---

## 4. Agentic Architecture

Implement the application using these agents.

| Agent | Responsibility |
|---|---|
| Router Agent | Determines user type and requested workflow |
| Product Discovery Agent | Calls mock MCP catalogue and recommends products |
| Document Intake Agent | Accepts file paths, parses PDFs, runs OCR when needed |
| Document Classifier Agent | Identifies document types |
| Extraction Agent | Extracts structured fields from documents |
| Reconciliation Agent | Compares values across documents |
| Validation Agent | Applies claim, KYC, and KYB rules |
| Report Agent | Produces JSON and Markdown reports |
| Database Agent | Saves reports and successful submissions |
| Escalation Agent | Decides whether human review is required |

Each agent should:

1. Accept a structured input message
2. Return a structured output message
3. Avoid printing directly to CLI
4. Avoid reading global state
5. Log its action in a workflow trace

---

## 5. Structured Messaging

Create `schemas/messages.py`.

Use Pydantic models to pass information between agents.

Minimum message objects:

```python
class UserIntentMessage(BaseModel):
    session_id: str
    customer_type: Literal["business", "individual"]
    intent: Literal["new_insurance", "claim_validation", "kyc_validation", "kyb_validation"]
    raw_input: str | None = None
```

```python
class ProductDiscoveryMessage(BaseModel):
    session_id: str
    customer_type: Literal["business", "individual"]
    insurance_category: str
    user_inputs: dict
```

```python
class DocumentPacketMessage(BaseModel):
    session_id: str
    customer_type: Literal["business", "individual"]
    workflow_type: Literal["claim_validation", "kyc_validation", "kyb_validation"]
    case_type: str
    file_paths: list[str]
```

```python
class ParsedDocumentMessage(BaseModel):
    session_id: str
    documents: list[dict]
```

```python
class ExtractionResultMessage(BaseModel):
    session_id: str
    extracted_fields: dict
    evidence: dict
    confidence: float
```

```python
class ValidationResultMessage(BaseModel):
    session_id: str
    status: Literal[
        "Ready for Submission",
        "Needs Additional Documents",
        "Needs Correction",
        "Human Review Required"
    ]
    human_review_required: bool
    confidence: float
    missing_documents: list[str]
    issues: list[dict]
    next_action: str
```

```python
class ReportMessage(BaseModel):
    session_id: str
    report_id: str
    report_type: str
    json_report: dict
    markdown_report: str
```

---

## 6. MCP Product Catalogue

Implement a mock MCP-style product catalogue.

Do not hardcode product recommendations inside the CLI.

The Product Discovery Agent must call an MCP client function.

Required MCP-style functions:

```python
get_business_insurance_schemes(...)
get_individual_insurance_schemes(...)
```

The catalogue can be a local JSON file.

Each product should include:

```json
{
  "scheme_id": "BUS-PROP-001",
  "customer_type": "business",
  "category": "property",
  "scheme_name": "Commercial Property Protect Plus",
  "description": "Covers commercial property against fire, burglary, natural disaster, and business interruption.",
  "eligibility": {},
  "coverage_highlights": [],
  "required_documents": [],
  "claim_types_supported": []
}
```

---

## 7. Document Handling Logic

The assistant must support:

1. Text PDFs
2. Scanned PDFs
3. Images
4. TXT files

Document processing logic:

```text
Receive file path
  -> check file exists
  -> if text PDF, extract text
  -> if scanned PDF, run OCR
  -> if image, run OCR
  -> if TXT, read text
  -> return parsed document object
```

Parsed document object should include:

- file name
- file path
- extracted text
- extraction method
- OCR used or not
- document type
- confidence

---

## 8. Validation Logic

Use deterministic validation wherever possible.

The LLM should help with:

- flexible field extraction
- ambiguous document classification
- explanation generation
- report wording

The LLM should not be the only source of truth for rules.

Validation should check:

1. Required documents
2. Conditional documents
3. Key field presence
4. Cross-document consistency
5. Format validation
6. Policy/date/amount consistency where fields are available

---

## 9. Claim Rules

Create rules for all claim types.

### Business claim types

- property_damage
- employee_health
- employee_life
- professional_liability

### Individual claim types

- health
- life
- motor
- travel
- home
- personal_accident

Each claim rule should define:

```yaml
required_documents:
  - claim_form
  - policy_copy

conditional_documents:
  - document: police_report
    condition: theft_or_legal_case

field_checks:
  - policy_number_present
  - incident_date_present
  - claim_amount_present

consistency_checks:
  - policy_number_matches_across_documents
```

---

## 10. Status Decisioning

Use this decision logic:

```text
If high severity issue exists:
    status = Human Review Required

Else if required documents are missing:
    status = Needs Additional Documents

Else if medium severity inconsistency exists:
    status = Needs Correction

Else if all mandatory checks pass:
    status = Ready for Submission

Else:
    status = Human Review Required
```

The system should always explain the status.

---

## 11. Database Persistence

Use SQLite.

Save:

1. Product recommendation logs
2. Claim validation reports
3. KYC validation reports
4. KYB validation reports

A clean KYC/KYB submission should be saved with status `Ready for Submission`.

A failed or incomplete submission should also be saved as a validation report for audit purposes.

---

## 12. Reports

Every validation workflow must produce:

1. JSON report
2. Markdown report
3. CLI summary

Report must include:

- workflow type
- customer type
- case type
- status
- confidence
- missing documents
- validation issues
- extracted key fields
- evidence
- next action
- human review required

---

## 13. Recommended Folder Structure

```text
insurance-agent/
├── app.py
├── cli/
├── orchestrator/
│   ├── workflow.py
│   └── trace.py
├── agents/
├── schemas/
│   ├── messages.py
│   └── reports.py
├── mcp_server/
│   ├── client.py
│   ├── server.py
│   └── insurance_catalog.json
├── document_processing/
├── rules/
├── db/
├── outputs/
│   └── reports/
└── tests/
```

---

## 14. Build Order for Codex

Build the project in this order.

### Step 1: CLI Skeleton

Create main menu and user flows.

Acceptance:

```text
User can select Business or Individual.
User can select one of the three workflows.
```

### Step 2: Structured Messages

Create Pydantic message objects.

Acceptance:

```text
CLI creates structured messages instead of passing raw strings.
```

### Step 3: Orchestrator

Create workflow orchestrator.

Acceptance:

```text
Workflow is executed by orchestrator, not directly by CLI.
```

### Step 4: Mock MCP Product Discovery

Create mock catalogue and MCP-style client.

Acceptance:

```text
Business and individual users can get product recommendations.
```

### Step 5: Document Intake

Implement PDF parsing and OCR.

Acceptance:

```text
System can extract text from PDFs and images.
```

### Step 6: Document Classification and Extraction

Implement document classification and key field extraction.

Acceptance:

```text
System identifies document types and extracts fields.
```

### Step 7: Rules and Validation

Implement claim, KYC, and KYB rules.

Acceptance:

```text
System detects missing documents and failed checks.
```

### Step 8: Report Generation

Generate JSON, Markdown, and CLI summaries.

Acceptance:

```text
Each workflow ends with a structured report.
```

### Step 9: SQLite Persistence

Save all workflow outputs.

Acceptance:

```text
Reports and recommendations are stored in SQLite.
```

### Step 10: Demo Polish

Add sample data and scripted demo flows.

Acceptance:

```text
Demo can run end-to-end without manual code changes.
```

---

## 15. Demo Scenarios

Prepare these demo scenarios.

### Demo 1: Business Property Insurance Discovery

Expected result:

```text
MCP catalogue returns relevant property insurance schemes.
```

### Demo 2: Business Property Damage Claim

Input packet is missing repair estimate.

Expected result:

```text
Status = Needs Additional Documents
Missing document = repair_estimate
Human review required = false
```

### Demo 3: Individual Health Claim

Input packet is missing discharge summary.

Expected result:

```text
Status = Needs Additional Documents
Missing document = discharge_summary
Human review required = false
```

### Demo 4: Business KYB

Input packet is missing beneficial ownership declaration.

Expected result:

```text
Status = Needs Additional Documents
Missing document = beneficial_ownership_declaration
```

### Demo 5: Individual KYC

Input packet has name mismatch across documents.

Expected result:

```text
Status = Needs Correction or Human Review Required
Issue = name mismatch
```

---

## 16. Final Value Proposition

This application reduces manual workload across insurance operations by automating routine product discovery, claim document validation, and KYC/KYB checks.

The solution demonstrates:

1. Agentic-first architecture
2. Structured inter-agent messaging
3. MCP-backed product discovery
4. PDF and OCR document intelligence
5. Deterministic compliance validation
6. LLM-generated explanations
7. Audit-ready reporting
8. Human escalation only when needed

The final demo should show that routine insurance operations can be processed faster, more consistently, and with less human intervention.
