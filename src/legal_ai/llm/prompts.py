from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptContract:
    contract_id: str
    version: str
    target_schema: str
    body: str
    path: Path


def prompts_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "assets" / "prompts"


def load_prompt_contract(
    contract_id: str,
    version: str = "v1",
    base_dir: Path | None = None,
) -> PromptContract:
    directory = base_dir or prompts_dir()
    path = directory / f"{contract_id}.{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt contract not found: {path}")

    body = path.read_text(encoding="utf-8")
    metadata = _parse_metadata(body)
    expected = {"contract_id": contract_id, "version": version}
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"Prompt {path} has {key}={metadata.get(key)!r}, expected {value!r}")
    if not metadata.get("target_schema"):
        raise ValueError(f"Prompt {path} is missing Target schema metadata")

    return PromptContract(
        contract_id=metadata["contract_id"],
        version=metadata["version"],
        target_schema=metadata["target_schema"],
        body=body,
        path=path,
    )


def load_all_prompt_contracts(
    version: str = "v1",
    base_dir: Path | None = None,
) -> list[PromptContract]:
    contract_ids = [
        "product-intake",
        "listing-claim-review",
        "market-compliance-eu-us",
        "evidence-gap-analysis",
        "report-drafting",
    ]
    return [load_prompt_contract(contract_id, version, base_dir) for contract_id in contract_ids]


def _parse_metadata(body: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    key_map = {
        "contract id": "contract_id",
        "version": "version",
        "target schema": "target_schema",
    }
    for line in body.splitlines():
        if ":" not in line:
            continue
        raw_key, raw_value = line.split(":", 1)
        key = key_map.get(raw_key.strip().lower())
        if key:
            metadata[key] = raw_value.strip()
    return metadata
