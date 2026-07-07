from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from legal_ai.models import Market, Platform


LLMEnabled = Literal["auto", "always", "off"]


class ProjectConfig(BaseModel):
    name: str = "demo-product"


class DefaultsConfig(BaseModel):
    markets: list[Market] = Field(default_factory=lambda: ["EU", "US"])
    platform: Platform = "amazon"
    language: str = "bilingual"
    strict: bool = False


class GuardrailsConfig(BaseModel):
    packs: list[str] = Field(
        default_factory=lambda: [
            "eu-gpsr-basic",
            "us-ftc-claims-basic",
            "amazon-policy-basic",
        ]
    )


class LLMConfig(BaseModel):
    enabled: LLMEnabled = "auto"
    provider: str = "deepseek-compatible"
    model: str = "deepseek-chat"
    timeout_seconds: float = 45
    max_retries: int = 1
    prompt_version: str = "v1"

    @field_validator("enabled", mode="before")
    @classmethod
    def normalize_yaml_boolean_mode(cls, value: object) -> object:
        if value is False:
            return "off"
        return value


class PrivacyConfig(BaseModel):
    local_first: bool = True
    redact_supplier_name: bool = False
    allow_supplier_doc_upload: bool = False


class CLIOverrides(BaseModel):
    markets: list[Market] | None = None
    platform: Platform | None = None
    language: str | None = None
    strict: bool | None = None
    llm_enabled: LLMEnabled | None = None
    model: str | None = None
    timeout_seconds: float | None = None
    allow_supplier_doc_upload: bool | None = None


class AppConfig(BaseModel):
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    guardrails: GuardrailsConfig = Field(default_factory=GuardrailsConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)

    def with_overrides(self, overrides: CLIOverrides | None = None) -> "AppConfig":
        if overrides is None:
            return self

        data = self.model_dump()
        if overrides.markets is not None:
            data["defaults"]["markets"] = overrides.markets
        if overrides.platform is not None:
            data["defaults"]["platform"] = overrides.platform
        if overrides.language is not None:
            data["defaults"]["language"] = overrides.language
        if overrides.strict is not None:
            data["defaults"]["strict"] = overrides.strict
        if overrides.llm_enabled is not None:
            data["llm"]["enabled"] = overrides.llm_enabled
        if overrides.model is not None:
            data["llm"]["model"] = overrides.model
        if overrides.timeout_seconds is not None:
            data["llm"]["timeout_seconds"] = overrides.timeout_seconds
        if overrides.allow_supplier_doc_upload is not None:
            data["privacy"]["allow_supplier_doc_upload"] = overrides.allow_supplier_doc_upload
        return AppConfig.model_validate(data)


def load_config(path: Path, overrides: CLIOverrides | None = None) -> AppConfig:
    with path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle) or {}
    return AppConfig.model_validate(raw).with_overrides(overrides)
