"""Strict TS500 column free-length promotion from source-bound endpoint support facts.

The strict topology kernel exposes ``analysis_clear_length_candidate_m`` as an
ETABS geometry fact only. This module is the separate regulatory promotion
boundary that may turn that candidate into TS500 column free length ``ln`` only
when both physical column ends have source-bound horizontal lateral support.

Supported proof mechanisms are intentionally conservative:

* explicit ETABS point translational restraint in both global X and Y; or
* a connected supported-RC-beam network whose horizontal member axes span the
  global XY plane (at least two non-collinear directions).

The second mechanism establishes a beam-supported column end for free-length
segmentation only. It does NOT classify the storey as sway-prevented, does not
calculate effective-length ``k`` and does not assert a rigid/fixed joint.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

from tbdy_engine.design.columns.slenderness_basis import REGULATORY_FREE_LENGTH_AUTHORITY
from tbdy_engine.features.column_shear_topology import BeamJointConnection, ColumnTopologyEvidence


class ColumnFreeLengthPromotionError(ValueError):
    """Raised when endpoint support evidence is malformed or inconsistent."""


END_SUPPORT_AUTHORITY = "TS500_FREE_LENGTH_ENDPOINT_LATERAL_SUPPORT"
POINT_XY_RESTRAINT = "ETABS_POINT_TRANSLATIONAL_RESTRAINT_XY"
RC_BEAM_NETWORK = "ETABS_SUPPORTED_RC_BEAM_NETWORK_2D"
SUPPORT_NOT_PROVEN = "HORIZONTAL_LATERAL_SUPPORT_NOT_PROVEN"
FREE_LENGTH_PROVEN = "PROVEN_TS500_REGULATORY_FREE_LENGTH"
FREE_LENGTH_BLOCKED = "BLOCKED_TS500_REGULATORY_FREE_LENGTH"


@dataclass(frozen=True, slots=True)
class ColumnEndpointSupportResolution:
    end_tag: str
    joint_unique_name: str
    status: str
    proof_methods: tuple[str, ...]
    support_vectors_xy: tuple[tuple[float, float], ...]
    source_refs: tuple[str, ...]
    authority: str = END_SUPPORT_AUTHORITY

    @property
    def proven(self) -> bool:
        return self.status == "PROVEN_HORIZONTAL_LATERAL_SUPPORT"


@dataclass(frozen=True, slots=True)
class ColumnFreeLengthResolution:
    component_id: str
    status: str
    free_length_ln_mm: float | None
    factual_candidate_mm: float
    bottom_support: ColumnEndpointSupportResolution
    top_support: ColumnEndpointSupportResolution
    source_refs: tuple[str, ...]
    authority: str = REGULATORY_FREE_LENGTH_AUTHORITY

    @property
    def resolved(self) -> bool:
        return self.status == FREE_LENGTH_PROVEN


def _restraint_dofs(value: Sequence[bool], label: str) -> tuple[bool, bool, bool, bool, bool, bool]:
    if not isinstance(value, (list, tuple)) or len(value) != 6 or not all(isinstance(item, bool) for item in value):
        raise ColumnFreeLengthPromotionError(f"{label} must contain exactly six boolean restraint flags")
    return tuple(value)  # type: ignore[return-value]


def _unit_xy(dx: float, dy: float) -> tuple[float, float] | None:
    length = math.hypot(dx, dy)
    if length <= 1e-12:
        return None
    return (dx / length, dy / length)


def _independent_xy(vectors: Iterable[tuple[float, float]], *, tolerance: float = 1e-8) -> bool:
    items = tuple(vectors)
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            determinant = a[0] * b[1] - a[1] * b[0]
            if abs(determinant) > tolerance:
                return True
    return False


def _beam_vectors(beams: Sequence[BeamJointConnection]) -> tuple[tuple[float, float], ...]:
    vectors: list[tuple[float, float]] = []
    for beam in beams:
        if not beam.is_supported_rc_beam:
            continue
        vector = _unit_xy(beam.vector_from_joint_m[0], beam.vector_from_joint_m[1])
        if vector is not None:
            vectors.append(vector)
    return tuple(vectors)


def resolve_column_endpoint_lateral_support(
    *,
    end_tag: str,
    joint_unique_name: str,
    restraint_dofs: Sequence[bool],
    connected_beams: Sequence[BeamJointConnection],
    restraint_source_ref: str,
    topology_source_ref: str,
) -> ColumnEndpointSupportResolution:
    """Resolve horizontal endpoint support without assigning sway/fixity semantics."""
    if end_tag not in {"BOTTOM", "TOP"}:
        raise ColumnFreeLengthPromotionError("end_tag must be BOTTOM or TOP")
    if not isinstance(joint_unique_name, str) or not joint_unique_name.strip():
        raise ColumnFreeLengthPromotionError("joint_unique_name must be nonblank")
    dofs = _restraint_dofs(restraint_dofs, f"{end_tag}.restraint_dofs")
    if not restraint_source_ref or not topology_source_ref:
        raise ColumnFreeLengthPromotionError("endpoint support evidence requires source refs")

    methods: list[str] = []
    refs: list[str] = []
    vectors: list[tuple[float, float]] = []

    # Explicit translational restraints contribute exact global support axes.
    if dofs[0]:
        vectors.append((1.0, 0.0))
        refs.append(restraint_source_ref)
    if dofs[1]:
        vectors.append((0.0, 1.0))
        if restraint_source_ref not in refs:
            refs.append(restraint_source_ref)
    if dofs[0] and dofs[1]:
        methods.append(POINT_XY_RESTRAINT)

    beam_vectors = _beam_vectors(connected_beams)
    vectors.extend(beam_vectors)
    if _independent_xy(beam_vectors):
        methods.append(RC_BEAM_NETWORK)
        refs.append(topology_source_ref)

    proven = _independent_xy(vectors)
    if proven and not methods:
        # Mixed proof, e.g. one point-restraint direction + a nonparallel beam.
        methods.append("COMBINED_RESTRAINT_AND_RC_BEAM_SUPPORT")
        refs.extend((restraint_source_ref, topology_source_ref))

    return ColumnEndpointSupportResolution(
        end_tag=end_tag,
        joint_unique_name=joint_unique_name,
        status="PROVEN_HORIZONTAL_LATERAL_SUPPORT" if proven else SUPPORT_NOT_PROVEN,
        proof_methods=tuple(dict.fromkeys(methods)),
        support_vectors_xy=tuple(vectors),
        source_refs=tuple(dict.fromkeys(refs or (restraint_source_ref, topology_source_ref))),
    )


def resolve_ts500_column_free_length(
    column: ColumnTopologyEvidence,
    *,
    bottom_restraint_dofs: Sequence[bool],
    top_restraint_dofs: Sequence[bool],
    bottom_restraint_source_ref: str,
    top_restraint_source_ref: str,
) -> ColumnFreeLengthResolution:
    """Promote the strict ETABS clear-length candidate to TS500 ``ln`` or block.

    Promotion is allowed only when both physical endpoints have proven
    horizontal support. The ETABS end-offset-derived candidate is then used as
    the support-face-to-support-face free length. No sway or effective-length
    conclusion is made here.
    """
    candidate_mm = float(column.analysis_clear_length_candidate_m) * 1000.0
    if not math.isfinite(candidate_mm) or candidate_mm <= 0.0:
        raise ColumnFreeLengthPromotionError("factual clear-length candidate must be finite and > 0")

    topology_bottom_ref = f"ETABS strict topology:{column.component_id}:BOTTOM"
    topology_top_ref = f"ETABS strict topology:{column.component_id}:TOP"
    bottom = resolve_column_endpoint_lateral_support(
        end_tag="BOTTOM",
        joint_unique_name=column.joint_bottom,
        restraint_dofs=bottom_restraint_dofs,
        connected_beams=column.beams_at_bottom,
        restraint_source_ref=bottom_restraint_source_ref,
        topology_source_ref=topology_bottom_ref,
    )
    top = resolve_column_endpoint_lateral_support(
        end_tag="TOP",
        joint_unique_name=column.joint_top,
        restraint_dofs=top_restraint_dofs,
        connected_beams=column.beams_at_top,
        restraint_source_ref=top_restraint_source_ref,
        topology_source_ref=topology_top_ref,
    )

    refs = tuple(
        dict.fromkeys(
            (
                f"ETABS:Frame Assignments - End Length Offsets:UniqueName={column.unique_name}",
                *bottom.source_refs,
                *top.source_refs,
                "TS500 7.6.2.2 free length between lateral supports",
            )
        )
    )
    if not (bottom.proven and top.proven):
        return ColumnFreeLengthResolution(
            component_id=column.component_id,
            status=FREE_LENGTH_BLOCKED,
            free_length_ln_mm=None,
            factual_candidate_mm=candidate_mm,
            bottom_support=bottom,
            top_support=top,
            source_refs=refs,
        )

    return ColumnFreeLengthResolution(
        component_id=column.component_id,
        status=FREE_LENGTH_PROVEN,
        free_length_ln_mm=candidate_mm,
        factual_candidate_mm=candidate_mm,
        bottom_support=bottom,
        top_support=top,
        source_refs=refs,
    )


__all__ = [
    "ColumnEndpointSupportResolution",
    "ColumnFreeLengthPromotionError",
    "ColumnFreeLengthResolution",
    "END_SUPPORT_AUTHORITY",
    "FREE_LENGTH_BLOCKED",
    "FREE_LENGTH_PROVEN",
    "POINT_XY_RESTRAINT",
    "RC_BEAM_NETWORK",
    "SUPPORT_NOT_PROVEN",
    "resolve_column_endpoint_lateral_support",
    "resolve_ts500_column_free_length",
]
