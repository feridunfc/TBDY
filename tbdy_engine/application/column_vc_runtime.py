"""A37 source binding for the canonical Vcr/Vc owner.

HIGH uses exact reviewed A23/B5 identities.
LIMITED selects minimum Nd only inside an exact reviewed vertical+earthquake
A23 population.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Mapping, Sequence

from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.features.column_shear_demand_evidence import (
    ColumnShearDemandEvidenceBundle,
    column_shear_source_identity,
)
from tbdy_engine.regulatory.column_shear_limited_program import (
    LimitedColumnShearRun,
)
from tbdy_engine.regulatory.column_shear_vc import QualifiedColumnVc, qualify_column_vc
from tbdy_engine.regulatory.column_transverse_confinement import ColumnTransverseConfinementInput
from tbdy_engine.regulatory.units import UNIT_KN, conversion_factor
from tbdy_engine.regulatory.vs6_column_shear_p7_program import VS6P7ColumnShearRun


class ColumnVcRuntimeError(ValueError):
    pass


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnVcRuntimeError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{label} must be a sequence")
    refs = tuple(dict.fromkeys(_text(x, label) for x in values))
    if not refs:
        raise ColumnVcRuntimeError(f"{label} must be nonempty")
    return refs


@dataclass(frozen=True, slots=True)
class ReviewedHighColumnVcDirectionPlan:
    component_id: str
    direction: str
    ts500_axial_state_id: str
    suppression_axial_state_id: str
    earthquake_only_source_identity: str
    total_seismic_source_identity: str
    suppression_concurrency_proven: bool
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        if self.direction not in {"V2", "V3"}:
            raise ColumnVcRuntimeError("direction must be V2 or V3")
        for name in (
            "ts500_axial_state_id",
            "suppression_axial_state_id",
            "earthquake_only_source_identity",
            "total_seismic_source_identity",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.earthquake_only_source_identity == self.total_seismic_source_identity:
            raise ColumnVcRuntimeError("earthquake-only and total-seismic identities must differ")
        if type(self.suppression_concurrency_proven) is not bool:
            raise TypeError("suppression_concurrency_proven must be bool")
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "review_ref"))


@dataclass(frozen=True, slots=True)
class ReviewedLimitedColumnVcDirectionPlan:
    component_id: str
    direction: str
    vertical_plus_earthquake_state_ids: tuple[str, ...]
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        if self.direction not in {"V2", "V3"}:
            raise ColumnVcRuntimeError("direction must be V2 or V3")
        ids = tuple(dict.fromkeys(_text(x, "state_id") for x in self.vertical_plus_earthquake_state_ids))
        if not ids:
            raise ColumnVcRuntimeError("LIMITED reviewed vertical+earthquake population must be nonempty")
        object.__setattr__(self, "vertical_plus_earthquake_state_ids", ids)
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "review_ref"))


@dataclass(frozen=True, slots=True)
class ReviewedColumnVcRuntimeContext:
    component_id: str
    high_directions: tuple[ReviewedHighColumnVcDirectionPlan, ...] = ()
    limited_directions: tuple[ReviewedLimitedColumnVcDirectionPlan, ...] = ()
    review_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        component = _text(self.component_id, "component_id")
        object.__setattr__(self, "component_id", component)
        high, limited = tuple(self.high_directions), tuple(self.limited_directions)
        if bool(high) == bool(limited):
            raise ColumnVcRuntimeError("Vc context must define exactly one HIGH or LIMITED family")
        active = high if high else limited
        if len(active) != 2 or {x.direction for x in active} != {"V2", "V3"}:
            raise ColumnVcRuntimeError("Vc context must cover V2 and V3 exactly once")
        if any(x.component_id != component for x in active):
            raise ColumnVcRuntimeError("Vc plan component identity mismatch")
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "review_ref"))


def _state_map(states: Sequence[ColumnDemandState], component_id: str) -> dict[str, ColumnDemandState]:
    items = tuple(states)
    if not items or any(not isinstance(x, ColumnDemandState) or x.component_id != component_id for x in items):
        raise ColumnVcRuntimeError("Vc requires retained canonical A23 states")
    by_id = {x.state_id: x for x in items}
    if len(by_id) != len(items):
        raise ColumnVcRuntimeError("Vc A23 state identities must be unique")
    return by_id


def _require_state(by_id: Mapping[str, ColumnDemandState], state_id: str) -> ColumnDemandState:
    try:
        return by_id[state_id]
    except KeyError as exc:
        raise ColumnVcRuntimeError(f"reviewed Vc state not found: {state_id}") from exc


def _row(bundle: ColumnShearDemandEvidenceBundle, *, source_identity: str, unique_name: str):
    matches = tuple(
        row for row in bundle.rows
        if column_shear_source_identity(row) == source_identity
        and str(row.get("UniqueName")) == unique_name
    )
    if len(matches) != 1:
        raise ColumnVcRuntimeError("reviewed Vc shear identity must resolve exactly once")
    return matches[0]


def _shear_kn(bundle: ColumnShearDemandEvidenceBundle, row, direction: str) -> float:
    try:
        number = float(row.get(direction))
    except Exception as exc:
        raise ColumnVcRuntimeError(f"{direction} shear must be numeric") from exc
    if not math.isfinite(number):
        raise ColumnVcRuntimeError(f"{direction} shear must be finite")
    return abs(number * float(conversion_factor(bundle.force_unit, UNIT_KN)))


def _p7_direction(run: VS6P7ColumnShearRun, direction: str):
    if not isinstance(run, VS6P7ColumnShearRun):
        raise TypeError("p7_run must be VS6P7ColumnShearRun")
    matches = tuple(x for x in run.directions if x.direction == direction)
    if (
        len(matches) != 1
        or not matches[0].effective_depth.resolved
        or matches[0].effective_depth.web_width_bw_mm is None
        or matches[0].effective_depth.effective_depth_d_mm is None
    ):
        raise ColumnVcRuntimeError(f"P7 exact bw/d unresolved for {direction}")
    return matches[0]



def _limited_direction(
    run: LimitedColumnShearRun,
    direction: str,
):
    if not isinstance(run, LimitedColumnShearRun):
        raise TypeError(
            "limited_run must be LimitedColumnShearRun"
        )
    matches = tuple(
        item
        for item in run.directions
        if item.direction == direction
    )
    if len(matches) != 1:
        raise ColumnVcRuntimeError(
            f"limited run must expose exactly one {direction}"
        )
    return matches[0]


def apply_reviewed_vc_to_transverse_input(
    request: ColumnTransverseConfinementInput,
    *,
    reviewed: ReviewedColumnVcRuntimeContext,
    a23_states: Sequence[ColumnDemandState],
    shear_evidence: ColumnShearDemandEvidenceBundle,
    p7_run: VS6P7ColumnShearRun | None = None,
    limited_run: LimitedColumnShearRun | None = None,
    fcd_mpa: float,
    target_unique_name: str,
    material_source_refs: Sequence[str],
) -> ColumnTransverseConfinementInput:
    if not isinstance(request, ColumnTransverseConfinementInput):
        raise TypeError("request must be ColumnTransverseConfinementInput")
    if not isinstance(reviewed, ReviewedColumnVcRuntimeContext):
        raise TypeError("reviewed must be ReviewedColumnVcRuntimeContext")
    if reviewed.component_id != request.component_id:
        raise ColumnVcRuntimeError("Vc context component identity mismatch")
    if not isinstance(shear_evidence, ColumnShearDemandEvidenceBundle):
        raise TypeError("shear_evidence must be ColumnShearDemandEvidenceBundle")
    if shear_evidence.model_fingerprint != request.model_fingerprint:
        raise ColumnVcRuntimeError("Vc shear-evidence model mismatch")
    if (
        p7_run is not None
        and p7_run.component_id != request.component_id
    ):
        raise ColumnVcRuntimeError(
            "Vc/P7 component identity mismatch"
        )
    if (
        limited_run is not None
        and limited_run.component_id != request.component_id
    ):
        raise ColumnVcRuntimeError(
            "Vc/limited component identity mismatch"
        )

    states = _state_map(a23_states, request.component_id)
    unique_name = _text(target_unique_name, "target_unique_name")
    common_refs = tuple(dict.fromkeys((
        *reviewed.review_refs,
        *material_source_refs,
        *shear_evidence.unit_provenance_refs,
    )))
    qualified: dict[str, QualifiedColumnVc] = {}

    if request.high_ductility_applies is True:
        if (
            request.limited_ductility_applies is True
            or not reviewed.high_directions
            or p7_run is None
            or limited_run is not None
        ):
            raise ColumnVcRuntimeError(
                "HIGH Vc requires P7 and forbids limited shear run"
            )
        for plan in reviewed.high_directions:
            ts500_state = _require_state(states, plan.ts500_axial_state_id)
            suppression_state = _require_state(states, plan.suppression_axial_state_id)
            eq_row = _row(
                shear_evidence,
                source_identity=plan.earthquake_only_source_identity,
                unique_name=unique_name,
            )
            total_row = _row(
                shear_evidence,
                source_identity=plan.total_seismic_source_identity,
                unique_name=unique_name,
            )
            p7 = _p7_direction(p7_run, plan.direction)
            qualified[plan.direction] = qualify_column_vc(
                component_id=request.component_id,
                direction=plan.direction,
                fck_mpa=request.fck_mpa,
                fcd_mpa=fcd_mpa,
                gross_area_ac_mm2=request.gross_area_ac_mm2,
                web_width_bw_mm=p7.effective_depth.web_width_bw_mm,
                effective_depth_d_mm=p7.effective_depth.effective_depth_d_mm,
                ts500_axial_nd_signed_compression_n=ts500_state.nd_compression_n,
                high_ductility_applies=True,
                limited_ductility_applies=False,
                earthquake_only_shear_kn=_shear_kn(shear_evidence, eq_row, plan.direction),
                total_seismic_shear_kn=_shear_kn(shear_evidence, total_row, plan.direction),
                suppression_axial_nd_signed_compression_n=suppression_state.nd_compression_n,
                suppression_concurrency_proven=plan.suppression_concurrency_proven,
                source_refs=tuple(dict.fromkeys((
                    *common_refs,
                    *plan.review_refs,
                    ts500_state.source_identity,
                    suppression_state.source_identity,
                    plan.earthquake_only_source_identity,
                    plan.total_seismic_source_identity,
                    *p7.effective_depth.source_refs,
                ))),
            )
    elif request.limited_ductility_applies is True:
        short_applies = (
            request.short_column is not None
            and request.short_column.applies is True
        )
        if not reviewed.limited_directions:
            raise ColumnVcRuntimeError(
                "LIMITED column requires reviewed LIMITED Vc context"
            )
        if short_applies:
            if p7_run is None or limited_run is not None:
                raise ColumnVcRuntimeError(
                    "LIMITED short-column Vc requires short P7 "
                    "and forbids ordinary §7.7.5 shear run"
                )
        elif limited_run is None or p7_run is not None:
            raise ColumnVcRuntimeError(
                "LIMITED ordinary Vc requires limited shear run "
                "and forbids P7"
            )

        for plan in reviewed.limited_directions:
            population = tuple(
                _require_state(states, sid)
                for sid in plan.vertical_plus_earthquake_state_ids
            )
            selected = min(
                population,
                key=lambda x: (
                    x.nd_compression_n,
                    x.state_id,
                ),
            )
            if short_applies:
                p7 = _p7_direction(
                    p7_run,
                    plan.direction,
                )
                effective = p7.effective_depth
                # LIMITED short-column Vc under TBDY 7.7.5.3
                # depends on the reviewed minimum-Nd population plus
                # factual bw/d geometry. The short-column P7 shear-demand
                # row is not an input to Vc and must not be cited as though
                # it were.
                shear_refs = tuple(
                    p7.effective_depth.source_refs
                )
            else:
                limited = _limited_direction(
                    limited_run,
                    plan.direction,
                )
                effective = limited.effective_depth
                shear_refs = (
                    *effective.source_refs,
                    *limited.source_refs,
                )

            qualified[plan.direction] = qualify_column_vc(
                component_id=request.component_id,
                direction=plan.direction,
                fck_mpa=request.fck_mpa,
                fcd_mpa=fcd_mpa,
                gross_area_ac_mm2=request.gross_area_ac_mm2,
                web_width_bw_mm=effective.web_width_bw_mm,
                effective_depth_d_mm=effective.effective_depth_d_mm,
                ts500_axial_nd_signed_compression_n=(
                    selected.nd_compression_n
                ),
                high_ductility_applies=False,
                limited_ductility_applies=True,
                source_refs=tuple(
                    dict.fromkeys(
                        (
                            *common_refs,
                            *plan.review_refs,
                            *(
                                x.source_identity
                                for x in population
                            ),
                            "TBDY2018_AFAD:7.7.5.3:"
                            "MINIMUM_ND_WITHIN_REVIEWED_"
                            "VERTICAL_PLUS_EARTHQUAKE_POPULATION",
                            *shear_refs,
                        )
                    )
                ),
            )
    else:
        raise ColumnVcRuntimeError("Vc requires proven HIGH or LIMITED ductility")

    local_map = {"DIR2": "V2", "DIR3": "V3"}
    directions = []
    for item in request.directions:
        local = local_map.get(item.direction)
        if local is None or local not in qualified:
            raise ColumnVcRuntimeError(f"unsupported/unqualified direction {item.direction}")
        vc = qualified[local]
        directions.append(replace(
            item,
            qualified_vc_kn=vc.vc_kn,
            source_refs=tuple(dict.fromkeys((
                *item.source_refs,
                *vc.source_refs,
                f"QUALIFIED_VC:{local}:{vc.vc_kn:.12g}kN",
            ))),
        ))

    return replace(
        request,
        directions=tuple(directions),
        source_refs=tuple(dict.fromkeys((
            *request.source_refs,
            *(ref for value in qualified.values() for ref in value.source_refs),
        ))),
    )


__all__ = [
    "ColumnVcRuntimeError",
    "ReviewedColumnVcRuntimeContext",
    "ReviewedHighColumnVcDirectionPlan",
    "ReviewedLimitedColumnVcDirectionPlan",
    "apply_reviewed_vc_to_transverse_input",
]
