from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

try:
    from pydantic import BaseModel as _PydanticBaseModel
    from pydantic import Field
except ModuleNotFoundError:
    _PydanticBaseModel = None

    def Field(default_factory=None, default=None):  # type: ignore[no-redef]
        if default_factory is not None:
            return field(default_factory=default_factory)
        return default


if _PydanticBaseModel:

    class MessageModel(_PydanticBaseModel):
        def to_dict(self) -> dict[str, Any]:
            return self.model_dump()

else:

    @dataclass
    class MessageModel:
        def __init_subclass__(cls) -> None:
            dataclass(cls)

        def to_dict(self) -> dict[str, Any]:
            return asdict(self)


class UserIntentMessage(MessageModel):
    session_id: str
    customer_type: Literal["business", "individual"]
    intent: Literal["new_insurance", "claim_validation", "kyc_validation", "kyb_validation"]
    raw_input: str | None = None


class ProductDiscoveryMessage(MessageModel):
    session_id: str
    customer_type: Literal["business", "individual"]
    insurance_category: str
    user_inputs: dict[str, Any] = Field(default_factory=dict)


class ProductRecommendationMessage(MessageModel):
    session_id: str
    customer_type: Literal["business", "individual"]
    insurance_category: str
    user_inputs: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)


class DocumentPacketMessage(MessageModel):
    session_id: str
    customer_type: Literal["business", "individual"]
    workflow_type: Literal["claim_validation", "kyc_validation", "kyb_validation"]
    case_type: str
    file_paths: list[str] = Field(default_factory=list)
    user_inputs: dict[str, Any] = Field(default_factory=dict)
    incident_description: str | None = None


class ParsedDocumentMessage(MessageModel):
    session_id: str
    documents: list[dict[str, Any]] = Field(default_factory=list)


class ClassifiedDocumentMessage(MessageModel):
    session_id: str
    documents: list[dict[str, Any]] = Field(default_factory=list)


class ExtractionResultMessage(MessageModel):
    session_id: str
    extracted_fields: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0


class ReconciliationMessage(MessageModel):
    session_id: str
    inconsistencies: list[dict[str, Any]] = Field(default_factory=list)
    canonical_fields: dict[str, Any] = Field(default_factory=dict)


class ValidationResultMessage(MessageModel):
    session_id: str
    status: Literal[
        "Ready for Submission",
        "Needs Additional Documents",
        "Needs Correction",
        "Human Review Required",
    ]
    human_review_required: bool
    confidence: float = 0.0
    missing_documents: list[str] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    next_action: str = ""


class ReportMessage(MessageModel):
    session_id: str
    report_id: str
    report_type: str
    json_report: dict[str, Any] = Field(default_factory=dict)
    markdown_report: str = ""
