from __future__ import annotations

from dataclasses import is_dataclass
from pathlib import Path

import yaml

from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.input_adapter import (
    CheckInputBuildResult,
    GeometryCheckInput,
    build_geometry_check_inputs_from_feature_snapshot,
)
from tbdy_engine.checks.result import CheckResult
from tbdy_engine.coverage.models import (
    CoverageEvidenceStatus,
    CoveragePolicyStatus,
    CoverageStatus,
)
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus

ROOT = Path(__file__).resolve().parents[2]
BASE_CHECK_CATALOG = ROOT / "tbdy_engine/catalogs/check_catalog.yaml"
C13_5_CHECK_OVERLAY = ROOT / "tbdy_engine/catalogs/check_catalog_c13_5_p1_column_geometry.yaml"


def _defs():
    definitions = yaml.safe_load(BASE_CHECK_CATALOG.read_text(encoding="utf-8"))["checks"]
    definitions.update(yaml.safe_load(C13_5_CHECK_OVERLAY.read_text(encoding="utf-8"))["checks"])
    return definitions


def _evidence(name: str, value: float, unit: str = "mm") -> FeatureEvidence:
    return FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table="source_geometry_table",
        actual_table_name="ETABS Geometry Source",
        source_column=name,
        source_row={"component": "fixture", "feature": name},
        raw_value=value,
        normalized_value=value,
        unit=unit,
        resolver="c13_4_p3_fixture_resolver",
    )


def _feature(
    name: str,
    value: float,
    *,
    unit: str = "mm",
    status: FeatureValueStatus = FeatureValueStatus.RESOLVED,
) -> FeatureValue:
    return FeatureValue(
        feature_name=name,
        value=value,
        unit=unit,
        semantic_role="GEOMETRY",
        status=status,
        evidence=(_evidence(name, value, unit),),
    )


def _snapshot(component_type: str, component_id: str, **features: FeatureValue) -> FeatureSnapshot:
    return FeatureSnapshot(
        component_type=component_type,
        component_id=component_id,
        identity={"story": "+14.5", "section": "TEST"},
        features=features,
    )


def _ids(result: CheckInputBuildResult) -> tuple[str, ...]:
    return tuple(item.check_id for item in result.check_inputs)


def test_beam_snapshot_with_resolved_mm_geometry_builds_three_inputs():
    snapshot = _snapshot(
        "beam",
        "B1",
        beam_width_mm=_feature("beam_width_mm", 300),
        beam_depth_mm=_feature("beam_depth_mm", 600),
    )

    result = build_geometry_check_inputs_from_feature_snapshot(snapshot)

    assert isinstance(result, CheckInputBuildResult)
    assert _ids(result) == (
        "beam_geometry_min_width",
        "beam_geometry_min_depth",
        "beam_depth_width_ratio",
    )
    assert result.diagnostics == ()
    for item in result.check_inputs:
        assert isinstance(item, GeometryCheckInput)
        assert item.component_id == "B1"
        assert item.component_type == "beam"
        assert item.story == "+14.5"
        assert item.section == "TEST"
        assert item.coverage.coverage_status == CoverageStatus.RUNNABLE
        assert item.coverage.required_features == item.required_features
        assert item.coverage.resolved_features == item.required_features
        assert item.coverage.missing_features == ()
        assert item.coverage.combo_policy_status == CoveragePolicyStatus.NOT_APPLICABLE
        assert item.coverage.section_state_status == CoveragePolicyStatus.NOT_APPLICABLE
        assert item.coverage.ductility_context_status == CoveragePolicyStatus.NOT_APPLICABLE
        assert item.coverage.evidence_status == CoverageEvidenceStatus.FULL


def test_column_snapshot_with_resolved_mm_geometry_builds_three_inputs():
    snapshot = _snapshot(
        "column",
        "C1",
        column_width_mm=_feature("column_width_mm", 400),
        column_depth_mm=_feature("column_depth_mm", 500),
    )

    result = build_geometry_check_inputs_from_feature_snapshot(snapshot)

    assert _ids(result) == (
        "column_geometry_min_dimension",
        "column_geometry_min_width",
        "column_geometry_min_depth",
    )
    assert result.diagnostics == ()
    required_by_check = {item.check_id: item.required_features for item in result.check_inputs}
    assert required_by_check == {
        "column_geometry_min_dimension": ("column_width_mm", "column_depth_mm"),
        "column_geometry_min_width": ("column_width_mm",),
        "column_geometry_min_depth": ("column_depth_mm",),
    }
    assert all(item.coverage.coverage_status == CoverageStatus.RUNNABLE for item in result.check_inputs)


