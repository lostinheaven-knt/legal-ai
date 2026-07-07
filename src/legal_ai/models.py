from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


Market = Literal["EU", "US"]
RiskMarket = Literal["EU", "US", "general"]
Platform = Literal["amazon"]
RiskPlatform = Literal["amazon", "general"]
Severity = Literal["high", "medium", "low", "uncertain"]
EvidenceStatus = Literal["present", "missing", "incomplete", "unreadable", "uncertain"]
EvidencePriority = Literal["P0", "P1", "P2"]
LLMMode = Literal["enabled", "fallback", "disabled"]

DISCLAIMER = (
    "This output is an AI-assisted ecommerce compliance pre-check. It does not constitute "
    "formal legal advice. High-risk items should be reviewed by a qualified legal or "
    "compliance professional in the relevant jurisdiction."
)


class MissingField(BaseModel):
    field: str
    reason: str
    question: str | None = None


class SensitiveAttributes(BaseModel):
    child_directed: bool = False
    age_range: str | None = None
    battery_powered: bool = False
    skin_contact: bool = False
    food_contact: bool = False
    small_parts: bool = False
    material_hints: list[str] = Field(default_factory=list)


class SupplierInfo(BaseModel):
    name: str | None = None
    country: str | None = None


class DocumentReference(BaseModel):
    kind: str
    path: str


class EvidenceRef(BaseModel):
    source_path: str
    quote: str | None = None
    line_number: int | None = None
    hash_sha256: str | None = None


class PromptContractMeta(BaseModel):
    contract_id: str
    version: str
    target_schema: str


class RulePackMeta(BaseModel):
    pack_id: str
    version: str
    market: str | None = None
    platform: str | None = None


class ProductProfile(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    product_id: str | None = None
    name: str | None = None
    category: str | None = None
    subcategory: str | None = None
    markets: list[Market] = Field(
        default_factory=list,
        validation_alias=AliasChoices("markets", "target_markets"),
    )
    platform: Platform | None = Field(
        default=None,
        validation_alias=AliasChoices("platform", "platforms"),
    )
    attributes: SensitiveAttributes = Field(default_factory=SensitiveAttributes)
    supplier: SupplierInfo | None = None
    declared_documents: list[DocumentReference] = Field(default_factory=list)
    missing_fields: list[MissingField] = Field(default_factory=list)

    @field_validator("platform", mode="before")
    @classmethod
    def normalize_platform(cls, value: Any) -> Any:
        if isinstance(value, list):
            return value[0] if value else None
        return value

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ProductProfile":
        document_refs: list[DocumentReference] = []
        for kind, paths in (data.get("documents") or {}).items():
            if isinstance(paths, list):
                document_refs.extend(DocumentReference(kind=kind, path=str(path)) for path in paths)

        profile = cls.model_validate({**data, "declared_documents": document_refs})
        missing: list[MissingField] = []
        required = {
            "product_id": profile.product_id,
            "name": profile.name,
            "category": profile.category,
            "target_markets": profile.markets,
            "platforms": profile.platform,
        }
        for field_name, value in required.items():
            if value is None or value == []:
                missing.append(
                    MissingField(
                        field=field_name,
                        reason="Required for a complete single-SKU pre-check profile.",
                        question=f"Please provide {field_name}.",
                    )
                )
        return profile.model_copy(update={"missing_fields": missing})


class ClaimFinding(BaseModel):
    claim_type: str
    source_quote: str
    line_number: int | None = None
    risk_level: Severity
    reason: str
    suggested_rewrite: str | None = None
    evidence_required: bool = False
    source_mode: Literal["llm", "guardrail", "fallback"]


class EvidenceGap(BaseModel):
    material: str
    status: EvidenceStatus
    priority: EvidencePriority
    reason: str
    source_path: str | None = None
    suggested_supplier_follow_up: str | None = None


class RiskItem(BaseModel):
    id: str
    source: Literal["llm", "guardrail", "fallback", "evidence"]
    market: RiskMarket = "general"
    platform: RiskPlatform = "general"
    prompt_contract: str | None = None
    model: str | None = None
    guardrail_pack: str | None = None
    guardrail_id: str | None = None
    severity: Severity
    issue: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    rationale: str
    suggested_actions: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    requires_expert_review: bool = False


class StructuredResult(BaseModel):
    run_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    product_profile: ProductProfile
    risk_items: list[RiskItem] = Field(default_factory=list)
    claim_findings: list[ClaimFinding] = Field(default_factory=list)
    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)
    outputs: dict[str, str] = Field(default_factory=dict)
    prompt_contracts: list[PromptContractMeta] = Field(default_factory=list)
    guardrail_packs: list[RulePackMeta] = Field(default_factory=list)
    llm_mode: LLMMode
    disclaimer: str = DISCLAIMER
    uncertainty_notes: list[str] = Field(default_factory=list)
    expert_review_flags: list[str] = Field(default_factory=list)
