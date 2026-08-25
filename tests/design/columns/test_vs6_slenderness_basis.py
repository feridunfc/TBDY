import pytest

from tbdy_engine.design.columns.slenderness import SWAY_PERMITTED, SWAY_PREVENTED
from tbdy_engine.design.columns.slenderness_basis import (
    ColumnSlendernessAxisEvidence,
    ColumnSlendernessEvidence,
    EFFECTIVE_LENGTH_AUTHORITY,
    FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
    REGULATORY_FREE_LENGTH_AUTHORITY,
    SWAY_CLASSIFICATION_AUTHORITY,
    resolve_ts500_column_slenderness_basis,
)


COMP = "+0.00:C2:236"


def _axis(
    axis,
    *,
    ln=None,
    sway=None,
    k=None,
    factual_candidate=4450.0,
    conservative_ratio=True,
):
    return ColumnSlendernessAxisEvidence(
        axis=axis,
        section_dimension_mm=800.0,
        factual_clear_length_candidate_mm=factual_candidate,
        factual_clear_length_source_ref=f"topology:{axis}:analysis-clear-length-candidate",
        factual_clear_length_authority=FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
        regulatory_free_length_ln_mm=ln,
        regulatory_free_length_source_ref=(None if ln is None else f"reviewed:{axis}:TS500-ln"),
        regulatory_free_length_authority=(None if ln is None else REGULATORY_FREE_LENGTH_AUTHORITY),
        sway_classification=sway,
        sway_source_ref=(None if sway is None else f"reviewed:{axis}:sway"),
        sway_authority=(None if sway is None else SWAY_CLASSIFICATION_AUTHORITY),
        effective_length_factor_k=k,
        effective_length_source_ref=(None if k is None else f"reviewed:{axis}:k"),
        effective_length_authority=(None if k is None else EFFECTIVE_LENGTH_AUTHORITY),
        allow_conservative_braced_ratio=conservative_ratio,
    )


def _evidence(m2, m3):
    return ColumnSlendernessEvidence(
        component_id=COMP,
        m2=m2,
        m3=m3,
        source_refs=("fixture:slenderness-evidence",),
    )


def test_factual_clear_length_candidate_is_preserved_but_never_auto_promoted_to_ln():
    result = resolve_ts500_column_slenderness_basis(
        _evidence(
            _axis("M2", sway=SWAY_PREVENTED),
            _axis("M3", sway=SWAY_PREVENTED),
        ),
        component_id=COMP,
    )
    assert result.status == "BLOCKED_TS500_SLENDERNESS_BASIS"
    assert result.basis is None
    assert set(result.blocked_items) == {
        "M2:REGULATORY_FREE_LENGTH_NOT_PROMOTED",
        "M3:REGULATORY_FREE_LENGTH_NOT_PROMOTED",
    }
    assert any("not promoted to TS500 ln" in note for note in result.derivation_notes)


def test_sway_prevented_can_use_source_bound_k1_and_conservative_ratio_plus_one():
    result = resolve_ts500_column_slenderness_basis(
        _evidence(
            _axis("M2", ln=3000.0, sway=SWAY_PREVENTED),
            _axis("M3", ln=3000.0, sway=SWAY_PREVENTED),
        ),
        component_id=COMP,
    )
    assert result.status == "PROVEN_TS500_SLENDERNESS_BASIS"
    assert result.basis is not None
    assert result.basis.m2.effective_length_factor_k == pytest.approx(1.0)
    assert result.basis.m3.effective_length_factor_k == pytest.approx(1.0)
    assert result.basis.m2.moment_ratio_m1_over_m2 == pytest.approx(1.0)
    assert result.basis.m3.moment_ratio_m1_over_m2 == pytest.approx(1.0)
    assert any("conservative all-curvature" in note for note in result.derivation_notes)


def test_sway_permitted_requires_explicit_effective_length_factor():
    result = resolve_ts500_column_slenderness_basis(
        _evidence(
            _axis("M2", ln=3000.0, sway=SWAY_PERMITTED),
            _axis("M3", ln=3000.0, sway=SWAY_PERMITTED),
        ),
        component_id=COMP,
    )
    assert result.basis is None
    assert set(result.blocked_items) == {
        "M2:EFFECTIVE_LENGTH_FACTOR_NOT_PROMOTED",
        "M3:EFFECTIVE_LENGTH_FACTOR_NOT_PROMOTED",
    }


def test_sway_permitted_with_explicit_k_resolves_without_m1_m2_ratio():
    result = resolve_ts500_column_slenderness_basis(
        _evidence(
            _axis("M2", ln=3000.0, sway=SWAY_PERMITTED, k=1.4),
            _axis("M3", ln=3000.0, sway=SWAY_PERMITTED, k=1.6),
        ),
        component_id=COMP,
    )
    assert result.resolved
    assert result.basis is not None
    assert result.basis.m2.moment_ratio_m1_over_m2 is None
    assert result.basis.m3.moment_ratio_m1_over_m2 is None


def test_braced_without_explicit_ratio_can_fail_closed_if_conservative_bound_is_disabled():
    result = resolve_ts500_column_slenderness_basis(
        _evidence(
            _axis("M2", ln=3000.0, sway=SWAY_PREVENTED, conservative_ratio=False),
            _axis("M3", ln=3000.0, sway=SWAY_PREVENTED, conservative_ratio=False),
        ),
        component_id=COMP,
    )
    assert set(result.blocked_items) == {
        "M2:M1_M2_RATIO_NOT_PROMOTED",
        "M3:M1_M2_RATIO_NOT_PROMOTED",
    }
