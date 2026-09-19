"""A37 production composition for TBDY §7.7.5 limited-column shear.

The runtime binds reviewed exact B5 row identities to the canonical source-bound
§7.7.5 rule program.  It never reuses high-ductility P7 Ve.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.application.column_longitudinal_runtime import (
    ColumnLongitudinalRuntimeComposition,
)
from tbdy_engine.application.column_p7_runtime import (
    build_b5_bound_column_shear_evidence,
)
from tbdy_engine.features.column_shear_demand_evidence import (
    ColumnShearDemandEvidenceBundle,
)
from tbdy_engine.integration.etabs_analysis_execution import (
    AnalysisExecutionResult,
)
from tbdy_engine.integration.live_etabs_acquisition_context import (
    TrustedLiveAcquisitionContext,
)
from tbdy_engine.regulatory.column_shear_limited_program import (
    LimitedColumnShearRun,
    build_limited_column_shear_run,
    run_limited_column_shear_direction,
)
from tbdy_engine.regulatory.vs6_column_shear_p7_integration import (
    ColumnShearDemandSelection,
    resolve_exact_source_bound_shear_demand,
    resolve_selected_rebar_effective_depth,
)


class ColumnLimitedShearRuntimeError(ValueError):
    pass


def _text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise ColumnLimitedShearRuntimeError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _refs(
    values: Sequence[str],
    label: str,
) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(
            f"{label} must be a sequence"
        )
    refs = tuple(
        dict.fromkeys(
            _text(item, label)
            for item in values
        )
    )
    if not refs:
        raise ColumnLimitedShearRuntimeError(
            f"{label} must be nonempty"
        )
    return refs


@dataclass(frozen=True, slots=True)
class ReviewedLimitedColumnShearDirectionPlan:
    component_id: str
    direction: str
    vd_source_identity: str
    d_amplified_vertical_plus_earthquake_proven: bool
    authority_ref: str
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "component_id",
            _text(
                self.component_id,
                "component_id",
            ),
        )
        if self.direction not in {"V2", "V3"}:
            raise ColumnLimitedShearRuntimeError(
                "direction must be V2 or V3"
            )
        object.__setattr__(
            self,
            "vd_source_identity",
            _text(
                self.vd_source_identity,
                "vd_source_identity",
            ),
        )
        object.__setattr__(
            self,
            "authority_ref",
            _text(
                self.authority_ref,
                "authority_ref",
            ),
        )
        if type(
            self.d_amplified_vertical_plus_earthquake_proven
        ) is not bool:
            raise TypeError(
                "d_amplified_vertical_plus_earthquake_proven "
                "must be bool"
            )
        object.__setattr__(
            self,
            "review_refs",
            _refs(
                self.review_refs,
                "review_ref",
            ),
        )


@dataclass(frozen=True, slots=True)
class ReviewedLimitedColumnShearRuntimeContext:
    component_id: str
    directions: tuple[
        ReviewedLimitedColumnShearDirectionPlan, ...
    ]
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        component = _text(
            self.component_id,
            "component_id",
        )
        object.__setattr__(
            self,
            "component_id",
            component,
        )
        directions = tuple(self.directions)
        if (
            len(directions) != 2
            or any(
                not isinstance(
                    item,
                    ReviewedLimitedColumnShearDirectionPlan,
                )
                for item in directions
            )
            or {item.direction for item in directions}
            != {"V2", "V3"}
        ):
            raise ColumnLimitedShearRuntimeError(
                "limited shear context must cover V2/V3 exactly once"
            )
        if any(
            item.component_id != component
            for item in directions
        ):
            raise ColumnLimitedShearRuntimeError(
                "limited shear plan component mismatch"
            )
        object.__setattr__(
            self,
            "directions",
            tuple(
                sorted(
                    directions,
                    key=lambda item: item.direction,
                )
            ),
        )
        object.__setattr__(
            self,
            "review_refs",
            _refs(
                self.review_refs,
                "review_ref",
            ),
        )


@dataclass(frozen=True, slots=True)
class ColumnLimitedShearRuntimeComposition:
    component_id: str
    shear_evidence: ColumnShearDemandEvidenceBundle
    limited_run: LimitedColumnShearRun


def compose_column_limited_shear_runtime(
    *,
    component_id: str,
    model_fingerprint: str,
    acquisition_context: TrustedLiveAcquisitionContext,
    analysis_execution: AnalysisExecutionResult,
    longitudinal_runtime: ColumnLongitudinalRuntimeComposition,
    reviewed_context: ReviewedLimitedColumnShearRuntimeContext,
    shear_evidence: (
        ColumnShearDemandEvidenceBundle | None
    ) = None,
) -> ColumnLimitedShearRuntimeComposition:
    component = _text(
        component_id,
        "component_id",
    )
    if not isinstance(
        reviewed_context,
        ReviewedLimitedColumnShearRuntimeContext,
    ):
        raise TypeError(
            "reviewed_context must be "
            "ReviewedLimitedColumnShearRuntimeContext"
        )
    if reviewed_context.component_id != component:
        raise ColumnLimitedShearRuntimeError(
            "limited reviewed context component mismatch"
        )
    if not isinstance(
        longitudinal_runtime,
        ColumnLongitudinalRuntimeComposition,
    ):
        raise TypeError(
            "longitudinal_runtime must be "
            "ColumnLongitudinalRuntimeComposition"
        )
    if longitudinal_runtime.component_id != component:
        raise ColumnLimitedShearRuntimeError(
            "limited longitudinal runtime component mismatch"
        )
    if (
        not longitudinal_runtime.selection.selected
        or longitudinal_runtime.selection.selected_rebar
        is None
    ):
        raise ColumnLimitedShearRuntimeError(
            "limited shear requires ENGINE_SELECTED_REBAR"
        )

    basis = longitudinal_runtime.bound_design_basis
    if (
        basis.high_ductility_applies is not False
        or basis.limited_ductility_applies is not True
    ):
        raise ColumnLimitedShearRuntimeError(
            "TBDY 7.7.5 runtime applies only to "
            "proven LIMITED columns"
        )

    target = longitudinal_runtime.target_topology
    if target.component_id != component:
        raise ColumnLimitedShearRuntimeError(
            "limited topology component mismatch"
        )

    material_context = basis.material_context
    if (
        material_context.component_id != component
        or material_context.model_fingerprint
        != model_fingerprint
    ):
        raise ColumnLimitedShearRuntimeError(
            "limited material identity mismatch"
        )

    if shear_evidence is None:
        bundle = build_b5_bound_column_shear_evidence(
            model_fingerprint=model_fingerprint,
            acquisition_context=acquisition_context,
            analysis_execution=analysis_execution,
        )
    else:
        if not isinstance(
            shear_evidence,
            ColumnShearDemandEvidenceBundle,
        ):
            raise TypeError(
                "shear_evidence must be "
                "ColumnShearDemandEvidenceBundle or None"
            )
        if (
            shear_evidence.model_fingerprint
            != model_fingerprint
        ):
            raise ColumnLimitedShearRuntimeError(
                "limited shear-evidence model mismatch"
            )
        bundle = shear_evidence

    material_refs = tuple(
        dict.fromkeys(
            (
                material_context.section_material_binding_ref,
                material_context.binding_ref,
                *material_context.concrete_strength_source_refs,
                *material_context.concrete_design_strength_review_refs,
                *basis.source_refs,
            )
        )
    )
    geometry_ref = (
        f"STRICT_TOPOLOGY:{target.unique_name}:"
        f"{target.section}"
    )
    width_mm = float(target.width_t2_m) * 1000.0
    depth_mm = float(target.depth_t3_m) * 1000.0

    direction_runs = []
    for plan in reviewed_context.directions:
        if (
            not plan
            .d_amplified_vertical_plus_earthquake_proven
        ):
            raise ColumnLimitedShearRuntimeError(
                "TBDY 7.7.5.1 reviewed D-amplified "
                "vertical+earthquake semantics not proven"
            )

        plan_refs = tuple(
            dict.fromkeys(
                (
                    *reviewed_context.review_refs,
                    *plan.review_refs,
                    plan.authority_ref,
                )
            )
        )
        selection = ColumnShearDemandSelection(
            component_id=component,
            column_unique_name=target.unique_name,
            direction=plan.direction,
            evidence_epoch_id=bundle.evidence_epoch_id,
            source_identity=plan.vd_source_identity,
            review_refs=plan_refs,
        )
        resolved = resolve_exact_source_bound_shear_demand(
            bundle=bundle,
            selection=selection,
        )

        effective = (
            resolve_selected_rebar_effective_depth(
                selected_rebar=(
                    longitudinal_runtime
                    .selection
                    .selected_rebar
                ),
                topology=target,
                direction=plan.direction,
                review_refs=plan_refs,
            )
        )
        if not effective.resolved:
            raise ColumnLimitedShearRuntimeError(
                "limited effective depth unresolved:"
                f"{plan.direction}"
            )

        direction_runs.append(
            run_limited_column_shear_direction(
                component_id=component,
                story=target.story,
                section=target.section,
                direction=plan.direction,
                vd=resolved.demand,
                d_amplified_vertical_plus_earthquake_proven=(
                    plan
                    .d_amplified_vertical_plus_earthquake_proven
                ),
                authority_ref=plan.authority_ref,
                width_mm=width_mm,
                depth_mm=depth_mm,
                fck_mpa=(
                    material_context.material.fck_mpa
                ),
                fcd_mpa=(
                    material_context.material.fcd_mpa
                ),
                geometry_source_ref=geometry_ref,
                material_source_refs=material_refs,
                effective_depth=effective,
                source_refs=plan_refs,
            )
        )

    run = build_limited_column_shear_run(
        component_id=component,
        directions=tuple(direction_runs),
    )
    return ColumnLimitedShearRuntimeComposition(
        component_id=component,
        shear_evidence=bundle,
        limited_run=run,
    )


__all__ = [
    "ColumnLimitedShearRuntimeComposition",
    "ColumnLimitedShearRuntimeError",
    "ReviewedLimitedColumnShearDirectionPlan",
    "ReviewedLimitedColumnShearRuntimeContext",
    "compose_column_limited_shear_runtime",
]
