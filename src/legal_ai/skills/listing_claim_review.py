from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from pydantic import BaseModel, Field

from legal_ai.config import AppConfig
from legal_ai.llm.client import (
    LLMClient,
    LLMInvalidJSONError,
    LLMProviderError,
    LLMSchemaValidationError,
    LLMTimeoutError,
    MissingProviderConfig,
    provider_configured,
)
from legal_ai.llm.prompts import load_prompt_contract
from legal_ai.llm.schemas import ListingClaimReviewResponse
from legal_ai.models import ClaimFinding, LLMMode, ProductProfile, PromptContractMeta


class ListingLLMClient(Protocol):
    def complete_json(
        self,
        prompt_contract: Any,
        user_content: str,
        response_model: type[ListingClaimReviewResponse],
    ) -> ListingClaimReviewResponse:
        ...


class ListingReviewResult(BaseModel):
    findings: list[ClaimFinding] = Field(default_factory=list)
    llm_mode: LLMMode
    prompt_contracts: list[PromptContractMeta] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class PhrasePattern:
    phrase: str
    claim_type: str
    risk_level: str
    reason: str
    suggested_rewrite: str
    evidence_required: bool = True


PHRASE_PATTERNS = [
    PhrasePattern(
        "100% safe for all ages",
        "absolute_safety",
        "high",
        "Absolute safety wording can overstate product safety and age suitability.",
        "Designed with safety considerations; verify suitability for the intended age range.",
    ),
    PhrasePattern(
        "100% safe",
        "absolute_safety",
        "high",
        "Absolute safety claims require strong substantiation and may be misleading.",
        "Designed with safety considerations when used as directed.",
    ),
    PhrasePattern(
        "safe for all ages",
        "absolute_safety",
        "high",
        "All-ages safety claims can be misleading without age-specific evidence.",
        "Suitable for the age range supported by product testing and labeling.",
    ),
    PhrasePattern(
        "FDA approved",
        "regulatory_endorsement",
        "high",
        "Regulatory approval claims require exact authorization and supporting evidence.",
        "Remove approval wording unless verified documentation supports it.",
    ),
    PhrasePattern(
        "CPSC approved",
        "regulatory_endorsement",
        "high",
        "CPSC approval wording is high risk and should not be used without verified basis.",
        "Describe applicable testing or standards only when documentation supports them.",
    ),
    PhrasePattern(
        "CE certified",
        "regulatory_endorsement",
        "medium",
        "CE certification wording should match available declarations and product scope.",
        "State documented conformity information only when evidence is available.",
    ),
    PhrasePattern(
        "cure",
        "medical_health",
        "high",
        "Medical cure claims can trigger health-product and advertising substantiation risk.",
        "Use non-medical product benefit wording supported by evidence.",
    ),
    PhrasePattern(
        "treat",
        "medical_health",
        "high",
        "Treatment claims can imply medical efficacy and require substantiation.",
        "Use non-medical product benefit wording supported by evidence.",
    ),
    PhrasePattern(
        "pain relief",
        "medical_health",
        "high",
        "Pain-relief claims can imply medical efficacy and require substantiation.",
        "Remove medical benefit wording unless cleared and substantiated.",
    ),
    PhrasePattern(
        "eco-friendly",
        "environmental_material",
        "medium",
        "Broad environmental claims need specific, substantiated qualifications.",
        "Use a specific environmental attribute supported by evidence.",
    ),
    PhrasePattern(
        "non-toxic",
        "environmental_material",
        "medium",
        "Non-toxic claims require test evidence and clear context.",
        "Describe tested materials or standards only when evidence is available.",
    ),
    PhrasePattern(
        "biodegradable",
        "environmental_material",
        "medium",
        "Biodegradable claims require specific substantiation and conditions.",
        "Use qualified environmental wording supported by documentation.",
    ),
    PhrasePattern(
        "#1 rated",
        "superlative_or_proof",
        "medium",
        "Ranking claims require current, reliable proof.",
        "Use a documented ranking claim only with cited evidence.",
    ),
    PhrasePattern(
        "clinically proven",
        "superlative_or_proof",
        "high",
        "Clinically proven claims require robust clinical evidence.",
        "Remove clinical proof wording unless validated evidence is available.",
    ),
    PhrasePattern(
        "best",
        "superlative_or_proof",
        "low",
        "Unqualified superlatives can require comparative support.",
        "Use specific product attributes instead of unsupported superlatives.",
        evidence_required=False,
    ),
]


