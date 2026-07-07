from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Protocol

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
from legal_ai.llm.schemas import EvidenceGapAnalysisResponse
from legal_ai.models import (
    ClaimFinding,
    EvidenceGap,
    LLMMode,
    ProductProfile,
    PromptContractMeta,
    RiskItem,
)


READABLE_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml"}


class EvidenceLLMClient(Protocol):
    def complete_json(
        self,
        prompt_contract: Any,
        user_content: str,
        response_model: type[EvidenceGapAnalysisResponse],
    ) -> EvidenceGapAnalysisResponse:
        ...


class EvidenceGapResult(BaseModel):
    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)
    inventory: list[dict[str, Any]] = Field(default_factory=list)
    llm_mode: LLMMode
    prompt_contracts: list[PromptContractMeta] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


def analyze_evidence_gaps(
    product_profile: ProductProfile,
    supplier_docs_dir: Path,
    *,
    risk_items: list[RiskItem] | None = None,
    claim_findings: list[ClaimFinding] | None = None,
    config: AppConfig | None = None,
    llm_client: EvidenceLLMClient | None = None,
    env: Mapping[str, str] | None = None,
) -> EvidenceGapResult:
    app_config = config or AppConfig()
    docs_dir = supplier_docs_dir.expanduser().resolve()
    workspace_root = docs_dir.parent
    inventory = build_evidence_inventory(docs_dir)
    expected = _expected_materials(
        product_profile,
        workspace_root,
        inventory,
        risk_items or [],
        claim_findings or [],
    )

    llm_mode: LLMMode = "disabled" if app_config.llm.enabled == "off" else "fallback"
    prompt_meta: list[PromptContractMeta] = []
    uncertainty_notes: list[str] = []
    llm_gaps: list[EvidenceGap] = []

    response = _call_evidence_llm(
        product_profile,
        inventory,
        risk_items or [],
        expected,
        app_config,
        llm_client,
        env,
    )
    if response is not None:
        contract = load_prompt_contract("evidence-gap-analysis", app_config.llm.prompt_version)
        prompt_meta.append(
            PromptContractMeta(
                contract_id=contract.contract_id,
                version=contract.version,
                target_schema=contract.target_schema,
            )
        )
        llm_gaps = _sanitize_llm_gaps(response.evidence_gaps, workspace_root, product_profile)
        uncertainty_notes.extend(response.uncertainty_notes)
        llm_mode = "enabled"

    return EvidenceGapResult(
        evidence_gaps=_deduplicate_gaps([*expected, *llm_gaps]),
        inventory=inventory,
        llm_mode=llm_mode,
        prompt_contracts=prompt_meta,
        uncertainty_notes=uncertainty_notes,
    )


def build_evidence_inventory(supplier_docs_dir: Path) -> list[dict[str, Any]]:
    docs_dir = supplier_docs_dir.expanduser().resolve()
    if not docs_dir.exists():
        return []

    inventory: list[dict[str, Any]] = []
    for path in sorted(item for item in docs_dir.rglob("*") if item.is_file()):
        relative = path.relative_to(docs_dir.parent).as_posix()
        item: dict[str, Any] = {
            "path": relative,
            "filename": path.name,
            "extension": path.suffix.lower(),
            "size_bytes": path.stat().st_size,
            "readable_text": path.suffix.lower() in READABLE_EXTENSIONS,
            "snippet": None,
        }
        if item["readable_text"]:
            try:
                item["snippet"] = path.read_text(encoding="utf-8")[:1000]
            except UnicodeDecodeError:
                item["readable_text"] = False
        inventory.append(item)
    return inventory


def _expected_materials(
    product_profile: ProductProfile,
    workspace_root: Path,
    inventory: list[dict[str, Any]],
    risk_items: list[RiskItem],
    claim_findings: list[ClaimFinding],
) -> list[EvidenceGap]:
    gaps: list[EvidenceGap] = []
    inventory_paths = {item["path"] for item in inventory}

    for document in product_profile.declared_documents:
        declared_path = document.path
        status = (
            "present"
            if _declared_path_exists(declared_path, workspace_root, inventory_paths)
            else "missing"
        )
        source_path = declared_path if status == "present" else None
        gaps.append(
            EvidenceGap(
                material=_humanize_material(document.kind),
                status=status,
                priority="P0" if status == "missing" else "P1",
                reason=(
                    "Declared document path exists in the workspace."
                    if status == "present"
                    else f"Declared document path was not found: {declared_path}"
                ),
                source_path=source_path,
                suggested_supplier_follow_up=(
                    None
                    if status == "present"
                    else f"Please provide {_humanize_material(document.kind)}."
                ),
            )
        )

    for material in _required_documents(risk_items):
        if _material_already_recorded(gaps, material):
            continue
        matched = _match_inventory(material, inventory)
        gaps.append(
            EvidenceGap(
                material=material,
                status="present" if matched else "missing",
                priority="P0" if _material_priority(material, risk_items) == "P0" else "P1",
                reason=(
                    f"Workspace file appears to cover required material: {matched}."
                    if matched
                    else "Required by one or more market, platform, or guardrail findings."
                ),
                source_path=matched,
                suggested_supplier_follow_up=None if matched else f"Please provide {material}.",
            )
        )

    for finding in claim_findings:
        if not finding.evidence_required:
            continue
        material = f"Claim substantiation for: {finding.source_quote}"
        if _material_already_recorded(gaps, material):
            continue
        gaps.append(
            EvidenceGap(
                material=material,
                status="missing",
                priority="P0" if finding.risk_level == "high" else "P1",
                reason="Listing claim review marked this claim as requiring evidence.",
                suggested_supplier_follow_up=(
                    f"Please provide substantiation for: {finding.source_quote}."
                ),
            )
        )

    return gaps


