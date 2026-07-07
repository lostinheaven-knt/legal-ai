from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from legal_ai.models import Severity


SupportedOperator = Literal["equals", "contains", "missing", "present", "any_true"]


class RuleCondition(BaseModel):
    fact: str
    op: SupportedOperator
    value: Any = None


class RuleWhen(BaseModel):
    all: list[RuleCondition] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_conditions(self) -> "RuleWhen":
        if not self.all:
            raise ValueError("Guardrail rule must include at least one condition")
        return self


class GuardrailRule(BaseModel):
    rule_id: str
    purpose: str
    severity: Severity
    when: RuleWhen
    issue: str
    rationale: str
    suggested_actions: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    requires_expert_review: bool = False


class RulePack(BaseModel):
    pack_id: str
    version: str
    market: str | None = None
    platform: str | None = None
    description: str
    guardrails: list[GuardrailRule] = Field(default_factory=list)

    @field_validator("market")
    @classmethod
    def validate_market(cls, value: str | None) -> str | None:
        if value is not None and value not in {"EU", "US", "general"}:
            raise ValueError("Supported rule-pack markets are EU, US, and general")
        return value

    @field_validator("platform")
    @classmethod
    def validate_platform(cls, value: str | None) -> str | None:
        if value is not None and value not in {"amazon", "general"}:
            raise ValueError("Supported rule-pack platforms are amazon and general")
        return value
