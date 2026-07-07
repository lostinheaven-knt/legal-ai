from pathlib import Path

import click
import typer
from pydantic import ValidationError

from legal_ai.audit import (
    AuditWriteError,
    build_audit_event,
    safe_append_audit_event,
    workspace_input_files,
)
from legal_ai.config import AppConfig, load_config
from legal_ai.workspace import WorkspaceManager, WorkspaceExistsError


def init_workspace(
    target: Path = typer.Argument(..., help="Workspace directory to create."),
) -> None:
    """Create a demo single-SKU legal-ai workspace."""
    manager = WorkspaceManager()
    try:
        created = manager.create(target)
    except WorkspaceExistsError as exc:
        paths = WorkspaceManager.resolve(target)
        if _audit_location_exists(paths):
            try:
                _append_init_audit(paths, status="handled_error", error=exc)
            except AuditWriteError as audit_exc:
                raise click.ClickException(str(audit_exc)) from audit_exc
        raise typer.BadParameter(str(exc)) from exc

    paths = WorkspaceManager.resolve(created)
    try:
        _append_init_audit(paths, status="success", config=_config_for_audit(paths))
    except AuditWriteError as exc:
        raise click.ClickException(str(exc)) from exc
    typer.echo(f"Created legal-ai workspace at {created}")


def _append_init_audit(
    paths: dict[str, Path],
    *,
    status: str,
    config: AppConfig | None = None,
    error: BaseException | None = None,
) -> None:
    event = build_audit_event(
        command="init",
        workspace_root=paths["root"],
        input_files=workspace_input_files(paths),
        status=status,
        config=config,
        error=error,
        outputs={
            "product": paths["product"].as_posix(),
            "listing": paths["listing"].as_posix(),
            "config": paths["config"].as_posix(),
            "audit_log": paths["audit_log"].as_posix(),
            "reports": paths["reports"].as_posix(),
        },
    )
    safe_append_audit_event(paths["audit_log"], event)


def _config_for_audit(paths: dict[str, Path]) -> AppConfig | None:
    try:
        return load_config(paths["config"])
    except (FileNotFoundError, ValueError, ValidationError):
        return None


def _audit_location_exists(paths: dict[str, Path]) -> bool:
    return paths["audit_log"].exists() or paths["audit_log"].parent.exists()
