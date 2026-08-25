"""Factual slenderness-evidence adapter from strict ETABS column topology.

Strict topology always preserves the ETABS clear-length candidate as factual
evidence. A separate ``ColumnFreeLengthResolution`` may optionally promote that
candidate to TS500 regulatory ``ln`` after both endpoints have source-bound
lateral-support proof. Sway class, effective-length factor ``k`` and physical
M1/M2 curvature sign remain separate unresolved inputs unless later providers
supply them.
"""
from __future__ import annotations

from tbdy_engine.design.columns.free_length_basis import ColumnFreeLengthResolution
from tbdy_engine.design.columns.slenderness_basis import (
    ColumnSlendernessAxisEvidence,
    ColumnSlendernessEvidence,
    FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
    REGULATORY_FREE_LENGTH_AUTHORITY,
)
from tbdy_engine.features.column_shear_topology import ColumnTopologyEvidence


FACTUAL_SLENDERNESS_EVIDENCE_AUTHORITY = "ETABS_FACTUAL_SLENDERNESS_GEOMETRY_EVIDENCE"


def build_factual_slenderness_evidence_from_topology(
    column: ColumnTopologyEvidence,
    *,
    free_length_resolution: ColumnFreeLengthResolution | None = None,
) -> ColumnSlendernessEvidence:
    """Build two-axis slenderness evidence from strict topology and optional ln proof.

    For a rectangular frame section, M2 is bending about local axis 2 and uses
    the local-3 section dimension for the bending-plane depth; M3 analogously
    uses the local-2 dimension. ``analysis_clear_length_candidate_m`` remains
    factual in every case. Regulatory ``ln`` is populated only from a resolved
    source-bound ``ColumnFreeLengthResolution`` for the same component.
    """
    uid = column.unique_name
    candidate_mm = column.analysis_clear_length_candidate_m * 1000.0
    common_ref = f"ETABS strict topology:Column UniqueName={uid}"
    clear_ref = f"ETABS:Frame Assignments - End Length Offsets:UniqueName={uid}"
    section_ref = f"ETABS:Concrete Rectangular Section:{column.section}"

    regulatory_ln_mm: float | None = None
    regulatory_ln_ref: str | None = None
    additional_refs: tuple[str, ...] = ()
    if free_length_resolution is not None:
        if free_length_resolution.component_id != column.component_id:
            raise ValueError("free_length_resolution.component_id differs from topology component")
        additional_refs = free_length_resolution.source_refs
        if free_length_resolution.resolved:
            regulatory_ln_mm = free_length_resolution.free_length_ln_mm
            regulatory_ln_ref = f"VS6 TS500 free-length resolution:{column.component_id}"

    def axis_record(axis: str, dimension_mm: float) -> ColumnSlendernessAxisEvidence:
        return ColumnSlendernessAxisEvidence(
            axis=axis,
            section_dimension_mm=dimension_mm,
            factual_clear_length_candidate_mm=candidate_mm,
            factual_clear_length_source_ref=clear_ref,
            factual_clear_length_authority=FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
            regulatory_free_length_ln_mm=regulatory_ln_mm,
            regulatory_free_length_source_ref=regulatory_ln_ref,
            regulatory_free_length_authority=(
                REGULATORY_FREE_LENGTH_AUTHORITY if regulatory_ln_mm is not None else None
            ),
            sway_classification=None,
            sway_source_ref=None,
            sway_authority=None,
            effective_length_factor_k=None,
            effective_length_source_ref=None,
            effective_length_authority=None,
            moment_ratio_m1_over_m2=None,
            moment_ratio_source_ref=None,
            moment_ratio_authority=None,
        )

    return ColumnSlendernessEvidence(
        component_id=column.component_id,
        m2=axis_record("M2", column.depth_t3_m * 1000.0),
        m3=axis_record("M3", column.width_t2_m * 1000.0),
        source_refs=tuple(
            dict.fromkeys(
                (
                    common_ref,
                    clear_ref,
                    section_ref,
                    FACTUAL_SLENDERNESS_EVIDENCE_AUTHORITY,
                    *additional_refs,
                )
            )
        ),
    )


__all__ = [
    "FACTUAL_SLENDERNESS_EVIDENCE_AUTHORITY",
    "build_factual_slenderness_evidence_from_topology",
]
