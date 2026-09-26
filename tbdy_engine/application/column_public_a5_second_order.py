"""Canonical PUBLIC-A5 A17-A23 second-order composition for FND-COL-2.

This module owns application composition only.  Engineering equations remain in
existing A17-A23/design authorities.  Missing source-bound facts are encoded as
canonical typed blockers; they never become defaults and they do not prevent the
existing FND-COL-2 lifecycle from receiving a truthful payload.
"""
from __future__ import annotations

from typing import Sequence

from tbdy_engine.application.column_a18_end_restraint import A18_READY
from tbdy_engine.application.column_a19_effective_length import (
    A19_READY,
    materialize_ts500_effective_lengths,
)
from tbdy_engine.application.column_a20_end_moment_ratio import (
    A20_READY,
    materialize_exact_static_end_moment_ratios,
)
from tbdy_engine.application.column_a21_slenderness import (
    A21_READY,
    materialize_ts500_slenderness_decisions,
)
from tbdy_engine.application.column_a22_moment_magnification import (
    A22HorizontalLoadEvidence,
    materialize_ts500_moment_magnification,
)
from tbdy_engine.application.column_a23_design_demands import (
    build_a23_pre_magnification_population,
    materialize_canonical_concurrent_design_demands,
)
from tbdy_engine.application.column_design_basis import (
    BoundColumnActionFamilyApplicability,
)
from tbdy_engine.application.column_fnd2_second_order_payload import (
    build_canonical_second_order_fnd2_payload,
)
from tbdy_engine.application.column_local_sway_runtime import (
    STATUS_READY as A17_READY,
    compose_column_local_axis_sway_runtime,
)
from tbdy_engine.application.column_route_c_direction_binding import (
    resolve_route_c_source_bound_directions,
)
from tbdy_engine.application.column_stability_runtime import (
    compose_story_stability_candidate_runtime,
)
from tbdy_engine.design.columns.column_design_demand_engine import ColumnComboDefinition
from tbdy_engine.design.columns.combo_pattern_engine import ComboPatternConstituent
from tbdy_engine.design.columns.free_length_basis import ColumnFreeLengthResolution
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.design.columns.stability_combo_basis import (
    FlattenedLinearCombo,
    resolve_existing_ts500_stability_combos,
)
from tbdy_engine.design.columns.story_relative_translation import (
    ReviewedStoryTranslationTolerance,
)
from tbdy_engine.features.column_shear_topology import (
    ColumnTopologyEvidence,
    StrictColumnTopologyBundle,
)
from tbdy_engine.integration.etabs_analysis_execution import AnalysisExecutionResult
from tbdy_engine.etabs.safety import read_verified_unit_snapshot
from tbdy_engine.etabs.source_units import decode_csi_length_unit
from tbdy_engine.providers.etabs_frame_eq713_population_provider import (
    FrameEq713FactualPopulation,
)
from tbdy_engine.providers.etabs_static_linear_case_provider import (
    capture_etabs_static_linear_cases_from_session,
)
from tbdy_engine.providers.etabs_ts500_stability_action_provider import (
    promote_etabs_static_cases_to_ts500_stability_actions,
)
from tbdy_engine.regulatory.contracts import ApplicabilityState

PUBLIC_A5_SECOND_ORDER_AUTHORITY = "COLUMN_R1_PUBLIC_A5_CANONICAL_SECOND_ORDER_COMPOSITION"

ROUTE_C_W_ACTION_SOURCE_BLOCKER = (
    "ROUTE_C_W_ACTION_SOURCE_NOT_PROVEN"
)

ROUTE_C_W_DIRECTION_BLOCKER_PREFIX = (
    "ROUTE_C_W_DIRECTION_SOURCE_BOUND_EVIDENCE_NOT_AVAILABLE:"
)


def _reviewed_displacement_unit_from_session(session) -> str:
    unit_snapshot = read_verified_unit_snapshot(session)
    return decode_csi_length_unit(
        unit_snapshot.present_length_unit
    ).value


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if isinstance(value, str) and value.strip()))


def _block(
    *,
    component_id: str,
    blockers: Sequence[str],
    refs: Sequence[str],
) -> dict[str, object]:
    return build_canonical_second_order_fnd2_payload(
        component_id=component_id,
        upstream_blockers=tuple(dict.fromkeys(blockers)),
        upstream_source_refs=_refs((PUBLIC_A5_SECOND_ORDER_AUTHORITY, *refs)),
    )