def test_adapter_output_is_typed_dataclass_not_plain_payload():
    snapshot = _snapshot(
        "beam",
        "B1",
        beam_width_mm=_feature("beam_width_mm", 300),
        beam_depth_mm=_feature("beam_depth_mm", 600),
    )

    result = build_geometry_check_inputs_from_feature_snapshot(snapshot)

    assert is_dataclass(result)
    assert not isinstance(result, dict)
    assert isinstance(result.check_inputs, tuple)
    assert all(is_dataclass(item) for item in result.check_inputs)
    assert all(not isinstance(item, dict) for item in result.check_inputs)
    assert all(not isinstance(item, tuple) for item in result.check_inputs)


def test_adapter_preserves_feature_evidence_on_inputs():
    snapshot = _snapshot(
        "beam",
        "B1",
        beam_width_mm=_feature("beam_width_mm", 300),
        beam_depth_mm=_feature("beam_depth_mm", 600),
    )

    result = build_geometry_check_inputs_from_feature_snapshot(snapshot)
    ratio_input = next(item for item in result.check_inputs if item.check_id == "beam_depth_width_ratio")

    width_evidence = ratio_input.evidence_by_feature["beam_width_mm"][0]
    depth_evidence = ratio_input.evidence_by_feature["beam_depth_mm"][0]
    assert width_evidence.source_table == "source_geometry_table"
    assert width_evidence.source_column == "beam_width_mm"
    assert width_evidence.raw_value == 300
    assert width_evidence.normalized_value == 300
    assert width_evidence.unit == "mm"
    assert depth_evidence.source_column == "beam_depth_mm"
    assert depth_evidence.raw_value == 600


def test_beam_adapter_inputs_run_through_minimal_engine_and_preserve_evidence_trace():
    snapshot = _snapshot(
        "beam",
        "B1",
        beam_width_mm=_feature("beam_width_mm", 300),
        beam_depth_mm=_feature("beam_depth_mm", 600),
    )
    adapter_result = build_geometry_check_inputs_from_feature_snapshot(snapshot)
    engine = MinimalCheckEngine(_defs())

    results = [engine.run_check(item.check_id, item.snapshot, item.coverage) for item in adapter_result.check_inputs]

    assert len(results) == 3
    assert all(isinstance(item, CheckResult) for item in results)
    assert all(not hasattr(item, "status") for item in adapter_result.check_inputs)
    for check_result in results:
        assert check_result.check_id in _ids(adapter_result)
        assert check_result.evidence
        evidence = check_result.evidence[0]
        assert evidence["source_table"] == "source_geometry_table"
        assert evidence["source_column"] in check_result.check_id or evidence["source_column"] in {
            "beam_width_mm",
            "beam_depth_mm",
        }
        assert evidence["raw_value"] in {300, 600}
        assert evidence["normalized_value"] in {300, 600}
        assert evidence["unit"] == "mm"


def test_column_adapter_inputs_run_through_minimal_engine_and_preserve_evidence_trace():
    snapshot = _snapshot(
        "column",
        "C1",
        column_width_mm=_feature("column_width_mm", 400),
        column_depth_mm=_feature("column_depth_mm", 500),
    )
    adapter_result = build_geometry_check_inputs_from_feature_snapshot(snapshot)
    engine = MinimalCheckEngine(_defs())

    results = [engine.run_check(item.check_id, item.snapshot, item.coverage) for item in adapter_result.check_inputs]

    assert len(results) == 3
    assert all(isinstance(item, CheckResult) for item in results)
    assert {item.check_id for item in results} == {
        "column_geometry_min_dimension",
        "column_geometry_min_width",
        "column_geometry_min_depth",
    }
    dimension_result = next(item for item in results if item.check_id == "column_geometry_min_dimension")
    assert dimension_result.evidence
    evidence_payloads = list(dimension_result.evidence)
    assert {item["source_column"] for item in evidence_payloads} == {"column_width_mm", "column_depth_mm"}
    assert {item["raw_value"] for item in evidence_payloads} == {400, 500}
    assert {item["normalized_value"] for item in evidence_payloads} == {400, 500}
    assert {item["unit"] for item in evidence_payloads} == {"mm"}
