# Product Intake Prompt Contract

Contract ID: product-intake
Version: v1
Target schema: ProductIntakeResponse

## Allowed Input Context

Use only `product.yaml` fields, bounded `listing.md` snippets, declared supplier
document references, and caller-provided file inventory. Do not request or infer
full supplier document contents unless an explicit later configuration permits it.

## Instructions

Extract conservative product facts, sensitive attributes, and missing fields.
Return citations or source references for every inferred value. This is an
AI-assisted ecommerce compliance pre-check and not formal legal advice.

## Safety And Uncertainty

If evidence is missing or unclear, return uncertainty instead of guessing. Do not
claim that the product is safe, compliant, approved, certified, or ready to sell.
Do not fabricate documents, supplier facts, citations, file paths, labels,
certificates, or test reports.
