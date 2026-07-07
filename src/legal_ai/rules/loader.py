from __future__ import annotations

from pathlib import Path

import yaml

from legal_ai.rules.schema import RulePack


def rule_packs_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "assets" / "rule-packs"


def load_rule_pack(pack: str | Path, base_dir: Path | None = None) -> RulePack:
    path = _resolve_pack_path(pack, base_dir or rule_packs_dir())
    if not path.exists():
        raise FileNotFoundError(f"Rule pack not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    loaded = RulePack.model_validate(raw)
    expected_pack_id = path.stem
    is_pack_id = isinstance(pack, str) and "/" not in pack and "\\" not in pack
    if is_pack_id and loaded.pack_id != expected_pack_id:
        raise ValueError(
            f"Rule pack {path} has pack_id={loaded.pack_id!r}, "
            f"expected {expected_pack_id!r}"
        )
    return loaded


def load_rule_packs(packs: list[str | Path], base_dir: Path | None = None) -> list[RulePack]:
    return [load_rule_pack(pack, base_dir) for pack in packs]


def _resolve_pack_path(pack: str | Path, base_dir: Path) -> Path:
    path = Path(pack)
    if path.suffix in {".yaml", ".yml"} or path.is_absolute() or path.parent != Path("."):
        return path
    return base_dir / f"{pack}.yaml"
