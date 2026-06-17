"""C13.3-P0 minimal source-to-feature projection proof.

The builder consumes bounded source rows and emits a FeatureSnapshot-shaped dict
with raw unit metadata, normalized display metadata, evidence, readiness status,
and permanent check guardrails.  It deliberately does not import or call the
CheckEngine.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from tbdy_engine.features.readiness import (
    FeatureProofStatus,
    ReadinessStatus,
    assert_no_engineering_verdict_text,
)
from tbdy_engine.features.unit_metadata import normalize_value

SPRINT = "C13.3-P0"
BASELINE = "c13.2-p5-contract-closure-source-feature-readiness"
SOURCE_FAMILIES = ("material_properties", "story_definitions", "pier_section_properties")
INTERNAL_SOURCE_TABLE_KEY = "__source_table"

MATERIAL_SOURCE_FIELDS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
    "material_type": ("material_type", "identity_context", "unitless", ("Type", "MaterialType", "MatType")),
    "material_e1": ("material_e1", "material_mechanical_constants", "MPa", ("E1", "E", "ModulusOfElasticity")),
    "material_g12": ("material_g12", "material_mechanical_constants", "MPa", ("G12", "G", "ShearModulus")),
    "material_u12": ("material_u12", "unitless", "unitless", ("U12", "Nu12", "Poisson", "PoissonRatio")),
    "material_fc": ("material_fc", "stress_material_strength", "MPa", ("Fc", "fc", "Fck", "ConcreteStrength")),
    "material_fy": ("material_fy", "stress_material_strength", "MPa", ("Fy", "fy", "Fyk", "YieldStress")),
    "material_fu": ("material_fu", "stress_material_strength", "MPa", ("Fu", "fu", "TensileStress")),
    "material_fye": ("material_fye", "stress_material_strength", "MPa", ("Fye",)),
    "material_fys": ("material_fys", "stress_material_strength", "MPa", ("Fys",)),
}

BLOCKED_CHECK_RECORDS = (
    (
        "material_compliance_locked",
        "material_properties",
        "LOCKED_CHECK_NOT_ALLOWED",
        "material/rebar compliance concepts are outside this proof",
    ),
    (
        "story_drift_torsion_force_locked",
        "story_definitions",
        "BLOCKED_SEMANTIC_REVIEW",
        "drift/torsion/story force result semantics remain blocked",
    ),
    (
        "pier_wall_force_capacity_detailing_locked",
        "pier_section_properties",
        "BLOCKED_SEMANTIC_REVIEW",
        "pier/wall force, capacity, and detailing semantics remain blocked",
    ),
)


def fixture_source_rows() -> dict[str, list[dict[str, Any]]]:
    """Small deterministic offline fixture set; not an Excel production path."""
    return {
        "material_properties": [
            {
                INTERNAL_SOURCE_TABLE_KEY: "Material Properties - Basic Mechanical Properties",
                "Material": "C30",
                "Type": "Concrete",
                "E1": 32000.0,
                "G12": 13333.0,
                "U12": 0.20,
                "Fc": 30.0,
            },
            {
                INTERNAL_SOURCE_TABLE_KEY: "Material Properties - Rebar Data",
                "Material": "B420C",
                "Type": "Rebar",
                "E1": 200000.0,
                "G12": 76923.0,
                "U12": 0.30,
                "Fy": 420.0,
            },
        ],
        "story_definitions": [
            {INTERNAL_SOURCE_TABLE_KEY: "Tower and Base Story Definitions", "Tower": "Tower 1", "BSElev": 0.0},
            {INTERNAL_SOURCE_TABLE_KEY: "Story Definitions", "Story": "BASE", "Height": 0.0},
            {INTERNAL_SOURCE_TABLE_KEY: "Story Definitions", "Story": "+3.0", "Height": 3.0},
            {INTERNAL_SOURCE_TABLE_KEY: "Story Definitions", "Story": "+6.0", "Height": 3.0},
        ],
        "pier_section_properties": [
            {
                INTERNAL_SOURCE_TABLE_KEY: "Pier Section Properties",
                "Story": "+3.0",
                "Pier": "P1",
                "Width": 1200.0,
                "Thickness": 250.0,
                "Material": "C30",
            },
            {
                INTERNAL_SOURCE_TABLE_KEY: "Pier Section Properties",
                "Story": "+6.0",
                "Pier": "P1",
                "Width": 1200.0,
                "Thickness": 250.0,
                "Material": "C30",
            },
        ],
    }


def _as_list(source_rows: Mapping[str, Iterable[Mapping[str, Any]]] | None, family: str) -> list[dict[str, Any]]:
    return [dict(row) for row in (source_rows or {}).get(family, [])]


def _clean_key(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def _key_index(row: Mapping[str, Any]) -> dict[str, str]:
    return {_clean_key(str(key)): str(key) for key in row if str(key) != INTERNAL_SOURCE_TABLE_KEY}


def _actual_key(row: Mapping[str, Any], aliases: Iterable[str]) -> str | None:
    index = _key_index(row)
    for alias in aliases:
        key = index.get(_clean_key(alias))
        if key is not None:
            return key
    return None


def _value(row: Mapping[str, Any], aliases: Iterable[str]) -> tuple[str | None, Any]:
    key = _actual_key(row, aliases)
    if key is None:
        return None, None
    value = row.get(key)
    if value == "":
        return key, None
    return key, value


def _first_real_value(row: Mapping[str, Any]) -> tuple[str | None, Any]:
    for key, value in row.items():
        if key == INTERNAL_SOURCE_TABLE_KEY:
            continue
        if value not in (None, ""):
            return str(key), value
    return None, None


def _source_table(row: Mapping[str, Any], default: str) -> str:
    value = row.get(INTERNAL_SOURCE_TABLE_KEY)
    return str(value) if value else default


def _source_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in row.items() if str(key) != INTERNAL_SOURCE_TABLE_KEY}


def _as_number(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text:
            try:
                return float(text)
            except ValueError:
                return value
    return value


def _feature_value(value: Any, quantity_kind: str) -> Any:
    if quantity_kind in {"identity_context", "unitless"}:
        return _as_number(value) if quantity_kind == "unitless" else value
    return _as_number(value)


def _status_from_value(value: Any) -> str:
    return FeatureProofStatus.RESOLVED.value if value not in (None, "") else FeatureProofStatus.PARTIAL.value


def _record(
    *,
    feature_id: str,
    feature_name: str,
    source_family: str,
    source_table: str,
    readiness_status: str,
    feature_status: str,
    raw_value: Any,
    raw_unit: str | None,
    quantity_kind: str,
    component_type: str | None = None,
    component_id: str | None = None,
    source_columns: list[str] | None = None,
    source_row: Mapping[str, Any] | None = None,
    derived: bool = False,
    derivation_policy: Mapping[str, Any] | None = None,
    semantic_guardrails: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    norm = normalize_value(raw_value, raw_unit=raw_unit, quantity_kind=quantity_kind)
    row = dict(source_row or {})
    evidence_status = "FULL" if feature_status == FeatureProofStatus.RESOLVED.value else "PARTIAL"
    record = {
        "feature_id": feature_id,
        "feature_name": feature_name,
        "component_type": component_type,
        "component_id": component_id,
        "source_family": source_family,
        "source_tables": [source_table],
        "source_columns": list(source_columns or []),
        "readiness_status": readiness_status,
        "feature_status": feature_status,
        "raw_value": norm.raw_value,
        "raw_unit": norm.raw_unit,
        "normalized_value": norm.normalized_value,
        "normalized_unit": norm.normalized_unit,
        "quantity_kind": norm.quantity_kind,
        "unit_policy": norm.unit_policy,
        "conversion_provenance": norm.provenance,
        "evidence": {
            "evidence_status": evidence_status,
            "source_family": source_family,
            "source_table": source_table,
            "source_columns": list(source_columns or []),
            "source_row": row,
            "raw_value": norm.raw_value,
            "normalized_value": norm.normalized_value,
            "resolver": "c13_3_p0_source_feature_snapshot_builder",
        },
        "semantic_guardrails": {
            "check_unlock_allowed": False,
            "safe_to_use_for_check": False,
            "safe_to_implement_checks_now": False,
            "engineering_formulas_implemented": False,
            **dict(semantic_guardrails or {}),
        },
        "check_unlock_allowed": False,
        "safe_to_use_for_check": False,
        "derived": derived,
    }
    if derivation_policy is not None:
        record["derivation_policy"] = dict(derivation_policy)
    return record


def _material_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        table_name = _source_table(row, "Material Properties")
        material_key, material = _value(row, ("Material", "Name", "MaterialName", "MatProp", "PropName"))
        if material is None:
            material_key, material = _first_real_value(row)
        component_id = str(material) if material not in (None, "") else f"material_row_{index}"
        records.append(
            _record(
                feature_id=f"material_name::{component_id}",
                feature_name="material_name",
                component_type="MATERIAL",
                component_id=component_id,
                source_family="material_properties",
                source_table=table_name,
                source_columns=[material_key] if material_key else [],
                source_row=_source_row(row),
                readiness_status=ReadinessStatus.READY_DIRECT_SOURCE.value,
                feature_status=_status_from_value(material),
                raw_value=material,
                raw_unit="unitless",
                quantity_kind="identity_context",
            )
        )
        for _, (feature_name, quantity_kind, unit, aliases) in MATERIAL_SOURCE_FIELDS.items():
            actual_key, value = _value(row, aliases)
            if actual_key is None:
                continue
            raw_value = _feature_value(value, quantity_kind)
            records.append(
                _record(
                    feature_id=f"{feature_name}::{component_id}",
                    feature_name=feature_name,
                    component_type="MATERIAL",
                    component_id=component_id,
                    source_family="material_properties",
                    source_table=table_name,
                    source_columns=[actual_key],
                    source_row=_source_row(row),
                    readiness_status=ReadinessStatus.READY_DIRECT_SOURCE.value,
                    feature_status=_status_from_value(raw_value),
                    raw_value=raw_value,
                    raw_unit=unit,
                    quantity_kind=quantity_kind,
                )
            )
    return records


def _story_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    base_candidates: list[tuple[dict[str, Any], str, Any]] = []
    story_rows: list[dict[str, Any]] = []
    for row in rows:
        bselev_key, bselev = _value(row, ("BSElev", "BaseElevation", "BaseElev"))
        if bselev_key is not None:
            base_candidates.append((row, bselev_key, bselev))
        story_key, story = _value(row, ("Story", "Name", "StoryName"))
        height_key, height = _value(row, ("Height", "StoryHeight"))
        if story_key is not None or height_key is not None:
            story_rows.append(row)

    base_elev = _as_number(base_candidates[0][2]) if base_candidates else 0.0
    if base_candidates:
        base_row, bselev_key, bselev = base_candidates[0]
        tower_key, tower = _value(base_row, ("Tower", "TowerName", "Name"))
        component_id = str(tower or "base_story")
        records.append(
            _record(
                feature_id=f"story_base_elevation::{component_id}",
                feature_name="story_base_elevation",
                component_type="STORY_CONTEXT",
                component_id=component_id,
                source_family="story_definitions",
                source_table=_source_table(base_row, "Tower and Base Story Definitions"),
                source_columns=[bselev_key],
                source_row=_source_row(base_row),
                readiness_status=ReadinessStatus.READY_DIRECT_SOURCE.value,
                feature_status=_status_from_value(bselev),
                raw_value=_feature_value(bselev, "global_length_elevation"),
                raw_unit="m",
                quantity_kind="global_length_elevation",
                semantic_guardrails={"base_elevation_column": bselev_key},
            )
        )

    cumulative = float(base_elev or 0.0)
    for index, row in enumerate(story_rows):
        table_name = _source_table(row, "Story Definitions")
        story_key, story = _value(row, ("Story", "Name", "StoryName"))
        height_key, height = _value(row, ("Height", "StoryHeight"))
        component_id = str(story) if story not in (None, "") else f"story_row_{index}"
        records.append(
            _record(
                feature_id=f"story_name::{component_id}",
                feature_name="story_name",
                component_type="STORY",
                component_id=component_id,
                source_family="story_definitions",
                source_table=table_name,
                source_columns=[story_key] if story_key else [],
                source_row=_source_row(row),
                readiness_status=ReadinessStatus.READY_DIRECT_SOURCE.value,
                feature_status=_status_from_value(story),
                raw_value=story,
                raw_unit="unitless",
                quantity_kind="identity_context",
            )
        )
        raw_height = _feature_value(height, "global_length_elevation")
        records.append(
            _record(
                feature_id=f"story_height::{component_id}",
                feature_name="story_height",
                component_type="STORY",
                component_id=component_id,
                source_family="story_definitions",
                source_table=table_name,
                source_columns=[height_key] if height_key else [],
                source_row=_source_row(row),
                readiness_status=ReadinessStatus.READY_DIRECT_SOURCE.value,
                feature_status=_status_from_value(raw_height),
                raw_value=raw_height,
                raw_unit="m",
                quantity_kind="global_length_elevation",
            )
        )
        derived_ok = isinstance(raw_height, (int, float)) and isinstance(base_elev, (int, float))
        if derived_ok:
            cumulative += float(raw_height)
        records.append(
            _record(
                feature_id=f"story_derived_elevation::{component_id}",
                feature_name="story_derived_elevation",
                component_type="STORY",
                component_id=component_id,
                source_family="story_definitions",
                source_table=table_name,
                source_columns=[column for column in (base_candidates[0][1] if base_candidates else "BSElev", height_key) if column],
                source_row=_source_row(row),
                readiness_status=ReadinessStatus.READY_DERIVED_SOURCE.value,
                feature_status=FeatureProofStatus.RESOLVED.value if derived_ok else FeatureProofStatus.PARTIAL.value,
                raw_value=cumulative if derived_ok else None,
                raw_unit="m",
                quantity_kind="global_length_elevation",
                derived=True,
                derivation_policy={
                    "derived_elevation_supported": True,
                    "elevation_is_direct_column": False,
                    "base_elevation_column": base_candidates[0][1] if base_candidates else "BSElev",
                    "input_fields": ["Story", "Height", "BSElev"],
                },
            )
        )
    return records


def _pier_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    specs = (
        ("pier_id", "identity_context", "unitless", ("Pier", "PierName", "PierID", "Name")),
        ("pier_story", "identity_context", "unitless", ("Story", "StoryName")),
        ("pier_width", "section_dimensions", "mm", ("Width", "PierWidth", "Length")),
        ("pier_thickness", "section_dimensions", "mm", ("Thickness", "Thick", "T", "WallThickness")),
        ("pier_material", "identity_context", "unitless", ("Material", "MatProp", "MaterialName")),
    )
    for index, row in enumerate(rows):
        table_name = _source_table(row, "Pier Section Properties")
        _, pier = _value(row, ("Pier", "PierName", "PierID", "Name"))
        _, story = _value(row, ("Story", "StoryName"))
        component_id = f"{story or 'UNKNOWN_STORY'}:{pier or f'pier_row_{index}'}"
        section_key = _actual_key(row, ("Section", "SectionName"))
        material_key = _actual_key(row, ("Material", "MatProp", "MaterialName"))
        for feature_name, quantity_kind, unit, aliases in specs:
            actual_key, value = _value(row, aliases)
            raw_value = _feature_value(value, quantity_kind)
            records.append(
                _record(
                    feature_id=f"{feature_name}::{component_id}",
                    feature_name=feature_name,
                    component_type="PIER_SECTION",
                    component_id=component_id,
                    source_family="pier_section_properties",
                    source_table=table_name,
                    source_columns=[actual_key] if actual_key else [],
                    source_row=_source_row(row),
                    readiness_status=ReadinessStatus.READY_DIRECT_SOURCE.value,
                    feature_status=_status_from_value(raw_value),
                    raw_value=raw_value,
                    raw_unit=unit,
                    quantity_kind=quantity_kind,
                    semantic_guardrails={
                        "direct_section_geometry_present": True,
                        "section_name_column_required": False,
                        "section_name_column_present": section_key is not None,
                        "material_present": material_key is not None,
                    },
                )
            )
    return records


def _blocked_records() -> list[dict[str, Any]]:
    records = []
    for feature_id, source_family, status, reason in BLOCKED_CHECK_RECORDS:
        records.append(
            _record(
                feature_id=feature_id,
                feature_name=feature_id,
                component_type=None,
                component_id=None,
                source_family=source_family,
                source_table="source_feature_readiness_matrix",
                source_columns=[],
                source_row={"reason": reason},
                readiness_status=status,
                feature_status=status,
                raw_value=None,
                raw_unit="unitless",
                quantity_kind="identity_context",
                semantic_guardrails={"lock_reason": reason},
            )
        )
    return records


def build_c13_3_p0_feature_snapshot(
    source_rows: Mapping[str, Iterable[Mapping[str, Any]]] | None,
    *,
    live_etabs_connected: bool = False,
    model_path: str | None = None,
    etabs_version: str | None = None,
    target_family: str = "all",
    generated_at: str | None = None,
) -> dict[str, Any]:
    families = SOURCE_FAMILIES if target_family == "all" else (target_family,)
    feature_records: list[dict[str, Any]] = []
    if "material_properties" in families:
        feature_records.extend(_material_records(_as_list(source_rows, "material_properties")))
    if "story_definitions" in families:
        feature_records.extend(_story_records(_as_list(source_rows, "story_definitions")))
    if "pier_section_properties" in families:
        feature_records.extend(_pier_records(_as_list(source_rows, "pier_section_properties")))
    feature_records.extend(_blocked_records())

    feature_status_counts = Counter(record["feature_status"] for record in feature_records)
    readiness_status_counts = Counter(record["readiness_status"] for record in feature_records)
    snapshot = {
        "sprint": SPRINT,
        "source_contract_baseline": BASELINE,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "live_etabs_connected": bool(live_etabs_connected),
        "model_path": model_path,
        "etabs_version": etabs_version,
        "feature_status_counts": dict(sorted(feature_status_counts.items())),
        "readiness_status_counts": dict(sorted(readiness_status_counts.items())),
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "unit_policy_closed": True,
        "target_family": target_family,
        "feature_records": feature_records,
    }
    assert_no_engineering_verdict_text(snapshot)
    return snapshot


def summarize_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sprint": snapshot["sprint"],
        "live_etabs_connected": snapshot["live_etabs_connected"],
        "feature_record_count": len(snapshot.get("feature_records", [])),
        "feature_status_counts": dict(snapshot.get("feature_status_counts", {})),
        "readiness_status_counts": dict(snapshot.get("readiness_status_counts", {})),
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "unit_policy_closed": True,
    }


def unit_normalization_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    records = snapshot.get("feature_records", [])
    numeric_records = [record for record in records if isinstance(record.get("raw_value"), (int, float))]
    return {
        "sprint": SPRINT,
        "numeric_feature_count": len(numeric_records),
        "all_numeric_have_units": all(record.get("raw_unit") and record.get("normalized_unit") for record in numeric_records),
        "all_numeric_have_quantity_kind": all(record.get("quantity_kind") for record in numeric_records),
        "all_numeric_have_conversion_provenance": all(record.get("conversion_provenance") for record in numeric_records),
        "raw_values_preserved": all(record.get("evidence", {}).get("raw_value") == record.get("raw_value") for record in records),
        "source_contract_silent_conversion_allowed": False,
        "check_unlock_allowed": False,
    }


def readiness_projection_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sprint": SPRINT,
        "readiness_status_counts": dict(snapshot.get("readiness_status_counts", {})),
        "projected_families": sorted({record["source_family"] for record in snapshot.get("feature_records", [])}),
        "check_unlock_allowed": False,
        "safe_to_implement_checks_now": False,
    }


def blocked_check_guardrail_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    blocked = [
        record
        for record in snapshot.get("feature_records", [])
        if record["feature_status"]
        in {
            FeatureProofStatus.LOCKED_CHECK_NOT_ALLOWED.value,
            FeatureProofStatus.BLOCKED_SEMANTIC_REVIEW.value,
            FeatureProofStatus.BLOCKED_NEEDS_LIVE_PROBE.value,
            FeatureProofStatus.OUT_OF_SCOPE_UNSUPPORTED.value,
        }
    ]
    return {
        "sprint": SPRINT,
        "blocked_or_locked_record_count": len(blocked),
        "records": blocked,
        "check_unlock_allowed": False,
        "safe_to_implement_checks_now": False,
        "engineering_verdicts_emitted": False,
    }


__all__ = [
    "BASELINE",
    "INTERNAL_SOURCE_TABLE_KEY",
    "SOURCE_FAMILIES",
    "SPRINT",
    "blocked_check_guardrail_report",
    "build_c13_3_p0_feature_snapshot",
    "fixture_source_rows",
    "readiness_projection_report",
    "summarize_snapshot",
    "unit_normalization_report",
]
