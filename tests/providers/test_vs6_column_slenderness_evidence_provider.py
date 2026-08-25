from types import SimpleNamespace

from tbdy_engine.design.columns.free_length_basis import (
    ColumnEndpointSupportResolution,
    ColumnFreeLengthResolution,
    FREE_LENGTH_PROVEN,
)
from tbdy_engine.design.columns.slenderness_basis import (
    FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
    REGULATORY_FREE_LENGTH_AUTHORITY,
    resolve_ts500_column_slenderness_basis,
)
from tbdy_engine.providers.column_slenderness_evidence_provider import (
    FACTUAL_SLENDERNESS_EVIDENCE_AUTHORITY,
    build_factual_slenderness_evidence_from_topology,
)


def _column():
    return SimpleNamespace(
        unique_name="236",
        component_id="+0.00:C2:236",
        section="Column_80x60",
        width_t2_m=0.60,
        depth_t3_m=0.80,
        analysis_clear_length_candidate_m=4.45,
    )


def _support(end_tag, joint):
    return ColumnEndpointSupportResolution(
        end_tag=end_tag,
        joint_unique_name=joint,
        status="PROVEN_HORIZONTAL_LATERAL_SUPPORT",
        proof_methods=("TEST_SOURCE_BOUND_SUPPORT",),
        support_vectors_xy=((1.0, 0.0), (0.0, 1.0)),
        source_refs=(f"test:{joint}",),
    )


def _free_length():
    return ColumnFreeLengthResolution(
        component_id="+0.00:C2:236",
        status=FREE_LENGTH_PROVEN,
        free_length_ln_mm=4450.0,
        factual_candidate_mm=4450.0,
        bottom_support=_support("BOTTOM", "956"),
        top_support=_support("TOP", "760"),
        source_refs=("TS500 7.6.2.2", "ETABS strict support proof"),
    )


def test_adapter_preserves_candidate_and_maps_rectangular_principal_dimensions_without_regulatory_promotion():
    evidence = build_factual_slenderness_evidence_from_topology(_column())
    assert evidence.m2.section_dimension_mm == 800.0
    assert evidence.m3.section_dimension_mm == 600.0
    assert evidence.m2.factual_clear_length_candidate_mm == 4450.0
    assert evidence.m3.factual_clear_length_candidate_mm == 4450.0
    assert evidence.m2.factual_clear_length_authority == FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY
    assert evidence.m2.regulatory_free_length_ln_mm is None
    assert evidence.m3.regulatory_free_length_ln_mm is None
    assert evidence.m2.sway_classification is None
    assert FACTUAL_SLENDERNESS_EVIDENCE_AUTHORITY in evidence.source_refs


def test_factual_adapter_alone_cannot_resolve_ts500_slenderness_basis():
    evidence = build_factual_slenderness_evidence_from_topology(_column())
    result = resolve_ts500_column_slenderness_basis(evidence, component_id=evidence.component_id)
    assert result.status == "BLOCKED_TS500_SLENDERNESS_BASIS"
    assert set(result.blocked_items) == {
        "M2:REGULATORY_FREE_LENGTH_NOT_PROMOTED",
        "M2:SWAY_CLASSIFICATION_NOT_PROMOTED",
        "M2:EFFECTIVE_LENGTH_FACTOR_NOT_PROMOTED",
        "M3:REGULATORY_FREE_LENGTH_NOT_PROMOTED",
        "M3:SWAY_CLASSIFICATION_NOT_PROMOTED",
        "M3:EFFECTIVE_LENGTH_FACTOR_NOT_PROMOTED",
    }
    assert all("M1_M2" not in item for item in result.blocked_items)


def test_proven_free_length_is_promoted_but_sway_and_k_remain_blocked():
    evidence = build_factual_slenderness_evidence_from_topology(
        _column(),
        free_length_resolution=_free_length(),
    )
    assert evidence.m2.regulatory_free_length_ln_mm == 4450.0
    assert evidence.m3.regulatory_free_length_ln_mm == 4450.0
    assert evidence.m2.regulatory_free_length_authority == REGULATORY_FREE_LENGTH_AUTHORITY

    result = resolve_ts500_column_slenderness_basis(evidence, component_id=evidence.component_id)
    assert result.status == "BLOCKED_TS500_SLENDERNESS_BASIS"
    assert all("REGULATORY_FREE_LENGTH" not in item for item in result.blocked_items)
    assert set(result.blocked_items) == {
        "M2:SWAY_CLASSIFICATION_NOT_PROMOTED",
        "M2:EFFECTIVE_LENGTH_FACTOR_NOT_PROMOTED",
        "M3:SWAY_CLASSIFICATION_NOT_PROMOTED",
        "M3:EFFECTIVE_LENGTH_FACTOR_NOT_PROMOTED",
    }
