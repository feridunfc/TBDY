import inspect

import tools.probe_vs6_ts500_slenderness_sources as probe


def test_slenderness_source_probe_is_read_only_and_factual_only():
    source = inspect.getsource(probe)
    for forbidden in (
        "RunAnalysis(",
        "StartDesign(",
        "SetPresentUnits(",
        ".Save(",
        "SetRebarColumn(",
        "SetSection(",
        "resolve_ts500_column_slenderness_basis(",
        "evaluate_ts500_column_slenderness(",
        "ENGINE_SELECTED_REBAR",
    ):
        assert forbidden not in source

    assert '"regulatory_ln_promoted": False' in source
    assert '"sway_classification_promoted": False' in source
    assert '"engineering_calculation_performed": False' in source
    assert '"compliance_verdict_emitted": False' in source


def test_slenderness_source_probe_requests_support_and_sway_candidate_sources():
    assert "Joint Assignments - Restraints" in probe.SUPPORT_SOURCE_TABLE_CANDIDATES
    assert "Story Definitions" in probe.SWAY_SOURCE_TABLE_CANDIDATES
    assert "Story Drifts" in probe.SWAY_SOURCE_TABLE_CANDIDATES
    assert "Story Forces" in probe.SWAY_SOURCE_TABLE_CANDIDATES
    assert "Story Stiffness" in probe.SWAY_SOURCE_TABLE_CANDIDATES
    assert "Load Case Definitions - Summary" in probe.SWAY_SOURCE_TABLE_CANDIDATES


def test_slenderness_source_probe_captures_endpoint_restraint_api_without_promoting_it():
    class PointObj:
        def GetRestraint(self, name):
            return ([True, True, True, True, True, True], 0)

    result = probe._point_restraint_probe(PointObj(), "956")
    assert result["status"] == "RAW_CAPTURED"
    assert result["point"] == "956"
    assert result["regulatory_lateral_support_promoted"] is False
    assert result["raw_get_restraint"] == [[True, True, True, True, True, True], 0]
