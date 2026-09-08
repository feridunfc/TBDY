from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

import tbdy_engine.regulatory.column_transverse_confinement as subject
from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.regulatory.sources.fnd_col_1_longitudinal import (
    SOURCE_DATA,
    TBDY_SOURCE_ID,
    TS500_SOURCE_ID,
)


def _arrangement():
    return subject.SpecialTieDetailingFacts(
        hoop_both_ends_135_hooks=True,
        min_inner_bend_diameter_mm=40.0,
        min_hook_tail_length_mm=80.0,
        hoops_enclose_longitudinal_bars=True,
        hooks_close_around_longitudinal_bar=True,
        cross_tie_present=True,
        cross_tie_diameter_mm=8.0,
        cross_tie_spacing_mm=100.0,
        cross_tie_ends_wrap_longitudinal_and_hoop=True,
        source_refs=("DETAILING:reviewed",),
    )


def _direction(name: str, ash: float, *, asw: float = 200.0, mapping=True, ve=200.0):
    return subject.TransverseDirectionFacts(
        direction=name,
        confined_core_width_bk_mm=420.0 if name == "DIR2" else 720.0,
        provided_ash_mm2=ash,
        horizontal_leg_spacing_mm=200.0,
        source_refs=(f"{name}:fact",),
        provided_asw_mm2=asw,
        effective_depth_mm=450.0,
        shear_mapping_proven=mapping,
        qualified_vc_kn=100.0,
        p7_ve_kn=ve,
    )


def _request(**changes):
    base = subject.ColumnTransverseConfinementInput(
        component_id="Story1:C1:10",
        story="Story1",
        section="C50x80",
        high_ductility_applies=True,
        limited_ductility_applies=False,
        ts500_general_applies=True,
        cantilever_column=False,
        clear_height_mm=3000.0,
        width_mm=500.0,
        depth_mm=800.0,
        gross_area_ac_mm2=400000.0,
        confined_core_area_ack_mm2=300000.0,
        fck_mpa=30.0,
        fywk_mpa=420.0,
        axial_design_force_nd_n=1000000.0,
        transverse_diameter_mm=8.0,
        confinement_spacing_mm=100.0,
        middle_spacing_mm=150.0,
        provided_confinement_region_length_mm=1200.0,
        directions=(
            _direction("DIR2", 1000.0),
            _direction("DIR3", 1000.0),
        ),
        arrangement=_arrangement(),
        restrained_longitudinal_bar_spacing_mm=250.0,
        fywd_mpa=365.0,
        shear_spacing_mm=100.0,
        model_fingerprint="model:1",
        evidence_epoch_id="epoch:1",
        design_result_ref="design-result:1",
        source_refs=("GEOMETRY:exact", "MATERIAL:exact", "DEMAND:exact", "P7:exact"),
    )
    return replace(base, **changes)


def _by_id(result, check_id):
    return next(item for item in result.checks if item.check_id == check_id)


def _patch_selected_phi(monkeypatch, value=20.0):
    monkeypatch.setattr(
        subject,
        "_selected_longitudinal_diameter",
        lambda _selected, _component: value,
    )


def test_high_ductility_full_supported_facts_execute_deterministically(monkeypatch):
    _patch_selected_phi(monkeypatch)
    one = subject.evaluate_column_transverse_confinement(_request(), selected_rebar=object())
    two = subject.evaluate_column_transverse_confinement(_request(), selected_rebar=object())
    assert one == two
    assert one.complete is True
    assert one.failed is False
    assert one.ductility is subject.ColumnDuctility.HIGH
    assert one.required_confinement_region_length_mm == pytest.approx(1200.0)
    assert one.confinement_spacing_limit_mm == pytest.approx(120.0)
    assert one.middle_spacing_limit_mm == pytest.approx(200.0)
    assert dict(one.shear_vr_by_direction_kn)["DIR2"] == pytest.approx(428.5)
    assert all(item.status in {CheckStatus.OK, CheckStatus.OUT_OF_SCOPE} for item in one.checks)


def test_hd_false_does_not_make_the_whole_transverse_universe_out_of_scope(monkeypatch):
    _patch_selected_phi(monkeypatch)
    result = subject.evaluate_column_transverse_confinement(
        _request(high_ductility_applies=False, limited_ductility_applies=True),
        selected_rebar=object(),
    )
    assert result.applicable is True
    assert result.ductility is subject.ColumnDuctility.LIMITED
    assert _by_id(result, "COL_HD_CONFINEMENT_APPLICABILITY").status is CheckStatus.OUT_OF_SCOPE
    assert _by_id(result, "COL_LD_CONFINEMENT_SPACING").status is CheckStatus.OK
    assert _by_id(result, "COL_TS500_TRANSVERSE_SPACING").status is CheckStatus.OK


def test_hd_and_ld_false_still_executes_ts500_general_family(monkeypatch):
    _patch_selected_phi(monkeypatch)
    result = subject.evaluate_column_transverse_confinement(
        _request(high_ductility_applies=False, limited_ductility_applies=False),
        selected_rebar=object(),
    )
    assert result.applicable is True
    assert result.ductility is None
    assert _by_id(result, "COL_TS500_TRANSVERSE_DIAMETER").status is CheckStatus.OK
    assert _by_id(result, "COL_TS500_RESTRAINED_BAR_SPACING").status is CheckStatus.OK


