from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.coverage.models import CoverageMissingFeature, CoverageRow
from tbdy_engine.features.snapshot import FeatureSnapshot


def _snap():
    return FeatureSnapshot(component_type="beam", component_id="B1", identity={}, features={})


def test_blocked_coverage_never_emits_ok():
    row = CoverageRow(
        check_id="beam_geometry_min_width",
        component_type="beam",
        component_id="B1",
        required_features=["beam_width_mm"],
        missing_features=[CoverageMissingFeature("beam_width_mm", "missing")],
        coverage_status="BLOCKED",
        evidence_status="MISSING",
        reason="missing feature",
        expected_evidence_requirements={"beam_width_mm": ["source_table"]},
    )
    result = MinimalCheckEngine({"beam_geometry_min_width": {"required_features": ["beam_width_mm"], "c6_allowed": True}}).run_check("beam_geometry_min_width", _snap(), row)
    assert result.status == "NO_DATA"


def test_partial_coverage_never_silent_ok():
    row = CoverageRow(
        check_id="beam_geometry_min_width",
        component_type="beam",
        component_id="B1",
        required_features=["beam_width_mm"],
        coverage_status="PARTIAL",
        evidence_status="PARTIAL",
        reason="partial evidence",
        expected_evidence_requirements={"beam_width_mm": ["source_table"]},
    )
    result = MinimalCheckEngine({"beam_geometry_min_width": {"required_features": ["beam_width_mm"], "c6_allowed": True}}).run_check("beam_geometry_min_width", _snap(), row)
    assert result.status == "WARNING"
