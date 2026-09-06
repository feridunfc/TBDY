from __future__ import annotations

from dataclasses import replace

import pytest

import tbdy_engine.regulatory.column_transverse_confinement as subject
from tbdy_engine.checks.result import CheckStatus


def _request(**changes):
    arrangement = subject.SpecialTieDetailingFacts(
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
    base = subject.ColumnTransverseConfinementInput(
        component_id="Story1:C1:10",
        story="Story1",
        section="C50x80",
        high_ductility_applies=True,
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
            subject.TransverseDirectionFacts("DIR2", 420.0, 1000.0, 200.0, ("DIR2:fact",)),
            subject.TransverseDirectionFacts("DIR3", 720.0, 1000.0, 200.0, ("DIR3:fact",)),
        ),
        arrangement=arrangement,
        source_refs=("GEOMETRY:exact", "MATERIAL:exact", "DEMAND:exact"),
    )
    return replace(base, **changes)


def _by_id(result, check_id):
    return next(item for item in result.checks if item.check_id == check_id)


def test_complete_facts_execute_deterministically(monkeypatch):
    monkeypatch.setattr(subject, "_selected_longitudinal_diameter", lambda _selected, _component: 20.0)
    one = subject.evaluate_column_transverse_confinement(_request(), selected_rebar=object())
    two = subject.evaluate_column_transverse_confinement(_request(), selected_rebar=object())
    assert one == two
    assert one.complete is True
    assert one.failed is False
    assert one.required_confinement_region_length_mm == pytest.approx(1200.0)
    assert one.confinement_spacing_limit_mm == pytest.approx(120.0)
    assert one.middle_spacing_limit_mm == pytest.approx(200.0)
    assert all(item.status is CheckStatus.OK for item in one.checks)
    assert all(item.evidence for item in one.checks)


def test_missing_selected_longitudinal_blocks_only_dependent_spacing_branch():
    result = subject.evaluate_column_transverse_confinement(_request(), selected_rebar=None)
    assert "ENGINE_SELECTED_REBAR_REQUIRED_FOR_CONFINEMENT_SPACING" in result.blockers
    assert _by_id(result, "COL_CONFINEMENT_SPACING_MAX").status is CheckStatus.BLOCKED
    assert _by_id(result, "COL_TRANSVERSE_MIN_DIAMETER").status is CheckStatus.OK
    assert _by_id(result, "COL_CONFINEMENT_REGION_LENGTH").status is CheckStatus.OK
    assert _by_id(result, "COL_MIDDLE_TRANSVERSE_SPACING_MAX").status is CheckStatus.OK


def test_proven_non_applicable_is_out_of_scope_not_pass():
    result = subject.evaluate_column_transverse_confinement(
        _request(high_ductility_applies=False), selected_rebar=None
    )
    assert result.applicable is False
    assert result.blockers == ()
    assert result.checks[0].status is CheckStatus.OUT_OF_SCOPE


def test_unproven_applicability_fails_closed():
    result = subject.evaluate_column_transverse_confinement(
        _request(high_ductility_applies=None), selected_rebar=None
    )
    assert result.applicable is None
    assert result.checks[0].status is CheckStatus.BLOCKED
    assert "CONFINEMENT_APPLICABILITY_NOT_PROVEN" in result.blockers


def test_spacing_diameter_and_arrangement_violations_are_truthful(monkeypatch):
    monkeypatch.setattr(subject, "_selected_longitudinal_diameter", lambda _selected, _component: 20.0)
    bad_arrangement = replace(
        _request().arrangement,
        hoop_both_ends_135_hooks=False,
    )
    result = subject.evaluate_column_transverse_confinement(
        _request(
            transverse_diameter_mm=6.0,
            confinement_spacing_mm=130.0,
            arrangement=bad_arrangement,
        ),
        selected_rebar=object(),
    )
    assert _by_id(result, "COL_TRANSVERSE_MIN_DIAMETER").status is CheckStatus.FAIL
    assert _by_id(result, "COL_CONFINEMENT_SPACING_MAX").status is CheckStatus.FAIL
    assert _by_id(result, "COL_SPECIAL_TIE_DETAILING").status is CheckStatus.FAIL


def test_missing_detailing_facts_block_not_pass(monkeypatch):
    monkeypatch.setattr(subject, "_selected_longitudinal_diameter", lambda _selected, _component: 20.0)
    result = subject.evaluate_column_transverse_confinement(
        _request(arrangement=None), selected_rebar=object()
    )
    assert _by_id(result, "COL_SPECIAL_TIE_DETAILING").status is CheckStatus.BLOCKED
    assert "SPECIAL_TIE_DETAILING_FACTS_NOT_AVAILABLE" in result.blockers


def test_source_chain_is_exact_and_nonempty():
    assert subject.TBDY_2018_SOURCE_FINGERPRINT == "8d3a959ece2804ed2f37f5c6269566503fa21e86e71ae8e45c4b8a8cce37625c"
    assert set(subject.CLAIM_REFS) == {
        "COL_TRANSVERSE_CONFINEMENT_REGION",
        "COL_TRANSVERSE_CONFINEMENT_REINFORCEMENT",
        "COL_TRANSVERSE_MIDDLE_REINFORCEMENT",
        "COL_TRANSVERSE_SPECIAL_TIE_DETAILING",
    }
    assert all(value.startswith("sha256:") for value in subject.CLAIM_REFS.values())
