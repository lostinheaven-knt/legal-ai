from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Protocol

import yaml
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
from legal_ai.llm.schemas import ProductIntakeResponse
from legal_ai.models import LLMMode, MissingField, ProductProfile, PromptContractMeta


class ProductLLMClient(Protocol):
    def complete_json(
        self,
        prompt_contract: Any,
        user_content: str,
        response_model: type[ProductIntakeResponse],
    ) -> ProductIntakeResponse:
        ...


class ProductIntakeResult(BaseModel):
    product_profile: ProductProfile
    llm_mode: LLMMode
    prompt_contracts: list[PromptContractMeta] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


def intake_product(
    product_path: Path,
    *,
    listing_path: Path | None = None,
    listing_text: str | None = None,
    config: AppConfig | None = None,
    llm_client: ProductLLMClient | None = None,
    env: Mapping[str, str] | None = None,
) -> ProductIntakeResult:
    product_data = read_product_yaml(product_path)
    if listing_text is None and listing_path is not None and listing_path.exists():
        listing_text = listing_path.read_text(encoding="utf-8")
    return build_product_profile(
        product_data,
        listing_text=listing_text or "",
        config=config,
        llm_client=llm_client,
        env=env,
    )


def read_product_yaml(product_path: Path) -> dict[str, Any]:
    with product_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, dict):
        raise ValueError("product.yaml must contain a mapping at the document root")
    return raw


def build_product_profile(
    product_data: dict[str, Any],
    *,
    listing_text: str = "",
    config: AppConfig | None = None,
    llm_client: ProductLLMClient | None = None,
    env: Mapping[str, str] | None = None,
) -> ProductIntakeResult:
    app_config = config or AppConfig()
    explicit_fields = set(product_data)
    explicit_attributes = set()
    if isinstance(product_data.get("attributes"), dict):
        explicit_attributes = set(product_data["attributes"])

    profile = ProductProfile.from_mapping(product_data)
    prompt_meta: list[PromptContractMeta] = []
    uncertainty_notes: list[str] = []

    llm_mode: LLMMode = "disabled" if app_config.llm.enabled == "off" else "fallback"
    response = _call_product_intake_llm(
        profile,
        product_data,
        listing_text,
        app_config,
        llm_client,
        env,
    )
    if response is not None:
        contract = load_prompt_contract("product-intake", app_config.llm.prompt_version)
        prompt_meta.append(
            PromptContractMeta(
                contract_id=contract.contract_id,
                version=contract.version,
                target_schema=contract.target_schema,
            )
        )
        profile = _merge_llm_inferences(profile, response, explicit_fields, explicit_attributes)
        profile = _merge_missing_fields(profile, response.missing_fields)
        uncertainty_notes.extend(response.uncertainty_notes)
        llm_mode = "enabled"
    elif app_config.llm.enabled != "off":
        profile = _apply_keyword_fallback(
            profile, listing_text, explicit_fields, explicit_attributes
        )

    if app_config.llm.enabled == "off":
        profile = _apply_keyword_fallback(
            profile, listing_text, explicit_fields, explicit_attributes
        )

    return ProductIntakeResult(
        product_profile=profile,
        llm_mode=llm_mode,
        prompt_contracts=prompt_meta,
        uncertainty_notes=uncertainty_notes,
    )


def _call_product_intake_llm(
    profile: ProductProfile,
    product_data: dict[str, Any],
    listing_text: str,
    config: AppConfig,
    llm_client: ProductLLMClient | None,
    env: Mapping[str, str] | None,
) -> ProductIntakeResponse | None:
    if config.llm.enabled == "off":
        return None
    if llm_client is None and config.llm.enabled == "auto" and not provider_configured(env):
        return None

    contract = load_prompt_contract("product-intake", config.llm.prompt_version)
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
        "product": product_data,
        "normalized_profile": profile.model_dump(mode="json"),
        "listing_text": listing_text,
    }
    try:
        return client.complete_json(
            contract,
            json.dumps(payload, ensure_ascii=True),
            ProductIntakeResponse,
        )
    except (LLMInvalidJSONError, LLMProviderError, LLMSchemaValidationError, LLMTimeoutError):
        if config.llm.enabled == "always":
            raise
        return None


def _merge_llm_inferences(
    profile: ProductProfile,
    response: ProductIntakeResponse,
    explicit_fields: set[str],
    explicit_attributes: set[str],
) -> ProductProfile:
    updates: dict[str, Any] = {}
    attribute_updates: dict[str, Any] = {}
    for inferred in response.inferred_fields:
        field = inferred.field
        value = inferred.value
        if (
            field in {"category", "subcategory"}
            and field not in explicit_fields
            and value is not None
        ):
            updates[field] = value
        elif field.startswith("attributes."):
            attr_name = field.split(".", 1)[1]
            if attr_name not in explicit_attributes and value is not None:
                attribute_updates[attr_name] = value

    if attribute_updates:
        updates["attributes"] = profile.attributes.model_copy(update=attribute_updates)
    return profile.model_copy(update=updates) if updates else profile


def _merge_missing_fields(
    profile: ProductProfile,
    llm_missing_fields: list[MissingField],
) -> ProductProfile:
    by_field = {field.field: field for field in profile.missing_fields}
    for missing_field in llm_missing_fields:
        by_field.setdefault(missing_field.field, missing_field)
    return profile.model_copy(update={"missing_fields": list(by_field.values())})


def _apply_keyword_fallback(
    profile: ProductProfile,
    listing_text: str,
    explicit_fields: set[str],
    explicit_attributes: set[str],
) -> ProductProfile:
    text = " ".join(
        value
        for value in [profile.name, profile.category, profile.subcategory, listing_text]
        if value
    ).lower()
    updates: dict[str, Any] = {}
    attribute_updates: dict[str, Any] = {}

    if "category" not in explicit_fields and any(
        keyword in text for keyword in ["toy", "kids", "child"]
    ):
        updates["category"] = "toy"
    if "subcategory" not in explicit_fields and any(
        keyword in text for keyword in ["led", "battery"]
    ):
        updates["subcategory"] = "electronic_toy" if "toy" in text else "electronics"

    inferred_attributes = {
        "child_directed": any(keyword in text for keyword in ["toy", "kids", "children", "ages"]),
        "battery_powered": any(
            keyword in text for keyword in ["battery", "batteries", "rechargeable"]
        ),
        "skin_contact": any(keyword in text for keyword in ["skin", "wearable", "wear"]),
        "food_contact": any(
            keyword in text for keyword in ["food contact", "kitchen", "cup", "bottle"]
        ),
        "small_parts": "small parts" in text,
    }
    for attr_name, value in inferred_attributes.items():
        if attr_name not in explicit_attributes and value:
            attribute_updates[attr_name] = True

    if "material_hints" not in explicit_attributes:
        material_hints = list(profile.attributes.material_hints)
        for material in ["ABS plastic", "silicone", "stainless steel", "glass"]:
            if material.lower() in text and material not in material_hints:
                material_hints.append(material)
        if material_hints != profile.attributes.material_hints:
            attribute_updates["material_hints"] = material_hints

    if attribute_updates:
        updates["attributes"] = profile.attributes.model_copy(update=attribute_updates)
    return profile.model_copy(update=updates) if updates else profile
