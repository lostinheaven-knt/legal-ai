from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import click
import typer
from pydantic import ValidationError

from legal_ai.audit import (
    AuditWriteError,
    build_audit_event,
    safe_append_audit_event,
    workspace_input_files,
)
from legal_ai.config import AppConfig, CLIOverrides, load_config
from legal_ai.models import LLMMode, StructuredResult
from legal_ai.skills.evidence_gap import analyze_evidence_gaps
from legal_ai.skills.listing_claim_review import review_listing_claims
from legal_ai.skills.market_compliance import analyze_market_compliance
from legal_ai.skills.product_intake import intake_product
from legal_ai.skills.report_builder import build_reports
from legal_ai.workspace import WorkspaceManager


def check_workspace(
    workspace: Annotated[Path, typer.Argument(help="Workspace directory.")] = Path("."),
    market: Annotated[
        str | None,
        typer.Option("--market", help="Comma-separated markets, supported: EU,US."),
    ] = None,
    platform: Annotated[
        str | None,
        typer.Option("--platform", help="Marketplace platform, supported: amazon."),
    ] = None,
    strict: Annotated[
        bool | None,
        typer.Option("--strict/--no-strict", help="Enable strict pre-check behavior."),
    ] = None,
    llm: Annotated[
        str | None,
        typer.Option("--llm", help="LLM mode override: auto, always, or off."),
    ] = None,
) -> None:
    """Run product intake, listing review, market checks, evidence gaps, and reports."""
    paths = WorkspaceManager.resolve(workspace)
    try:
        result = run_check_pipeline(
            workspace,
            market=market,
            platform=platform,
            strict=strict,
            llm=llm,
        )
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        try:
            _append_command_audit(
                "check",
                paths,
                status="handled_error",
                error=exc,
                config=_config_for_audit(
                    paths,
                    market=market,
                    platform=platform,
                    strict=strict,
                    llm=llm,
                ),
            )
        except AuditWriteError as audit_exc:
            raise click.ClickException(str(audit_exc)) from audit_exc
        raise click.ClickException(str(exc)) from exc

    try:
        _append_command_audit(
            "check",
            paths,
            status="success",
            result=result,
            config=_config_for_audit(
                paths,
                market=market,
                platform=platform,
                strict=strict,
                llm=llm,
            ),
        )
    except AuditWriteError as exc:
        raise click.ClickException(str(exc)) from exc
    typer.echo("legal-ai check completed")
    typer.echo(f"Risk items: {len(result.risk_items)}")
    typer.echo(f"Evidence gaps: {len(result.evidence_gaps)}")
    for label, output_path in result.outputs.items():
        typer.echo(f"{label}: {output_path}")


def run_check_pipeline(
    workspace: Path,
    *,
    market: str | None = None,
    platform: str | None = None,
    strict: bool | None = None,
    llm: str | None = None,
    config: AppConfig | None = None,
) -> StructuredResult:
    paths = WorkspaceManager.resolve(workspace)
    _require_workspace_files(paths)
    app_config = config or load_workspace_config(
        paths,
        market=market,
        platform=platform,
        strict=strict,
        llm=llm,
    )

    listing_text = paths["listing"].read_text(encoding="utf-8") if paths["listing"].exists() else ""
    product_result = intake_product(
        paths["product"],
        listing_text=listing_text,
        config=app_config,
    )
    product_profile = product_result.product_profile.model_copy(
        update={
            "markets": app_config.defaults.markets,
            "platform": app_config.defaults.platform,
        }
    )
    listing_result = review_listing_claims(
        listing_text=listing_text,
        product_profile=product_profile,
        config=app_config,
    )
    market_result = analyze_market_compliance(
        product_profile,
        listing_text=listing_text,
        claim_findings=listing_result.findings,
        config=app_config,
    )
    evidence_result = analyze_evidence_gaps(
        product_profile,
        paths["supplier_docs"],
        risk_items=market_result.risk_items,
        claim_findings=listing_result.findings,
        config=app_config,
    )

    structured = build_structured_result(
        product_profile=product_profile,
        risk_items=market_result.risk_items,
        claim_findings=listing_result.findings,
        evidence_gaps=evidence_result.evidence_gaps,
        prompt_contracts=[
            *product_result.prompt_contracts,
            *listing_result.prompt_contracts,
            *market_result.prompt_contracts,
            *evidence_result.prompt_contracts,
        ],
        guardrail_packs=market_result.guardrail_packs,
        llm_modes=[
            product_result.llm_mode,
            listing_result.llm_mode,
            market_result.llm_mode,
            evidence_result.llm_mode,
        ],
        uncertainty_notes=[
            *product_result.uncertainty_notes,
            *listing_result.uncertainty_notes,
            *market_result.uncertainty_notes,
            *evidence_result.uncertainty_notes,
        ],
    )
    report_result = build_reports(structured, paths["reports"], config=app_config)
    final = structured.model_copy(
        update={
            "outputs": report_result.outputs,
            "prompt_contracts": _merge_prompt_contracts(
                [*structured.prompt_contracts, *report_result.prompt_contracts]
            ),
            "uncertainty_notes": _dedupe_strings(
                [*structured.uncertainty_notes, *report_result.uncertainty_notes]
            ),
        }
    )
    structured_path = Path(report_result.outputs["structured_result"])
    structured_path.write_text(final.model_dump_json(indent=2), encoding="utf-8")
    return final