def test_unknown_limited_branch_blocks_instead_of_treating_hd_false_as_total_out_of_scope(monkeypatch):
    _patch_selected_phi(monkeypatch)
    result = subject.evaluate_column_transverse_confinement(
        _request(high_ductility_applies=False, limited_ductility_applies=None),
        selected_rebar=object(),
    )
    assert "LIMITED_DUCTILITY_APPLICABILITY_NOT_PROVEN" in result.blockers
    assert _by_id(result, "COL_LD_CONFINEMENT_APPLICABILITY").status is CheckStatus.BLOCKED
    assert _by_id(result, "COL_TS500_TRANSVERSE_SPACING").status is CheckStatus.OK


def test_limited_confinement_does_not_import_hd_50mm_lower_spacing_bound(monkeypatch):
    _patch_selected_phi(monkeypatch)
    result = subject.evaluate_column_transverse_confinement(
        _request(
            high_ductility_applies=False,
            limited_ductility_applies=True,
            confinement_spacing_mm=40.0,
            arrangement=replace(_arrangement(), cross_tie_spacing_mm=40.0),
            shear_spacing_mm=40.0,
        ),
        selected_rebar=object(),
    )
    assert _by_id(result, "COL_LD_CONFINEMENT_SPACING").status is CheckStatus.OK


def test_ash_and_asw_remain_distinct_physical_quantities(monkeypatch):
    _patch_selected_phi(monkeypatch)
    # Huge Ash closes confinement, while tiny Asw fails final shear. If the two
    # quantities were collapsed this test could not express the failure.
    directions = (
        _direction("DIR2", 5000.0, asw=1.0, ve=300.0),
        _direction("DIR3", 5000.0, asw=1.0, ve=300.0),
    )
    result = subject.evaluate_column_transverse_confinement(
        _request(directions=directions),
        selected_rebar=object(),
    )
    assert _by_id(result, "COL_HD_CONFINEMENT_ASH_DIR2").status is CheckStatus.OK
    assert _by_id(result, "COL_FINAL_SHEAR_VR_DIR2").status is CheckStatus.FAIL


def test_unproven_rectangular_column_asw_direction_mapping_blocks_vr(monkeypatch):
    _patch_selected_phi(monkeypatch)
    directions = (
        _direction("DIR2", 1000.0, mapping=None),
        _direction("DIR3", 1000.0, mapping=False),
    )
    result = subject.evaluate_column_transverse_confinement(
        _request(directions=directions),
        selected_rebar=object(),
    )
    assert _by_id(result, "COL_FINAL_SHEAR_VR_DIR2").status is CheckStatus.BLOCKED
    assert _by_id(result, "COL_FINAL_SHEAR_VR_DIR3").status is CheckStatus.BLOCKED
    assert any("TS500_COLUMN_BW_D_ASW_DIRECTION_MAPPING_NOT_PROVEN" in item for item in result.blockers)


def test_missing_engine_selected_rebar_blocks_every_dependent_family():
    result = subject.evaluate_column_transverse_confinement(_request(), selected_rebar=None)
    assert "ENGINE_SELECTED_REBAR_REQUIRED_FOR_HD_SPACING" in result.blockers
    assert "ENGINE_SELECTED_REBAR_REQUIRED_FOR_TS500_TRANSVERSE" in result.blockers
    assert _by_id(result, "COL_HD_CONFINEMENT_REGION_LENGTH").status is CheckStatus.OK


def test_canonical_regulatory_source_ids_and_fingerprints_are_reused():
    assert subject.TBDY_2018_SOURCE_FINGERPRINT == SOURCE_DATA[TBDY_SOURCE_ID][4].removeprefix("sha256:")
    assert subject.TS500_SOURCE_FINGERPRINT == SOURCE_DATA[TS500_SOURCE_ID][4].removeprefix("sha256:")
    assert all(value.startswith("sha256:") for value in subject.CLAIM_REFS.values())
    result_refs = subject.evaluate_column_transverse_confinement(
        _request(high_ductility_applies=False, limited_ductility_applies=False),
        selected_rebar=None,
    ).source_refs
    assert any(TBDY_SOURCE_ID in ref for ref in result_refs)
    assert any(TS500_SOURCE_ID in ref for ref in result_refs)


def test_bound_production_evaluator_fails_closed_on_model_epoch_or_design_result_mismatch(monkeypatch):
    class FakeSelected:
        authority = subject.ENGINE_SELECTED_REBAR_AUTHORITY
        component_id = "Story1:C1:10"
        model_fingerprint = "wrong-model"
        evidence_epoch_id = "epoch:1"
        candidate_id = "candidate:1"
        selected_candidate = SimpleNamespace(candidate_id="candidate:1", bar_diameter_mm=20.0)

    class FakeLineage:
        qualified = True
        design_state = SimpleNamespace(model_fingerprint="model:1", evidence_epoch_id="epoch:1")
        def require_qualified_result(self):
            return SimpleNamespace(identity_ref="design-result:1")

    monkeypatch.setattr(subject, "CanonicalEngineSelectedRebar", FakeSelected)
    monkeypatch.setattr(subject, "DesignLineageQualification", FakeLineage)
    with pytest.raises(subject.ColumnTransverseConfinementError, match="model"):
        subject.evaluate_column_transverse_confinement_bound(
            _request(),
            selected_rebar=FakeSelected(),
            design_lineage=FakeLineage(),
        )
