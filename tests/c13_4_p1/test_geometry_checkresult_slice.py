from __future__ import annotations

from pathlib import Path

import yaml

from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.result import CheckResult
from tbdy_engine.coverage.models import CoverageRow, CoverageStatus
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus

ROOT = Path(__file__).resolve().parents[2]


def _defs():
    return yaml.safe_load((ROOT / "tbdy_engine/catalogs/check_catalog.yaml").read_text(encoding="utf-8"))["checks"]


def _feature(name: str, value: float) -> FeatureValue:
    evidence = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table="fixture",
        actual_table_name="fixture",
        source_column=name,
        source_row={"component": "fixture"},
        raw_value=value,
        normalized_value=value,
        unit="mm",
        resolver="test_fixture",
    )
    return FeatureValue(feature_name=name, value=value, unit="mm", semantic_role="GEOMETRY", status=FeatureValueStatus.RESOLVED, evidence=(evidence,))


def _snapshot(component_type: str, component_id: str, **features: float) -> FeatureSnapshot:
    return FeatureSnapshot(
        component_type=component_type,
        component_id=component_id,
        identity={"story": "+14.5", "section": "TEST"},
        features={name: _feature(name, value) for name, value in features.items()},
    )


def _coverage(check_id: str, component_type: str, component_id: str, required: tuple[str, ...]) -> CoverageRow:
    return CoverageRow(
        check_id=check_id,
        component_type=component_type,
        component_id=component_id,
        required_features=required,
        resolved_features=required,
        coverage_status=CoverageStatus.RUNNABLE,
    )


def _run(check_id: str, snapshot: FeatureSnapshot, required: tuple[str, ...]) -> CheckResult:
    coverage = _coverage(check_id, snapshot.component_type, snapshot.component_id, required)
    result = MinimalCheckEngine(_defs()).run_check(check_id, snapshot, coverage)
    assert isinstance(result, CheckResult)
    return result


def test_column_geometry_min_dimension_ok_for_800_by_800():
    result = _run(
        "column_geometry_min_dimension",
        _snapshot("column", "C1", column_width_mm=800, column_depth_mm=800),
        ("column_width_mm", "column_depth_mm"),
    )
    assert result.status == "OK"
    assert result.value == 800
    assert result.limit == 300
    assert result.ratio_type == "actual_over_minimum"


def test_column_geometry_min_dimension_fails_for_250_by_800():
    result = _run(
        "column_geometry_min_dimension",
        _snapshot("column", "C1", column_width_mm=250, column_depth_mm=800),
        ("column_width_mm", "column_depth_mm"),
    )
    assert result.status == "FAIL"
    assert result.value == 250
    assert result.limit == 300


def test_beam_geometry_min_width_ok_for_400():
    result = _run("beam_geometry_min_width", _snapshot("beam", "B1", beam_width_mm=400), ("beam_width_mm",))
    assert result.status == "OK"
    assert result.value == 400
    assert result.limit == 250


def test_beam_geometry_min_width_fails_for_200():
    result = _run("beam_geometry_min_width", _snapshot("beam", "B1", beam_width_mm=200), ("beam_width_mm",))
    assert result.status == "FAIL"
    assert result.value == 200
    assert result.limit == 250


def test_beam_geometry_min_depth_ok_for_700():
    result = _run("beam_geometry_min_depth", _snapshot("beam", "B1", beam_depth_mm=700), ("beam_depth_mm",))
    assert result.status == "OK"
    assert result.value == 700
    assert result.limit == 300


def test_beam_depth_width_ratio_ok_for_700_over_400():
    result = _run("beam_depth_width_ratio", _snapshot("beam", "B1", beam_depth_mm=700, beam_width_mm=400), ("beam_depth_mm", "beam_width_mm"))
    assert result.status == "OK"
    assert result.value == 1.75
    assert result.limit == 3.5
    assert result.ratio_type == "value_over_maximum"


def test_beam_depth_width_ratio_fails_above_3_5():
    result = _run("beam_depth_width_ratio", _snapshot("beam", "B1", beam_depth_mm=1000, beam_width_mm=250), ("beam_depth_mm", "beam_width_mm"))
    assert result.status == "FAIL"
    assert result.value == 4.0
    assert result.limit == 3.5
