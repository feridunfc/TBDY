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
        "evaluate_ts500_story_stability_index(",
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


def test_probe_reads_ln_status_from_canonical_topology_projection():
    source = inspect.getsource(probe)
    assert "column_projection = column.as_dict()" in source
    assert 'column_projection["regulatory_ln_status"]' in source
    assert "column.regulatory_ln_status" not in source


def test_selected_story_projection_is_exact_and_does_not_infer_quantity_semantics():
    rows = (
        {"Story": "+0.00", "OutputCase": "A", "Drift": "0.001"},
        {"Story": "+3.20", "OutputCase": "A", "Drift": "0.002"},
        {"Story": "+0.00", "OutputCase": "B", "Drift": "0.003"},
    )
    selected = probe._selected_story_rows(rows, "+0.00")
    assert selected == [
        {"Story": "+0.00", "OutputCase": "A", "Drift": "0.001"},
        {"Story": "+0.00", "OutputCase": "B", "Drift": "0.003"},
    ]
    source = inspect.getsource(probe)
    assert "No ETABS quantity is interpreted as Delta_i, V_fi or sum(N_di) here" in source
