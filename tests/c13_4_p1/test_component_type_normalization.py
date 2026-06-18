from __future__ import annotations

from pathlib import Path

import yaml

from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.coverage.models import CoverageRow, CoverageStatus
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus

ROOT = Path(__file__).resolve().parents[2]


def _defs():
    return yaml.safe_load(
        (ROOT / "tbdy_engine/catalogs/check_catalog.yaml").read_text(encoding="utf-8")
    )["checks"]


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
    return FeatureValue(
        feature_name=name,
        value=value,
        unit="mm",
        semantic_role="GEOMETRY",
        status=FeatureValueStatus.RESOLVED,
        evidence=(evidence,),
    )


def _snapshot(component_type: str, component_id: str = "X1", **features: float) -> FeatureSnapshot:
    return FeatureSnapshot(
        component_type=component_type,
        component_id=component_id,
        identity={"story": "+14.5", "section": "TEST"},
        features={name: _feature(name, value) for name, value in features.items()},
    )


def _coverage(check_id: str, component_type: str, required: tuple[str, ...]) -> CoverageRow:
    return CoverageRow(
        check_id=check_id,
        component_type=component_type,
        component_id="X1",
        required_features=required,
        resolved_features=required,
        coverage_status=CoverageStatus.RUNNABLE,
    )


def test_uppercase_beam_component_type_runs_beam_geometry_check():
    result = MinimalCheckEngine(_defs()).run_check(
        "beam_geometry_min_width",
        _snapshot("BEAM", beam_width_mm=400),
        _coverage("beam_geometry_min_width", "beam", ("beam_width_mm",)),
    )

    assert result.status == CheckStatus.OK
    assert result.value == 400
    assert result.limit == 250


def test_uppercase_column_component_type_runs_column_geometry_check():
    result = MinimalCheckEngine(_defs()).run_check(
        "column_geometry_min_dimension",
        _snapshot("COLUMN", column_width_mm=800, column_depth_mm=800),
        _coverage("column_geometry_min_dimension", "column", ("column_width_mm", "column_depth_mm")),
    )

    assert result.status == CheckStatus.OK
    assert result.value == 800
    assert result.limit == 300


def test_real_component_type_mismatch_still_returns_out_of_scope():
    result = MinimalCheckEngine(_defs()).run_check(
        "beam_geometry_min_width",
        _snapshot("WALL", beam_width_mm=400),
        _coverage("beam_geometry_min_width", "beam", ("beam_width_mm",)),
    )

    assert result.status == CheckStatus.OUT_OF_SCOPE
