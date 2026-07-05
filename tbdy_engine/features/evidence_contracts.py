"""P1.17 frozen evidence-contract validators.

The validators in this module are deliberately data-only.  They inspect the
already-produced feature snapshot/evidence payloads from live-smoke or fixture
replay paths; they do not fetch ETABS tables, run analysis/design, execute
checks, or compute engineering thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from tbdy_engine.json_safe import to_jsonable

P1_17_EVIDENCE_CONTRACT_VERSION = "P1.17_EVIDENCE_CONTRACT_FREEZE_V1"

MATERIAL_FEATURES: tuple[str, ...] = (
    "component_section_name",
    "component_section_type",
    "section_concrete_material_name",
    "section_rebar_material_name",
    "concrete_fck_mpa",
    "rebar_fyk_mpa",
    "concrete_material_source_reference",
    "rebar_material_source_reference",
    "material_unit_basis",
)

STORY_FEATURES: tuple[str, ...] = (
    "story_drift_value",
    "story_drift_output_case",
    "story_drift_direction",
    "story_torsion_a1_coefficient",
)

BASE_FEATURES: tuple[str, ...] = (
    "base_reaction_fx",
    "base_reaction_fy",
)

MATERIAL_SOURCE_REFERENCE_FEATURES: tuple[str, ...] = (
    "concrete_material_source_reference",
    "rebar_material_source_reference",
)

_FALSE_ONLY_METADATA_KEYS = frozenset(
    {
        "check_engine_executed",
        "check_result_emitted",
        "engineering_verdict_emitted",
        "live_verdict_emitted",
        "analysis_run",
        "design_run",
        "etabs_model_mutated",
        "model_mutated",
    }
)

_FORBIDDEN_EXACT_KEYS = frozenset(
    {
        "checkresult",
        "check_result",
        "check_results",
        "engineering_verdict",
        "live_verdict",
        "verdict",
        "pass_fail",
        "pass_rule",
        "tbdy_threshold",
        "threshold_verdict",
        "utilization",
        "demand_capacity_ratio",
        "result_panel",
        "formula_panel",
    }
)

_FORBIDDEN_TYPE_NAME_TOKENS = ("checkresult",)


@dataclass(frozen=True, slots=True)
class EvidenceContractViolation:
    """One deterministic evidence-contract violation."""

    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}


@dataclass(frozen=True, slots=True)
class EvidenceContractReport:
    """Stable validation report for P1.17 evidence-contract checks."""

    contract_version: str
    validated_components: tuple[str, ...]
    validated_features: tuple[str, ...]
    source_references: tuple[str, ...]
    stable_json_sha256: str
    violations: tuple[EvidenceContractViolation, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "ok": self.ok,
            "validated_components": list(self.validated_components),
            "validated_features": list(self.validated_features),
            "source_references": list(self.source_references),
            "stable_json_sha256": self.stable_json_sha256,
            "violations": [item.as_dict() for item in self.violations],
        }


class EvidenceContractError(AssertionError):
    """Raised when a P1.17 evidence payload violates the frozen contract."""

    def __init__(self, report: EvidenceContractReport):
        self.report = report
        details = "; ".join(f"{v.path}: {v.message}" for v in report.violations)
        super().__init__(f"P1.17 evidence contract violation(s): {details}")


def stable_json_text(payload: Any) -> str:
    """Return deterministic JSON or raise for unsafe/non-finite values."""

    jsonable = to_jsonable(payload)
    return json.dumps(jsonable, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def stable_json_sha256(payload: Any) -> str:
    return hashlib.sha256(stable_json_text(payload).encode("utf-8")).hexdigest()


def assert_p1_17_evidence_contract(payload: Any, *, require: Sequence[str] = ()) -> EvidenceContractReport:
    """Validate and raise ``EvidenceContractError`` on any violation."""

    report = validate_p1_17_evidence_contract(payload, require=require)
    if not report.ok:
        raise EvidenceContractError(report)
    return report


def validate_p1_17_evidence_contract(payload: Any, *, require: Sequence[str] = ()) -> EvidenceContractReport:
    """Validate current live/offline feature-evidence outputs against P1.17.

    ``require`` may contain ``"material"`` and/or ``"story_base"`` to force
    those accepted P1.14/P1.15 surfaces to be present.  The checks are shape and
    safety checks only; no TBDY thresholds, engineering pass/fail logic, or
    stale live expected values are evaluated.
    """

    violations: list[EvidenceContractViolation] = []
    source_references: list[str] = []
    validated_features: list[str] = []
    validated_components: list[str] = []

    try:
        jsonable = to_jsonable(payload)
        stable_hash = stable_json_sha256(jsonable)
    except Exception as exc:  # noqa: BLE001 - contract report should preserve any serialization failure.
        jsonable = payload
        stable_hash = ""
        violations.append(EvidenceContractViolation("$", f"payload is not deterministic JSON-safe: {exc}"))

    _validate_forbidden_keys(jsonable, "$", violations)
    _validate_false_only_safety_flags(jsonable, "$", violations)

    snapshots = _snapshot_list(jsonable)
    by_component: dict[str, Mapping[str, Any]] = {}
    for index, snapshot in enumerate(snapshots):
        if not isinstance(snapshot, Mapping):
            violations.append(EvidenceContractViolation(f"$.snapshots[{index}]", "snapshot entry must be an object"))
            continue
        component_type = _string(snapshot.get("component_type"))
        if component_type:
            by_component[component_type] = snapshot
            validated_components.append(component_type)

    require_set = {item.casefold() for item in require}
    if "material" in require_set and "material" not in by_component:
        violations.append(EvidenceContractViolation("$.snapshots", "material snapshot is required but missing"))
    if "story_base" in require_set:
        if "story" not in by_component:
            violations.append(EvidenceContractViolation("$.snapshots", "story snapshot is required but missing"))
        if "global" not in by_component:
            violations.append(EvidenceContractViolation("$.snapshots", "global/base snapshot is required but missing"))

    validate_material = not require_set or "material" in require_set
    validate_story_base = not require_set or "story_base" in require_set

    if validate_material and "material" in by_component:
        _validate_feature_group(
            by_component["material"],
            MATERIAL_FEATURES,
            "$.snapshots[material]",
            violations,
            validated_features,
            source_references,
            material=True,
        )

    if validate_story_base and "story" in by_component:
        _validate_feature_group(
            by_component["story"],
            STORY_FEATURES,
            "$.snapshots[story]",
            violations,
            validated_features,
            source_references,
            story_base=True,
        )

    if validate_story_base and "global" in by_component:
        _validate_feature_group(
            by_component["global"],
            BASE_FEATURES,
            "$.snapshots[global]",
            violations,
            validated_features,
            source_references,
            story_base=True,
        )

    return EvidenceContractReport(
        contract_version=P1_17_EVIDENCE_CONTRACT_VERSION,
        validated_components=tuple(sorted(set(validated_components))),
        validated_features=tuple(sorted(set(validated_features))),
        source_references=tuple(sorted(set(source_references))),
        stable_json_sha256=stable_hash,
        violations=tuple(violations),
    )


def validate_p1_17_evidence_contract_file(path: str | Path, *, require: Sequence[str] = ()) -> EvidenceContractReport:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return assert_p1_17_evidence_contract(payload, require=require)


def _snapshot_list(payload: Any) -> list[Any]:
    if isinstance(payload, Mapping):
        snapshots = payload.get("snapshots")
        if isinstance(snapshots, list):
            return snapshots
        if payload.get("component_type"):
            return [payload]
    if isinstance(payload, list):
        return payload
    return []


def _validate_feature_group(
    snapshot: Mapping[str, Any],
    names: Iterable[str],
    path: str,
    violations: list[EvidenceContractViolation],
    validated_features: list[str],
    source_references: list[str],
    *,
    material: bool = False,
    story_base: bool = False,
) -> None:
    features = snapshot.get("features")
    if not isinstance(features, Mapping):
        violations.append(EvidenceContractViolation(f"{path}.features", "features object is required"))
        return

    for feature_name in names:
        feature_path = f"{path}.features.{feature_name}"
        feature = features.get(feature_name)
        if not isinstance(feature, Mapping):
            violations.append(EvidenceContractViolation(feature_path, "required feature is missing"))
            continue
        validated_features.append(feature_name)
        _validate_resolved_feature(feature, feature_path, violations, source_references, material=material, story_base=story_base)

        if material and feature_name in MATERIAL_SOURCE_REFERENCE_FEATURES:
            value = feature.get("value")
            if not _is_stable_live_table_reference(value):
                violations.append(EvidenceContractViolation(f"{feature_path}.value", "material source reference must be a stable LIVE_ETABS_DISPLAY_TABLE string"))


def _validate_resolved_feature(
    feature: Mapping[str, Any],
    path: str,
    violations: list[EvidenceContractViolation],
    source_references: list[str],
    *,
    material: bool,
    story_base: bool,
) -> None:
    if feature.get("status") != "RESOLVED":
        violations.append(EvidenceContractViolation(f"{path}.status", "frozen evidence feature must be RESOLVED"))
    evidence_items = feature.get("evidence")
    if not isinstance(evidence_items, list) or not evidence_items:
        violations.append(EvidenceContractViolation(f"{path}.evidence", "resolved feature requires at least one evidence row"))
        return
    evidence = evidence_items[0]
    if not isinstance(evidence, Mapping):
        violations.append(EvidenceContractViolation(f"{path}.evidence[0]", "evidence row must be an object"))
        return
    if evidence.get("evidence_status") != "FULL":
        violations.append(EvidenceContractViolation(f"{path}.evidence[0].evidence_status", "resolved evidence must be FULL"))
    for key in ("source_table", "actual_table_name", "source_column"):
        if evidence.get(key) in (None, ""):
            violations.append(EvidenceContractViolation(f"{path}.evidence[0].{key}", f"{key} is required"))
    source_row = evidence.get("source_row")
    if not isinstance(source_row, Mapping):
        violations.append(EvidenceContractViolation(f"{path}.evidence[0].source_row", "source_row object is required"))
        return
    _validate_source_row(source_row, f"{path}.evidence[0].source_row", violations, source_references, material=material, story_base=story_base)


def _validate_source_row(
    source_row: Mapping[str, Any],
    path: str,
    violations: list[EvidenceContractViolation],
    source_references: list[str],
    *,
    material: bool,
    story_base: bool,
) -> None:
    for key in ("source_kind", "source_table", "actual_table_name", "selection_reason", "complete_source_row"):
        if source_row.get(key) in (None, "", {}):
            violations.append(EvidenceContractViolation(f"{path}.{key}", f"{key} is required"))
    if not isinstance(source_row.get("row_index"), int):
        violations.append(EvidenceContractViolation(f"{path}.row_index", "row_index must be an integer for row-backed resolved evidence"))
    if source_row.get("source_table") and source_row.get("actual_table_name"):
        if source_row.get("stable_row_reference") in (None, "", {}):
            violations.append(EvidenceContractViolation(f"{path}.stable_row_reference", "stable_row_reference is required"))
    if not isinstance(source_row.get("complete_source_row"), Mapping):
        violations.append(EvidenceContractViolation(f"{path}.complete_source_row", "complete_source_row must be an object"))

    source_ref = source_row.get("source_reference")
    if source_ref is not None:
        if not _is_stable_live_table_reference(source_ref):
            violations.append(EvidenceContractViolation(f"{path}.source_reference", "source_reference must be a stable LIVE_ETABS_DISPLAY_TABLE string"))
        else:
            source_references.append(str(source_ref))

    if material:
        if not isinstance(source_row.get("selected_component_identity_context"), Mapping):
            violations.append(EvidenceContractViolation(f"{path}.selected_component_identity_context", "material evidence must retain selected component context"))
        if not isinstance(source_row.get("selected_section_context"), Mapping):
            violations.append(EvidenceContractViolation(f"{path}.selected_section_context", "material evidence must retain selected section context"))

    if story_base:
        if source_row.get("output_case") in (None, ""):
            violations.append(EvidenceContractViolation(f"{path}.output_case", "story/base evidence must retain output case context"))
        table_key = str(source_row.get("source_table") or "")
        if table_key.startswith("story_"):
            if source_row.get("story") in (None, ""):
                violations.append(EvidenceContractViolation(f"{path}.story", "story evidence must retain story context"))
            if table_key in {"story_drifts", "story_max_over_avg_drifts"} and source_row.get("direction") in (None, ""):
                violations.append(EvidenceContractViolation(f"{path}.direction", "story evidence must retain direction context where exposed"))


def _is_stable_live_table_reference(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parts = value.split(":")
    if len(parts) < 3:
        return False
    if parts[0] != "LIVE_ETABS_DISPLAY_TABLE":
        return False
    if not parts[1]:
        return False
    if not parts[2].startswith("row="):
        return False
    return True


def _validate_false_only_safety_flags(value: Any, path: str, violations: list[EvidenceContractViolation]) -> None:
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            key_text = str(key)
            next_path = f"{path}.{key_text}"
            if key_text.casefold() in _FALSE_ONLY_METADATA_KEYS and nested_value is not False:
                violations.append(EvidenceContractViolation(next_path, "global evidence safety flag must be explicitly false"))
            _validate_false_only_safety_flags(nested_value, next_path, violations)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_false_only_safety_flags(item, f"{path}[{index}]", violations)


def _validate_forbidden_keys(value: Any, path: str, violations: list[EvidenceContractViolation]) -> None:
    type_name = type(value).__name__.casefold()
    if any(token in type_name for token in _FORBIDDEN_TYPE_NAME_TOKENS):
        violations.append(EvidenceContractViolation(path, f"forbidden object type leaked into evidence payload: {type(value).__name__}"))
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            key_text = str(key)
            folded = key_text.casefold()
            next_path = f"{path}.{key_text}"
            if folded not in _FALSE_ONLY_METADATA_KEYS and folded in _FORBIDDEN_EXACT_KEYS:
                violations.append(EvidenceContractViolation(next_path, "check/verdict/threshold field is forbidden in evidence contract payload"))
            _validate_forbidden_keys(nested_value, next_path, violations)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_forbidden_keys(item, f"{path}[{index}]", violations)


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


__all__ = [
    "BASE_FEATURES",
    "EvidenceContractError",
    "EvidenceContractReport",
    "EvidenceContractViolation",
    "MATERIAL_FEATURES",
    "P1_17_EVIDENCE_CONTRACT_VERSION",
    "STORY_FEATURES",
    "assert_p1_17_evidence_contract",
    "stable_json_sha256",
    "stable_json_text",
    "validate_p1_17_evidence_contract",
    "validate_p1_17_evidence_contract_file",
]
