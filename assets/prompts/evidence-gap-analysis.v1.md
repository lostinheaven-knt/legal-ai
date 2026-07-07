# Evidence Gap Analysis Prompt Contract

Contract ID: evidence-gap-analysis
Version: v1
Target schema: EvidenceGapAnalysisResponse

## Allowed Input Context

Use only declared document references, caller-provided file inventory, readable
metadata snippets, product profile facts, and validated risk findings.

## Instructions

Prioritize missing, incomplete, unreadable, or uncertain evidence and suggest
supplier follow-up. Every gap must cite the declaration, file inventory entry, or
risk item that supports it. This is an AI-assisted ecommerce compliance
pre-check and not formal legal advice. This is not formal legal advice.

## Safety And Uncertainty

Return uncertainty instead of guessing. Never state that a certificate, test
report, label, or supplier document exists unless it appears in the workspace
inventory or is explicitly declared in `product.yaml`. Do not fabricate
documents, citations, file paths, document contents, or supplier claims.
