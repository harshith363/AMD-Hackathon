from __future__ import annotations

import json
import platform
import urllib.error
import urllib.request
import argparse

from notebook_demo import run_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="AMD Jupyter smoke test")
    parser.add_argument("--use-llm", action="store_true", help="Use vLLM for optional report explanations")
    parser.add_argument("--vllm-base-url", default="http://localhost:8000/v1")
    parser.add_argument("--vllm-model", default="amd-hackathon-model")
    parser.add_argument("--vllm-api-key", default="EMPTY")
    parser.add_argument("--vllm-timeout-seconds", type=int, default=20)
    args = parser.parse_args()
    print("Python:", platform.python_version())
    print("Platform:", platform.platform())
    print("ROCm/PyTorch:", _torch_rocm_status())
    print("vLLM endpoint:", _vllm_status(args.vllm_base_url))
    reports = run_demo(
        "all",
        use_llm=args.use_llm,
        vllm_base_url=args.vllm_base_url,
        vllm_model=args.vllm_model,
        vllm_api_key=args.vllm_api_key,
        vllm_timeout_seconds=args.vllm_timeout_seconds,
    )
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


def _vllm_status(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    try:
        with urllib.request.urlopen(f"{base_url}/models", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return f"not reachable at {base_url}; pass --use-llm after starting vLLM"
    model_ids = [item.get("id", "unknown") for item in payload.get("data", [])]
    return f"reachable at {base_url}; models={model_ids or ['unknown']}"


if __name__ == "__main__":
    main()
