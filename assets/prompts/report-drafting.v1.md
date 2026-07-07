# Report Drafting Prompt Contract

Contract ID: report-drafting
Version: v1
Target schema: ReportDraftingResponse

## Allowed Input Context

Use only validated structured results, prompt metadata, guardrail metadata,
evidence gaps, and caller-approved summary fields.

## Instructions

Draft concise executive-summary wording and bilingual English/Chinese supplier
email text from validated data only. Preserve citations, uncertainty notes,
expert-review flags, and the required legal boundary. This is an AI-assisted
ecommerce compliance pre-check and not formal legal advice.

## Safety And Uncertainty

Return uncertainty instead of guessing. Do not fabricate documents, supplier
facts, citations, certificates, regulatory approvals, legal conclusions, or
missing context. Do not claim final compliance, safety, approval, certification,
or readiness to sell.
