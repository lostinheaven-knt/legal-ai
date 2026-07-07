from __future__ import annotations

import json
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
from legal_ai.llm.schemas import MarketComplianceResponse
from legal_ai.models import (
    ClaimFinding,
    LLMMode,
    ProductProfile,
    PromptContractMeta,
    RiskItem,
    RulePackMeta,
)
from legal_ai.rules.guardrails import evaluate_guardrails
from legal_ai.rules.loader import load_rule_packs
from legal_ai.rules.schema import RulePack


class MarketLLMClient(Protocol):
    def complete_json(
        self,
        prompt_contract: Any,
        user_content: str,
        response_model: type[MarketComplianceResponse],
    ) -> MarketComplianceResponse:
        ...


class MarketComplianceResult(BaseModel):
    risk_items: list[RiskItem] = Field(default_factory=list)
    llm_mode: LLMMode
    prompt_contracts: list[PromptContractMeta] = Field(default_factory=list)
    guardrail_packs: list[RulePackMeta] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


def analyze_market_compliance(
    product_profile: ProductProfile,
    *,
    listing_text: str = "",
    claim_findings: list[ClaimFinding] | None = None,
    evidence_inventory: list[dict[str, Any]] | None = None,
    config: AppConfig | None = None,
    llm_client: MarketLLMClient | None = None,
    env: Mapping[str, str] | None = None,
) -> MarketComplianceResult:
    app_config = config or AppConfig()
    packs = _selected_rule_packs(product_profile, app_config)
    guardrail_items = evaluate_guardrails(
        product_profile,
        packs,
        listing_text=listing_text,
        extra_facts=_extra_facts(product_profile),
    )
    guardrail_meta = [_pack_meta(pack) for pack in packs]

    llm_mode: LLMMode = "disabled" if app_config.llm.enabled == "off" else "fallback"
    prompt_meta: list[PromptContractMeta] = []
    uncertainty_notes: list[str] = []
    llm_items: list[RiskItem] = []

    response = _call_market_llm(
        product_profile,
        listing_text,
        claim_findings or [],
        evidence_inventory or [],
        packs,
        app_config,
        llm_client,
        env,
    )
    if response is not None:
        contract = load_prompt_contract("market-compliance-eu-us", app_config.llm.prompt_version)
        prompt_meta.append(
            PromptContractMeta(
                contract_id=contract.contract_id,
                version=contract.version,
                target_schema=contract.target_schema,
            )
        )
        llm_items = _sanitize_llm_risk_items(response.risk_items, contract.contract_id, app_config)
        uncertainty_notes.extend(response.uncertainty_notes)
        llm_mode = "enabled"

    merged = _deduplicate_risks([*llm_items, *guardrail_items])
    if not merged:
        uncertainty_notes.append(
            "No concrete risks were identified by the MVP checks; this is not a "
            "compliance clearance."
        )

    return MarketComplianceResult(
        risk_items=merged,
        llm_mode=llm_mode,
        prompt_contracts=prompt_meta,
        guardrail_packs=guardrail_meta,
        uncertainty_notes=uncertainty_notes,
    )


def _selected_rule_packs(product_profile: ProductProfile, config: AppConfig) -> list[RulePack]:
    selected_ids: list[str] = []
    configured = set(config.guardrails.packs)
    if "EU" in product_profile.markets and "eu-gpsr-basic" in configured:
        selected_ids.append("eu-gpsr-basic")
    if "US" in product_profile.markets and "us-ftc-claims-basic" in configured:
        selected_ids.append("us-ftc-claims-basic")
    if product_profile.platform == "amazon" and "amazon-policy-basic" in configured:
        selected_ids.append("amazon-policy-basic")
    return load_rule_packs(selected_ids)


def _extra_facts(product_profile: ProductProfile) -> dict[str, Any]:
    attributes = product_profile.attributes
    return {
        "sensitive_attribute_flags": [
            attributes.child_directed,
            attributes.battery_powered,
            attributes.skin_contact,
            attributes.food_contact,
            attributes.small_parts,
        ]
    }


def _call_market_llm(
    product_profile: ProductProfile,
    listing_text: str,
    claim_findings: list[ClaimFinding],
    evidence_inventory: list[dict[str, Any]],
    packs: list[RulePack],
    config: AppConfig,
    llm_client: MarketLLMClient | None,
    env: Mapping[str, str] | None,
) -> MarketComplianceResponse | None:
    if config.llm.enabled == "off":
        return None
    if llm_client is None and config.llm.enabled == "auto" and not provider_configured(env):
        return None

    contract = load_prompt_contract("market-compliance-eu-us", config.llm.prompt_version)
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
        "product_profile": product_profile.model_dump(mode="json"),
        "listing_text": listing_text,
        "claim_findings": [finding.model_dump(mode="json") for finding in claim_findings],
        "evidence_inventory": evidence_inventory,
        "guardrail_context": [
            {
                "pack_id": pack.pack_id,
                "version": pack.version,
                "guardrails": [rule.model_dump(mode="json") for rule in pack.guardrails],
            }
            for pack in packs
        ],
    }
    try:
        return client.complete_json(
            contract,
            json.dumps(payload, ensure_ascii=True),
            MarketComplianceResponse,
        )
    except (LLMInvalidJSONError, LLMProviderError, LLMSchemaValidationError, LLMTimeoutError):
        if config.llm.enabled == "always":
            raise
        return None


def _sanitize_llm_risk_items(
    risk_items: list[RiskItem],
    prompt_contract: str,
    config: AppConfig,
) -> list[RiskItem]:
    sanitized: list[RiskItem] = []
    for index, item in enumerate(risk_items, start=1):
        has_source = bool(item.evidence or item.guardrail_id or item.severity == "uncertain")
        updates: dict[str, Any] = {
            "source": "llm",
            "prompt_contract": item.prompt_contract or prompt_contract,
            "model": item.model or config.llm.model,
            "id": item.id or f"LLM_MARKET_{index:03d}",
        }
        if not has_source:
            updates.update(
                {
                    "severity": "uncertain",
                    "confidence": min(item.confidence, 0.35),
                    "requires_expert_review": True,
                    "rationale": (
                        f"{item.rationale} Model finding lacked source evidence or guardrail "
                        "reference, so it was downgraded to uncertain."
                    ),
                }
            )
        sanitized.append(item.model_copy(update=updates))
    return sanitized


def _deduplicate_risks(risk_items: list[RiskItem]) -> list[RiskItem]:
    seen: set[tuple[str, str | None, str | None]] = set()
    deduped: list[RiskItem] = []
    for item in risk_items:
        key = (item.issue.lower(), item.guardrail_pack, item.guardrail_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _pack_meta(pack: RulePack) -> RulePackMeta:
    return RulePackMeta(
        pack_id=pack.pack_id,
        version=pack.version,
        market=pack.market,
        platform=pack.platform,
    )
