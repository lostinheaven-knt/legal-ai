---
name: market-compliance-eu-us
description: Use when triaging EU, US, or Amazon ecommerce product compliance risk from product facts, listing claims, and evidence context
---

# Market Compliance EU/US

Use this skill to run a first-pass ecommerce compliance pre-check for EU, US,
and Amazon contexts from a validated product profile, listing findings, evidence
inventory, and the MVP guardrail packs.

## Inputs

- `ProductProfile` from product intake.
- Listing text and listing claim findings.
- Evidence inventory or evidence-gap output.
- Guardrail packs: `eu-gpsr-basic`, `us-ftc-claims-basic`, and
  `amazon-policy-basic`.
- Optional DeepSeek/OpenAI-compatible LLM client.

## Behavior

- Prefer the `market-compliance-eu-us.v1` LLM prompt when model use is enabled
  and a provider or mock client is available.
- Validate model output against `MarketComplianceResponse`.
- Downgrade model findings that lack workspace evidence, guardrail references,
  or explicit uncertainty.
- Always merge deterministic guardrail findings for obvious phrase checks,
  required evidence prompts, and expert-review triggers.
- Never state that a product is compliant, approved, certified, safe, or ready
  to sell.

## Outputs

- Structured `RiskItem` records.
- Prompt contract metadata when the LLM path is used.
- Guardrail pack metadata for report traceability.
- Uncertainty notes for report rendering.
