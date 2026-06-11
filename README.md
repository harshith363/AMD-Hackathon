# Agentic Insurance Operations Assistant

CLI and notebook-friendly prototype for an agentic insurance operations assistant. It was built for an AMD Jupyter cloud hackathon environment with optional ROCm/vLLM support.

The app supports:

- Business and individual user journeys
- Insurance product discovery through a mock MCP-style catalogue
- Claim document validation
- Individual KYC validation
- Business KYB validation
- Deterministic rule checks for missing documents, field presence, format validation, and cross-document consistency
- JSON and Markdown reports
- SQLite audit persistence
- Optional vLLM-generated report explanations

The LLM does not decide compliance outcomes. Status, missing documents, issues, and human escalation are decided by deterministic validation rules.

## Project Layout

```text
.
├── app.py                         # CLI entrypoint
├── notebook_demo.py               # Notebook-friendly demo helper
├── amd_jupyter_smoke_test.py      # Environment and workflow smoke test
├── config.py                      # Lightweight .env loader
├── agents/                        # Specialized workflow agents
├── cli/                           # Interactive CLI prompts
├── db/                            # SQLite persistence agent
├── demo_data/                     # Scripted hackathon demo documents
├── document_processing/           # Intake, classification, extraction
├── llm/                           # Optional vLLM client
├── mcp_server/                    # Mock MCP catalogue and client
├── orchestrator/                  # Workflow orchestration and trace
├── rules/                         # Claim, KYC, and KYB validation rules
├── schemas/                       # Structured inter-agent messages
└── tests/                         # Unit tests for demo workflows
```

## Requirements

Minimum:

- Python 3.10+

Optional:

- `pydantic` for stricter message models
- `pypdf` for text PDF extraction
- `tesseract` system binary for image OCR
- vLLM running with an OpenAI-compatible API for LLM explanations

The deterministic demo runs with the Python standard library only.

## Setup

From the project root:

```bash
python3 --version
python3 app.py --demo all
```

Optional Python packages:

```bash
python3 -m pip install -r requirements.txt
```

## Run The CLI

Interactive mode:

```bash
python3 app.py
```

Scripted demo mode:

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

Reports are written to:

```text
outputs/reports/
```

SQLite audit data is written to:

```text
outputs/insurance_assistant.sqlite3
```

`outputs/` is intentionally ignored by git.

## Run In AMD Jupyter

In a notebook cell:

```python
from notebook_demo import run_demo

reports = run_demo("all")
reports[0].json_report
```

Run one scenario:

```python
reports = run_demo("4")
reports[0].markdown_report
```

Environment smoke test:

```bash
python3 amd_jupyter_smoke_test.py
```

The smoke test prints Python/platform details, checks whether PyTorch ROCm is visible, checks whether a vLLM endpoint is reachable, then runs all deterministic demos.

## Configure vLLM With `.env`

Copy the example file:

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
VLLM_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=<served-model-name>
VLLM_API_KEY=EMPTY
VLLM_TIMEOUT_SECONDS=20
INSURANCE_USE_LLM=1
```

Then run:

```bash
python3 app.py --demo all --use-llm
```

Or from a notebook:

```python
from notebook_demo import run_demo

reports = run_demo("all", use_llm=True)
reports[0].json_report.get("llm_explanation")
```

The app expects vLLM to expose an OpenAI-compatible endpoint at:

```text
{VLLM_BASE_URL}/chat/completions
```

If vLLM is not reachable, the app still completes the deterministic workflow and simply omits the LLM explanation.

## Validate Before Push

Run these commands before committing:

```bash
python3 -m py_compile config.py app.py notebook_demo.py amd_jupyter_smoke_test.py llm/*.py agents/*.py orchestrator/*.py schemas/messages.py document_processing/*.py rules/*.py mcp_server/*.py db/database.py tests/test_demo_workflows.py
python3 app.py --demo all
python3 -m unittest discover -s tests
python3 amd_jupyter_smoke_test.py
```

Expected result:

- All five demos complete
- Unit tests pass
- Smoke test generates five reports
- No `.env`, `outputs/`, `__pycache__/`, or notebook checkpoint files are included in git

## Git Hygiene

The repository is configured to ignore generated and local-only files:

- `.env`
- `outputs/`
- `__pycache__/`
- `*.pyc`
- `.ipynb_checkpoints/`
- `.venv/`

Commit source files, demo data, tests, `.env.example`, and this README. Do not commit real credentials, generated reports, SQLite output, or local notebook checkpoints.
