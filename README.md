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
python3.12 -m pip install --ignore-installed blinker streamlit
python3.12 -m pip install "starlette<0.49.0" "protobuf<7.0.0" "numpy<2.3"
```

These commands were specifically tested against the default Docker image. Avoid uninstalling unrelated dependencies.

Do not install Streamlit through `pip install -r requirements.txt` in the AMD default image. The base image has a distutils-installed `blinker 1.4`, and a normal Streamlit install can fail while trying to uninstall it. The `--ignore-installed blinker` command above avoids that.

Optional backend packages:

```bash
python3.12 -m pip install -r requirements.txt
```

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

For PAN/Aadhaar image parsing, use a multimodal model. The app defaults to Gemma 4 E4B:

```bash
vllm serve google/gemma-4-E4B-it \
  --host 0.0.0.0 \
  --port 8000 \
  --dtype bfloat16 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.95 \
  --enable-auto-tool-choice \
  --tool-call-parser gemma4 \
  --reasoning-parser gemma4 \
  --trust-remote-code
```

```bash
vllm serve mistralai/Ministral-3-14B-Instruct-2512 \
  --tokenizer_mode mistral \
  --config_format mistral \
  --load_format mistral \
  --tensor-parallel-size 1 \
  --enable-auto-tool-choice \
  --tool-call-parser mistral
```

Google's Gemma 4 docs list text and image input support, including OCR and document/PDF parsing. The smaller E4B instruction-tuned model is a practical default for the hackathon environment; use `google/gemma-4-12B-it`, `google/gemma-4-26B-A4B-it`, or `google/gemma-4-31B-it` only if your GPU memory allows it.

## 3. Start The Streamlit App

Run this in another terminal from the project root:

```bash
streamlit run streamlit_app.py \
  --server.address 0.0.0.0 \
  --server.port 8501 \
  --server.baseUrlPath proxy/8501 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false
```

The `--server.baseUrlPath proxy/8501` flag is important in the AMD notebook proxy. Without it, the HTML page may load but CSS, fonts, and JavaScript can be requested from `/proxy/static/...` instead of `/proxy/8501/static/...`, which produces a blank page.

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

The app opens as a centered GPT-style chat. Chat naturally:

```text
I am an individual
give me options
I want a new policy
health
My name is Harshith
yes
```

When the assistant needs a structured choice, such as customer type, workflow, insurance category, or claim type, the app shows horizontal option cards. Click a card, then press `Enter`. You can also keep typing free-form text in the chat input.

For document workflows, either type local file paths in chat or upload files through the inline document uploader when it appears. Uploaded files are stored under `outputs/uploads/` and passed into the same document validation agents.

The Streamlit app uses these built-in vLLM defaults:

```text
Base URL: http://localhost:8000/v1
Model: Qwen/Qwen2.5-32B-Instruct
API key: EMPTY
```

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
