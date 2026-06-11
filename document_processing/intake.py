from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def parse_document(path_text: str) -> dict[str, Any]:
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
        text = _extract_pdf_text(path)
        result["extracted_text"] = text
        result["ocr_used"] = not bool(text.strip())
        result["extraction_method"] = "pdf_text" if text.strip() else "pdf_ocr_unavailable"
        result["confidence"] = 0.85 if text.strip() else 0.25
    elif suffix in {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"}:
        text = _ocr_image(path)
        result["extracted_text"] = text
        result["ocr_used"] = True
        result["extraction_method"] = "image_ocr" if text.strip() else "image_ocr_unavailable"
        result["confidence"] = 0.75 if text.strip() else 0.25
    else:
        result["extracted_text"] = path.read_text(encoding="utf-8", errors="ignore")
        result["extraction_method"] = "generic_text"
        result["confidence"] = 0.65

    return result


def _extract_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return ""
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _ocr_image(path: Path) -> str:
    try:
        completed = subprocess.run(
            ["tesseract", str(path), "stdout"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return ""
    return completed.stdout if completed.returncode == 0 else ""
