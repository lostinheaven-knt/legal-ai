from __future__ import annotations

import shutil
from pathlib import Path


class WorkspaceExistsError(ValueError):
    """Raised when init would overwrite a non-empty workspace."""


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


class WorkspaceManager:
    """Create and resolve legal-ai workspace paths."""

    def __init__(self, template_dir: Path | None = None) -> None:
        self.template_dir = template_dir or project_root() / "assets" / "workspace-template"

    def create(self, target: Path) -> Path:
        workspace = target.expanduser().resolve()
        if workspace.exists() and any(workspace.iterdir()):
            raise WorkspaceExistsError(f"Refusing to overwrite non-empty directory: {workspace}")

        workspace.mkdir(parents=True, exist_ok=True)
        self._copy_template(workspace)
        (workspace / "supplier-docs").mkdir(exist_ok=True)
        (workspace / "reports").mkdir(exist_ok=True)
        legal_dir = workspace / ".legal-ai"
        legal_dir.mkdir(exist_ok=True)
        (legal_dir / "audit-log.jsonl").touch(exist_ok=True)
        return workspace

    def _copy_template(self, workspace: Path) -> None:
        if not self.template_dir.exists():
            raise FileNotFoundError(f"Workspace template not found: {self.template_dir}")

        for source in self.template_dir.rglob("*"):
            relative = source.relative_to(self.template_dir)
            destination = workspace / relative
            if source.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    @staticmethod
    def resolve(workspace: Path) -> dict[str, Path]:
        root = workspace.expanduser().resolve()
        return {
            "root": root,
            "product": root / "product.yaml",
            "listing": root / "listing.md",
            "supplier_docs": root / "supplier-docs",
            "config": root / ".legal-ai" / "config.yaml",
            "audit_log": root / ".legal-ai" / "audit-log.jsonl",
            "reports": root / "reports",
        }
