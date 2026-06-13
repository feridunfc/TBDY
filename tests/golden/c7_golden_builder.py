"""C7 deterministic golden JSON builder.

This module is test-only. It uses artificial FeatureSnapshot fixtures and the
minimal CheckEngine; it does not touch providers, ETABS, table registries,
feature resolvers, live data, runner_v2, runtime, or archx.
"""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping as AbcMapping
from types import MappingProxyType
from typing import Any

from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.coverage.models import (
    CoverageExpectedSource,
    CoverageMatrix,
    CoverageMissingFeature,
    CoverageRow,
)
from tbdy_engine.features.evidence import FeatureEvidence
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue

EVIDENCE_FIELDS = (
    "source_table",
    "source_row",
    "source_column",
    "raw_value",
    "normalized_value",
    "unit",
    "output_case",
    "combo_family",
)

CHECK_DEFINITIONS: dict[str, dict[str, Any]] = {
    "beam_geometry_min_width": {
        "required_features": ["beam_width_mm"],
        "minimum": 250,
        "unit": "mm",
        "code_ref": "TBDY2018/Beam geometry min width fixture",
        "c6_allowed": True,
    },
    "beam_depth_width_ratio": {
        "required_features": ["beam_depth_mm", "beam_width_mm"],
        "limit": 3.5,
        "unit": "ratio",
        "code_ref": "TBDY2018/Beam depth-width screening fixture",
        "c6_allowed": True,
    },
    "story_drift_ratio": {
        # Feature names remain data-only per C4, so the ratio value is carried
        # by story_drift_value even though the check_id is story_drift_ratio.
        "required_features": ["story_drift_value"],
        "limit": 1.0,
        "unit": "ratio",
        "code_ref": "TBDY2018/Story drift upper-bound fixture",
        "c6_allowed": True,
    },
    "modal_mass_sumux_ge_threshold": {
        "required_features": ["modal_sum_ux"],
        "ratio_type": "value_over_minimum",
        "minimum": 0.90,
        "unit": "ratio",
        "code_ref": "TBDY2018/Modal participating mass fixture",
        "c6_allowed": True,
    },
    "required_feature_missing_no_data": {
        "required_features": ["missing_artificial_feature"],
        "ratio_type": "availability",
        "unit": "",
        "code_ref": "Contract coverage gate fixture",
        "c6_allowed": True,
    },
}


def _evidence(feature_name: str, value: Any, unit: str, component_id: str) -> FeatureEvidence:
    return FeatureEvidence(
        evidence_status="FULL",
        source_table="artificial_fixture",
        actual_table_name="artificial_fixture",
        source_column=feature_name,
        source_row={"component_id": component_id, feature_name: value},
        output_case=None,
        combo_family="NONE",
        raw_value=value,
        normalized_value=value,
        unit=unit,
        resolver="c7_artificial_fixture",
    )


def _feature(feature_name: str, value: Any, unit: str, semantic_role: str, component_id: str) -> FeatureValue:
    return FeatureValue(
        feature_name=feature_name,
        value=value,
        unit=unit,
        semantic_role=semantic_role,
        status="RESOLVED",
        evidence=[_evidence(feature_name, value, unit, component_id)],
    )


def _snapshot(component_type: str, component_id: str, identity: dict[str, Any], features: dict[str, FeatureValue]) -> FeatureSnapshot:
    return FeatureSnapshot(
        component_type=component_type,
        component_id=component_id,
        identity=identity,
        features=features,
    )


def _source(feature_name: str, unit: str) -> CoverageExpectedSource:
    return CoverageExpectedSource(
        source_kind="etabs_table",
        feature_name=feature_name,
        table_key="artificial_fixture_table",
        table_aliases=["Artificial Fixture Table"],
        field_aliases=[feature_name],
        combo_family="NONE",
        aggregation="first",
        unit=unit,
        expected_evidence_fields=EVIDENCE_FIELDS,
    )


def _coverage(
    *,
    check_id: str,
    component_type: str,
    component_id: str,
    required_features: list[str],
    resolved_features: list[str] | None = None,
    coverage_status: str = "RUNNABLE",
    evidence_status: str = "FULL",
    reason: str | None = None,
    missing_features: list[CoverageMissingFeature] | None = None,
    expected_sources: dict[str, CoverageExpectedSource] | None = None,
    expected_evidence: dict[str, list[str]] | None = None,
) -> CoverageRow:
    return CoverageRow(
        check_id=check_id,
        component_type=component_type,
        component_id=component_id,
        required_features=required_features,
        resolved_features=resolved_features if resolved_features is not None else required_features,
        missing_features=missing_features or [],
        coverage_status=coverage_status,
        evidence_status=evidence_status,
        reason=reason,
        missing_feature_sources=expected_sources or {},
        expected_evidence_requirements=expected_evidence or {},
    )


