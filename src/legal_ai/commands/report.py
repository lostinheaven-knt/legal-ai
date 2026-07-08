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
from legal_ai.commands.check import load_workspace_config
from legal_ai.commands.errors import LLM_COMMAND_EXCEPTIONS, map_llm_exception
from legal_ai.config import AppConfig
from legal_ai.models import StructuredResult
from legal_ai.skills.report_builder import build_reports
from legal_ai.workspace import WorkspaceManager


def build_report_workspace(
    workspace: Annotated[Path, typer.Argument(help="Workspace directory.")] = Path("."),
    llm: Annotated[
        str | None,
        typer.Option("--llm", help="LLM mode override: auto, always, or off."),
    ] = None,
) -> None:
    """Rebuild report artifacts from reports/structured-result.json."""
    paths = WorkspaceManager.resolve(workspace)
    try:
        result = run_report_build_pipeline(workspace, llm=llm)
    except (FileNotFoundError, ValueError, ValidationError) as exc:
        try:
            _append_report_audit(
                paths,
                status="handled_error",
                error=exc,
                config=_config_for_audit(paths, llm=llm),
            )
        except AuditWriteError as audit_exc:
            raise ClickException(str(audit_exc)) from audit_exc
        raise ClickException(str(exc)) from exc
    except LLM_COMMAND_EXCEPTIONS as exc:
        mapped = map_llm_exception(exc)
        try:
            _append_report_audit(
                paths,
                status="handled_error",
                error=mapped,
                config=_config_for_audit(paths, llm=llm),
            )
        except AuditWriteError as audit_exc:
            raise ClickException(str(audit_exc)) from audit_exc
        raise ClickException(str(mapped)) from exc

    try:
        _append_report_audit(
            paths,
            status="success",
            result=result,
            config=_config_for_audit(paths, llm=llm),
        )
    except AuditWriteError as exc:
        raise ClickException(str(exc)) from exc
    typer.echo("legal-ai report build completed")
    for label, output_path in result.outputs.items():
        typer.echo(f"{label}: {output_path}")


def run_report_build_pipeline(
    workspace: Path,
    *,
    llm: str | None = None,
    config: AppConfig | None = None,
) -> StructuredResult:
    paths = WorkspaceManager.resolve(workspace)
    _require_report_workspace(paths)
    app_config = config or load_workspace_config(paths, llm=llm)
    structured_path = paths["reports"] / "structured-result.json"
    structured = StructuredResult.model_validate_json(structured_path.read_text(encoding="utf-8"))
    report_result = build_reports(structured, paths["reports"], config=app_config)
    final = structured.model_copy(
        update={
            "outputs": report_result.outputs,
            "prompt_contracts": _merge_prompt_meta(
                [*structured.prompt_contracts, *report_result.prompt_contracts]
            ),
            "uncertainty_notes": _dedupe_strings(
                [*structured.uncertainty_notes, *report_result.uncertainty_notes]
            ),
        }
    )
    structured_path.write_text(final.model_dump_json(indent=2), encoding="utf-8")
    return final


def _require_report_workspace(paths: dict[str, Path]) -> None:
    for key in ["config"]:
        if not paths[key].exists():
            raise FileNotFoundError(f"Required workspace file not found: {paths[key]}")
    structured_path = paths["reports"] / "structured-result.json"
    if not structured_path.exists():
        raise FileNotFoundError(f"Required structured result not found: {structured_path}")
    paths["reports"].mkdir(parents=True, exist_ok=True)


def _append_report_audit(
    paths: dict[str, Path],
    *,
    status: str,
    result: StructuredResult | None = None,
    config: AppConfig | None = None,
    error: BaseException | None = None,
) -> None:
    event = build_audit_event(
        command="report build",
        workspace_root=paths["root"],
        input_files=workspace_input_files(paths, include_structured_result=True),
        status=status,
        config=config,
        result=result,
        error=error,
    )
    safe_append_audit_event(paths["audit_log"], event)


def _config_for_audit(paths: dict[str, Path], *, llm: str | None) -> AppConfig | None:
    try:
        return load_workspace_config(paths, llm=llm)
    except (FileNotFoundError, ValueError, ValidationError):
        return None


def _merge_prompt_meta(prompt_contracts):
    seen: set[tuple[str, str]] = set()
    merged = []
    for meta in prompt_contracts:
        key = (meta.contract_id, meta.version)
        if key in seen:
            continue
        seen.add(key)
        merged.append(meta)
    return merged


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
