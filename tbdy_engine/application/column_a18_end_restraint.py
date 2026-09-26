"""COLUMN-R1 A18 source-bound TS500 end-restraint materialization.

Consumes the existing strict topology and same-generation factual Frame
population only.  No ETABS read is performed here.  TS500 Eq.7.16 remains
owned exclusively by ``design.columns.effective_length``.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Iterable, Mapping, Sequence

from tbdy_engine.design.columns.effective_length import (
    ColumnEffectiveLengthError,
    EndRestraintMemberContribution,
    evaluate_ts500_end_restraint_ratio,
)
from tbdy_engine.features.column_shear_topology import (
    ColumnTopologyEvidence,
    StrictColumnTopologyBundle,
)
from tbdy_engine.providers.etabs_frame_eq713_population_provider import (
    FrameEq713FactualFact,
    FrameEq713FactualPopulation,
)
from tbdy_engine.providers.frame_section_inertia_normalization import (
    normalize_frame_section_inertia_m4,
)

A18_READY = "READY"
A18_EXPLICIT_UNRESOLVED = "EXPLICIT_UNRESOLVED"
A18_AUTHORITY = "COLUMN_R1_A18_TS500_END_RESTRAINT_FACTUAL_MATERIALIZATION"
A18_LOCAL_AXIS_AUTHORITY = "COLUMN_R1_A18_FRAME_LOCAL_AXIS_FACTUAL_BINDING"
TS500_EQ716_COLUMN_GROSS_IG_REF = "TS500_7.6.2.2_EQ7.16:COLUMN_GROSS_UNCRACKED_IG"
TS500_EQ716_BEAM_HALF_IG_REF = "TS500_7.6.2.2_EQ7.16:BEAM_SUPPORTED_FALLBACK_0.5_IG"

_ANGLE_TOL = 1.0e-8


class A18InertiaBasis(str, Enum):
    COLUMN_GROSS_UNCRACKED_IG_1_0 = "COLUMN_GROSS_UNCRACKED_IG_1_0"
    BEAM_TS500_SUPPORTED_FALLBACK_0_5_GROSS_IG = (
        "BEAM_TS500_SUPPORTED_FALLBACK_0_5_GROSS_IG"
    )


_BASIS = {
    A18InertiaBasis.COLUMN_GROSS_UNCRACKED_IG_1_0: (
        1.0,
        TS500_EQ716_COLUMN_GROSS_IG_REF,
    ),
    A18InertiaBasis.BEAM_TS500_SUPPORTED_FALLBACK_0_5_GROSS_IG: (
        0.5,
        TS500_EQ716_BEAM_HALF_IG_REF,
    ),
}


@dataclass(frozen=True, slots=True)
class A18EndRestraintMaterialization:
    component_id: str
    end_tag: str
    local_bending_axis: str
    disposition: str
    alpha: float | None
    numerator_column_i_over_l_m3: float | None
    denominator_beam_i_over_l_m3: float | None
    column_member_ids: tuple[str, ...]
    beam_member_ids: tuple[str, ...]
    source_refs: tuple[str, ...]
    unresolved_reasons: tuple[str, ...] = ()
    authority: str = A18_AUTHORITY


@dataclass(frozen=True, slots=True)
class A18FrameLocalAxisEvidence:
    """Exact supplemental Frame local-axis fact for A18.

    This does not replace strict topology.  It supplies the exact
    FrameObj.GetLocalAxes result when the display-table topology has no
    explicit local-axis row.
    """

    frame_name: str
    angle_degrees: float
    advanced: bool
    source_refs: tuple[str, ...]
    authority: str = A18_LOCAL_AXIS_AUTHORITY

    def __post_init__(self) -> None:
        if (
            not isinstance(self.frame_name, str)
            or not self.frame_name.strip()
            or self.frame_name != self.frame_name.strip()
        ):
            raise ValueError(
                "frame_name must be a nonblank canonical string"
            )

        if (
            isinstance(self.angle_degrees, bool)
            or self.angle_degrees is None
        ):
            raise ValueError(
                "angle_degrees must be finite numeric"
            )

        try:
            angle = float(
                self.angle_degrees
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "angle_degrees must be finite numeric"
            ) from exc

        if not math.isfinite(angle):
            raise ValueError(
                "angle_degrees must be finite numeric"
            )

        if type(self.advanced) is not bool:
            raise TypeError(
                "advanced must be bool"
            )

        refs = tuple(
            dict.fromkeys(
                ref
                for ref in self.source_refs
                if (
                    isinstance(ref, str)
                    and ref.strip()
                    and ref == ref.strip()
                )
            )
        )

        if not refs:
            raise ValueError(
                "source_refs must contain factual provenance"
            )

        object.__setattr__(
            self,
            "angle_degrees",
            angle,
        )

        object.__setattr__(
            self,
            "source_refs",
            refs,
        )


class _Unresolved(RuntimeError):
    def __init__(self, reason: str, *refs: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.refs = tuple(refs)


def _refs(values: Iterable[object]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            value
            for value in values
            if isinstance(value, str) and value.strip() and value == value.strip()
        )
    )


def _positive(value: object, reason: str) -> float:
    if isinstance(value, bool) or value is None:
        raise _Unresolved(reason)
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise _Unresolved(reason) from exc
    if not math.isfinite(result) or result <= 0.0:
        raise _Unresolved(reason)
    return result


def _member_id(member: object, role: str) -> str:
    value = getattr(
        member,
        "unique_name" if role == "COLUMN" else "beam_unique_name",
        None,
    )
    if not isinstance(value, str) or not value.strip():
        raise _Unresolved(f"MISSING_{role}_CONNECTION_IDENTITY")
    return value


def _local_axis(
    member: object,
    member_id: str,
    local_axis_facts: Mapping[
        str,
        A18FrameLocalAxisEvidence,
    ] | None = None,
) -> tuple[float, tuple[str, ...]]:
    """Resolve A18 local-axis rotation without manufacturing an assignment.

    Existing explicit strict-topology table evidence remains authoritative.
    When that row is absent, an exact non-advanced FrameObj.GetLocalAxes
    fact may supply the missing factual rotation.
    """

    row = getattr(
        member,
        "local_axis_row",
        None,
    )

    angle = getattr(
        member,
        "local_axis_angle_deg",
        None,
    )

    explicit = (
        getattr(
            member,
            "local_axis_explicit",
            False,
        )
        is True
    )

    # Existing supported path: preserve exact table authority.
    if (
        explicit
        and row is not None
        and angle is not None
        and not isinstance(
            angle,
            bool,
        )
    ):
        try:
            resolved = float(
                angle
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            raise _Unresolved(
                f"INVALID_LOCAL_AXIS:{member_id}"
            ) from exc

        if not math.isfinite(
            resolved
        ):
            raise _Unresolved(
                f"INVALID_LOCAL_AXIS:{member_id}"
            )

        raw_angle = (
            row.get("Angle")
            if hasattr(
                row,
                "get",
            )
            else angle
        )

        return (
            resolved,
            _refs(
                (
                    f"strict-topology:"
                    f"frame-local-axis:"
                    f"{member_id}",

                    "ETABS:"
                    "Frame Assignments - "
                    "Local Axes:"
                    f"{member_id}:"
                    f"Angle={raw_angle}",
                )
            ),
        )

    # Missing table row may be supplemented only by an exact OAPI fact.
    factual = (
        None
        if local_axis_facts is None
        else local_axis_facts.get(
            member_id
        )
    )

    if factual is None:
        raise _Unresolved(
            f"MISSING_LOCAL_AXIS:{member_id}",
            f"strict-topology:frame:{member_id}",
        )

    if not isinstance(
        factual,
        A18FrameLocalAxisEvidence,
    ):
        raise _Unresolved(
            f"INVALID_LOCAL_AXIS_FACT:{member_id}",
            f"strict-topology:frame:{member_id}",
        )

    if (
        factual.frame_name
        != member_id
    ):
        raise _Unresolved(
            f"LOCAL_AXIS_IDENTITY_MISMATCH:{member_id}",
            *factual.source_refs,
        )

    if factual.advanced:
        raise _Unresolved(
            f"ADVANCED_LOCAL_AXIS_UNSUPPORTED:{member_id}",
            *factual.source_refs,
        )

    resolved = float(
        factual.angle_degrees
    )

    if not math.isfinite(
        resolved
    ):
        raise _Unresolved(
            f"INVALID_LOCAL_AXIS:{member_id}",
            *factual.source_refs,
        )

    # If topology claims an explicit assignment but could not materialize
    # the corresponding table row/angle, do not let OAPI hide an internal
    # topology contradiction.
    if explicit:
        raise _Unresolved(
            f"STRICT_TOPOLOGY_LOCAL_AXIS_INCOMPLETE:{member_id}",
            *factual.source_refs,
        )

    if (
        row is not None
        or angle is not None
    ):
        raise _Unresolved(
            f"STRICT_TOPOLOGY_LOCAL_AXIS_FLAG_MISMATCH:{member_id}",
            *factual.source_refs,
        )

    return (
        resolved,
        _refs(
            (
                *factual.source_refs,
                factual.authority,
                f"strict-topology:"
                f"frame-local-axis-table-absent:"
                f"{member_id}",
            )
        ),
    )


def _parallel(a: float, b: float) -> bool:
    return abs(math.sin(math.radians(a - b))) <= _ANGLE_TOL


def _perpendicular(a: float, b: float) -> bool:
    return abs(math.cos(math.radians(a - b))) <= _ANGLE_TOL


def _fact_map(population: FrameEq713FactualPopulation) -> dict[str, FrameEq713FactualFact]:
    result: dict[str, FrameEq713FactualFact] = {}
    for fact in tuple(getattr(population, "rows", ()) or ()):
        name = getattr(fact, "frame_name", None)
        if not isinstance(name, str) or not name.strip():
            raise _Unresolved("MISSING_FRAME_FACT_IDENTITY")
        if name in result:
            raise _Unresolved(f"DUPLICATE_FRAME_FACT:{name}")
        result[name] = fact
    return result


def _frame_evidence(
    fact: FrameEq713FactualFact,
    member_id: str,
    role: str,
) -> tuple[str, ...]:
    if getattr(fact, "member_role", None) != role:
        raise _Unresolved(f"FRAME_ROLE_MISMATCH:{member_id}")
    fact_refs = _refs(tuple(getattr(fact, "source_refs", ()) or ()))
    if not fact_refs:
        raise _Unresolved(f"MISSING_FRAME_FACT_PROVENANCE:{member_id}")

    release = getattr(fact, "releases", None)
    release_ref = getattr(release, "evidence_ref", None)
    release_success = getattr(release, "success", False)
    if (
        release is None
        or release_success is not True
        or not isinstance(release_ref, str)
        or not release_ref.strip()
    ):
        raise _Unresolved(f"MISSING_RELEASE_EVIDENCE:{member_id}", *fact_refs)
    try:
        supported = fact.supported_end_condition
    except Exception as exc:
        raise _Unresolved(
            f"MISSING_RELEASE_EVIDENCE:{member_id}",
            *fact_refs,
            release_ref,
        ) from exc
    if supported is not True:
        raise _Unresolved(
            f"RELEASE_OR_PARTIAL_FIXITY_UNSUPPORTED:{member_id}",
            *fact_refs,
            release_ref,
        )
    return _refs((*fact_refs, release_ref))


def _inertia_m4(
    fact: FrameEq713FactualFact,
    member_id: str,
    mechanics_axis: str,
) -> tuple[float, tuple[str, ...]]:
    mechanics = getattr(fact, "section_mechanics", None)
    if mechanics is None or getattr(mechanics, "success", False) is not True:
        raise _Unresolved(f"MISSING_SECTION_MECHANICS:{member_id}")
    raw = getattr(
        mechanics,
        "inertia_22" if mechanics_axis == "M2" else "inertia_33",
        None,
    )
    raw = _positive(
        raw,
        f"MISSING_OR_INVALID_SECTION_INERTIA:{member_id}:{mechanics_axis}",
    )
    base = getattr(fact, "base_fact", None)
    unit = getattr(base, "present_length_unit", None)
    if unit is None or isinstance(unit, bool):
        raise _Unresolved(f"MISSING_PRESENT_LENGTH_UNIT:{member_id}")
    mechanics_ref = getattr(mechanics, "evidence_ref", None)
    if not isinstance(mechanics_ref, str) or not mechanics_ref.strip():
        raise _Unresolved(f"MISSING_SECTION_MECHANICS_PROVENANCE:{member_id}")
    try:
        normalized = normalize_frame_section_inertia_m4(
            raw,
            unit,
            source_ref=mechanics_ref,
        )
    except Exception as exc:
        raise _Unresolved(f"UNSUPPORTED_PRESENT_LENGTH_UNIT:{member_id}") from exc
    return normalized.inertia_m4, _refs(
        (
            mechanics_ref,
            getattr(base, "evidence_ref", ""),
            normalized.source_ref,
            normalized.authority,
            f"PropFrame.GetSectProps:{member_id}:{mechanics_axis}",
        )
    )


def _connected_columns(
    topology: StrictColumnTopologyBundle,
    joint: str,
) -> tuple[ColumnTopologyEvidence, ...]:
    connected: list[ColumnTopologyEvidence] = []
    seen: set[str] = set()
    for column in tuple(getattr(topology, "columns", ()) or ()):
        member_id = _member_id(column, "COLUMN")
        bottom = getattr(column, "joint_bottom", None)
        top = getattr(column, "joint_top", None)
        if not isinstance(bottom, str) or not bottom or not isinstance(top, str) or not top:
            raise _Unresolved(f"MISSING_COLUMN_CONNECTION_IDENTITY:{member_id}")
        if joint in {bottom, top}:
            if member_id in seen:
                raise _Unresolved(f"DUPLICATE_COLUMN_CONNECTION:{member_id}")
            seen.add(member_id)
            connected.append(column)
    if not connected:
        raise _Unresolved(f"NO_COLUMN_CONNECTION_AT_JOINT:{joint}")
    return tuple(sorted(connected, key=lambda item: _member_id(item, "COLUMN")))


def _column_contribution(
    column: ColumnTopologyEvidence,
    fact: FrameEq713FactualFact,
    target_axis_azimuth: float,
    *,
    local_axis_facts: Mapping[
        str,
        A18FrameLocalAxisEvidence,
    ] | None,
) -> EndRestraintMemberContribution:
    member_id = _member_id(column, "COLUMN")

    angle, axis_refs = _local_axis(
        column,
        member_id,
        local_axis_facts,
    )
    if _parallel(target_axis_azimuth, angle):
        mechanics_axis = "M2"
    elif _parallel(target_axis_azimuth, angle + 90.0):
        mechanics_axis = "M3"
    else:
        raise _Unresolved(
            f"AMBIGUOUS_COLUMN_BENDING_PLANE:{member_id}",
            *axis_refs,
        )
    if getattr(column, "connectivity_row", None) is None:
        raise _Unresolved(f"MISSING_COLUMN_CONNECTION_IDENTITY:{member_id}")
    length_m = _positive(
        getattr(column, "object_length_m", None),
        f"MISSING_COLUMN_LENGTH:{member_id}",
    )
    inertia_m4, inertia_refs = _inertia_m4(fact, member_id, mechanics_axis)
    factor, regulatory_ref = _BASIS[A18InertiaBasis.COLUMN_GROSS_UNCRACKED_IG_1_0]
    return EndRestraintMemberContribution(
        member_id=member_id,
        member_role="COLUMN",
        inertia_m4=inertia_m4,
        member_length_m=length_m,
        inertia_factor=factor,
        source_refs=_refs(
            (
                *axis_refs,
                *_frame_evidence(fact, member_id, "COLUMN"),
                *inertia_refs,
                f"strict-topology:column-object-length:{member_id}",
                A18InertiaBasis.COLUMN_GROSS_UNCRACKED_IG_1_0.value,
                regulatory_ref,
                A18_AUTHORITY,
            )
        ),
    )


def _beam_geometry_eligibility(
    beam: object,
    member_id: str,
    target_axis_azimuth: float,
) -> tuple[bool, str]:
    """Classify Eq.7.16 beam-plane eligibility before stiffness facts.

    Geometry alone is sufficient to prove that a parallel beam cannot
    contribute to the target bending-axis denominator.  Only a geometrically
    relevant perpendicular beam is allowed to proceed to FrameEq713 factual
    stiffness qualification.
    """
    azimuth = getattr(
        beam,
        "horizontal_azimuth_deg",
        None,
    )
    if azimuth is None or isinstance(
        azimuth,
        bool,
    ):
        raise _Unresolved(
            f"MISSING_BEAM_BENDING_PLANE:{member_id}"
        )
    try:
        azimuth = float(
            azimuth
        )
    except (TypeError, ValueError) as exc:
        raise _Unresolved(
            f"MISSING_BEAM_BENDING_PLANE:{member_id}"
        ) from exc

    span_ref = (
        f"strict-topology:beam-azimuth:"
        f"{member_id}:deg={azimuth:g}"
    )

    if _parallel(
        azimuth,
        target_axis_azimuth,
    ):
        return False, span_ref

    if not _perpendicular(
        azimuth,
        target_axis_azimuth,
    ):
        raise _Unresolved(
            f"AMBIGUOUS_BEAM_BENDING_PLANE:{member_id}",
            span_ref,
        )

    return True, span_ref


def _beam_contribution(
    beam: object,
    fact: FrameEq713FactualFact,
    *,
    joint: str,
    target_axis_azimuth: float,
    local_axis_facts: Mapping[
        str,
        A18FrameLocalAxisEvidence,
    ] | None,
) -> EndRestraintMemberContribution | None:
    member_id = _member_id(
        beam,
        "BEAM",
    )

    contributes, span_ref = (
        _beam_geometry_eligibility(
            beam,
            member_id,
            target_axis_azimuth,
        )
    )

    if not contributes:
        return None

    angle, axis_refs = _local_axis(
        beam,
        member_id,
        local_axis_facts,
    )
    if _parallel(angle, 0.0):
        mechanics_axis = "M3"
    elif _perpendicular(angle, 0.0):
        mechanics_axis = "M2"
    else:
        raise _Unresolved(
            f"AMBIGUOUS_BEAM_LOCAL_BENDING_AXIS:{member_id}",
            span_ref,
            *axis_refs,
        )

    row = getattr(beam, "connectivity_row", None)
    connected_end = getattr(beam, "connected_end", None)
    other_joint = getattr(beam, "other_joint_unique_name", None)
    if (
        row is None
        or getattr(beam, "joint_unique_name", None) != joint
        or connected_end not in {"I", "J"}
        or not isinstance(other_joint, str)
        or not other_joint.strip()
        or other_joint == joint
    ):
        raise _Unresolved(f"MISSING_BEAM_CONNECTION_IDENTITY:{member_id}")
    try:
        raw_length = row.get("Length")
    except AttributeError as exc:
        raise _Unresolved(f"MISSING_BEAM_LENGTH:{member_id}") from exc
    length_m = _positive(raw_length, f"MISSING_BEAM_LENGTH:{member_id}")

    inertia_m4, inertia_refs = _inertia_m4(fact, member_id, mechanics_axis)
    factor, regulatory_ref = _BASIS[
        A18InertiaBasis.BEAM_TS500_SUPPORTED_FALLBACK_0_5_GROSS_IG
    ]
    return EndRestraintMemberContribution(
        member_id=member_id,
        member_role="BEAM",
        inertia_m4=inertia_m4,
        member_length_m=length_m,
        inertia_factor=factor,
        source_refs=_refs(
            (
                span_ref,
                *axis_refs,
                *_frame_evidence(fact, member_id, "BEAM"),
                *inertia_refs,
                f"strict-topology:beam-connectivity:{member_id}",
                f"strict-topology:beam-connected-end:{member_id}:{connected_end}",
                A18InertiaBasis.BEAM_TS500_SUPPORTED_FALLBACK_0_5_GROSS_IG.value,
                regulatory_ref,
                A18_AUTHORITY,
            )
        ),
    )


def _one(
    *,
    target_column: ColumnTopologyEvidence,
    topology: StrictColumnTopologyBundle,
    facts: dict[str, FrameEq713FactualFact],
    end_tag: str,
    axis: str,
    local_axis_facts: Mapping[
        str,
        A18FrameLocalAxisEvidence,
    ] | None,
) -> A18EndRestraintMaterialization:
    component_id = getattr(target_column, "component_id", "")
    target_id = getattr(target_column, "unique_name", "")
    beams = tuple(
        getattr(
            target_column,
            "beams_at_bottom" if end_tag == "BOTTOM" else "beams_at_top",
            (),
        )
        or ()
    )
    column_ids: tuple[str, ...] = ()
    beam_ids = tuple(
        sorted(
            value
            for value in (getattr(item, "beam_unique_name", None) for item in beams)
            if isinstance(value, str) and value
        )
    )
    evidence = list(
        _refs(
            (
                A18_AUTHORITY,
                f"strict-topology:component:{component_id}",
                f"strict-topology:target-column:{target_id}",
                f"A18:{component_id}:{end_tag}:{axis}",
            )
        )
    )
    try:
        target_id = _member_id(target_column, "COLUMN")
        joint = getattr(
            target_column,
            "joint_bottom" if end_tag == "BOTTOM" else "joint_top",
            None,
        )
        if not isinstance(joint, str) or not joint.strip():
            raise _Unresolved(f"MISSING_TARGET_END_JOINT:{end_tag}")
        target_angle, target_axis_refs = _local_axis(
            target_column,
            target_id,
            local_axis_facts,
        )
        evidence.extend(target_axis_refs)
        target_axis_azimuth = target_angle if axis == "M2" else target_angle + 90.0

        resolved_beam_ids = tuple(_member_id(item, "BEAM") for item in beams)
        if len(resolved_beam_ids) != len(set(resolved_beam_ids)):
            raise _Unresolved(f"DUPLICATE_BEAM_CONNECTION_AT_END:{end_tag}")
        beam_ids = tuple(sorted(resolved_beam_ids))

        columns = _connected_columns(topology, joint)
        column_ids = tuple(_member_id(item, "COLUMN") for item in columns)
        if target_id not in column_ids:
            raise _Unresolved(f"TARGET_COLUMN_NOT_CONNECTED_AT_END:{target_id}:{end_tag}")

        column_contributions = []
        for column in columns:
            member_id = _member_id(column, "COLUMN")
            fact = facts.get(member_id)
            if fact is None:
                raise _Unresolved(f"MISSING_FRAME_FACT:{member_id}")
            contribution = _column_contribution(
                column,
                fact,
                target_axis_azimuth,
                local_axis_facts=local_axis_facts,
            )
            column_contributions.append(contribution)
            evidence.extend(contribution.source_refs)

        beam_contributions = []
        for beam in beams:
            member_id = _member_id(
                beam,
                "BEAM",
            )

            contributes, _span_ref = (
                _beam_geometry_eligibility(
                    beam,
                    member_id,
                    target_axis_azimuth,
                )
            )

            if not contributes:
                continue

            fact = facts.get(
                member_id
            )
            if fact is None:
                raise _Unresolved(
                    f"MISSING_FRAME_FACT:{member_id}"
                )

            contribution = _beam_contribution(
                beam,
                fact,
                joint=joint,
                target_axis_azimuth=target_axis_azimuth,
                local_axis_facts=local_axis_facts,
            )

            if contribution is not None:
                beam_contributions.append(
                    contribution
                )
                evidence.extend(
                    contribution.source_refs
                )

        ratio = evaluate_ts500_end_restraint_ratio(
            end_tag=end_tag,
            axis=axis,
            column_contributions=column_contributions,
            beam_contributions=beam_contributions,
            source_refs=_refs(evidence),
        )
        return A18EndRestraintMaterialization(
            component_id=component_id,
            end_tag=end_tag,
            local_bending_axis=axis,
            disposition=A18_READY,
            alpha=ratio.alpha,
            numerator_column_i_over_l_m3=ratio.numerator_column_i_over_l_m3,
            denominator_beam_i_over_l_m3=ratio.denominator_beam_i_over_l_m3,
            column_member_ids=ratio.column_member_ids,
            beam_member_ids=ratio.beam_member_ids,
            source_refs=_refs((A18_AUTHORITY, *ratio.source_refs)),
        )
    except _Unresolved as exc:
        evidence.extend(exc.refs)
        reason = exc.reason
    except ColumnEffectiveLengthError as exc:
        reason = f"END_RESTRAINT_RATIO_UNRESOLVED:{exc}"

    return A18EndRestraintMaterialization(
        component_id=component_id,
        end_tag=end_tag,
        local_bending_axis=axis,
        disposition=A18_EXPLICIT_UNRESOLVED,
        alpha=None,
        numerator_column_i_over_l_m3=None,
        denominator_beam_i_over_l_m3=None,
        column_member_ids=column_ids,
        beam_member_ids=beam_ids,
        source_refs=_refs(evidence),
        unresolved_reasons=(reason,),
    )


def materialize_ts500_column_end_restraint_ratios(
    *,
    target_column: ColumnTopologyEvidence,
    topology: StrictColumnTopologyBundle,
    frame_population: FrameEq713FactualPopulation,
    frame_local_axes: Mapping[
        str,
        A18FrameLocalAxisEvidence,
    ] | None = None,
) -> tuple[A18EndRestraintMaterialization, ...]:
    """Return exact BOTTOM/TOP x M2/M3 A18 facts or explicit unresolved rows."""
    component_id = getattr(target_column, "component_id", "")
    try:
        facts = _fact_map(frame_population)
    except _Unresolved as exc:
        refs = _refs(
            (A18_AUTHORITY, f"strict-topology:component:{component_id}", *exc.refs)
        )
        return tuple(
            A18EndRestraintMaterialization(
                component_id=component_id,
                end_tag=end_tag,
                local_bending_axis=axis,
                disposition=A18_EXPLICIT_UNRESOLVED,
                alpha=None,
                numerator_column_i_over_l_m3=None,
                denominator_beam_i_over_l_m3=None,
                column_member_ids=(),
                beam_member_ids=(),
                source_refs=refs,
                unresolved_reasons=(exc.reason,),
            )
            for end_tag in ("BOTTOM", "TOP")
            for axis in ("M2", "M3")
        )

    return tuple(
        _one(
            target_column=target_column,
            topology=topology,
            facts=facts,
            end_tag=end_tag,
            axis=axis,
            local_axis_facts=frame_local_axes,
        )
        for end_tag in ("BOTTOM", "TOP")
        for axis in ("M2", "M3")
    )


__all__ = [
    "A18_AUTHORITY",
    "A18_EXPLICIT_UNRESOLVED",
    "A18_LOCAL_AXIS_AUTHORITY",
    "A18_READY",
    "A18EndRestraintMaterialization",
    "A18FrameLocalAxisEvidence",
    "A18InertiaBasis",
    "TS500_EQ716_BEAM_HALF_IG_REF",
    "TS500_EQ716_COLUMN_GROSS_IG_REF",
    "materialize_ts500_column_end_restraint_ratios",
]
