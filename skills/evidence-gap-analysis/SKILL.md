---
name: evidence-gap-analysis
description: Use when inspecting supplier evidence, certificates, labels, or document gaps for a single-SKU ecommerce compliance workspace
---

# Evidence Gap Analysis

Use this skill to inspect a single-SKU workspace's `supplier-docs/` folder and
identify missing, incomplete, unreadable, or uncertain evidence needed for the
pre-check.

## Inputs

- `ProductProfile` with declared document references from `product.yaml`.
- Supplier document directory.
- Risk items and listing claim findings.
- Optional DeepSeek/OpenAI-compatible LLM client.

## Behavior

- Build a local file inventory from filenames, extensions, sizes, and short
  snippets for readable text files.
- Treat declared document paths as present only when the file exists or was
  explicitly declared.
- Add evidence requests from risk-item required documents and claim findings
  requiring substantiation.
- Prefer the `evidence-gap-analysis.v1` LLM prompt when enabled, but sanitize
  model output so missing files are never marked present.
- Do not upload full supplier document contents unless a future explicit privacy
  setting allows it.

## Outputs

- Structured `EvidenceGap` rows for Markdown, XLSX, JSON, and supplier-email
  rendering.
- Evidence inventory for downstream market checks and debugging.
- Prompt metadata and uncertainty notes when the LLM path is used.
