---
name: legal-compliance-hub
description: Use when coordinating the Legal AI Toolkit CLI workflow for a single-SKU EU or US Amazon ecommerce compliance pre-check
---

# Legal Compliance Hub

Use this skill as the operator-facing entry point for the Legal AI Toolkit MVP.
It coordinates the local workspace workflow for one ecommerce SKU and routes to
the focused toolkit skills.

## Inputs

- A local workspace containing `product.yaml`, `listing.md`, `supplier-docs/`,
  `.legal-ai/config.yaml`, and `reports/`.
- Optional DeepSeek/OpenAI-compatible provider settings through
  `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and workspace config.
- Target scope limited to `EU`, `US`, and `amazon`.

## Commands

- `legal-ai check WORKSPACE --market EU,US --platform amazon --strict`
  runs product intake, listing review, market/platform triage, evidence-gap
  analysis, report rendering, structured JSON output, and audit logging.
- `legal-ai listing review WORKSPACE`
  runs product intake plus listing claim review and writes
  `reports/listing-redline.md`.
- `legal-ai evidence gap WORKSPACE`
  runs the analysis needed to produce `reports/evidence-gap.xlsx`.
- `legal-ai report build WORKSPACE`
  rebuilds report artifacts from `reports/structured-result.json`.

## Behavior

- Prefer LLM analysis when model use is enabled and a DeepSeek/OpenAI-compatible
  provider is configured.
- Fall back to deterministic local checks when LLM use is disabled, unavailable,
  or invalid in `auto` mode.
- Validate structured model output before using it in reports.
- Keep supplier-document upload disabled unless explicitly configured in a
  future policy path.
- Append audit events with input hashes, output paths, model/prompt metadata,
  guardrail versions, and command status.
- Do not store raw full listing, product, prompt, secret, or supplier-document
  content in the audit log.

## Outputs

- `reports/risk-report.md`
- `reports/listing-redline.md`
- `reports/evidence-gap.xlsx`
- `reports/supplier-email.md`
- `reports/structured-result.json`
- `.legal-ai/audit-log.jsonl`

## Safety Boundary

The toolkit provides an AI-assisted ecommerce compliance pre-check. It must not
represent the product as compliant, approved, certified, safe, or ready to sell.
High-risk, uncertain, child-directed, battery/electronics, medical/health,
recall, enforcement, and unclear mandatory-document scenarios should be routed
to qualified legal or compliance review.
