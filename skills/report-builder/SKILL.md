---
name: report-builder
description: Use when rendering Legal AI Toolkit risk reports, listing redlines, evidence spreadsheets, supplier emails, or structured results
---

# Report Builder

Use this skill to render the MVP artifacts from one validated
`StructuredResult`.

## Inputs

- `StructuredResult` containing product profile, risk items, listing findings,
  evidence gaps, prompt metadata, guardrail metadata, LLM mode, uncertainty
  notes, expert-review flags, and disclaimer.
- Output `reports/` directory.
- Optional DeepSeek/OpenAI-compatible LLM client for summary and supplier-email
  drafting from already validated data.

## Behavior

- Write `risk-report.md`, `listing-redline.md`, `evidence-gap.xlsx`,
  `supplier-email.md`, and `structured-result.json`.
- Include the required disclaimer in every user-facing artifact.
- Include LLM/fallback mode, prompt versions, guardrail versions, uncertainty
  notes, and expert-review flags.
- Supplier email requests only materials with `missing`, `incomplete`,
  `unreadable`, or `uncertain` status.
- Do not rerun analysis or claim final legal compliance.

## Outputs

- A mapping of artifact labels to generated paths.
- Report-drafting prompt metadata and uncertainty notes when the LLM path is
  used.
