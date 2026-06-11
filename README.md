# Agentic Insurance Operations Assistant

LLM-powered CLI and notebook-friendly prototype for insurance operations. It was built for an AMD Jupyter cloud hackathon environment with ROCm/vLLM support.

The interactive CLI is conversational: it does not show numbered workflow menus. The LLM asks the user questions, extracts the user’s typed answers into structured messages, and then routes the case through the agent workflow.

Capabilities and menu-like options are not hardcoded into LLM prompts. They come from local domain tools, and the LLM turns those tool results into natural language.

The app supports:

- Business and individual user journeys
- Insurance product discovery through a mock MCP-style catalogue
- Claim document validation
- Individual KYC validation
- Business KYB validation
- Deterministic validation rules for missing documents, field presence, format checks, and cross-document consistency
- Tool-backed discovery of supported workflows, insurance categories, claim types, and required documents
- JSON and Markdown reports
- SQLite audit persistence
- vLLM-generated conversational intake and optional report explanations

Important: deterministic rules still decide status, missing documents, validation issues, and human escalation. The LLM powers conversation and extraction of the user’s intent; it does not override compliance decisions.

## Tool-Backed Conversation

When the user asks a clarification question like `give me options`, the CLI invokes local domain tools:

```text
get_supported_workflows(customer_type)
get_insurance_categories(customer_type)
get_claim_types(customer_type)
get_required_documents(customer_type, workflow_type, case_type)
```

The tool result is then sent to vLLM so the model can phrase a helpful answer. This keeps business logic in Python modules and lets the LLM focus on reasoning, wording, and conversational flow.

## Project Layout

```text
.
├── app.py                         # CLI entrypoint
├── notebook_demo.py               # Notebook-friendly scripted demo helper
├── amd_jupyter_smoke_test.py      # Environment and workflow smoke test
├── agents/                        # Specialized workflow agents
├── cli/                           # LLM conversational CLI loop
├── db/                            # SQLite persistence agent
├── demo_data/                     # Scripted hackathon demo documents
├── domain_tools/                  # Tool functions for workflows, categories, claims, and documents
├── document_processing/           # Intake, classification, extraction
├── llm/                           # vLLM/OpenAI-compatible client
├── mcp_server/                    # Mock MCP catalogue and client
├── orchestrator/                  # Workflow orchestration and trace
├── rules/                         # Claim, KYC, and KYB validation rules
├── schemas/                       # Structured inter-agent messages
└── tests/                         # Unit tests for demo workflows
```

## Requirements

Minimum for scripted demos:

- Python 3.10+

Required for conversational CLI:

- vLLM server exposing an OpenAI-compatible API
- A served model name available from that vLLM server

Optional:

- `pydantic` for stricter message models
- `pypdf` for text PDF extraction
- `tesseract` system binary for image OCR

Install optional Python packages:

```bash
python3 -m pip install -r requirements.txt
```

## vLLM Configuration

The AMD Jupyter environment does not need a `.env` file. Pass vLLM settings directly to the CLI.

Default endpoint assumptions:

```text
base URL: http://localhost:8000/v1
model: amd-hackathon-model
API key: EMPTY
```

Override them with flags:

```bash
python3 app.py \
  --use-llm \
  --vllm-base-url http://localhost:8000/v1 \
  --vllm-model <served-model-name> \
  --vllm-api-key EMPTY
```

The app calls:

```text
{vllm-base-url}/chat/completions
```

## Run The Conversational CLI

Start vLLM first, then run:

```bash
python3 app.py --use-llm --vllm-model <served-model-name>
```

Example conversation:

```text
Assistant: What kind of insurance operation do you want to process?
You: I am a business user and I need to validate a property damage claim.
Assistant: Please share the document file paths for the claim packet.
You: demo_data/business_property_claim/claim_form.txt demo_data/business_property_claim/policy_copy.txt demo_data/business_property_claim/incident_report.txt
```

The assistant will generate a structured report after it has enough information.

You can type `exit`, `quit`, or `bye` to leave the CLI.

## Scripted Demo Mode

Scripted demos do not require vLLM. They are useful for judging, CI, and quick verification.

Run all demos:

```bash
python3 app.py --demo all
```

Run a single demo:

```bash
python3 app.py --demo 1
python3 app.py --demo 2
python3 app.py --demo 3
python3 app.py --demo 4
python3 app.py --demo 5
```

Demo scenarios:

- `1`: Business property insurance discovery
- `2`: Business property damage claim missing `repair_estimate`
- `3`: Individual health claim missing `discharge_summary`
- `4`: Business KYB missing `beneficial_ownership_declaration`
- `5`: Individual KYC with name mismatch

To include optional vLLM report explanations in demo mode:

```bash
python3 app.py --demo all --use-llm --vllm-model <served-model-name>
```

## Outputs

Reports are written to:

```text
outputs/reports/
```

SQLite audit data is written to:

```text
outputs/insurance_assistant.sqlite3
```

`outputs/` is ignored by git.

## Run In AMD Jupyter

Scripted notebook demo:

```python
from notebook_demo import run_demo

reports = run_demo("all")
reports[0].json_report
```

Notebook demo with vLLM explanations:

```python
from notebook_demo import run_demo

reports = run_demo(
    "all",
    use_llm=True,
    vllm_base_url="http://localhost:8000/v1",
    vllm_model="<served-model-name>",
    vllm_api_key="EMPTY",
)
reports[0].json_report.get("llm_explanation")
```

Environment smoke test:

```bash
python3 amd_jupyter_smoke_test.py
```

Smoke test with vLLM:

```bash
python3 amd_jupyter_smoke_test.py --use-llm --vllm-model <served-model-name>
```

The smoke test prints Python/platform details, checks whether PyTorch ROCm is visible, checks whether the vLLM endpoint is reachable, then runs all scripted demos.

## Validate Before Push

Run these commands before committing:

```bash
python3 -m py_compile app.py notebook_demo.py amd_jupyter_smoke_test.py cli/*.py llm/*.py agents/*.py orchestrator/*.py schemas/messages.py document_processing/*.py rules/*.py mcp_server/*.py db/database.py tests/test_demo_workflows.py
python3 app.py --demo all
python3 -m unittest discover -s tests
python3 amd_jupyter_smoke_test.py
```

Expected result:

- All five scripted demos complete
- Unit tests pass
- Smoke test generates five reports
- Generated `outputs/`, `__pycache__/`, and notebook checkpoint files are not committed

## Git Hygiene

The repository ignores generated and local-only files:

- `outputs/`
- `__pycache__/`
- `*.pyc`
- `.ipynb_checkpoints/`
- `.venv/`
- `.env`

Commit source files, demo data, tests, and this README. Do not commit generated reports, SQLite output, credentials, virtual environments, or notebook checkpoints.