def _combo_definitions(
    flattened_combos: Sequence[tuple[str, Sequence[tuple[str, float]]]],
) -> tuple[ColumnComboDefinition, ...]:
    return tuple(
        ColumnComboDefinition(
            name=combo_name,
            combo_type="LINEAR_ADD",
            constituents=tuple(
                ComboPatternConstituent(
                    name=case_name,
                    scale_factor=float(scale),
                    cname_type="LOAD_CASE",
                )
                for case_name, scale in leaves
            ),
        )
        for combo_name, leaves in flattened_combos
    )


def _flattened_stability_combos(
    flattened_combos: Sequence[tuple[str, Sequence[tuple[str, float]]]],
) -> tuple[FlattenedLinearCombo, ...]:
    return tuple(
        FlattenedLinearCombo(
            name=combo_name,
            constituents=tuple((case_name, float(scale)) for case_name, scale in leaves),
            source_refs=(f"ETABS:RespCombo:{combo_name}", PUBLIC_A5_SECOND_ORDER_AUTHORITY),
        )
        for combo_name, leaves in flattened_combos
    )


def _target_frame_fact(frame_population: FrameEq713FactualPopulation, target_uid: str):
    matches = tuple(row for row in frame_population.rows if row.frame_name == target_uid)
    if len(matches) != 1:
        raise ValueError(f"TARGET_FRAME_FACT_NOT_UNIQUE:{target_uid}:{len(matches)}")
    return matches[0]


def _static_case_names(
    demand_states: Sequence[ColumnDemandState],
    *,
    additional_case_names: Sequence[str] = (),
) -> tuple[str, ...]:
    additional = tuple(additional_case_names)

    if (
        len(additional) != len(set(additional))
        or any(
            not isinstance(name, str)
            or not name.strip()
            or name != name.strip()
            for name in additional
        )
    ):
        raise ValueError(
            "QUALIFIED_RESPONSE_STATIC_CASE_NAMES_NOT_CANONICAL"
        )

    names = tuple(
        sorted(
            {
                row.output_case
                for row in demand_states
                if row.case_type == "LinStatic"
            }
            | set(additional)
        )
    )

    if not names:
        raise ValueError("NO_FACTUAL_LINEAR_STATIC_CASE_DEMANDS")

    return names


def _partition_end_moment_ratio_capability(
    design_demands,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
]:
    """Partition supported outputs without manufacturing RS physical end signs."""
    exact_static: list[str] = []
    supported_nonexact: list[str] = []

    for combo in design_demands.combo_results:
        name = combo.definition.name

        if combo.build is None:
            raise ValueError(
                f"A20_COMBO_BUILD_NOT_AVAILABLE:"
                f"{name}"
            )

        states = tuple(
            combo.build.states
        )

        if not states:
            raise ValueError(
                f"A20_COMBO_STATE_POPULATION_EMPTY:"
                f"{name}"
            )

        case_types = {
            state.case_type
            for state in states
        }

        if (
            case_types
            == {"DesignStaticLinearExact"}
        ):
            exact_static.append(
                name
            )

        elif (
            case_types
            ==
            {"DesignResponseSpectrumPermutation"}
        ):
            supported_nonexact.append(
                name
            )

        else:
            raise ValueError(
                "A20_UNSUPPORTED_END_MOMENT_STATE_TYPES:"
                f"{name}:"
                + ",".join(
                    sorted(case_types)
                )
            )

    return (
        tuple(
            sorted(exact_static)
        ),
        tuple(
            sorted(supported_nonexact)
        ),
    )


