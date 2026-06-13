# Agentic Insurance Operations Assistant

Interactive Streamlit app for insurance operations, built for the AMD Jupyter hackathon environment. The app uses vLLM for conversation and local Python tools/agents for insurance business logic.

## What It Does

- Supports `individual` and `business` users.
- Finds new insurance products from a mock MCP-style catalogue.
- Validates claim document packets.
- Validates individual KYC and business KYB document packets.
- Uses local domain tools for supported workflows, insurance categories, claim types, and required documents.
- Uses deterministic rules for missing documents, field checks, consistency checks, status, and human-review decisions.
- Saves JSON and Markdown reports under `outputs/reports/`.
- Saves audit records in SQLite under `outputs/insurance_assistant.sqlite3`.

The LLM handles conversation and reasoning over tool results. It does not own the business rules or validation status.

## Architecture

```text
Streamlit UI
  -> vLLM chat endpoint
  -> Domain tools
  -> Structured messages
  -> Workflow orchestrator
  -> Specialized agents
  -> Reports + SQLite
```

Key folders:

```text
agents/               Specialized workflow agents
cli/                  Shared conversational intake logic
domain_tools/         Tool functions for workflows, categories, claims, documents
mcp_server/           Mock MCP product catalogue
rules/                Claim, KYC, and KYB validation rules
schemas/              Structured message models
sample_data/          Sample document packets used by tests
tests/                Unit tests
```

## 1. Install Streamlit In AMD Jupyter

For the default ROCm + vLLM Docker image, the hackathon FAQ recommends:

```bash
pip install streamlit --ignore-installed blinker
pip install "starlette<0.49.0" "protobuf<7.0.0" "numpy<2.3"
```

These commands were specifically tested against the default Docker image. Avoid uninstalling unrelated dependencies.

## 2. Serve The vLLM Model

Run this in one terminal:

```bash
vllm serve Qwen/Qwen2.5-32B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype bfloat16 \
  --max-model-len 4096 \
  --gpu-memory-utilization 0.92
```

Optional health check from another terminal:

```bash
curl http://localhost:8000/v1/models
```

## 3. Start The Streamlit App

Run this in another terminal from the project root:

```bash
streamlit run streamlit_app.py \
  --server.port 8501 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false
```

## 4. Open The App

If your notebook URL is:

```text
https://notebooks.amd.com/<pod-name>/lab
```

open:

```text
https://notebooks.amd.com/<pod-name>/proxy/8501/
```

Example:

```text
https://notebooks.amd.com/jupyter-hack-team-5000-260609205410-931e891d/proxy/8501/
```

## 5. Use The App

In the Streamlit sidebar, keep:

```text
Base URL: http://localhost:8000/v1
Model: Qwen/Qwen2.5-32B-Instruct
API key: EMPTY
```

Then chat naturally:

```text
I am an individual
give me options
I want a new policy
health
My name is Harshith
yes
```

For document workflows, either type local file paths in chat or upload files through the document uploader panel. Uploaded files are stored under `outputs/uploads/` and passed into the same document validation agents.

## 6. Tool-Backed Conversation

When the user asks something like `give me options`, the app invokes local domain tools:

```text
get_supported_workflows(customer_type)
get_insurance_categories(customer_type)
get_claim_types(customer_type)
get_required_documents(customer_type, workflow_type, case_type)
```

The tool result is passed to vLLM so the model can phrase a helpful answer. This keeps insurance logic out of prompts and inside Python modules.

## 7. Optional CLI Mode

The Streamlit app is the recommended interface. A terminal chat interface is also available:

```bash
python3 app.py \
  --use-llm \
  --vllm-base-url http://localhost:8000/v1 \
  --vllm-model Qwen/Qwen2.5-32B-Instruct \
  --vllm-api-key EMPTY
```

## 8. Validation Before Push

Run:

```bash
python3 -m py_compile app.py streamlit_app.py cli/*.py domain_tools/*.py llm/*.py agents/*.py orchestrator/*.py schemas/messages.py document_processing/*.py rules/*.py mcp_server/*.py db/database.py tests/*.py
python3 -m unittest discover -s tests
```

Expected:

- Compile succeeds.
- Unit tests pass.

## 9. Git Hygiene

Ignored generated/local files:

- `outputs/`
- `__pycache__/`
- `*.pyc`
- `.ipynb_checkpoints/`
- `.venv/`
- `.env`

Commit source files, sample data, tests, and this README. Do not commit generated reports, SQLite output, uploaded files, credentials, virtual environments, or notebook checkpoints.
