from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable


VisionExtractor = Callable[[Path], dict[str, Any] | None]


def parse_document(
    path_text: str,
    vision_extractor: VisionExtractor | None = None,
    *,
    prefer_vision: bool = False,
) -> dict[str, Any]:
    path = Path(path_text).expanduser()
    result: dict[str, Any] = {
        "file_name": path.name,
        "file_path": str(path),
        "extracted_text": "",
        "extraction_method": "unread",
        "ocr_used": False,
        "document_type": "unknown",
        "confidence": 0.0,
        "exists": path.exists(),
        "debug": {
            "file_size_bytes": path.stat().st_size if path.exists() else 0,
            "suffix": path.suffix.lower(),
            "text_length": 0,
            "text_preview": "",
            "warnings": [],
        },
    }
    if not path.exists():
        result["extraction_method"] = "missing_file"
        return result

    suffix = path.suffix.lower()
    if suffix == ".txt":
        result["extracted_text"] = path.read_text(encoding="utf-8", errors="ignore")
        result["extraction_method"] = "text"
        result["confidence"] = 0.95
    elif suffix == ".pdf":
        if prefer_vision and _apply_vision_extraction(result, path, vision_extractor, preferred=True):
            _finalize_debug(result)
            return result
        text = _extract_pdf_text(path)
        result["extracted_text"] = text
        result["ocr_used"] = not bool(text.strip())
        result["extraction_method"] = "pdf_text" if text.strip() else "pdf_ocr_unavailable"
        result["confidence"] = 0.85 if text.strip() else 0.25
        if _needs_vision_fallback(result):
            _apply_vision_extraction(result, path, vision_extractor)
    elif suffix in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}:
        if prefer_vision and _apply_vision_extraction(result, path, vision_extractor, preferred=True):
            _finalize_debug(result)
            return result
        text, ocr_debug = _ocr_image(path)
        result["debug"]["ocr"] = ocr_debug
        result["extracted_text"] = text
        result["ocr_used"] = True
        result["extraction_method"] = "image_ocr" if text.strip() else "image_ocr_unavailable"
        result["confidence"] = 0.75 if text.strip() else 0.25
        if _needs_vision_fallback(result):
            _apply_vision_extraction(result, path, vision_extractor)
    else:
        result["extracted_text"] = path.read_text(encoding="utf-8", errors="ignore")
        result["extraction_method"] = "generic_text"
        result["confidence"] = 0.65

    _finalize_debug(result)
    return result


def _needs_vision_fallback(result: dict[str, Any]) -> bool:
    text = result.get("extracted_text", "").strip()
    if not text:
        return True
    useful_tokens = ["pan", "aadhaar", "aadhar", "date of birth", "dob", "address", "policy number"]
    return len(text) < 40 or not any(token in text.lower() for token in useful_tokens)


def _apply_vision_extraction(
    result: dict[str, Any],
    path: Path,
    vision_extractor: VisionExtractor | None,
    *,
    preferred: bool = False,
) -> bool:
    attempt_label = "Vision parsing" if preferred else "Vision fallback"
    if vision_extractor is None:
        result["vision_fallback_attempted"] = False
        result["debug"]["vision_fallback_attempted"] = False
        result["debug"]["warnings"].append(f"{attempt_label} unavailable because no multimodal LLM extractor is configured.")
        return False
    result["vision_fallback_attempted"] = True
    result["debug"]["vision_fallback_attempted"] = True
    result["debug"]["vision_preferred"] = preferred
    started = time.perf_counter()
    parsed = vision_extractor(path)
    result["debug"]["vision_latency_ms"] = round((time.perf_counter() - started) * 1000)
    if not parsed or not _has_useful_vision_payload(parsed):
        result["vision_fallback_succeeded"] = False
        result["debug"]["vision_fallback_succeeded"] = False
        result["debug"]["warnings"].append(f"{attempt_label} did not return structured fields.")
        return False
    result["vision_fallback_succeeded"] = True
    result["debug"]["vision_fallback_succeeded"] = True
    result["vision_extracted_fields"] = _normalize_vision_fields(parsed.get("fields") or {})
    if parsed.get("document_type"):
        result["document_type"] = parsed["document_type"]
    result["extracted_text"] = _vision_payload_to_text(parsed)
    result["extraction_method"] = "vision_llm"
    result["confidence"] = 0.88
    return True


def _has_useful_vision_payload(parsed: dict[str, Any]) -> bool:
    fields = parsed.get("fields")
    if isinstance(fields, dict) and any(_has_present_value(value) for value in fields.values()):
        return True
    return parsed.get("document_type") not in {None, "", "unknown"}


def _has_present_value(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, dict):
        return any(_has_present_value(nested_value) for nested_value in value.values())
    if isinstance(value, list):
        return any(_has_present_value(item) for item in value)
    return True