def build_c7_artificial_chain() -> tuple[list[FeatureSnapshot], CoverageMatrix, list[dict[str, Any]]]:
    """Build deterministic FeatureSnapshot -> CoverageMatrix -> CheckResult[] proof."""
    engine = MinimalCheckEngine(CHECK_DEFINITIONS)

    snapshots: list[FeatureSnapshot] = [
        _snapshot(
            "beam",
            "B_OK",
            {"story": "+14.5", "section": "B30x60"},
            {"beam_width_mm": _feature("beam_width_mm", 300, "mm", "GEOMETRY", "B_OK")},
        ),
        _snapshot(
            "beam",
            "B_WIDTH_FAIL",
            {"story": "+14.5", "section": "B20x60"},
            {"beam_width_mm": _feature("beam_width_mm", 200, "mm", "GEOMETRY", "B_WIDTH_FAIL")},
        ),
        _snapshot(
            "beam",
            "B_RATIO_FAIL",
            {"story": "+14.5", "section": "B30x120"},
            {
                "beam_width_mm": _feature("beam_width_mm", 300, "mm", "GEOMETRY", "B_RATIO_FAIL"),
                "beam_depth_mm": _feature("beam_depth_mm", 1200, "mm", "GEOMETRY", "B_RATIO_FAIL"),
            },
        ),
        _snapshot(
            "story",
            "S_DRIFT_FAIL",
            {"story": "+14.5"},
            {"story_drift_value": _feature("story_drift_value", 1.20, "ratio", "DRIFT", "S_DRIFT_FAIL")},
        ),
        _snapshot(
            "global",
            "GLOBAL_MODAL_OK",
            {"component": "global"},
            {"modal_sum_ux": _feature("modal_sum_ux", 0.95, "ratio", "MODAL", "GLOBAL_MODAL_OK")},
        ),
        _snapshot(
            "beam",
            "B_MISSING",
            {"story": "+14.5", "section": "B30x60"},
            {},
        ),
        _snapshot(
            "beam",
            "B_PARTIAL",
            {"story": "+14.5", "section": "B30x60"},
            {"beam_width_mm": _feature("beam_width_mm", 300, "mm", "GEOMETRY", "B_PARTIAL")},
        ),
    ]

    coverage_rows: list[CoverageRow] = [
        _coverage(check_id="beam_geometry_min_width", component_type="beam", component_id="B_OK", required_features=["beam_width_mm"]),
        _coverage(check_id="beam_geometry_min_width", component_type="beam", component_id="B_WIDTH_FAIL", required_features=["beam_width_mm"]),
        _coverage(check_id="beam_depth_width_ratio", component_type="beam", component_id="B_RATIO_FAIL", required_features=["beam_depth_mm", "beam_width_mm"]),
        _coverage(check_id="story_drift_ratio", component_type="story", component_id="S_DRIFT_FAIL", required_features=["story_drift_value"]),
        _coverage(check_id="modal_mass_sumux_ge_threshold", component_type="global", component_id="GLOBAL_MODAL_OK", required_features=["modal_sum_ux"]),
        _coverage(
            check_id="required_feature_missing_no_data",
            component_type="beam",
            component_id="B_MISSING",
            required_features=["missing_artificial_feature"],
            resolved_features=[],
            missing_features=[CoverageMissingFeature("missing_artificial_feature", "intentionally absent in C7 golden fixture")],
            coverage_status="BLOCKED",
            evidence_status="MISSING",
            reason="Required artificial feature is intentionally absent",
            expected_sources={"missing_artificial_feature": _source("missing_artificial_feature", "")},
            expected_evidence={"missing_artificial_feature": list(EVIDENCE_FIELDS)},
        ),
        _coverage(
            check_id="beam_geometry_min_width",
            component_type="beam",
            component_id="B_PARTIAL",
            required_features=["beam_width_mm"],
            resolved_features=["beam_width_mm"],
            coverage_status="PARTIAL",
            evidence_status="PARTIAL",
            reason="Artificial partial coverage path for C7 warning proof",
            expected_evidence={"beam_width_mm": list(EVIDENCE_FIELDS)},
        ),
    ]
    coverage = CoverageMatrix(coverage_rows)

    by_component = {snapshot.component_id: snapshot for snapshot in snapshots}
    results = [
        engine.run_check(row.check_id, by_component[row.component_id], row).as_dict()
        for row in coverage_rows
    ]
    results.sort(key=lambda item: (item["component_type"], item["component"], item["check_id"]))
    return snapshots, coverage, results


def _jsonable(value: Any) -> Any:
    if isinstance(value, (MappingProxyType, AbcMapping)):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def build_golden_documents() -> dict[str, Any]:
    snapshots, coverage, results = build_c7_artificial_chain()
    snapshot_doc = OrderedDict(
        [
            ("contract_version", "1.0"),
            ("source", "C7 artificial fixture only"),
            ("snapshots", [_jsonable(snapshot.as_dict()) for snapshot in sorted(snapshots, key=lambda s: (s.component_type, s.component_id))]),
        ]
    )
    coverage_doc = coverage.as_schema_document(
        {
            "required_feature_missing_no_data": "missing_features",
            "beam_geometry_min_width": "partial",
        }
    )
    results_doc = OrderedDict(
        [
            ("contract_version", "1.0"),
            ("source", "C7 artificial fixture only"),
            ("check_results", _jsonable(results)),
        ]
    )
    return {
        "feature_snapshot": _jsonable(snapshot_doc),
        "coverage_matrix": _jsonable(coverage_doc),
        "check_results": _jsonable(results_doc),
    }
