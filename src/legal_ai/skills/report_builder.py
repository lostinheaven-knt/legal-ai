from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any, Mapping, Protocol
from zipfile import ZIP_DEFLATED, ZipFile

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field

from legal_ai.config import AppConfig
from legal_ai.llm.client import (
    LLMClient,
    LLMInvalidJSONError,
    LLMProviderError,
    LLMSchemaValidationError,
    LLMTimeoutError,
    MissingProviderConfig,
    provider_configured,
)
from legal_ai.llm.prompts import load_prompt_contract
from legal_ai.llm.schemas import ReportDraftingResponse
from legal_ai.models import EvidenceGap, PromptContractMeta, StructuredResult


class ReportLLMClient(Protocol):
    def complete_json(
        self,
        prompt_contract: Any,
        user_content: str,
        response_model: type[ReportDraftingResponse],
    ) -> ReportDraftingResponse:
        ...


class ReportBuilderResult(BaseModel):
    outputs: dict[str, str] = Field(default_factory=dict)
    prompt_contracts: list[PromptContractMeta] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


def build_reports(
    structured_result: StructuredResult,
    reports_dir: Path,
    *,
    config: AppConfig | None = None,
    llm_client: ReportLLMClient | None = None,
    env: Mapping[str, str] | None = None,
) -> ReportBuilderResult:
    app_config = config or AppConfig()
    output_dir = reports_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    draft = _call_report_llm(structured_result, app_config, llm_client, env)
    prompt_meta: list[PromptContractMeta] = []
    uncertainty_notes: list[str] = []
    if draft is not None:
        contract = load_prompt_contract("report-drafting", app_config.llm.prompt_version)
        prompt_meta.append(
            PromptContractMeta(
                contract_id=contract.contract_id,
                version=contract.version,
                target_schema=contract.target_schema,
            )
        )
        uncertainty_notes.extend(draft.uncertainty_notes)

    render_context = {
        "result": structured_result,
        "executive_summary": (
            draft.executive_summary if draft else _fallback_summary(structured_result)
        ),
        "supplier_email_en": draft.supplier_email_en if draft else None,
        "supplier_email_zh": draft.supplier_email_zh if draft else None,
        "request_gaps": _requestable_gaps(structured_result.evidence_gaps),
    }
    outputs = {
        "risk_report": _render_template(
            "risk-report.md.j2",
            output_dir / "risk-report.md",
            render_context,
        ),
        "listing_redline": _render_template(
            "listing-redline.md.j2", output_dir / "listing-redline.md", render_context
        ),
        "supplier_email": _render_template(
            "supplier-email.md.j2", output_dir / "supplier-email.md", render_context
        ),
    }
    outputs["evidence_gap"] = _write_evidence_gap_xlsx(
        structured_result.evidence_gaps,
        output_dir / "evidence-gap.xlsx",
    )

    result_for_json = structured_result.model_copy(
        update={
            "outputs": outputs,
            "prompt_contracts": _merge_prompt_meta(structured_result, prompt_meta),
        }
    )
    structured_path = output_dir / "structured-result.json"
    structured_path.write_text(result_for_json.model_dump_json(indent=2), encoding="utf-8")
    outputs["structured_result"] = structured_path.as_posix()
    result_for_json = result_for_json.model_copy(update={"outputs": outputs})
    structured_path.write_text(result_for_json.model_dump_json(indent=2), encoding="utf-8")

    return ReportBuilderResult(
        outputs=outputs,
        prompt_contracts=prompt_meta,
        uncertainty_notes=uncertainty_notes,
    )


def build_listing_redline(structured_result: StructuredResult, reports_dir: Path) -> dict[str, str]:
    output_dir = reports_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "listing_redline": _render_template(
            "listing-redline.md.j2",
            output_dir / "listing-redline.md",
            {"result": structured_result},
        )
    }


