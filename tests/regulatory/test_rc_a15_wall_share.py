from __future__ import annotations

import pytest

from tbdy_engine.regulatory.kernel import AnalysisBasisStatus
from tbdy_engine.regulatory.rc_a15_wall_share import (
    A15QualificationBranch,
    BLOCKED_RESULT_OPERATOR_AMBIGUITY,
    classify_alpha_m,
    resolve_a15_effective_policy,
    resolve_analysis_basis_status,
)


def _evidence(alpha_a: float, alpha_b: float):
    return {
        "regulatory_ready": True,
        "blocking_status": None,
        "analysis_method": "MODAL_COMBINATION",
        "scaling_state_id": "reviewed:scaled-final",
        "result_operator_id": "reviewed:signed-same-realization",
        "compatibility": {
            "mdev_population_resolved": True,
            "mo_resolved": True,
            "same_direction": True,
            "same_regulatory_base": True,
            "analysis_method_compatible": True,
            "same_result_realization": True,
            "same_scaling_state": True,
            "wall_population_complete": True,
            "result_operator_resolved": True,
        },
        "cases": (
            {"case_name": "+ecc", "sum_mdev": alpha_a * 100.0, "mo": 100.0},
            {"case_name": "-ecc", "sum_mdev": alpha_b * 100.0, "mo": 100.0},
        ),
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.399999, A15QualificationBranch.LOWER),
        (0.400000, A15QualificationBranch.LOWER),
        (0.400001, A15QualificationBranch.NOMINAL),
        (0.749999, A15QualificationBranch.NOMINAL),
        (0.750000, A15QualificationBranch.UPPER),
        (0.750001, A15QualificationBranch.UPPER),
    ],
)
def test_exact_4345_boundaries(value, expected):
    assert classify_alpha_m(value) is expected


def test_lower_policy_keeps_declared_a15_and_changes_only_effective_bys():
    policy = resolve_a15_effective_policy(_evidence(0.40, 0.399999))
    assert policy["declared_system_row"] == "A15"
    assert policy["qualification_branch"] == "LOWER"
    assert policy["effective_parameter_basis"] == "A15"
    assert policy["effective_r"] == 7.0
    assert policy["effective_d"] == 2.5
    assert policy["effective_bys_policy"] == 3


def test_nominal_policy_is_a15_r7_d25_bys2():
    policy = resolve_a15_effective_policy(_evidence(0.60, 0.61))
    assert policy["declared_system_row"] == "A15"
    assert policy["qualification_branch"] == "NOMINAL"
    assert policy["effective_parameter_basis"] == "A15"
    assert policy["effective_r"] == 7.0
    assert policy["effective_d"] == 2.5
    assert policy["effective_bys_policy"] == 2


def test_upper_policy_preserves_declaration_but_uses_a13_effective_parameter_basis():
    policy = resolve_a15_effective_policy(_evidence(0.75, 0.80))
    assert policy["declared_system_row"] == "A15"
    assert policy["qualification_branch"] == "UPPER"
    assert policy["effective_parameter_basis"] == "A13"
    assert policy["effective_r"] == 6.0
    assert policy["effective_d"] == 2.5
    assert policy["effective_bys_policy"] == 2


def test_eccentricity_branch_disagreement_fails_closed_without_envelope():
    with pytest.raises(ValueError, match=BLOCKED_RESULT_OPERATOR_AMBIGUITY):
        resolve_a15_effective_policy(_evidence(0.60, 0.80))


def test_upper_branch_requires_reanalysis_for_existing_a15_r7_d25_analysis_basis():
    policy = resolve_a15_effective_policy(_evidence(0.80, 0.81))
    assert resolve_analysis_basis_status(
        policy,
        assumed_row="A15",
        assumed_r=7.0,
        assumed_d=2.5,
        building_bys=2,
    ) is AnalysisBasisStatus.REANALYSIS_REQUIRED


def test_nominal_exact_existing_a15_analysis_basis_matches():
    policy = resolve_a15_effective_policy(_evidence(0.60, 0.61))
    assert resolve_analysis_basis_status(
        policy,
        assumed_row="A15",
        assumed_r=7.0,
        assumed_d=2.5,
        building_bys=2,
    ) is AnalysisBasisStatus.MATCH


def test_lower_branch_bys2_is_invalid_even_when_r_d_and_row_match():
    policy = resolve_a15_effective_policy(_evidence(0.30, 0.31))
    assert resolve_analysis_basis_status(
        policy,
        assumed_row="A15",
        assumed_r=7.0,
        assumed_d=2.5,
        building_bys=2,
    ) is AnalysisBasisStatus.INVALID
