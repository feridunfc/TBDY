from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.coverage.models import CoverageRow
from tbdy_engine.features.evidence import FeatureEvidence
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue


def _evidence(name="beam_width_mm", value=300, unit="mm"):
    return FeatureEvidence(
        evidence_status="FULL",
        source_table="fixture",
        actual_table_name="fixture",
        source_column=name,
        raw_value=value,
        normalized_value=value,
        unit=unit,
    )


def _feature(name, value, unit="mm"):
    return FeatureValue(feature_name=name, value=value, unit=unit, semantic_role="GEOMETRY", status="RESOLVED", evidence=[_evidence(name, value, unit)])


def _snapshot(features=None, component_type="beam"):
    return FeatureSnapshot(
        component_type=component_type,
        component_id="B1",
        identity={"story": "+14.5", "section": "B30x60"},
        features=features
        or {
            "beam_width_mm": _feature("beam_width_mm", 300),
            "beam_depth_mm": _feature("beam_depth_mm", 600),
        },
    )


def _coverage(check_id="beam_geometry_min_width", status="RUNNABLE", required=None):
    required = required or ["beam_width_mm"]
    kwargs = {}
    if status != "RUNNABLE":
        kwargs["reason"] = "coverage gate"
        kwargs["expected_evidence_requirements"] = {required[0]: ["source_table"]}
    return CoverageRow(
        check_id=check_id,
        component_type="beam",
        component_id="B1",
        required_features=required,
        resolved_features=required if status == "RUNNABLE" else [],
        coverage_status=status,
        evidence_status="FULL" if status == "RUNNABLE" else "PARTIAL",
        **kwargs,
    )


def test_minimal_engine_runnable_ok_on_artificial_snapshot():
    engine = MinimalCheckEngine({"beam_geometry_min_width": {"required_features": ["beam_width_mm"], "minimum": 250, "unit": "mm", "c6_allowed": True}})
    result = engine.run_check("beam_geometry_min_width", _snapshot(), _coverage())
    assert result.status == "OK"
    assert result.ratio == 1.2


def test_minimal_engine_can_fail_artificial_snapshot():
    snap = _snapshot({"beam_width_mm": _feature("beam_width_mm", 200)})
    engine = MinimalCheckEngine({"beam_geometry_min_width": {"required_features": ["beam_width_mm"], "minimum": 250, "c6_allowed": True}})
    assert engine.run_check("beam_geometry_min_width", snap, _coverage()).status == "FAIL"


def test_beam_depth_width_ratio_fixture():
    engine = MinimalCheckEngine({"beam_depth_width_ratio": {"required_features": ["beam_depth_mm", "beam_width_mm"], "limit": 3.5, "c6_allowed": True}})
    coverage = _coverage("beam_depth_width_ratio", required=["beam_depth_mm", "beam_width_mm"])
    result = engine.run_check("beam_depth_width_ratio", _snapshot(), coverage)
    assert result.status == "OK"
    assert round(result.ratio, 3) == round(2.0 / 3.5, 3)
    assert result.ratio_type == "value_over_maximum"


def _story_engine():
    return MinimalCheckEngine({"story_drift_ratio": {"required_features": ["story_drift_value"], "limit": 1.0, "unit": "ratio", "c6_allowed": True}})


def _story_snapshot(value):
    return FeatureSnapshot(
        component_type="story",
        component_id="S1",
        identity={"story": "+14.5"},
        features={"story_drift_value": _feature("story_drift_value", value, "ratio")},
    )


def _story_coverage():
    return CoverageRow(
        check_id="story_drift_ratio",
        component_type="story",
        component_id="S1",
        required_features=["story_drift_value"],
        resolved_features=["story_drift_value"],
        coverage_status="RUNNABLE",
        evidence_status="FULL",
    )


def test_story_drift_ratio_below_limit_ok():
    result = _story_engine().run_check("story_drift_ratio", _story_snapshot(0.8), _story_coverage())
    assert result.status == "OK"
    assert result.ratio_type == "value_over_maximum"


def test_story_drift_ratio_equal_limit_ok():
    assert _story_engine().run_check("story_drift_ratio", _story_snapshot(1.0), _story_coverage()).status == "OK"


def test_story_drift_ratio_above_limit_fail():
    assert _story_engine().run_check("story_drift_ratio", _story_snapshot(1.2), _story_coverage()).status == "FAIL"


def test_story_drift_does_not_use_value_over_minimum():
    result = _story_engine().run_check("story_drift_ratio", _story_snapshot(0.8), _story_coverage())
    assert result.pass_rule != "value_over_minimum"
    assert result.ratio_type != "value_over_minimum"


def test_story_drift_does_not_silently_ok_when_above_limit():
    result = _story_engine().run_check("story_drift_ratio", _story_snapshot(1.2), _story_coverage())
    assert result.status == "FAIL"
    assert result.status != "OK"
