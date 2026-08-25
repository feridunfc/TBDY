import pytest

from tbdy_engine.design.columns.sway_stability import (
    LOAD_BASIS_AUTHORITY,
    STORY_STABILITY_INPUT_AUTHORITY,
    TS500_LOAD_GQE,
    TS500_LOAD_GQW,
    UNCRACKED_SECTION_BASIS_AUTHORITY,
    StoryStabilityIndexError,
    StoryStabilityIndexEvidence,
    evaluate_ts500_story_stability_index,
    resolve_ts500_story_sway_from_stability_indices,
)


def _evidence(load_basis: str, *, drift_mm: float) -> StoryStabilityIndexEvidence:
    return StoryStabilityIndexEvidence(
        story="+0.00",
        direction="X",
        load_basis=load_basis,
        story_height_mm=3000.0,
        relative_story_displacement_mm=drift_mm,
        story_shear_n=1_000_000.0,
        sum_column_axial_design_force_n=10_000_000.0,
        input_authority=STORY_STABILITY_INPUT_AUTHORITY,
        load_basis_authority=LOAD_BASIS_AUTHORITY,
        stiffness_basis="UNCRACKED",
        stiffness_basis_authority=UNCRACKED_SECTION_BASIS_AUTHORITY,
        source_refs=(f"fixture:{load_basis}",),
    )


def test_eq_7_13_exact_formula_and_limit():
    # phi = 1.5 * 9 * 10e6 / (1e6 * 3000) = 0.045
    result = evaluate_ts500_story_stability_index(_evidence(TS500_LOAD_GQE, drift_mm=9.0))
    assert result.phi == pytest.approx(0.045)
    assert result.limit == pytest.approx(0.05)
    assert result.status == "PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX"


def test_above_limit_does_not_claim_sway_permitted():
    result = evaluate_ts500_story_stability_index(_evidence(TS500_LOAD_GQE, drift_mm=12.0))
    assert result.phi == pytest.approx(0.06)
    assert result.status == "NOT_PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX"


def test_uncracked_basis_is_mandatory():
    e = _evidence(TS500_LOAD_GQE, drift_mm=9.0)
    e = StoryStabilityIndexEvidence(
        **{**e.__dict__, "stiffness_basis": "CRACKED"}  # type: ignore[attr-defined]
    )
    with pytest.raises(StoryStabilityIndexError, match="UNCRACKED"):
        evaluate_ts500_story_stability_index(e)


def test_both_prescribed_load_bases_are_required_and_unfavorable_governs():
    blocked = resolve_ts500_story_sway_from_stability_indices(
        (_evidence(TS500_LOAD_GQE, drift_mm=6.0),),
        story="+0.00",
        direction="X",
    )
    assert blocked.status == "BLOCKED_TS500_SWAY_STABILITY_INDEX_EVIDENCE"
    assert blocked.missing_load_bases == (TS500_LOAD_GQW,)

    result = resolve_ts500_story_sway_from_stability_indices(
        (
            _evidence(TS500_LOAD_GQE, drift_mm=6.0),   # phi=0.03
            _evidence(TS500_LOAD_GQW, drift_mm=9.0),   # phi=0.045 governs
        ),
        story="+0.00",
        direction="X",
    )
    assert result.status == "PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX"
    assert result.governing_phi == pytest.approx(0.045)
    assert result.governing_load_basis == TS500_LOAD_GQW


def test_if_unfavorable_basis_exceeds_limit_proof_route_stays_unresolved():
    result = resolve_ts500_story_sway_from_stability_indices(
        (
            _evidence(TS500_LOAD_GQE, drift_mm=6.0),
            _evidence(TS500_LOAD_GQW, drift_mm=12.0),
        ),
        story="+0.00",
        direction="X",
    )
    assert result.status == "NOT_PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX"
    assert result.governing_phi == pytest.approx(0.06)
