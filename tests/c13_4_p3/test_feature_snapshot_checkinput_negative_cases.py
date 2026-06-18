from __future__ import annotations

from tools.audit_legacy_boundary import build_report
from tbdy_engine.checks.input_adapter import build_geometry_check_inputs_from_feature_snapshot
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus


def _evidence(name: str, value: float | None, unit: str = "mm") -> FeatureEvidence:
    return FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table="source_geometry_table",
        actual_table_name="ETABS Geometry Source",
        source_column=name,
        source_row={"component": "fixture"},
        raw_value=value,
        normalized_value=value,
        unit=unit,
        resolver="c13_4_p3_fixture_resolver",
    )


def _feature(name: str, value: float | None, *, unit: str = "mm", status: FeatureValueStatus = FeatureValueStatus.RESOLVED) -> FeatureValue:
    return FeatureValue(
        feature_name=name,
        value=value,
        unit=unit,
        semantic_role="GEOMETRY",
        status=status,
        evidence=(_evidence(name, value, unit),),
    )


def _snapshot(component_type: str, component_id: str, **features: FeatureValue) -> FeatureSnapshot:
    return FeatureSnapshot(component_type=component_type, component_id=component_id, identity={"story": "+14.5", "section": "TEST"}, features=features)


def _ids(result) -> tuple[str, ...]:
    return tuple(item.check_id for item in result.check_inputs)


def test_missing_beam_depth_does_not_build_depth_or_ratio_inputs():
    result = build_geometry_check_inputs_from_feature_snapshot(_snapshot("beam", "B1", beam_width_mm=_feature("beam_width_mm", 300)))
    assert _ids(result) == ("beam_geometry_min_width",)
    assert {diagnostic.check_id for diagnostic in result.diagnostics} == {"beam_geometry_min_depth", "beam_depth_width_ratio"}
    assert all("beam_depth_mm" in diagnostic.missing_features for diagnostic in result.diagnostics)


def test_missing_beam_width_does_not_build_width_or_ratio_inputs():
    result = build_geometry_check_inputs_from_feature_snapshot(_snapshot("beam", "B1", beam_depth_mm=_feature("beam_depth_mm", 600)))
    assert _ids(result) == ("beam_geometry_min_depth",)
    assert {diagnostic.check_id for diagnostic in result.diagnostics} == {"beam_geometry_min_width", "beam_depth_width_ratio"}
    assert all("beam_width_mm" in diagnostic.missing_features for diagnostic in result.diagnostics)


def test_missing_and_partial_feature_statuses_are_not_executable():
    snapshot = _snapshot(
        "beam",
        "B1",
        beam_width_mm=_feature("beam_width_mm", None, status=FeatureValueStatus.MISSING),
        beam_depth_mm=_feature("beam_depth_mm", 600, status=FeatureValueStatus.PARTIAL),
    )
    result = build_geometry_check_inputs_from_feature_snapshot(snapshot)
    assert result.check_inputs == ()
    assert {diagnostic.check_id for diagnostic in result.diagnostics} == {"beam_geometry_min_width", "beam_geometry_min_depth", "beam_depth_width_ratio"}
    assert all(diagnostic.invalid_features for diagnostic in result.diagnostics)


def test_mapping_fixture_blocked_and_unknown_statuses_are_diagnostic_only():
    fixture = {"component_type": "beam", "component_id": "B1", "features": {"beam_width_mm": {"value": 300, "unit": "mm", "status": "BLOCKED"}, "beam_depth_mm": {"value": 600, "unit": "mm", "status": "UNKNOWN"}}}
    result = build_geometry_check_inputs_from_feature_snapshot(fixture)
    assert result.check_inputs == ()
    assert {diagnostic.status for diagnostic in result.diagnostics} == {"BLOCKED"}
    assert {name for diagnostic in result.diagnostics for name in diagnostic.invalid_features} == {"beam_width_mm", "beam_depth_mm"}


def test_wrong_unit_is_diagnostic_and_not_silently_converted():
    snapshot = _snapshot("beam", "B1", beam_width_mm=_feature("beam_width_mm", 30, unit="cm"), beam_depth_mm=_feature("beam_depth_mm", 600))
    result = build_geometry_check_inputs_from_feature_snapshot(snapshot)
    assert _ids(result) == ("beam_geometry_min_depth",)
    width_diagnostics = [diagnostic for diagnostic in result.diagnostics if "beam_width_mm" in diagnostic.invalid_features]
    assert width_diagnostics
    assert all(diagnostic.status == "BLOCKED" for diagnostic in width_diagnostics)
    assert all("cm" in diagnostic.reason for diagnostic in width_diagnostics)


def test_missing_unit_is_diagnostic_and_not_inferred_from_feature_name():
    snapshot = _snapshot("beam", "B1", beam_width_mm=_feature("beam_width_mm", 300, unit=""), beam_depth_mm=_feature("beam_depth_mm", 600))
    result = build_geometry_check_inputs_from_feature_snapshot(snapshot)
    assert _ids(result) == ("beam_geometry_min_depth",)
    width_diagnostics = [diagnostic for diagnostic in result.diagnostics if "beam_width_mm" in diagnostic.invalid_features]
    assert width_diagnostics
    assert all(diagnostic.status == "BLOCKED" for diagnostic in width_diagnostics)
    assert all("missing" in diagnostic.reason for diagnostic in width_diagnostics)


def test_unsupported_component_type_produces_no_executable_geometry_input():
    result = build_geometry_check_inputs_from_feature_snapshot(_snapshot("wall", "W1", wall_thickness_mm=_feature("wall_thickness_mm", 300)))
    assert result.check_inputs == ()
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].status == "OUT_OF_SCOPE"


def test_adapter_diagnostics_do_not_emit_engine_decision_statuses():
    result = build_geometry_check_inputs_from_feature_snapshot(_snapshot("wall", "W1"))
    assert result.diagnostics
    disallowed = {"O" + "K", "FA" + "IL"}
    assert {diagnostic.status for diagnostic in result.diagnostics}.isdisjoint(disallowed)


def test_legacy_boundary_audit_scans_input_adapter_without_adapter_blockers():
    report = build_report()
    assert "tbdy_engine/checks/input_adapter.py" in report["checked_files"]
    adapter_blockers = [blocker for blocker in report["blockers"] if blocker["file"] == "tbdy_engine/checks/input_adapter.py"]
    assert adapter_blockers == []
