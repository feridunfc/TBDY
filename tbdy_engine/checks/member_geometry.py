"""B1 domain-owned beam/column formal geometry registrations.

This module is deliberately small: immutable rule registrations plus pure numeric
rule evaluation.  Applicability, Coverage and CheckResult status authority stay
in MinimalCheckEngine.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping


COLUMN_MIN_DIMENSION = "column_geometry_min_dimension"
BEAM_MIN_WIDTH = "beam_geometry_min_width"
BEAM_MIN_DEPTH_300 = "beam_geometry_min_depth"
BEAM_DEPTH_WIDTH_RATIO = "beam_depth_width_ratio"

COLUMN_SECTION_SHAPE_CONTEXT = "column_section_shape"
BEAM_7411_APPLICABILITY_CONTEXT = "tbdy_7_4_1_1_applicability"

LEGACY_COLUMN_ALIASES = MappingProxyType({
    "column_geometry_min_width": COLUMN_MIN_DIMENSION,
    "column_geometry_min_depth": COLUMN_MIN_DIMENSION,
})


@dataclass(frozen=True, slots=True)
class MemberGeometryRegistration:
    check_id: str
    component_type: str
    required_features: tuple[str, ...]
    required_execution_context: tuple[str, ...]
    limit: float
    comparison: str
    ratio_type: str
    unit: str
    code_ref: str
    formal_scope_note: str


@dataclass(frozen=True, slots=True)
class MemberGeometryRule:
    value: float
    limit: float
    ratio: float
    ratio_type: str
    unit: str
    is_satisfied: bool


COLUMN_REGISTRATIONS = (
    MemberGeometryRegistration(
        check_id=COLUMN_MIN_DIMENSION,
        component_type="column",
        required_features=("column_width_mm", "column_depth_mm"),
        required_execution_context=(COLUMN_SECTION_SHAPE_CONTEXT,),
        limit=300.0,
        comparison="minimum",
        ratio_type="actual_over_minimum",
        unit="mm",
        code_ref="TBDY-2018-7.3.1.1",
        formal_scope_note="Rectangular-column minimum section dimension only.",
    ),
)

BEAM_REGISTRATIONS = (
    MemberGeometryRegistration(
        check_id=BEAM_MIN_WIDTH,
        component_type="beam",
        required_features=("beam_width_mm",),
        required_execution_context=(BEAM_7411_APPLICABILITY_CONTEXT,),
        limit=250.0,
        comparison="minimum",
        ratio_type="actual_over_minimum",
        unit="mm",
        code_ref="TBDY-2018-7.4.1.1(a)",
        formal_scope_note="Beam web-width condition within proven §7.4.1.1 scope.",
    ),
    MemberGeometryRegistration(
        check_id=BEAM_MIN_DEPTH_300,
        component_type="beam",
        required_features=("beam_depth_mm",),
        required_execution_context=(BEAM_7411_APPLICABILITY_CONTEXT,),
        limit=300.0,
        comparison="minimum",
        ratio_type="actual_over_minimum",
        unit="mm",
        code_ref="TBDY-2018-7.4.1.1(b)",
        formal_scope_note="300-mm beam-height sub-condition only; not complete §7.4.1.1(b) compliance.",
    ),
    MemberGeometryRegistration(
        check_id=BEAM_DEPTH_WIDTH_RATIO,
        component_type="beam",
        required_features=("beam_depth_mm", "beam_width_mm"),
        required_execution_context=(BEAM_7411_APPLICABILITY_CONTEXT,),
        limit=3.5,
        comparison="maximum",
        ratio_type="value_over_maximum",
        unit="",
        code_ref="TBDY-2018-7.4.1.1(b)",
        formal_scope_note="h/bw upper-bound condition within proven §7.4.1.1 scope.",
    ),
)


def compose_member_registrations(
    *domains: Iterable[MemberGeometryRegistration],
) -> Mapping[str, MemberGeometryRegistration]:
    """Deterministically compose immutable domain registrations; duplicates are fatal."""
    ordered: dict[str, MemberGeometryRegistration] = {}
    for registration in sorted(
        (item for domain in domains for item in domain),
        key=lambda item: item.check_id,
    ):
        if registration.check_id in ordered:
            raise ValueError(f"Duplicate formal check ID: {registration.check_id}")
        ordered[registration.check_id] = registration
    return MappingProxyType(ordered)


MEMBER_GEOMETRY_REGISTRATIONS = compose_member_registrations(
    COLUMN_REGISTRATIONS,
    BEAM_REGISTRATIONS,
)
MEMBER_FORMAL_CHECK_IDS = frozenset(MEMBER_GEOMETRY_REGISTRATIONS)


def registration_check_definitions() -> Mapping[str, Mapping[str, Any]]:
    """Canonical check-definition overlay consumed by Coverage/MinimalCheckEngine."""
    return MappingProxyType({
        check_id: MappingProxyType({
            "element_type": registration.component_type,
            "category": "GEOMETRY",
            "required_features": registration.required_features,
            "required_execution_context": registration.required_execution_context,
            "code_ref": registration.code_ref,
            "formal_scope_note": registration.formal_scope_note,
        })
        for check_id, registration in MEMBER_GEOMETRY_REGISTRATIONS.items()
    })


def evaluate_member_rule(
    registration: MemberGeometryRegistration,
    variables: Mapping[str, Any],
) -> MemberGeometryRule:
    """Pure formula evaluation using the registration as the single numeric authority."""
    def number(name: str) -> float:
        value = variables.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"Required numeric feature is missing or non-numeric: {name}")
        return float(value)

    if registration.check_id == COLUMN_MIN_DIMENSION:
        value = min(number("column_width_mm"), number("column_depth_mm"))
    elif registration.check_id == BEAM_MIN_WIDTH:
        value = number("beam_width_mm")
    elif registration.check_id == BEAM_MIN_DEPTH_300:
        value = number("beam_depth_mm")
    elif registration.check_id == BEAM_DEPTH_WIDTH_RATIO:
        width = number("beam_width_mm")
        if width == 0.0:
            raise ZeroDivisionError("beam_width_mm is zero; depth/width ratio cannot be evaluated")
        value = number("beam_depth_mm") / width
    else:
        raise ValueError(f"No formal member geometry formula registered for {registration.check_id}")

    ratio = value / registration.limit
    satisfied = value >= registration.limit if registration.comparison == "minimum" else value <= registration.limit
    return MemberGeometryRule(
        value=value,
        limit=registration.limit,
        ratio=ratio,
        ratio_type=registration.ratio_type,
        unit=registration.unit,
        is_satisfied=satisfied,
    )


__all__ = [
    "BEAM_7411_APPLICABILITY_CONTEXT",
    "BEAM_DEPTH_WIDTH_RATIO",
    "BEAM_MIN_DEPTH_300",
    "BEAM_MIN_WIDTH",
    "BEAM_REGISTRATIONS",
    "COLUMN_MIN_DIMENSION",
    "COLUMN_REGISTRATIONS",
    "COLUMN_SECTION_SHAPE_CONTEXT",
    "LEGACY_COLUMN_ALIASES",
    "MEMBER_FORMAL_CHECK_IDS",
    "MEMBER_GEOMETRY_REGISTRATIONS",
    "MemberGeometryRegistration",
    "MemberGeometryRule",
    "compose_member_registrations",
    "evaluate_member_rule",
    "registration_check_definitions",
]
