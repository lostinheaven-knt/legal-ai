from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from legal_ai.config import AppConfig
from legal_ai.hashutil import sha256_file
from legal_ai.models import StructuredResult


AUDIT_EVENT_VERSION = "audit.v1"
GUARDRAIL_ENGINE_VERSION = "guardrails.cycle4.v1"


class AuditWriteError(RuntimeError):
    """Raised when a workspace audit event cannot be persisted."""


def append_audit_event(audit_log: Path, event: dict[str, Any]) -> None:
    """Append one compact JSON event to the workspace audit log."""
    audit_log.parent.mkdir(parents=True, exist_ok=True)
    with audit_log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True, sort_keys=True) + "\n")


def build_audit_event(
    *,
    command: str,
    workspace_root: Path,
    input_files: list[Path],
    status: str,
    config: AppConfig | None = None,
    result: StructuredResult | None = None,
    outputs: dict[str, str] | None = None,
    error: BaseException | None = None,
) -> dict[str, Any]:
    prompt_contracts = result.prompt_contracts if result else []
    guardrail_packs = result.guardrail_packs if result else []
    return {
        "event_version": AUDIT_EVENT_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "workspace": workspace_root.as_posix(),
        "status": status,
        "error": _error_payload(error),
        "inputs": [_file_payload(path, workspace_root) for path in _dedupe_paths(input_files)],
        "outputs": _output_payloads(outputs or (result.outputs if result else {}), workspace_root),
        "llm": {
            "provider": config.llm.provider if config else None,
            "model": config.llm.model if config else None,
            "configured_mode": config.llm.enabled if config else None,
            "runtime_mode": result.llm_mode if result else None,
            "prompt_version": config.llm.prompt_version if config else None,
        },
        "prompt_contracts": [
            {
                "contract_id": meta.contract_id,
                "version": meta.version,
                "target_schema": meta.target_schema,
            }
            for meta in prompt_contracts
        ],
        "guardrails": {
            "engine_version": GUARDRAIL_ENGINE_VERSION,
            "packs": [
                {
                    "pack_id": meta.pack_id,
                    "version": meta.version,
                    "market": meta.market,
                    "platform": meta.platform,
                }
                for meta in guardrail_packs
            ],
        },
    }


def workspace_input_files(
    paths: dict[str, Path],
    *,
    include_structured_result: bool = False,
) -> list[Path]:
    inputs = [paths["product"], paths["listing"], paths["config"]]
    supplier_docs = paths["supplier_docs"]
    if supplier_docs.exists():
        inputs.extend(sorted(path for path in supplier_docs.rglob("*") if path.is_file()))
    if include_structured_result:
        inputs.append(paths["reports"] / "structured-result.json")
    return inputs


def safe_append_audit_event(audit_log: Path, event: dict[str, Any]) -> None:
    try:
        append_audit_event(audit_log, event)
    except OSError as exc:
        raise AuditWriteError(f"Unable to append audit event to {audit_log}: {exc}") from exc


def _file_payload(path: Path, workspace_root: Path) -> dict[str, Any]:
    exists = path.exists() and path.is_file()
    return {
        "path": _display_path(path, workspace_root),
        "exists": exists,
        "sha256": sha256_file(path) if exists else None,
    }


def _output_payloads(outputs: dict[str, str], workspace_root: Path) -> list[dict[str, str]]:
    payloads = []
    for label, raw_path in sorted(outputs.items()):
        path = Path(raw_path)
        payloads.append({"label": label, "path": _display_path(path, workspace_root)})
    return payloads


def _display_path(path: Path, workspace_root: Path) -> str:
    try:
        return path.resolve().relative_to(workspace_root.resolve()).as_posix()
    except ValueError:
        return path.expanduser().resolve().as_posix()


def _error_payload(error: BaseException | None) -> dict[str, str] | None:
    if error is None:
        return None
    return {"type": type(error).__name__, "message": str(error)}


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in paths:
        key = path.expanduser().resolve()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped
