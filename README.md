# Legal AI Toolkit

Local-first command-line toolkit for single-SKU ecommerce compliance pre-checks.
It turns a compact product workspace into practical EU/US Amazon risk reports,
listing claim redlines, supplier evidence requests, and structured audit output.

> Legal AI Toolkit is an AI-assisted triage tool. It is not legal advice,
> certification, product clearance, or a substitute for qualified compliance
> review.

## What It Does

- Normalizes product facts from `product.yaml` and listing context.
- Reviews ecommerce claims for unsupported, risky, or unclear wording.
- Triages EU, US, and Amazon compliance concerns with local guardrail packs.
- Inspects supplier evidence inventory and produces gap requests.
- Renders Markdown reports, supplier emails, XLSX evidence tables, and JSON.
- Supports deterministic offline fallback and DeepSeek/OpenAI-compatible LLM mode.

## Repository Layout

```text
.
├── assets/              # Prompt contracts, guardrail packs, workspace template
├── skills/              # Operator-facing workflow skills
├── src/legal_ai/        # CLI, models, LLM adapter, checks, and report builders
├── README.md
└── pyproject.toml
```

Only runtime source, public assets, skills, and project metadata are published.
Local experiments, caches, tests, docs, virtualenvs, and generated workspaces are
ignored by design.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
legal-ai --help
```

For development dependencies:

```bash
pip install -e ".[dev]"
```

## Quick Start

Create a single-SKU workspace:

```bash
legal-ai init demo-product
```

The generated workspace looks like this:

```text
demo-product/
├── product.yaml
├── listing.md
├── supplier-docs/
├── reports/
└── .legal-ai/
    ├── config.yaml
    └── audit-log.jsonl
```

Edit `product.yaml`, `listing.md`, and add any supplier documents. Then run:

```bash
legal-ai check demo-product --market EU,US --platform amazon --strict
```

Generated artifacts:

- `reports/risk-report.md`
- `reports/listing-redline.md`
- `reports/evidence-gap.xlsx`
- `reports/supplier-email.md`
- `reports/structured-result.json`

## LLM Mode

The toolkit can run with deterministic local checks or with a
DeepSeek/OpenAI-compatible provider.

```bash
export DEEPSEEK_API_KEY="..."
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
```

Workspace config:

```yaml
llm:
  enabled: auto        # auto, always, or off
  provider: deepseek-compatible
  model: deepseek-chat
  timeout_seconds: 45
  max_retries: 1
  prompt_version: v1
privacy:
  local_first: true
  allow_supplier_doc_upload: false
```

Useful modes:

```bash
legal-ai check demo-product --llm off
legal-ai check demo-product --llm always
```

`--llm always` fails fast if provider configuration or JSON schema validation
fails. `--llm off` stays fully local and deterministic.

## Focused Commands

```bash
legal-ai listing review demo-product --market EU,US --platform amazon
legal-ai evidence gap demo-product --market EU,US --platform amazon
legal-ai report build demo-product
```

## Privacy Model

- Product metadata, bounded listing text, prompt contracts, and evidence
  inventory can be sent to the configured LLM provider when LLM mode is enabled.
- Full supplier-document upload is disabled by default.
- Audit logs avoid API keys, raw prompts, and full supplier-document content.
- Every workspace command records input hashes, output paths, model mode, prompt
  contracts, and guardrail pack metadata.

## Guardrail Scope

Current guardrail packs focus on:

- EU product safety basics
- US FTC claim substantiation basics
- Amazon sensitive-product documentation prompts

The first release is intentionally narrow: single SKU, EU/US, Amazon, practical
pre-check output, and explicit uncertainty.

## Safety Boundary

Generated reports must not say a product is compliant, approved, certified,
safe, or ready to sell. High-risk, uncertain, child-directed, electronics,
medical/health, enforcement, recall, or unclear mandatory-document scenarios
should be routed to qualified legal or compliance professionals.
