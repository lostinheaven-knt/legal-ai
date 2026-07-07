from __future__ import annotations

from typing import Any

from legal_ai.models import ProductProfile, RiskItem
from legal_ai.rules.schema import GuardrailRule, RuleCondition, RulePack


def evaluate_guardrails(
    product_profile: ProductProfile,
    packs: list[RulePack],
    *,
    listing_text: str = "",
    extra_facts: dict[str, Any] | None = None,
) -> list[RiskItem]:
    facts = _profile_facts(product_profile, listing_text)
    if extra_facts:
        facts.update(extra_facts)

    findings: list[RiskItem] = []
    for pack in packs:
        for rule in pack.guardrails:
            if _rule_matches(rule, facts):
                findings.append(_risk_item_from_rule(pack, rule))
    return findings


def _profile_facts(product_profile: ProductProfile, listing_text: str) -> dict[str, Any]:
    attributes = product_profile.attributes
    return {
        "product_id": product_profile.product_id,
        "name": product_profile.name,
        "category": product_profile.category,
        "subcategory": product_profile.subcategory,
        "markets": product_profile.markets,
        "platform": product_profile.platform,
        "supplier.name": product_profile.supplier.name if product_profile.supplier else None,
        "supplier.country": product_profile.supplier.country if product_profile.supplier else None,
        "declared_documents": [document.path for document in product_profile.declared_documents],
        "attributes.child_directed": attributes.child_directed,
        "attributes.battery_powered": attributes.battery_powered,
        "attributes.skin_contact": attributes.skin_contact,
        "attributes.food_contact": attributes.food_contact,
        "attributes.small_parts": attributes.small_parts,
        "attributes.material_hints": attributes.material_hints,
        "listing_text": listing_text,
    }


def _rule_matches(rule: GuardrailRule, facts: dict[str, Any]) -> bool:
    return all(_condition_matches(condition, facts) for condition in rule.when.all)


def _condition_matches(condition: RuleCondition, facts: dict[str, Any]) -> bool:
    actual = facts.get(condition.fact)
    if condition.op == "equals":
        return actual == condition.value
    if condition.op == "contains":
        return _contains(actual, condition.value)
    if condition.op == "missing":
        return _is_missing(actual)
    if condition.op == "present":
        return not _is_missing(actual)
    if condition.op == "any_true":
        return _any_true(actual, condition.value, facts)
    raise ValueError(f"Unsupported guardrail operator: {condition.op}")


def _contains(actual: Any, expected: Any) -> bool:
    if actual is None:
        return False
    if isinstance(actual, str):
        return str(expected).lower() in actual.lower()
    if isinstance(actual, list):
        return expected in actual
    return False


def _is_missing(actual: Any) -> bool:
    return actual is None or actual == "" or actual == [] or actual == {}


def _any_true(actual: Any, expected: Any, facts: dict[str, Any]) -> bool:
    if isinstance(expected, list):
        return any(bool(facts.get(str(fact_name))) for fact_name in expected)
    if isinstance(actual, list):
        return any(bool(value) for value in actual)
    return bool(actual)


def _risk_item_from_rule(pack: RulePack, rule: GuardrailRule) -> RiskItem:
    market = pack.market if pack.market in {"EU", "US"} else "general"
    platform = pack.platform if pack.platform == "amazon" else "general"
    return RiskItem(
        id=rule.rule_id,
        source="guardrail",
        market=market,
        platform=platform,
        guardrail_pack=pack.pack_id,
        guardrail_id=rule.rule_id,
        severity=rule.severity,
        issue=rule.issue,
        rationale=rule.rationale,
        suggested_actions=rule.suggested_actions,
        required_documents=rule.required_documents,
        confidence=0.85,
        requires_expert_review=rule.requires_expert_review,
    )
