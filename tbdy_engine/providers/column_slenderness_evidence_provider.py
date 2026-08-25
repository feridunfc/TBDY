"""Factual slenderness-evidence adapter from strict ETABS column topology.

This module deliberately stops before regulatory promotion. It preserves the
strict topology clear-length candidate and rectangular local-axis dimensions as
factual evidence only. It does not assign TS500 free length ``ln``, sway class,
effective-length coefficient ``k`` or physical M1/M2 curvature sign.
"""
from __future__ import annotations

from tbdy_engine.design.columns.slenderness_basis import (
    ColumnSlendernessAxisEvidence,
    ColumnSlendernessEvidence,
    FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
)
from tbdy_engine.features.column_shear_topology import ColumnTopologyEvidence


FACTUAL_SLENDERNESS_EVIDENCE_AUTHORITY = "ETABS_FACTUAL_SLENDERNESS_GEOMETRY_EVIDENCE"


def build_factual_slenderness_evidence_from_topology(
    column: ColumnTopologyEvidence,
) -> ColumnSlendernessEvidence:
    """Build unpromoted two-axis slenderness evidence from strict topology.

    For a rectangular frame section, M2 is bending about local axis 2 and uses
    the local-3 section dimension for the bending-plane depth; M3 analogously
    uses the local-2 dimension. The same strict topology clear-length candidate
    is preserved for both axes, but it remains explicitly non-regulatory.
    """
    uid = column.unique_name
    candidate_mm = column.analysis_clear_length_candidate_m * 1000.0
    common_ref = f"ETABS strict topology:Column UniqueName={uid}"
    clear_ref = f"ETABS:Frame Assignments - End Length Offsets:UniqueName={uid}"
    section_ref = f"ETABS:Concrete Rectangular Section:{column.section}"

    def axis_record(axis: str, dimension_mm: float) -> ColumnSlendernessAxisEvidence:
        return ColumnSlendernessAxisEvidence(
            axis=axis,
            section_dimension_mm=dimension_mm,
            factual_clear_length_candidate_mm=candidate_mm,
            factual_clear_length_source_ref=clear_ref,
            factual_clear_length_authority=FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
            # Regulatory TS500 inputs intentionally absent.
            regulatory_free_length_ln_mm=None,
            regulatory_free_length_source_ref=None,
            regulatory_free_length_authority=None,
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
        source_refs=(
            common_ref,
            clear_ref,
            section_ref,
            FACTUAL_SLENDERNESS_EVIDENCE_AUTHORITY,
        ),
    )


__all__ = [
    "FACTUAL_SLENDERNESS_EVIDENCE_AUTHORITY",
    "build_factual_slenderness_evidence_from_topology",
]
