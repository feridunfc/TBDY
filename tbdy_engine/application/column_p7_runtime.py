"""A37 production composition for existing VS6-P7 Column shear authority.

Application sequencing only.  No P7 formula, governing-row heuristic,
second result-table read, or transverse-cage inference is owned here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.application.column_longitudinal_runtime import (
    ColumnLongitudinalRuntimeComposition,
)
from tbdy_engine.design.columns.free_length_basis import ColumnFreeLengthResolution
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.etabs.safety import read_verified_unit_snapshot
from tbdy_engine.features.column_shear_demand_evidence import (
    ColumnShearDemandEvidenceBundle,
    build_column_shear_demand_evidence,
    resolve_etabs_present_force_unit,
    resolve_etabs_present_length_unit,
)
from tbdy_engine.integration.etabs_analysis_execution import AnalysisExecutionResult
from tbdy_engine.integration.live_etabs_acquisition_context import (
    TrustedLiveAcquisitionContext,
)
from tbdy_engine.regulatory.vs6_column_shear_p7_integration import (
    ColumnShearCapacityStateSelection,
    ColumnShearDemandSelection,
    ReviewedDAmplifiedShearAuthority,
    run_vs6_p7_from_production_evidence,
)
from tbdy_engine.regulatory.vs6_column_shear_p7_program import (
    VS6P7ColumnShearRun,
    build_vs6_p7_column_shear_run,
)


class ColumnP7RuntimeError(ValueError):
    pass


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnP7RuntimeError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{label} must be a sequence of strings")
    refs = tuple(dict.fromkeys(_text(value, label) for value in values))
    if not refs:
        raise ColumnP7RuntimeError(f"{label} must be nonempty")
    return refs


@dataclass(frozen=True, slots=True)
class ReviewedColumnP7DirectionPlan:
    component_id: str
    direction: str
    tbdy_vd_source_identity: str
    ts500_vd_source_identity: str
    bottom_state_id: str
    top_state_id: str
    response_spectrum_concurrency_proven: bool
    d_amplified_authority: ReviewedDAmplifiedShearAuthority
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        direction = _text(self.direction, "direction")
        if direction not in {"V2", "V3"}:
            raise ColumnP7RuntimeError("P7 direction must be V2 or V3")
        object.__setattr__(self, "direction", direction)
        for name in (
            "tbdy_vd_source_identity",
            "ts500_vd_source_identity",
            "bottom_state_id",
            "top_state_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.bottom_state_id == self.top_state_id:
            raise ColumnP7RuntimeError("P7 bottom/top state identities must differ")
        if type(self.response_spectrum_concurrency_proven) is not bool:
            raise TypeError("response_spectrum_concurrency_proven must be bool")
        if not isinstance(self.d_amplified_authority, ReviewedDAmplifiedShearAuthority):
            raise TypeError("d_amplified_authority must be ReviewedDAmplifiedShearAuthority")
        if (
            self.d_amplified_authority.component_id != self.component_id
            or self.d_amplified_authority.direction != self.direction
        ):
            raise ColumnP7RuntimeError("reviewed D-amplified authority identity mismatch")
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "review_ref"))


@dataclass(frozen=True, slots=True)
class ReviewedColumnP7RuntimeContext:
    component_id: str
    directions: tuple[ReviewedColumnP7DirectionPlan, ...]
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        component = _text(self.component_id, "component_id")
        object.__setattr__(self, "component_id", component)
        directions = tuple(self.directions)
        if len(directions) != 2 or any(
            not isinstance(item, ReviewedColumnP7DirectionPlan) for item in directions
        ):
            raise ColumnP7RuntimeError("P7 runtime context requires exactly V2 and V3 plans")
        if {item.direction for item in directions} != {"V2", "V3"}:
            raise ColumnP7RuntimeError("P7 runtime context must cover V2 and V3 exactly once")
        if any(item.component_id != component for item in directions):
            raise ColumnP7RuntimeError("P7 direction plan component identity mismatch")
        object.__setattr__(self, "directions", tuple(sorted(directions, key=lambda item: item.direction)))
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "review_ref"))


@dataclass(frozen=True, slots=True)
class ColumnP7RuntimeComposition:
    component_id: str
    shear_evidence: ColumnShearDemandEvidenceBundle
    p7_run: VS6P7ColumnShearRun


def build_b5_bound_column_shear_evidence(
    *,
    model_fingerprint: str,
    acquisition_context: TrustedLiveAcquisitionContext,
    analysis_execution: AnalysisExecutionResult,
) -> ColumnShearDemandEvidenceBundle:
    """Reuse the exact qualified B5 Column-force populations; do not reread them."""
    if not isinstance(acquisition_context, TrustedLiveAcquisitionContext):
        raise TypeError("acquisition_context must be TrustedLiveAcquisitionContext")
    if not isinstance(analysis_execution, AnalysisExecutionResult):
        raise TypeError("analysis_execution must be AnalysisExecutionResult")
    if not analysis_execution.qualification.qualified:
        raise ColumnP7RuntimeError("P7 requires qualified B5 analysis lineage")
    qualified = analysis_execution.qualification.require_qualified_result()
    if qualified.identity_ref != analysis_execution.analysis_result_identity.identity_ref:
        raise ColumnP7RuntimeError("P7 B5 qualification/result identity mismatch")

    populations = tuple(analysis_execution.manifest.result_populations)
    expected_cases = tuple(analysis_execution.manifest.scope.case_names)
    if not populations or tuple(sorted(item.case_name for item in populations)) != expected_cases:
        raise ColumnP7RuntimeError("P7 requires the exact complete B5 result-population scope")
    rows = tuple(row for population in populations for row in population.rows)
    if not rows:
        raise ColumnP7RuntimeError("P7 B5 result population contains no rows")

    units = read_verified_unit_snapshot(acquisition_context.verified_session)
    if units.present_units_api != "GetPresentUnits_2":
        raise ColumnP7RuntimeError("P7 B5 projection requires GetPresentUnits_2 provenance")
    force_unit = resolve_etabs_present_force_unit(units.present_force_unit)
    length_unit = resolve_etabs_present_length_unit(units.present_length_unit)
    unit_refs = tuple(
        dict.fromkeys(
            (
                "CSI ETABS API GetPresentUnits_2",
                f"ETABS_PRESENT_FORCE_UNIT:{units.present_force_unit}",
                f"ETABS_PRESENT_LENGTH_UNIT:{units.present_length_unit}",
                analysis_execution.analysis_result_identity.identity_ref,
                analysis_execution.execution_proof_ref,
                *(item.evidence_ref for item in populations),
            )
        )
    )
    return build_column_shear_demand_evidence(
        model_fingerprint=_text(model_fingerprint, "model_fingerprint"),
        rows=rows,
        output_names=expected_cases,
        force_unit=force_unit,
        length_unit=length_unit,
        unit_provenance_refs=unit_refs,
    )


def compose_column_p7_runtime(
    *,
    component_id: str,
    model_fingerprint: str,
    acquisition_context: TrustedLiveAcquisitionContext,
    analysis_execution: AnalysisExecutionResult,
    free_length: ColumnFreeLengthResolution,
    demand_states: Sequence[ColumnDemandState],
    longitudinal_runtime: ColumnLongitudinalRuntimeComposition,
    reviewed_context: ReviewedColumnP7RuntimeContext,
) -> ColumnP7RuntimeComposition:
    component = _text(component_id, "component_id")
    if not isinstance(reviewed_context, ReviewedColumnP7RuntimeContext):
        raise TypeError("reviewed_context must be ReviewedColumnP7RuntimeContext")
    if reviewed_context.component_id != component:
        raise ColumnP7RuntimeError("P7 reviewed context component identity mismatch")
    if not isinstance(free_length, ColumnFreeLengthResolution):
        raise TypeError("free_length must be ColumnFreeLengthResolution")
    if free_length.component_id != component:
        raise ColumnP7RuntimeError("P7 free-length component identity mismatch")

    states = tuple(demand_states)
    if not states or any(not isinstance(item, ColumnDemandState) for item in states):
        raise ColumnP7RuntimeError("P7 requires retained canonical A23 demand states")
    if any(item.component_id != component for item in states):
        raise ColumnP7RuntimeError("P7 A23 demand-state component identity mismatch")
    if not isinstance(longitudinal_runtime, ColumnLongitudinalRuntimeComposition):
        raise TypeError("longitudinal_runtime must be ColumnLongitudinalRuntimeComposition")
    if longitudinal_runtime.component_id != component:
        raise ColumnP7RuntimeError("P7 longitudinal runtime component identity mismatch")
    if not longitudinal_runtime.selection.selected or longitudinal_runtime.selection.selected_rebar is None:
        raise ColumnP7RuntimeError("P7 requires canonical ENGINE_SELECTED_REBAR")

    target = longitudinal_runtime.target_topology
    if target.component_id != component:
        raise ColumnP7RuntimeError("P7 strict-topology component identity mismatch")
    material_context = longitudinal_runtime.bound_design_basis.material_context
    if material_context.component_id != component or material_context.model_fingerprint != model_fingerprint:
        raise ColumnP7RuntimeError("P7 bound material identity mismatch")

    material_refs = tuple(
        dict.fromkeys(
            (
                material_context.section_material_binding_ref,
                material_context.binding_ref,
                *material_context.concrete_strength_source_refs,
                *material_context.concrete_design_strength_review_refs,
                *material_context.steel_design_strength_review_refs,
                *longitudinal_runtime.bound_design_basis.source_refs,
            )
        )
    )
    bundle = build_b5_bound_column_shear_evidence(
        model_fingerprint=model_fingerprint,
        acquisition_context=acquisition_context,
        analysis_execution=analysis_execution,
    )

    runs = []
    for plan in reviewed_context.directions:
        plan_refs = tuple(dict.fromkeys((*reviewed_context.review_refs, *plan.review_refs)))
        tbdy_selection = ColumnShearDemandSelection(
            component_id=component,
            column_unique_name=target.unique_name,
            direction=plan.direction,
            evidence_epoch_id=bundle.evidence_epoch_id,
            source_identity=plan.tbdy_vd_source_identity,
            review_refs=plan_refs,
        )
        ts500_selection = ColumnShearDemandSelection(
            component_id=component,
            column_unique_name=target.unique_name,
            direction=plan.direction,
            evidence_epoch_id=bundle.evidence_epoch_id,
            source_identity=plan.ts500_vd_source_identity,
            review_refs=plan_refs,
        )
        state_selection = ColumnShearCapacityStateSelection(
            component_id=component,
            direction=plan.direction,
            bottom_state_id=plan.bottom_state_id,
            top_state_id=plan.top_state_id,
            response_spectrum_concurrency_proven=plan.response_spectrum_concurrency_proven,
            review_refs=plan_refs,
        )
        runs.append(
            run_vs6_p7_from_production_evidence(
                demand_states=states,
                section_material=material_context.material,
                selected_rebar=longitudinal_runtime.selection.selected_rebar,
                topology=target,
                free_length=free_length,
                shear_evidence=bundle,
                tbdy_vd_selection=tbdy_selection,
                ts500_vd_selection=ts500_selection,
                capacity_state_selection=state_selection,
                d_amplified_authority=plan.d_amplified_authority,
                tbdy_high_ductility_applies=(
                    longitudinal_runtime.bound_design_basis.high_ductility_applies
                ),
                ts500_rc_applies=True,
                material_source_refs=material_refs,
            )
        )

    p7_run = build_vs6_p7_column_shear_run(
        component_id=component,
        directions=tuple(runs),
    )
    return ColumnP7RuntimeComposition(
        component_id=component,
        shear_evidence=bundle,
        p7_run=p7_run,
    )


__all__ = [
    "ColumnP7RuntimeComposition",
    "ColumnP7RuntimeError",
    "ReviewedColumnP7DirectionPlan",
    "ReviewedColumnP7RuntimeContext",
    "build_b5_bound_column_shear_evidence",
    "compose_column_p7_runtime",
]