def load_workspace_config(
    paths: dict[str, Path],
    *,
    market: str | None = None,
    platform: str | None = None,
    strict: bool | None = None,
    llm: str | None = None,
) -> AppConfig:
    return load_config(paths["config"]).with_overrides(
        CLIOverrides(
            markets=_parse_markets(market) if market else None,
            platform=platform,  # type: ignore[arg-type]
            strict=strict,
            llm_enabled=llm,  # type: ignore[arg-type]
        )
    )


def build_structured_result(
    *,
    product_profile,
    risk_items,
    claim_findings,
    evidence_gaps,
    prompt_contracts,
    guardrail_packs,
    llm_modes: list[LLMMode],
    uncertainty_notes: list[str],
    outputs: dict[str, str] | None = None,
) -> StructuredResult:
    return StructuredResult(
        run_id=f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        generated_at=datetime.now(timezone.utc),
        product_profile=product_profile,
        risk_items=risk_items,
        claim_findings=claim_findings,
        evidence_gaps=evidence_gaps,
        outputs=outputs or {},
        prompt_contracts=_merge_prompt_contracts(prompt_contracts),
        guardrail_packs=guardrail_packs,
        llm_mode=_combined_llm_mode(llm_modes),
        uncertainty_notes=_dedupe_strings(uncertainty_notes),
        expert_review_flags=_expert_review_flags(risk_items),
    )


def _require_workspace_files(paths: dict[str, Path]) -> None:
    for key in ["product", "config"]:
        if not paths[key].exists():
            raise FileNotFoundError(f"Required workspace file not found: {paths[key]}")
    paths["reports"].mkdir(parents=True, exist_ok=True)
    paths["supplier_docs"].mkdir(parents=True, exist_ok=True)


def _parse_markets(raw: str) -> list[str]:
    markets = [part.strip().upper() for part in raw.split(",") if part.strip()]
    if not markets:
        raise ValueError("--market must include at least one market")
    return markets


def _combined_llm_mode(modes: list[LLMMode]) -> LLMMode:
    if "enabled" in modes:
        return "enabled"
    if "fallback" in modes:
        return "fallback"
    return "disabled"


def _merge_prompt_contracts(prompt_contracts):
    seen: set[tuple[str, str]] = set()
    merged = []
    for meta in prompt_contracts:
        key = (meta.contract_id, meta.version)
        if key in seen:
            continue
        seen.add(key)
        merged.append(meta)
    return merged


def _expert_review_flags(risk_items) -> list[str]:
    return _dedupe_strings(
        [
            f"{item.severity}: {item.issue}"
            for item in risk_items
            if item.requires_expert_review or item.severity in {"high", "uncertain"}
        ]
    )


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _append_command_audit(
    command: str,
    paths: dict[str, Path],
    *,
    status: str,
    result: StructuredResult | None = None,
    config: AppConfig | None = None,
    error: BaseException | None = None,
) -> None:
    event = build_audit_event(
        command=command,
        workspace_root=paths["root"],
        input_files=workspace_input_files(paths),
        status=status,
        config=config,
        result=result,
        error=error,
    )
    safe_append_audit_event(paths["audit_log"], event)


def _config_for_audit(
    paths: dict[str, Path],
    *,
    market: str | None,
    platform: str | None,
    strict: bool | None,
    llm: str | None,
) -> AppConfig | None:
    try:
        return load_workspace_config(
            paths,
            market=market,
            platform=platform,
            strict=strict,
            llm=llm,
        )
    except (FileNotFoundError, ValueError, ValidationError):
        return None
