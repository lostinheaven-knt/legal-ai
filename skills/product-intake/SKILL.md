---
name: product-intake
description: Use when normalizing a single-SKU product.yaml and listing context into a ProductProfile for ecommerce compliance pre-checks
---

# Product Intake

Use this skill to normalize a single-SKU `product.yaml` file into the toolkit's
`ProductProfile` model before compliance pre-check work.

## Inputs

- `product.yaml` with product identifier, name, category, target markets,
  platform, sensitive attributes, supplier details, and declared document paths.
- Optional `listing.md` text for conservative inference.

## Behavior

- Validates target markets and platform against the MVP scope: `EU`, `US`, and
  `amazon`.
- Preserves explicit values from `product.yaml`; inferred values do not silently
  overwrite user-provided fields.
- Uses the `product-intake.v1` LLM prompt contract when model use is enabled and
  a DeepSeek/OpenAI-compatible provider is configured by the caller.
- Falls back to local keyword inference for obvious signals such as children,
  toy, battery, small-parts, skin-contact, food-contact, and material hints.
- Records missing required fields as questions instead of guessing.

## Output

Returns a typed `ProductIntakeResult` containing:

- `product_profile`
- `llm_mode`
- `prompt_contracts`
- `uncertainty_notes`

This is an AI-assisted ecommerce compliance pre-check input step, not legal
advice or certification.