def _call_evidence_llm(
    product_profile: ProductProfile,
    inventory: list[dict[str, Any]],
    risk_items: list[RiskItem],
    local_gaps: list[EvidenceGap],
    config: AppConfig,
    llm_client: EvidenceLLMClient | None,
    env: Mapping[str, str] | None,
) -> EvidenceGapAnalysisResponse | None:
    if config.llm.enabled == "off":
        return None
    if llm_client is None and config.llm.enabled == "auto" and not provider_configured(env):
        return None

    contract = load_prompt_contract("evidence-gap-analysis", config.llm.prompt_version)
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
        "product_profile": product_profile.model_dump(mode="json"),
        "file_inventory": inventory,
        "risk_items": [item.model_dump(mode="json") for item in risk_items],
        "local_evidence_gaps": [gap.model_dump(mode="json") for gap in local_gaps],
        "supplier_document_upload_allowed": config.privacy.allow_supplier_doc_upload,
    }
    try:
        return client.complete_json(
            contract,
            json.dumps(payload, ensure_ascii=True),
            EvidenceGapAnalysisResponse,
        )
    except (LLMInvalidJSONError, LLMProviderError, LLMSchemaValidationError, LLMTimeoutError):
        if config.llm.enabled == "always":
            raise
        return None


def _sanitize_llm_gaps(
    gaps: list[EvidenceGap],
    workspace_root: Path,
    product_profile: ProductProfile,
) -> list[EvidenceGap]:
    declared_paths = {document.path for document in product_profile.declared_documents}
    sanitized: list[EvidenceGap] = []
    for gap in gaps:
        if gap.status == "present":
            path_present = bool(gap.source_path and (workspace_root / gap.source_path).exists())
            declared_present = bool(gap.source_path and gap.source_path in declared_paths)
            if not path_present and not declared_present:
                sanitized.append(
                    gap.model_copy(
                        update={
                            "status": "uncertain",
                            "source_path": None,
                            "reason": (
                                f"{gap.reason} Model marked this present without a workspace "
                                "file or explicit declaration, so it was downgraded."
                            ),
                        }
                    )
                )
                continue
        sanitized.append(gap)
    return sanitized


def _declared_path_exists(
    declared_path: str,
    workspace_root: Path,
    inventory_paths: set[str],
) -> bool:
    return declared_path in inventory_paths or (workspace_root / declared_path).exists()


def _required_documents(risk_items: list[RiskItem]) -> list[str]:
    materials: list[str] = []
    for item in risk_items:
        for document in item.required_documents:
            if document not in materials:
                materials.append(document)
    return materials


def _material_priority(material: str, risk_items: list[RiskItem]) -> str:
    for item in risk_items:
        if material in item.required_documents and item.severity == "high":
            return "P0"
    return "P1"


def _match_inventory(material: str, inventory: list[dict[str, Any]]) -> str | None:
    material_tokens = _tokens(material)
    for item in inventory:
        filename_tokens = _tokens(str(item["filename"]))
        if material_tokens & filename_tokens:
            return str(item["path"])
    return None


def _tokens(text: str) -> set[str]:
    normalized = text.lower().replace("_", " ").replace("-", " ").replace(".", " ")
    stop_words = {"or", "and", "the", "file", "photo", "documentation", "evidence"}
    return {token for token in normalized.split() if len(token) > 2 and token not in stop_words}


def _material_already_recorded(gaps: list[EvidenceGap], material: str) -> bool:
    return any(gap.material.lower() == material.lower() for gap in gaps)


def _deduplicate_gaps(gaps: list[EvidenceGap]) -> list[EvidenceGap]:
    seen: set[str] = set()
    deduped: list[EvidenceGap] = []
    for gap in gaps:
        key = gap.material.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(gap)
    return deduped


def _humanize_material(kind: str) -> str:
    return kind.replace("_", " ").replace("-", " ").strip().title()