def build_evidence_gap_workbook(
    evidence_gaps: list[EvidenceGap],
    reports_dir: Path,
) -> dict[str, str]:
    output_dir = reports_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "evidence_gap": _write_evidence_gap_xlsx(
            evidence_gaps,
            output_dir / "evidence-gap.xlsx",
        )
    }


def _call_report_llm(
    structured_result: StructuredResult,
    config: AppConfig,
    llm_client: ReportLLMClient | None,
    env: Mapping[str, str] | None,
) -> ReportDraftingResponse | None:
    if config.llm.enabled == "off":
        return None
    if llm_client is None and config.llm.enabled == "auto" and not provider_configured(env):
        return None

    contract = load_prompt_contract("report-drafting", config.llm.prompt_version)
    client = llm_client
    if client is None:
        try:
            client = LLMClient.from_environment(
                env,
                model=config.llm.model,
                timeout_seconds=config.llm.timeout_seconds,
                max_retries=config.llm.max_retries,
            )
        except MissingProviderConfig:
            if config.llm.enabled == "always":
                raise
            return None

    payload = {
        "structured_result": structured_result.model_dump(mode="json"),
        "requestable_evidence_gaps": [
            gap.model_dump(mode="json")
            for gap in _requestable_gaps(structured_result.evidence_gaps)
        ],
    }
    try:
        return client.complete_json(
            contract,
            json.dumps(payload, ensure_ascii=True),
            ReportDraftingResponse,
        )
    except (LLMInvalidJSONError, LLMProviderError, LLMSchemaValidationError, LLMTimeoutError):
        if config.llm.enabled == "always":
            raise
        return None


def _render_template(template_name: str, output_path: Path, context: dict[str, Any]) -> str:
    environment = Environment(
        loader=FileSystemLoader(_templates_dir()),
        autoescape=select_autoescape(disabled_extensions=("j2", "md")),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = environment.get_template(template_name)
    output_path.write_text(template.render(**context), encoding="utf-8")
    return output_path.as_posix()


def _write_evidence_gap_xlsx(evidence_gaps: list[EvidenceGap], output_path: Path) -> str:
    rows = [
        [
            "Material",
            "Status",
            "Priority",
            "Reason",
            "Source Path",
            "Suggested Supplier Follow-up",
        ],
        *[
            [
                gap.material,
                gap.status,
                gap.priority,
                gap.reason,
                gap.source_path or "",
                gap.suggested_supplier_follow_up or "",
            ]
            for gap in evidence_gaps
        ],
    ]
    _write_minimal_xlsx(output_path, rows)
    return output_path.as_posix()


def _fallback_summary(result: StructuredResult) -> str:
    high_count = sum(1 for item in result.risk_items if item.severity == "high")
    gap_count = sum(1 for gap in result.evidence_gaps if gap.status != "present")
    return (
        f"Reviewed {result.product_profile.name or 'the product'} for a single-SKU "
        f"EU/US Amazon pre-check. Found {len(result.risk_items)} risk item(s), "
        f"{high_count} high-risk item(s), and {gap_count} evidence request(s)."
    )


def _requestable_gaps(evidence_gaps: list[EvidenceGap]) -> list[EvidenceGap]:
    return [
        gap
        for gap in evidence_gaps
        if gap.status in {"missing", "incomplete", "unreadable", "uncertain"}
    ]


def _merge_prompt_meta(
    structured_result: StructuredResult,
    report_prompt_meta: list[PromptContractMeta],
) -> list[PromptContractMeta]:
    seen: set[tuple[str, str]] = set()
    merged: list[PromptContractMeta] = []
    for meta in [*structured_result.prompt_contracts, *report_prompt_meta]:
        key = (meta.contract_id, meta.version)
        if key in seen:
            continue
        seen.add(key)
        merged.append(meta)
    return merged


def _templates_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "templates"


def _write_minimal_xlsx(output_path: Path, rows: list[list[str]]) -> None:
    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            ref = f"{_column_name(column_index)}{row_index}"
            cells.append(
                f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
            )
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    worksheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        "</worksheet>"
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Evidence Gaps" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )

    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)


def _column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name
