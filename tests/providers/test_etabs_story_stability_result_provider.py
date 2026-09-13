from types import SimpleNamespace

import pytest

import tbdy_engine.providers.etabs_story_stability_result_provider as provider
from tbdy_engine.etabs.oapi.story_drift_results import StoryDriftResultFact, StoryDriftResultRow
from tbdy_engine.etabs.safety import RuntimeCaptureStatus


class FakeSession:
    def __init__(self):
        self.run_analysis_calls = 0

    def RunAnalysis(self):
        self.run_analysis_calls += 1
        raise AssertionError("story stability factual provider must not call RunAnalysis")


class FakeTopology:
    def __init__(self, columns):
        self.columns = tuple(columns)


def _column(uid, *, story="Story1", bottom="B", top="T", i_is_bottom=True, z0=0.0, z1=3.5):
    connectivity = {
        "UniquePtI": bottom if i_is_bottom else top,
        "UniquePtJ": top if i_is_bottom else bottom,
    }
    return SimpleNamespace(
        unique_name=uid,
        story=story,
        joint_bottom=bottom,
        joint_top=top,
        bottom_coord_m=(0.0, 0.0, z0),
        top_coord_m=(0.0, 0.0, z1),
        connectivity_row=connectivity,
    )


def _fetch(rows, *, restored=True):
    return SimpleNamespace(
        capture_status=RuntimeCaptureStatus.FULL,
        parsed=SimpleNamespace(rows=tuple(rows), row_count_reported=len(rows)),
        state_diagnostics=(
            {"phase": "restore_verify", "success": restored},
        ),
    )


def _drift_fact(name="GQE_X"):
    return StoryDriftResultFact(
        output_name=name,
        output_kind="combo",
        rows=(
            StoryDriftResultRow("Story1", name, "", 0.0, "X", 0.0011, "P1", 0.0, 0.0, 3.5),
            StoryDriftResultRow("Story1", name, "", 0.0, "X", -0.0014, "P2", 5.0, 0.0, 3.5),
            StoryDriftResultRow("Story1", name, "", 0.0, "Y", 0.0007, "P3", 0.0, 5.0, 3.5),
        ),
        return_code=0,
    )


def _force_rows(name="GQE_X"):
    return (
        # C1 physical bottom is minimum Station: -100 kN compression.
        {"Story": "Story1", "UniqueName": "C1", "OutputCase": name, "Station": 0.0, "P": -100.0},
        {"Story": "Story1", "UniqueName": "C1", "OutputCase": name, "Station": 3.5, "P": -90.0},
        # C2 physical bottom is maximum Station because J is bottom: +20 kN tension.
        {"Story": "Story1", "UniqueName": "C2", "OutputCase": name, "Station": 0.0, "P": -40.0},
        {"Story": "Story1", "UniqueName": "C2", "OutputCase": name, "Station": 3.5, "P": 20.0},
        # Full B5 population also contains another story and must remain in the capture.
        {"Story": "Story2", "UniqueName": "C3", "OutputCase": name, "Station": 0.0, "P": -50.0},
    )


def _topology():
    return FakeTopology(
        (
            _column("C1", bottom="B1", top="T1", i_is_bottom=True),
            _column("C2", bottom="B2", top="T2", i_is_bottom=False),
            _column("C3", story="Story2", bottom="B3", top="T3", i_is_bottom=True, z0=3.5, z1=7.0),
        )
    )


def test_physical_bottom_station_and_signed_axial_sum():
    topology = _topology()
    story_rows = tuple(row for row in _force_rows() if row["Story"] == "Story1")
    total_n, refs = provider._sum_story_axial_compression_n(
        topology,
        story="Story1",
        force_rows=story_rows,
        force_unit="kN",
    )
    # C1: +100 kN compression; C2: -20 kN because the physical-bottom row is tensile.
    assert total_n == pytest.approx(80_000.0)
    assert any("C1:physical-bottom:P=-100" in ref for ref in refs)
    assert any("C2:physical-bottom:P=20" in ref for ref in refs)