def review_listing_claims(
    listing_path: Path | None = None,
    *,
    listing_text: str | None = None,
    product_profile: ProductProfile | None = None,
    config: AppConfig | None = None,
    llm_client: ListingLLMClient | None = None,
    env: Mapping[str, str] | None = None,
) -> ListingReviewResult:
    if listing_text is None:
        if listing_path is None:
            raise ValueError("Either listing_path or listing_text is required")
        listing_text = listing_path.read_text(encoding="utf-8")

    app_config = config or AppConfig()
    prompt_meta: list[PromptContractMeta] = []
    llm_findings: list[ClaimFinding] = []
    uncertainty_notes: list[str] = []
    llm_mode: LLMMode = "disabled" if app_config.llm.enabled == "off" else "fallback"

    response = _call_listing_llm(listing_text, product_profile, app_config, llm_client, env)
    if response is not None:
        contract = load_prompt_contract("listing-claim-review", app_config.llm.prompt_version)
        prompt_meta.append(
            PromptContractMeta(
                contract_id=contract.contract_id,
                version=contract.version,
                target_schema=contract.target_schema,
            )
        )
        llm_findings = response.findings
        uncertainty_notes = response.uncertainty_notes
        llm_mode = "enabled"

    fallback_findings = deterministic_phrase_findings(listing_text)
    return ListingReviewResult(
        findings=_deduplicate_findings([*llm_findings, *fallback_findings]),
        llm_mode=llm_mode,
        prompt_contracts=prompt_meta,
        uncertainty_notes=uncertainty_notes,
    )


def deterministic_phrase_findings(listing_text: str) -> list[ClaimFinding]:
    findings: list[ClaimFinding] = []
    consumed_spans_by_line: dict[int, list[tuple[int, int]]] = {}
    for line_number, line in enumerate(listing_text.splitlines(), start=1):
        for pattern in PHRASE_PATTERNS:
            for match in re.finditer(re.escape(pattern.phrase), line, flags=re.IGNORECASE):
                spans = consumed_spans_by_line.setdefault(line_number, [])
                if any(match.start() >= start and match.end() <= end for start, end in spans):
                    continue
                spans.append((match.start(), match.end()))
                findings.append(
                    ClaimFinding(
                        claim_type=pattern.claim_type,
                        source_quote=line[match.start() : match.end()],
                        line_number=line_number,
                        risk_level=pattern.risk_level,  # type: ignore[arg-type]
                        reason=pattern.reason,
                        suggested_rewrite=pattern.suggested_rewrite,
                        evidence_required=pattern.evidence_required,
                        source_mode="fallback",
                    )
                )
    return findings


def _call_listing_llm(
    listing_text: str,
    product_profile: ProductProfile | None,
    config: AppConfig,
    llm_client: ListingLLMClient | None,
    env: Mapping[str, str] | None,
) -> ListingClaimReviewResponse | None:
    if config.llm.enabled == "off":
        return None
    if llm_client is None and config.llm.enabled == "auto" and not provider_configured(env):
        return None

    contract = load_prompt_contract("listing-claim-review", config.llm.prompt_version)
    client = llm_client
    if client is None:
        try:
            client = LLMClient.from_environment(
                env,
                model=config.llm.model,
                timeout_seconds=config.llm.timeout_seconds,
                max_retries=config.llm.max_retries,
            )
        except MissingProviderConfig:
            if config.llm.enabled == "always":
                raise
            return None

    payload = {
        "listing_text": listing_text,
        "product_profile": product_profile.model_dump(mode="json") if product_profile else None,
    }
    try:
        return client.complete_json(
            contract,
            json.dumps(payload, ensure_ascii=True),
            ListingClaimReviewResponse,
        )
    except (LLMInvalidJSONError, LLMProviderError, LLMSchemaValidationError, LLMTimeoutError):
        if config.llm.enabled == "always":
            raise
        return None


def _deduplicate_findings(findings: list[ClaimFinding]) -> list[ClaimFinding]:
    seen: set[tuple[str, str, int | None]] = set()
    deduped: list[ClaimFinding] = []
    for finding in findings:
        key = (finding.claim_type, finding.source_quote.lower(), finding.line_number)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped
