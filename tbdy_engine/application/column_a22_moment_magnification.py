"""COLUMN-R1 A22 source-bound moment-magnification basis materialization.

This module owns no TS500 magnification formula.  It composes exact A19/A20/A21
state evidence with factual column mechanics and exact load-action provenance,
then delegates Eq.7.19-7.29 exclusively to
``design.columns.moment_magnification``.

The pre-B6 supported stiffness slice is TS500 Eq.7.21 because it can be built
from factual concrete ``Ec`` and gross concrete ``Ic`` without inventing a
reinforcement stiffness ``Is``.  Missing member-between-end horizontal-load
evidence fails closed; ``False`` is never manufactured as a default.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from tbdy_engine.application.column_a19_effective_length import (
    A19_READY,
    A19AxisEffectiveLengthMaterialization,
)
from tbdy_engine.application.column_a20_end_moment_ratio import (
    A20_READY,
    A20AxisEndMomentMaterialization,
)
from tbdy_engine.application.column_a21_slenderness import (
    A21_READY,
    A21StateSlendernessMaterialization,
)
from tbdy_engine.design.columns.column_design_demand_engine import ColumnComboDefinition
from tbdy_engine.design.columns.moment_magnification import (
    STIFFNESS_METHOD_EQ_7_21,
    ColumnMomentMagnificationAxisBasis,
    ColumnMomentMagnificationAxisResult,
    evaluate_ts500_axis_moment_magnification,
)
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.design.columns.slenderness import (
    GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED,
    MOMENT_MAGNIFICATION_REQUIRED,
    SWAY_PERMITTED,
)
from tbdy_engine.design.columns.stability_action_basis import (
    StabilityActionSource,
    TS500_ACTION_G,
)
from tbdy_engine.providers.etabs_frame_eq713_population_provider import FrameEq713FactualFact
from tbdy_engine.providers.frame_section_inertia_normalization import (
    normalize_frame_section_inertia_m4,
)

A22_READY = "READY"
A22_NOT_REQUIRED = "NOT_REQUIRED"
A22_EXPLICIT_UNRESOLVED = "EXPLICIT_UNRESOLVED"
A22_REANALYSIS_REQUIRED = "REANALYSIS_REQUIRED"
A22_AUTHORITY = "COLUMN_R1_A22_TS500_MOMENT_MAGNIFICATION_COMPOSITION"
A22_EQ721_POLICY_AUTHORITY = "COLUMN_R1_PRE_B6_TS500_EQ7.21_FACTUAL_EC_GROSS_IC_POLICY"
A22_HORIZONTAL_LOAD_AUTHORITY = "COLUMN_R1_MEMBER_BETWEEN_END_HORIZONTAL_LOAD_EVIDENCE"


@dataclass(frozen=True, slots=True)
class A22HorizontalLoadEvidence:
    axis: str
    horizontal_load_between_ends: bool
    source_refs: tuple[str, ...]
    authority: str = A22_HORIZONTAL_LOAD_AUTHORITY

    def __post_init__(self) -> None:
        if self.axis not in {"M2", "M3"}:
            raise ValueError("axis must be M2 or M3")
        if type(self.horizontal_load_between_ends) is not bool:
            raise TypeError("horizontal_load_between_ends must be bool")
        if self.authority != A22_HORIZONTAL_LOAD_AUTHORITY:
            raise ValueError("unsupported horizontal-load evidence authority")
        if not self.source_refs or len(self.source_refs) != len(set(self.source_refs)):
            raise ValueError("horizontal-load source_refs must be nonempty and unique")


@dataclass(frozen=True, slots=True)
class A22AxisStateMaterialization:
    component_id: str
    demand_state_id: str
    output_case: str
    end_tag: str
    local_bending_axis: str
    disposition: str
    basis: ColumnMomentMagnificationAxisBasis | None
    result: ColumnMomentMagnificationAxisResult | None
    source_refs: tuple[str, ...]
    unresolved_reasons: tuple[str, ...] = ()
    authority: str = A22_AUTHORITY


@dataclass(frozen=True, slots=True)
class A22MomentMagnificationMaterialization:
    component_id: str
    rows: tuple[A22AxisStateMaterialization, ...]
    source_refs: tuple[str, ...]
    authority: str = A22_AUTHORITY

    @property
    def reanalysis_required(self) -> bool:
        return any(row.disposition == A22_REANALYSIS_REQUIRED for row in self.rows)

    @property
    def unresolved(self) -> bool:
        return any(row.disposition == A22_EXPLICIT_UNRESOLVED for row in self.rows)

    @property
    def bases(self) -> tuple[ColumnMomentMagnificationAxisBasis, ...]:
        return tuple(row.basis for row in self.rows if row.basis is not None)


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if isinstance(value, str) and value.strip()))


def _one_a19(rows: Sequence[A19AxisEffectiveLengthMaterialization], axis: str):
    matches = tuple(row for row in rows if row.local_bending_axis == axis)
    if len(matches) != 1 or matches[0].disposition != A19_READY:
        raise ValueError(f"A19_NOT_READY:{axis}")
    return matches[0]


def _one_a20(rows: Sequence[A20AxisEndMomentMaterialization], output_case: str, axis: str):
    matches = tuple(
        row for row in rows
        if row.output_case == output_case and row.local_bending_axis == axis
    )
    if len(matches) != 1 or matches[0].disposition != A20_READY or matches[0].evidence is None:
        raise ValueError(f"A20_NOT_READY:{output_case}:{axis}")
    return matches[0]


def _one_a21(rows: Sequence[A21StateSlendernessMaterialization], output_case: str):
    matches = tuple(row for row in rows if row.output_case == output_case)
    if len(matches) != 1 or matches[0].disposition != A21_READY or matches[0].result is None:
        raise ValueError(f"A21_NOT_READY:{output_case}")
    return matches[0]


def _horizontal(
    evidences: Sequence[A22HorizontalLoadEvidence],
    axis: str,
) -> A22HorizontalLoadEvidence:
    matches = tuple(item for item in evidences if item.axis == axis)
    if len(matches) != 1:
        raise ValueError(f"HORIZONTAL_LOAD_BETWEEN_ENDS_EVIDENCE_REQUIRED:{axis}")
    return matches[0]


def _column_mechanics(
    fact: FrameEq713FactualFact,
    axis: str,
) -> tuple[float, float, tuple[str, ...]]:
    ec = float(fact.factual_ec_mpa)
    if ec <= 0.0:
        raise ValueError("FACTUAL_EC_NOT_POSITIVE")
    mechanics = fact.section_mechanics
    if mechanics is None or not mechanics.success:
        raise ValueError("FACTUAL_SECTION_MECHANICS_NOT_READY")
    raw = mechanics.inertia_22 if axis == "M2" else mechanics.inertia_33
    if raw is None or float(raw) <= 0.0:
        raise ValueError(f"FACTUAL_GROSS_INERTIA_NOT_READY:{axis}")
    base = fact.base_fact
    normalized = normalize_frame_section_inertia_m4(
        raw,
        base.present_length_unit,
        source_ref=mechanics.evidence_ref,
    )
    return (
        ec,
        normalized.inertia_m4 * 1.0e12,
        _refs(
            (
                *fact.source_refs,
                mechanics.evidence_ref,
                normalized.source_ref,
                normalized.authority,
                A22_EQ721_POLICY_AUTHORITY,
            )
        ),
    )


def _combo_by_name(definitions: Sequence[ColumnComboDefinition]) -> Mapping[str, ColumnComboDefinition]:
    result: dict[str, ColumnComboDefinition] = {}
    for definition in definitions:
        if definition.name in result:
            raise ValueError(f"DUPLICATE_COMBO_DEFINITION:{definition.name}")
        result[definition.name] = definition
    return result


def _permanent_case_names(actions: Sequence[StabilityActionSource]) -> frozenset[str]:
    names = frozenset(item.case_name for item in actions if item.action_role == TS500_ACTION_G)
    if not names:
        raise ValueError("NO_SOURCE_BOUND_PERMANENT_G_CASE")
    return names


def _creep_ratio(
    *,
    state: ColumnDemandState,
    definition: ColumnComboDefinition,
    case_demands: Sequence[ColumnDemandState],
    permanent_names: frozenset[str],
) -> tuple[float, tuple[str, ...]]:
    if state.nd_compression_n <= 0.0:
        raise ValueError(f"NONPOSITIVE_COMPRESSION_FOR_MAGNIFICATION:{state.state_id}")
    permanent = 0.0
    refs: list[str] = []
    for term in definition.constituents:
        if term.cname_type != "LOAD_CASE" or term.name not in permanent_names:
            continue
        matches = tuple(
            row for row in case_demands
            if row.component_id == state.component_id
            and row.output_case == term.name
            and row.end_tag == state.end_tag
            and row.case_type == "LinStatic"
        )
        if len(matches) != 1:
            raise ValueError(
                f"PERMANENT_G_CASE_DEMAND_NOT_EXACT:{state.state_id}:{term.name}:{state.end_tag}"
            )
        row = matches[0]
        permanent += float(term.scale_factor) * row.nd_compression_n
        refs.extend((row.source_identity, f"PERMANENT_G_TERM:{definition.name}:{term.name}:{term.scale_factor:g}"))
    ratio = permanent / state.nd_compression_n
    if ratio < -1.0e-12 or ratio > 1.0 + 1.0e-12:
        raise ValueError(f"CREEP_RATIO_OUTSIDE_0_1:{state.state_id}:{ratio:.12g}")
    return max(0.0, min(1.0, ratio)), _refs(tuple(refs))


def materialize_ts500_moment_magnification(
    *,
    component_id: str,
    minimum_eccentricity_states: Sequence[ColumnDemandState],
    combo_definitions: Sequence[ColumnComboDefinition],
    constituent_case_demands: Sequence[ColumnDemandState],
    action_sources: Sequence[StabilityActionSource],
    target_frame_fact: FrameEq713FactualFact,
    a19_rows: Sequence[A19AxisEffectiveLengthMaterialization],
    a20_rows: Sequence[A20AxisEndMomentMaterialization],
    a21_rows: Sequence[A21StateSlendernessMaterialization],
    horizontal_load_evidence: Sequence[A22HorizontalLoadEvidence] = (),
) -> A22MomentMagnificationMaterialization:
    """Build/evaluate exact-state A22 bases; never magnify a different P/M state."""
    states = tuple(minimum_eccentricity_states)
    definitions = _combo_by_name(combo_definitions)
    permanent_names = _permanent_case_names(action_sources)
    common_refs = _refs(
        (
            A22_AUTHORITY,
            A22_EQ721_POLICY_AUTHORITY,
            *tuple(ref for item in action_sources for ref in item.source_refs),
        )
    )
    output: list[A22AxisStateMaterialization] = []

    for state in states:
        if state.component_id != component_id:
            raise ValueError("minimum-eccentricity state component_id mismatch")
        definition = definitions.get(state.output_case)
        for axis in ("M2", "M3"):
            row_refs = list(common_refs)
            try:
                a21 = _one_a21(a21_rows, state.output_case)
                slender = a21.result.m2 if axis == "M2" else a21.result.m3
                row_refs.extend(a21.source_refs)
                if slender.status == GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED:
                    output.append(
                        A22AxisStateMaterialization(
                            component_id=component_id,
                            demand_state_id=state.state_id,
                            output_case=state.output_case,
                            end_tag=state.end_tag,
                            local_bending_axis=axis,
                            disposition=A22_REANALYSIS_REQUIRED,
                            basis=None,
                            result=None,
                            source_refs=_refs(tuple(row_refs)),
                            unresolved_reasons=("TS500_7.6.1_GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED",),
                        )
                    )
                    continue
                if slender.status != MOMENT_MAGNIFICATION_REQUIRED:
                    output.append(
                        A22AxisStateMaterialization(
                            component_id=component_id,
                            demand_state_id=state.state_id,
                            output_case=state.output_case,
                            end_tag=state.end_tag,
                            local_bending_axis=axis,
                            disposition=A22_NOT_REQUIRED,
                            basis=None,
                            result=None,
                            source_refs=_refs(tuple(row_refs)),
                        )
                    )
                    continue
                if definition is None:
                    raise ValueError(f"MISSING_COMBO_DEFINITION:{state.output_case}")
                a19 = _one_a19(a19_rows, axis)
                a20 = _one_a20(a20_rows, state.output_case, axis)
                horizontal = _horizontal(horizontal_load_evidence, axis)
                row_refs.extend((*a19.source_refs, *a20.source_refs, *horizontal.source_refs))
                if a19.sway_classification == SWAY_PERMITTED:
                    raise ValueError(
                        f"SWAY_PERMITTED_STORY_MAGNIFICATION_AGGREGATES_NOT_MATERIALIZED:{axis}"
                    )
                if slender.radius_of_gyration_i_mm is None or a19.effective_length_lk_mm is None:
                    raise ValueError(f"SLENDERNESS_GEOMETRY_NOT_RESOLVED:{axis}")
                ec_mpa, ic_mm4, mechanics_refs = _column_mechanics(target_frame_fact, axis)
                row_refs.extend(mechanics_refs)
                rm, rm_refs = _creep_ratio(
                    state=state,
                    definition=definition,
                    case_demands=constituent_case_demands,
                    permanent_names=permanent_names,
                )
                row_refs.extend(rm_refs)
                basis = ColumnMomentMagnificationAxisBasis(
                    demand_state_id=state.state_id,
                    axis=axis,
                    sway_classification=str(a19.sway_classification),
                    nd_compression_n=state.nd_compression_n,
                    m1_over_m2=a20.evidence.moment_ratio_m1_over_m2,
                    effective_length_lk_mm=a19.effective_length_lk_mm,
                    radius_i_mm=slender.radius_of_gyration_i_mm,
                    ec_mpa=ec_mpa,
                    ic_mm4=ic_mm4,
                    creep_ratio_rm=rm,
                    stiffness_method=STIFFNESS_METHOD_EQ_7_21,
                    horizontal_load_between_ends=horizontal.horizontal_load_between_ends,
                    source_refs=_refs((*tuple(row_refs), state.source_identity)),
                )
                result = evaluate_ts500_axis_moment_magnification(basis)
                if not result.applied:
                    raise ValueError(
                        f"MAGNIFICATION_OWNER_BLOCKED:{state.state_id}:{axis}:"
                        + ",".join(result.blockers)
                    )
                output.append(
                    A22AxisStateMaterialization(
                        component_id=component_id,
                        demand_state_id=state.state_id,
                        output_case=state.output_case,
                        end_tag=state.end_tag,
                        local_bending_axis=axis,
                        disposition=A22_READY,
                        basis=basis,
                        result=result,
                        source_refs=_refs((*basis.source_refs, *result.source_refs, result.authority)),
                    )
                )
            except (TypeError, ValueError) as exc:
                output.append(
                    A22AxisStateMaterialization(
                        component_id=component_id,
                        demand_state_id=state.state_id,
                        output_case=state.output_case,
                        end_tag=state.end_tag,
                        local_bending_axis=axis,
                        disposition=A22_EXPLICIT_UNRESOLVED,
                        basis=None,
                        result=None,
                        source_refs=_refs(tuple(row_refs)),
                        unresolved_reasons=(str(exc),),
                    )
                )

    rows = tuple(output)
    return A22MomentMagnificationMaterialization(
        component_id=component_id,
        rows=rows,
        source_refs=_refs(tuple(ref for row in rows for ref in row.source_refs)),
    )


__all__ = [
    "A22_AUTHORITY",
    "A22_EQ721_POLICY_AUTHORITY",
    "A22_EXPLICIT_UNRESOLVED",
    "A22_HORIZONTAL_LOAD_AUTHORITY",
    "A22_NOT_REQUIRED",
    "A22_READY",
    "A22_REANALYSIS_REQUIRED",
    "A22AxisStateMaterialization",
    "A22HorizontalLoadEvidence",
    "A22MomentMagnificationMaterialization",
    "materialize_ts500_moment_magnification",
]