def test_provider_retains_exact_b5_identity_combo_story_rows_and_full_population(monkeypatch):
    session = FakeSession()
    topology = _topology()
    story_force_rows = (
        {"Story": "Story1", "OutputCase": "GQE_X", "Location": "Top", "VX": -4.0, "VY": 1.0},
        # Orthogonal response is deliberately nonzero. Direction authority is external/source-bound.
        {"Story": "Story1", "OutputCase": "GQE_X", "Location": "Bottom", "VX": -50.0, "VY": 7.0},
        {"Story": "Story1", "OutputCase": "OTHER", "Location": "Bottom", "VX": -999.0, "VY": 0.0},
    )
    calls = {"story_forces": [], "drifts": [], "column_forces": []}

    def fetch_story_forces(_session, table_name, *, preferred_output_case, max_rows, timeout_seconds):
        calls["story_forces"].append((table_name, preferred_output_case, max_rows, timeout_seconds))
        return _fetch(story_force_rows, restored=True)

    def read_drifts(_session, *, output_name, output_kind, timeout_seconds):
        calls["drifts"].append((output_name, output_kind, timeout_seconds))
        return _drift_fact(output_name)

    def capture_column_forces(_session, *, case_name, expectation, timeout_seconds):
        calls["column_forces"].append(
            (case_name, expectation.expected_unique_names, expectation.source_row_count, timeout_seconds)
        )
        assert expectation.expected_unique_names == ("C1", "C2", "C3")
        assert expectation.source_row_count == 3
        return SimpleNamespace(rows=_force_rows(case_name), evidence_ref="B5:COLUMN_FORCE_POPULATION:GQE_X")

    monkeypatch.setattr(provider, "EtabsVerifiedSession", FakeSession)
    monkeypatch.setattr(provider, "StrictColumnTopologyBundle", FakeTopology)
    monkeypatch.setattr(provider, "fetch_display_table_for_output_from_session", fetch_story_forces)
    monkeypatch.setattr(provider, "read_story_drifts_from_session", read_drifts)
    monkeypatch.setattr(provider, "capture_column_force_result_population_from_session", capture_column_forces)

    fact = provider.capture_story_stability_combo_fact_from_session(
        session,
        output_name="GQE_X",
        story="Story1",
        global_direction="X",
        direction_source_refs=("DIR:EX:GLOBAL_X",),
        topology=topology,
        analysis_result_ref="ANALYSIS_RESULT:exact-b5",
        execution_proof_ref="RUN_ANALYSIS:proof",
        reviewed_force_unit="kN",
        timeout_seconds=9.0,
    )

    assert fact.analysis_result_ref == "ANALYSIS_RESULT:exact-b5"
    assert fact.execution_proof_ref == "RUN_ANALYSIS:proof"
    assert fact.output_name == "GQE_X"
    assert fact.output_kind == "combo"
    assert fact.story == "Story1"
    assert fact.global_direction == "X"
    assert fact.story_height_mm == pytest.approx(3500.0)
    assert fact.story_shear_n == pytest.approx(50_000.0)
    assert fact.sum_column_axial_design_force_n == pytest.approx(80_000.0)
    assert tuple(row.point_label for row in fact.story_drift_rows) == ("P1", "P2")
    assert fact.ts500_delta_d_mapping_status == provider.TS500_DELTA_D_MAPPING_NOT_PROVEN
    assert not hasattr(fact, "relative_story_displacement_mm")
    assert not hasattr(fact, "governing_drift_point_label")
    assert "ANALYSIS_RESULT:exact-b5" in fact.source_refs
    assert "RUN_ANALYSIS:proof" in fact.source_refs
    assert "DIR:EX:GLOBAL_X" in fact.source_refs
    assert "B5:COLUMN_FORCE_POPULATION:GQE_X" in fact.source_refs
    assert provider.TS500_DELTA_D_MAPPING_NOT_PROVEN in fact.source_refs
    assert calls["story_forces"] == [("Story Forces", "GQE_X", None, 9.0)]
    assert calls["drifts"] == [("GQE_X", "combo", 9.0)]
    assert calls["column_forces"][0][0] == "GQE_X"
    assert session.run_analysis_calls == 0


def test_provider_requires_story_force_output_selection_restoration(monkeypatch):
    session = FakeSession()
    topology = _topology()
    rows = ({"Story": "Story1", "OutputCase": "GQE_X", "Location": "Bottom", "VX": 50.0, "VY": 0.0},)

    monkeypatch.setattr(provider, "EtabsVerifiedSession", FakeSession)
    monkeypatch.setattr(provider, "StrictColumnTopologyBundle", FakeTopology)
    monkeypatch.setattr(
        provider,
        "fetch_display_table_for_output_from_session",
        lambda *_args, **_kwargs: _fetch(rows, restored=False),
    )

    with pytest.raises(provider.StoryStabilityResultProviderError, match="restoration did not verify"):
        provider.capture_story_stability_combo_fact_from_session(
            session,
            output_name="GQE_X",
            story="Story1",
            global_direction="X",
            direction_source_refs=("DIR:X",),
            topology=topology,
            analysis_result_ref="ANALYSIS_RESULT:exact-b5",
            execution_proof_ref="RUN_ANALYSIS:proof",
            reviewed_force_unit="kN",
        )
    assert session.run_analysis_calls == 0


def test_story_force_requires_exact_bottom_story_and_combo_identity():
    rows = (
        {"Story": "Story1", "OutputCase": "GQE_X", "Location": "Top", "VX": 10.0, "VY": 0.0},
        {"Story": "Story2", "OutputCase": "GQE_X", "Location": "Bottom", "VX": 20.0, "VY": 0.0},
        {"Story": "Story1", "OutputCase": "OTHER", "Location": "Bottom", "VX": 30.0, "VY": 0.0},
    )
    with pytest.raises(provider.StoryStabilityResultProviderError, match="exactly one Bottom row"):
        provider._story_shear_row(rows, output_name="GQE_X", story="Story1")
