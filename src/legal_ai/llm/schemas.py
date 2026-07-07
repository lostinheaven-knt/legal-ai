from __future__ import annotations

from pydantic import BaseModel, Field

from legal_ai.models import ClaimFinding, EvidenceGap, EvidenceRef, MissingField, RiskItem


class InferredProductField(BaseModel):
    field: str
    value: str | int | float | bool | list[str] | None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ProductIntakeResponse(BaseModel):
    inferred_fields: list[InferredProductField] = Field(default_factory=list)
    missing_fields: list[MissingField] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


class ListingClaimReviewResponse(BaseModel):
    findings: list[ClaimFinding] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


class MarketComplianceResponse(BaseModel):
    risk_items: list[RiskItem] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


class EvidenceGapAnalysisResponse(BaseModel):
    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


class ReportDraftingResponse(BaseModel):
    executive_summary: str
    supplier_email_en: str | None = None
    supplier_email_zh: str | None = None
    uncertainty_notes: list[str] = Field(default_factory=list)


SCHEMA_BY_NAME = {
    "ProductIntakeResponse": ProductIntakeResponse,
    "ListingClaimReviewResponse": ListingClaimReviewResponse,
    "MarketComplianceResponse": MarketComplianceResponse,
    "EvidenceGapAnalysisResponse": EvidenceGapAnalysisResponse,
    "ReportDraftingResponse": ReportDraftingResponse,
}
