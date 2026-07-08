from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

try:
    from typer._click.exceptions import ClickException
except ModuleNotFoundError:
    from click import ClickException

from legal_ai.audit import (
    AuditWriteError,
    build_audit_event,
    safe_append_audit_event,
    workspace_input_files,
)
from legal_ai.commands.check import build_structured_result, load_workspace_config
from legal_ai.commands.errors import LLM_COMMAND_EXCEPTIONS, map_llm_exception
from legal_ai.config import AppConfig
from legal_ai.skills.listing_claim_review import review_listing_claims
from legal_ai.skills.product_intake import intake_product
from legal_ai.skills.report_builder import build_listing_redline
from legal_ai.workspace import WorkspaceManager


def review_listing_workspace(
    workspace: Annotated[Path, typer.Argument(help="Workspace directory.")] = Path("."),
    market: Annotated[
        str | None,
        typer.Option("--market", help="Comma-separated markets, supported: EU,US."),
    ] = None,
    platform: Annotated[
        str | None,
        typer.Option("--platform", help="Marketplace platform, supported: amazon."),
    ] = None,
    llm: Annotated[
        str | None,
        typer.Option("--llm", help="LLM mode override: auto, always, or off."),
    ] = None,
) -> None:
    """Review listing claims and write reports/listing-redline.md."""
    paths = WorkspaceManager.resolve(workspace)
    try:
        result = run_listing_review_pipeline(
            workspace,
            market=market,
            platform=platform,
            llm=llm,
        )
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        try:
            _append_listing_audit(
                paths,
                status="handled_error",
                error=exc,
                config=_config_for_audit(paths, market=market, platform=platform, llm=llm),
            )
        except AuditWriteError as audit_exc:
            raise ClickException(str(audit_exc)) from audit_exc
        raise ClickException(str(exc)) from exc
    except LLM_COMMAND_EXCEPTIONS as exc:
        mapped = map_llm_exception(exc)
        try:
            _append_listing_audit(
                paths,
                status="handled_error",
                error=mapped,
                config=_config_for_audit(paths, market=market, platform=platform, llm=llm),
            )
        except AuditWriteError as audit_exc:
            raise ClickException(str(audit_exc)) from audit_exc
        raise ClickException(str(mapped)) from exc

    try:
        _append_listing_audit(
            paths,
            status="success",
            result=result,
            config=_config_for_audit(paths, market=market, platform=platform, llm=llm),
        )
    except AuditWriteError as exc:
        raise ClickException(str(exc)) from exc
    typer.echo("legal-ai listing review completed")
    typer.echo(f"Claim findings: {len(result.claim_findings)}")
    typer.echo(f"listing_redline: {result.outputs['listing_redline']}")


def run_listing_review_pipeline(
    workspace: Path,
    *,
    market: str | None = None,
    platform: str | None = None,
    llm: str | None = None,
    config: AppConfig | None = None,
):
    paths = WorkspaceManager.resolve(workspace)
    _require_listing_workspace(paths)
    app_config = config or load_workspace_config(
        paths,
        market=market,
        platform=platform,
        llm=llm,
    )

    listing_text = paths["listing"].read_text(encoding="utf-8")
    product_result = intake_product(paths["product"], listing_text=listing_text, config=app_config)
    product_profile = product_result.product_profile.model_copy(
        update={"markets": app_config.defaults.markets, "platform": app_config.defaults.platform}
    )
    listing_result = review_listing_claims(
        listing_text=listing_text,
        product_profile=product_profile,
        config=app_config,
    )
    structured = build_structured_result(
        product_profile=product_profile,
        risk_items=[],
        claim_findings=listing_result.findings,
        evidence_gaps=[],
        prompt_contracts=[*product_result.prompt_contracts, *listing_result.prompt_contracts],
        guardrail_packs=[],
        llm_modes=[product_result.llm_mode, listing_result.llm_mode],
        uncertainty_notes=[*product_result.uncertainty_notes, *listing_result.uncertainty_notes],
    )
    outputs = build_listing_redline(structured, paths["reports"])
    structured_path = paths["reports"] / "structured-result.json"
    outputs["structured_result"] = structured_path.expanduser().resolve().as_posix()
    final = structured.model_copy(update={"outputs": outputs})
    structured_path.write_text(final.model_dump_json(indent=2), encoding="utf-8")
    return final


def _require_listing_workspace(paths: dict[str, Path]) -> None:
    for key in ["product", "listing", "config"]:
        if not paths[key].exists():
            raise FileNotFoundError(f"Required workspace file not found: {paths[key]}")
    paths["reports"].mkdir(parents=True, exist_ok=True)


def _append_listing_audit(
    paths: dict[str, Path],
    *,
    status: str,
    result=None,
    config: AppConfig | None = None,
    error: BaseException | None = None,
) -> None:
    event = build_audit_event(
        command="listing review",
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
    llm: str | None,
) -> AppConfig | None:
    try:
        return load_workspace_config(paths, market=market, platform=platform, llm=llm)
    except (FileNotFoundError, ValueError, ValidationError):
        return None