def build_public_a5_canonical_second_order_payload(
    *,
    component_id: str,
    session,
    topology: StrictColumnTopologyBundle,
    target_column: ColumnTopologyEvidence,
    frame_population: FrameEq713FactualPopulation,
    flattened_combos: Sequence[tuple[str, Sequence[tuple[str, float]]]],
    constituent_case_demands: Sequence[ColumnDemandState],
    a18_rows: Sequence[object],
    free_length: ColumnFreeLengthResolution | None,
    analysis_execution: AnalysisExecutionResult,
    route_c_w_applicability: BoundColumnActionFamilyApplicability | None = None,
    qualified_response_static_case_names: Sequence[str] = (),
    qualified_response_static_source_refs: Sequence[str] = (),
    reviewed_story_translation_tolerance: ReviewedStoryTranslationTolerance | None = None,
    horizontal_load_evidence: Sequence[A22HorizontalLoadEvidence] = (),
) -> dict[str, object]:
    """Compose canonical A17-A23 evidence and encode it for the existing FND2 key.

    Current production may legitimately stop at source-bound Route-C direction
    or A22 intermediate-load evidence.  Such stops are encoded in the typed
    payload rather than converted into application-level acquisition failure.
    """
    blockers: list[str] = []
    refs: list[str] = [PUBLIC_A5_SECOND_ORDER_AUTHORITY]

    if (
        route_c_w_applicability is not None
        and not isinstance(
            route_c_w_applicability,
            BoundColumnActionFamilyApplicability,
        )
    ):
        raise TypeError(
            "route_c_w_applicability must be "
            "BoundColumnActionFamilyApplicability or None"
        )

    if route_c_w_applicability is None:
        w_applicability_state = (
            ApplicabilityState.UNRESOLVED
        )
    else:
        w_applicability_state = (
            route_c_w_applicability.state
        )

        refs.extend(
            route_c_w_applicability.source_refs
        )

    if (
        w_applicability_state
        is ApplicabilityState.UNRESOLVED
    ):
        blockers.append(
            "A17:ROUTE_C_W_APPLICABILITY_UNRESOLVED"
        )

    elif (
        w_applicability_state
        is ApplicabilityState.INVALID_CONTEXT
    ):
        blockers.append(
            "A17:ROUTE_C_W_APPLICABILITY_INVALID_CONTEXT"
        )

    a18 = tuple(a18_rows)
    refs.extend(ref for row in a18 for ref in getattr(row, "source_refs", ()))
    if len(a18) != 4:
        blockers.append(f"A18_END_RESTRAINT_POPULATION_NOT_EXACT:{len(a18)}")
    for row in a18:
        if getattr(row, "disposition", None) != A18_READY:
            reasons = tuple(getattr(row, "unresolved_reasons", ()) or (getattr(row, "disposition", "UNRESOLVED"),))
            blockers.extend(
                f"A18:{getattr(row, 'end_tag', 'UNKNOWN')}:{getattr(row, 'local_bending_axis', 'UNKNOWN')}:{reason}"
                for reason in reasons
            )

    if free_length is None:
        blockers.append("A19:TS500_REGULATORY_FREE_LENGTH_NOT_MATERIALIZED")
    else:
        refs.extend(free_length.source_refs)
        if not free_length.resolved:
            blockers.append(f"A19:{free_length.status}")

    states = tuple(constituent_case_demands)

    qualified_response_static_names = tuple(
        qualified_response_static_case_names
    )
    qualified_response_static_refs = _refs(
        qualified_response_static_source_refs
    )

    if (
        qualified_response_static_names
        and not qualified_response_static_refs
    ):
        blockers.append(
            "A17:QUALIFIED_RESPONSE_STATIC_CASE_SCOPE_SOURCE_NOT_PROVEN"
        )

    refs.extend(qualified_response_static_refs)

    try:
        static_names = _static_case_names(
            states,
            additional_case_names=qualified_response_static_names,
        )
        route_c = resolve_route_c_source_bound_directions(
            session=session,
            static_case_names=static_names,
        )
        refs.extend(route_c.source_refs)

        route_c_blockers = tuple(
            route_c.blockers
        )

        if (
            w_applicability_state
            is ApplicabilityState.PROVEN_NOT_APPLICABLE
        ):
            factual_w_direction_blockers = tuple(
                item
                for item in route_c_blockers
                if item.startswith(
                    ROUTE_C_W_DIRECTION_BLOCKER_PREFIX
                )
            )

            blockers.extend(
                (
                    "A17:"
                    "ROUTE_C_W_APPLICABILITY_CONFLICT_"
                    "FACTUAL_W_SOURCE_PRESENT:"
                    + item[
                        len(
                            ROUTE_C_W_DIRECTION_BLOCKER_PREFIX
                        ):
                    ]
                )
                for item
                in factual_w_direction_blockers
            )

        if (
            w_applicability_state
            is not ApplicabilityState.APPLIES
        ):
            route_c_blockers = tuple(
                item
                for item in route_c_blockers
                if (
                    item
                    != ROUTE_C_W_ACTION_SOURCE_BLOCKER
                    and not item.startswith(
                        ROUTE_C_W_DIRECTION_BLOCKER_PREFIX
                    )
                )
            )

        blockers.extend(
            f"A17:{item}"
            for item in route_c_blockers
        )
    except Exception as exc:
        blockers.append(f"A17:ROUTE_C_DIRECTION_MATERIALIZATION_FAILED:{exc}")
        route_c = None
        static_names = ()

    # The currently known W-direction gap lands here.  Do not postpone FND2:
    # send the canonical typed blocker payload through the existing lifecycle.
    if blockers:
        return _block(component_id=component_id, blockers=blockers, refs=refs)

    if reviewed_story_translation_tolerance is None:
        return _block(
            component_id=component_id,
            blockers=("A17:REVIEWED_STORY_TRANSLATION_TOLERANCE_NOT_BOUND",),
            refs=refs,
        )
    assert route_c is not None

    if {
        item.global_direction
        for item in route_c.bindings
    } != {"X", "Y"}:
        return _block(
            component_id=component_id,
            blockers=(
                "A17:"
                "ROUTE_C_REQUIRED_DIRECTION_SET_NOT_PROVEN",
            ),
            refs=refs,
        )

    assert free_length is not None and free_length.resolved

    try:
        static_cases = capture_etabs_static_linear_cases_from_session(session, static_names)
        promotion = promote_etabs_static_cases_to_ts500_stability_actions(static_cases)
        actions = promotion.promoted_sources
        refs.append(promotion.authority)
        refs.extend(ref for source in actions for ref in source.source_refs)
        stability_combos = resolve_existing_ts500_stability_combos(
            _flattened_stability_combos(flattened_combos),
            actions,
        )
        refs.extend(
            stability_combos.source_refs
        )

        if (
            w_applicability_state
            is ApplicabilityState.PROVEN_NOT_APPLICABLE
        ):
            if not stability_combos.gqe_candidates:
                return _block(
                    component_id=component_id,
                    blockers=(
                        f"A17:{stability_combos.status}",
                    ),
                    refs=refs,
                )

            candidates = tuple(
                stability_combos.gqe_candidates
            )

        else:
            if not stability_combos.both_bases_present:
                return _block(
                    component_id=component_id,
                    blockers=(
                        f"A17:{stability_combos.status}",
                    ),
                    refs=refs,
                )

            candidates = (
                *stability_combos.gqe_candidates,
                *stability_combos.gqw_candidates,
            )

        binding_by_case = {
            item.case_name: item
            for item in route_c.bindings
        }
        reviewed_displacement_unit = _reviewed_displacement_unit_from_session(session)
        refs.append(
            f"ETABS:PresentLengthUnit:{reviewed_displacement_unit}"
        )
        runtimes = []
        for candidate in candidates:
            direction = binding_by_case.get(candidate.horizontal_case_name)
            if direction is None:
                return _block(
                    component_id=component_id,
                    blockers=(f"A17:DIRECTION_BINDING_MISSING:{candidate.horizontal_case_name}",),
                    refs=refs,
                )
            runtimes.append(
                compose_story_stability_candidate_runtime(
                    session,
                    topology=topology,
                    analysis_execution=analysis_execution,
                    candidate=candidate,
                    direction_binding=direction,
                    story=target_column.story,
                    reference_component_id=component_id,
                    translation_tolerance=reviewed_story_translation_tolerance,
                    reviewed_displacement_unit=reviewed_displacement_unit,
                    reviewed_force_unit="kN",
                    uncracked_basis_refs=(
                        analysis_execution.analysis_result_identity.parent_analysis_state_ref,
                        *frame_population.source_refs,
                    ),
                )
            )
        local_sway = compose_column_local_axis_sway_runtime(
            topology=topology,
            component_id=component_id,
            story=target_column.story,
            candidate_runtimes=tuple(runtimes),
            route_c_w_applicability=route_c_w_applicability,
        )
        refs.extend(local_sway.source_refs)
        if local_sway.status != A17_READY:
            return _block(
                component_id=component_id,
                blockers=(f"A17:{local_sway.status}",),
                refs=refs,
            )

        a19 = materialize_ts500_effective_lengths(
            component_id=component_id,
            a18_rows=tuple(a18),
            local_sway=local_sway,
            free_length=free_length,
        )
        refs.extend(ref for row in a19 for ref in row.source_refs)
        unresolved_a19 = tuple(row for row in a19 if row.disposition != A19_READY)
        if unresolved_a19:
            return _block(
                component_id=component_id,
                blockers=tuple(
                    f"A19:{row.local_bending_axis}:{reason}"
                    for row in unresolved_a19
                    for reason in (row.unresolved_reasons or (row.disposition,))
                ),
                refs=refs,
            )

        definitions = _combo_definitions(flattened_combos)
        design_demands, minimum = build_a23_pre_magnification_population(
            component_id=component_id,
            combo_definitions=definitions,
            constituent_case_demands=states,
            width_mm=float(target_column.width_t2_m * 1000.0),
            depth_mm=float(target_column.depth_t3_m * 1000.0),
        )
        if not design_demands.combination_scope_resolved:
            return _block(
                component_id=component_id,
                blockers=tuple(
                    f"A23:COMBINATION_SCOPE:{name}" for name in design_demands.blocked_combo_names
                ),
                refs=refs,
            )
        exact_combo_names, nonexact_combo_names = (
            _partition_end_moment_ratio_capability(
                design_demands
            )
        )

        qualified_output_case_names = tuple(
            sorted(
                (
                    *exact_combo_names,
                    *nonexact_combo_names,
                )
            )
        )

        if not qualified_output_case_names:
            raise ValueError(
                "A21_NO_SUPPORTED_DESIGN_OUTPUT_CASES"
            )

        # A20 remains exact-static only.
        # RS states are NOT promoted into physical signed end pairs.
        if exact_combo_names:
            a20 = (
                materialize_exact_static_end_moment_ratios(
                    component_id=component_id,

                    demand_states=(
                        design_demands.promoted_states
                    ),

                    qualified_static_case_names=(
                        exact_combo_names
                    ),

                    analysis_result_ref=(
                        analysis_execution
                        .analysis_result_identity
                        .identity_ref
                    ),

                    execution_proof_ref=(
                        analysis_execution
                        .execution_proof_ref
                    ),

                    case_scope_refs=(
                        analysis_execution
                        .analysis_result_identity
                        .parent_analysis_state_ref,

                        *refs,
                    ),
                )
            )
        else:
            a20 = ()

        refs.extend(
            ref
            for row in a20
            for ref in row.source_refs
        )

        # A20 is NOT a universal prerequisite.
        #
        # A21 owns ratio-independent progress where TS500 permits it.
        a21 = (
            materialize_ts500_slenderness_decisions(
                target_column=target_column,

                a19_rows=a19,

                a20_rows=a20,

                qualified_output_case_names=(
                    qualified_output_case_names
                ),
            )
        )

        refs.extend(
            ref
            for row in a21
            for ref in row.source_refs
        )

        unresolved_a21 = tuple(
            row
            for row in a21
            if row.disposition != A21_READY
        )

        if unresolved_a21:
            return _block(
                component_id=component_id,

                blockers=tuple(
                    (
                        f"A21:{row.output_case}:"
                        f"{reason}"
                    )
                    for row in unresolved_a21
                    for reason in (
                        row.unresolved_reasons
                        or (
                            row.disposition,
                        )
                    )
                ),

                refs=refs,
            )

        target_fact = _target_frame_fact(frame_population, target_column.unique_name)
        a22 = materialize_ts500_moment_magnification(
            component_id=component_id,
            minimum_eccentricity_states=minimum.states,
            combo_definitions=definitions,
            constituent_case_demands=states,
            action_sources=actions,
            target_frame_fact=target_fact,
            a19_rows=a19,
            a20_rows=a20,
            a21_rows=a21,
            horizontal_load_evidence=tuple(horizontal_load_evidence),
        )
        a23 = materialize_canonical_concurrent_design_demands(
            component_id=component_id,
            design_demands=design_demands,
            minimum_eccentricity=minimum,
            a21_rows=a21,
            a22=a22,
            analysis_result_ref=analysis_execution.analysis_result_identity.identity_ref,
            execution_proof_ref=analysis_execution.execution_proof_ref,
            source_model_ref=analysis_execution.analysis_result_identity.parent_analysis_state_ref,
        )
        return build_canonical_second_order_fnd2_payload(
            component_id=component_id,
            upstream_source_refs=_refs((PUBLIC_A5_SECOND_ORDER_AUTHORITY, *refs)),
            a21_rows=a21,
            a22=a22,
            a23=a23,
        )
    except Exception as exc:
        return _block(
            component_id=component_id,
            blockers=(f"CANONICAL_SECOND_ORDER_COMPOSITION_FAILED:{exc}",),
            refs=refs,
        )


__all__ = [
    "PUBLIC_A5_SECOND_ORDER_AUTHORITY",
    "build_public_a5_canonical_second_order_payload",
]
