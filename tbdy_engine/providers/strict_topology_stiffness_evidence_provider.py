"""Factual assigned RC-frame stiffness evidence from strict VS6 topology.

The strict topology bundle already proves exact frame-section assignment and
carries the concrete rectangular section-definition source row for columns and
supported RC beams. This adapter projects only the assigned I2/I3 modifier facts
needed by the TS500 Eq. 7.13 stiffness-basis assessment.

No regulatory conclusion is made here.
"""
from __future__ import annotations

from typing import Any, Mapping

from tbdy_engine.design.columns.stability_stiffness_basis import (
    AssignedFrameBendingModifierEvidence,
)
from tbdy_engine.features.column_shear_topology import StrictColumnTopologyBundle


class StrictTopologyStiffnessEvidenceError(ValueError):
    """Raised when strict topology lacks exact modifier facts for assigned RC frames."""


def _float(row: Mapping[str, Any], field: str, label: str) -> float:
    value = row.get(field)
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise StrictTopologyStiffnessEvidenceError(f"{label}.{field} must be numeric") from exc
    return result


def build_assigned_rc_frame_bending_modifier_evidence(
    topology: StrictColumnTopologyBundle,
) -> tuple[AssignedFrameBendingModifierEvidence, ...]:
    """Return unique assigned RC beam/column section modifier evidence."""
    by_identity: dict[tuple[str, str], AssignedFrameBendingModifierEvidence] = {}

    def add(*, kind: str, section: str, row: Mapping[str, Any], source_ref: str) -> None:
        if not section or section != section.strip():
            raise StrictTopologyStiffnessEvidenceError("assigned section name must be canonical")
        evidence = AssignedFrameBendingModifierEvidence(
            section_name=section,
            member_kind=kind,
            i2_modifier=_float(row, "I2Mod", section),
            i3_modifier=_float(row, "I3Mod", section),
            source_refs=(source_ref,),
        )
        key = (kind, section)
        previous = by_identity.get(key)
        if previous is not None:
            if (
                abs(previous.i2_modifier - evidence.i2_modifier) > 1e-12
                or abs(previous.i3_modifier - evidence.i3_modifier) > 1e-12
            ):
                raise StrictTopologyStiffnessEvidenceError(
                    f"contradictory modifier evidence for {kind} section {section}"
                )
            return
        by_identity[key] = evidence

    for column in topology.columns:
        add(
            kind="COLUMN",
            section=column.section,
            row=column.section_row,
            source_ref=(
                "ETABS:Frame Section Property Definitions - Concrete Rectangular:"
                f"Name={column.section}:assigned-column={column.unique_name}"
            ),
        )
        for beam in (*column.beams_at_bottom, *column.beams_at_top):
            if not beam.is_supported_rc_beam:
                continue
            if beam.section_row is None:
                raise StrictTopologyStiffnessEvidenceError(
                    f"supported RC beam {beam.beam_unique_name} lacks concrete section-definition row"
                )
            add(
                kind="BEAM",
                section=beam.section,
                row=beam.section_row,
                source_ref=(
                    "ETABS:Frame Section Property Definitions - Concrete Rectangular:"
                    f"Name={beam.section}:assigned-beam={beam.beam_unique_name}"
                ),
            )

    if not by_identity:
        raise StrictTopologyStiffnessEvidenceError("strict topology yielded no assigned RC-frame modifier evidence")
    return tuple(by_identity[key] for key in sorted(by_identity))


__all__ = [
    "StrictTopologyStiffnessEvidenceError",
    "build_assigned_rc_frame_bending_modifier_evidence",
]
