from __future__ import annotations

import json
import os
import platform
import urllib.error
import urllib.request

from config import load_dotenv
from notebook_demo import run_demo


def main() -> None:
    load_dotenv()
    print("Python:", platform.python_version())
    print("Platform:", platform.platform())
    print("ROCm/PyTorch:", _torch_rocm_status())
    print("vLLM endpoint:", _vllm_status())
    reports = run_demo("all", use_llm=os.getenv("INSURANCE_USE_LLM", "").lower() in {"1", "true", "yes", "on"})
    print(f"Smoke test generated {len(reports)} reports.")


def _torch_rocm_status() -> str:
    try:
        import torch
    except ModuleNotFoundError:
        return "torch not installed; app can still run deterministic demos"
    hip = getattr(torch.version, "hip", None)
    if hip:
        return f"available via torch {torch.__version__}, HIP {hip}, cuda_available={torch.cuda.is_available()}"
    return f"torch {torch.__version__} installed, HIP not detected"


def _vllm_status() -> str:
    base_url = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base_url}/models", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return f"not reachable at {base_url}; set INSURANCE_USE_LLM=1 after starting vLLM"
    model_ids = [item.get("id", "unknown") for item in payload.get("data", [])]
    return f"reachable at {base_url}; models={model_ids or ['unknown']}"


if __name__ == "__main__":
    main()