def _normalize_vision_fields(fields: Any) -> dict[str, Any]:
    if not isinstance(fields, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in fields.items():
        normalized[key] = _normalize_vision_value(value)
    return normalized


def _normalize_vision_value(value: Any) -> Any:
    if isinstance(value, dict):
        for key in ("value", "text", "number", "raw", "normalized"):
            nested_value = value.get(key)
            if _has_present_value(nested_value):
                return nested_value
        return next((nested_value for nested_value in value.values() if _has_present_value(nested_value)), None)
    if isinstance(value, list):
        present = [_normalize_vision_value(item) for item in value if _has_present_value(item)]
        return ", ".join(str(item) for item in present if _has_present_value(item))
    return value


def _vision_payload_to_text(parsed: dict[str, Any]) -> str:
    lines = []
    document_type = parsed.get("document_type")
    if document_type:
        lines.append(f"Document Type: {document_type}")
    fields = parsed.get("fields") or {}
    labels = {
        "customer_name": "Customer Name",
        "date_of_birth": "Date of Birth",
        "pan_number": "PAN Number",
        "aadhaar_number": "Aadhaar Number",
        "address": "Address",
        "phone_number": "Phone Number",
        "policy_number": "Policy Number",
        "patient_name": "Patient Name",
        "insured_name": "Insured Name",
        "claim_amount": "Claim Amount",
        "incident_date": "Incident Date",
    }
    for key, label in labels.items():
        value = fields.get(key)
        if value:
            lines.append(f"{label}: {value}")
    if parsed.get("summary"):
        lines.append(f"Summary: {parsed['summary']}")
    return "\n".join(lines)


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return ""
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _ocr_image(path: Path) -> tuple[str, dict[str, Any]]:
    diagnostics: dict[str, Any] = {
        "tesseract_path": shutil.which("tesseract"),
        "attempts": [],
        "preprocessing_available": False,
        "best_attempt": None,
    }
    if not diagnostics["tesseract_path"]:
        diagnostics["warnings"] = ["Tesseract is not installed or not on PATH."]
        return "", diagnostics

    candidates = [(path, "original")]
    preprocessed_path = _preprocess_image_for_ocr(path, diagnostics)
    if preprocessed_path:
        candidates.append((preprocessed_path, "preprocessed"))

    best_text = ""
    best_attempt: dict[str, Any] | None = None
    try:
        for candidate_path, candidate_label in candidates:
            for psm in ["6", "11", "4", "3"]:
                attempt = _run_tesseract(candidate_path, candidate_label, psm)
                diagnostics["attempts"].append(attempt)
                text = attempt.get("text", "")
                if len(text.strip()) > len(best_text.strip()):
                    best_text = text
                    best_attempt = {
                        "source": candidate_label,
                        "psm": psm,
                        "returncode": attempt.get("returncode"),
                        "text_length": len(text.strip()),
                    }
    finally:
        if preprocessed_path and preprocessed_path != path:
            try:
                os.unlink(preprocessed_path)
            except OSError:
                pass

    diagnostics["best_attempt"] = best_attempt
    return best_text, diagnostics


def _run_tesseract(path: Path, source: str, psm: str) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            ["tesseract", str(path), "stdout", "--psm", psm],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except FileNotFoundError:
        return {
            "source": source,
            "psm": psm,
            "returncode": None,
            "text": "",
            "text_length": 0,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "error": "tesseract_not_found",
        }
    except subprocess.TimeoutExpired:
        return {
            "source": source,
            "psm": psm,
            "returncode": None,
            "text": "",
            "text_length": 0,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "error": "timeout",
        }
    except subprocess.SubprocessError as exc:
        return {
            "source": source,
            "psm": psm,
            "returncode": None,
            "text": "",
            "text_length": 0,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "error": str(exc),
        }
    text = completed.stdout if completed.returncode == 0 else ""
    return {
        "source": source,
        "psm": psm,
        "returncode": completed.returncode,
        "text": text,
        "text_length": len(text.strip()),
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "stderr": completed.stderr.strip()[:300],
    }


def _preprocess_image_for_ocr(path: Path, diagnostics: dict[str, Any]) -> Path | None:
    try:
        from PIL import Image, ImageEnhance, ImageOps
    except ModuleNotFoundError:
        diagnostics["warnings"] = ["Pillow is not installed, so image preprocessing was skipped."]
        return None

    diagnostics["preprocessing_available"] = True
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            image = ImageOps.grayscale(image)
            image = ImageOps.autocontrast(image)
            image = ImageEnhance.Contrast(image).enhance(1.8)
            width, height = image.size
            if max(width, height) < 1600:
                image = image.resize((width * 2, height * 2))
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as handle:
                temp_path = Path(handle.name)
            image.save(temp_path)
            diagnostics["preprocessed_size"] = image.size
            return temp_path
    except Exception as exc:
        diagnostics.setdefault("warnings", []).append(f"Image preprocessing failed: {exc}")
        return None


def _finalize_debug(result: dict[str, Any]) -> None:
    text = result.get("extracted_text", "")
    debug = result.setdefault("debug", {})
    debug["text_length"] = len(text.strip())
    debug["text_preview"] = " ".join(text.split())[:240]
    debug["extraction_method"] = result.get("extraction_method")
    debug["confidence"] = result.get("confidence")
    if result.get("document_type") != "unknown":
        debug["document_type"] = result.get("document_type")
