---
name: listing-claim-review
description: Use when reviewing ecommerce listing text for high-risk compliance claims, unsafe wording, unsupported approvals, or claim rewrites
---

# Listing Claim Review

Use this skill to review one product listing for high-risk ecommerce compliance
claims before publishing or relisting.

## Inputs

- Listing text from `listing.md` or a provided string.
- Optional normalized `ProductProfile` context.

## Behavior

- Uses the `listing-claim-review.v1` LLM prompt contract when model use is
  enabled and a DeepSeek/OpenAI-compatible provider is configured by the caller.
- Always runs deterministic phrase checks so obvious high-risk claims are caught
  in offline fallback mode and in tests.
- Flags absolute safety, regulatory endorsement, medical or health,
  environmental or material, and superlative/proof claims.
- De-duplicates repeated model and fallback findings by claim type, quote, and
  line number.

## Required Fallback Examples

The deterministic review flags at least:

- `100% safe for all ages`
- `FDA approved`
- `CPSC approved`

## Output

Returns a typed `ListingReviewResult` containing:

- `findings`
- `llm_mode`
- `prompt_contracts`
- `uncertainty_notes`

Each finding includes the quoted text, line number when available, risk level,
reason, suggested rewrite, evidence requirement, and source mode.
