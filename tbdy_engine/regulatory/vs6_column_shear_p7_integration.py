"""Production evidence integration for VS6-P7 column shear.

This module closes the remaining adapter seam between already-canonical VS6
column design outputs, exact ETABS V2/V3 evidence, strict topology/free-length
promotion and the F0/F0.9 P7 regulatory program.

It performs no TBDY/TS500 compliance formula. Regulatory derivation/verdict
authority remains in ``tbdy_engine.regulatory.column_shear_p7``.

Working convention: kN, kN*m, mm, MPa. The frozen #145 section-capacity kernel
is adapted internally by ``resolve_exact_column_end_moment_capacity``.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from typing import Mapping, Sequence

from tbdy_engine.design.columns.column_design_engine import ColumnDesignEngineResult
from tbdy_engine.design.columns.column_longitudinal_selection import (
    CanonicalEngineSelectedRebar,
    ENGINE_SELECTED_REBAR_AUTHORITY,
)
from tbdy_engine.design.columns.column_rebar_design_engine import ColumnRebarDesignInputs
from tbdy_engine.design.columns.column_shear_demand import (
    CAPACITY_BLOCKED,
    CAPACITY_PROVEN,
    ColumnEndMomentCapacityBasis,
    associated_moment_axis,
    resolve_exact_column_end_moment_capacity,
)
from tbdy_engine.design.columns.column_shear_units import SourceBoundScalar, force_to_kn
from tbdy_engine.design.columns.column_shear_upper_bounds import (
    EFFECTIVE_DEPTH_BLOCKED,
    EFFECTIVE_DEPTH_PROVEN,
    ColumnEffectiveDepthResolution,
    resolve_exact_rectangular_column_effective_depth,
)
from tbdy_engine.design.columns.free_length_basis import ColumnFreeLengthResolution
from tbdy_engine.design.columns.rebar_layout import ColumnRebarGeometryCandidate
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.features.column_shear_demand_evidence import (
    ColumnShearDemandEvidenceBundle,
    column_shear_source_identity,
)
from tbdy_engine.features.column_shear_topology import ColumnTopologyEvidence
from tbdy_engine.regulatory.contracts import AvailabilityState
from tbdy_engine.regulatory.vs6_column_shear_p7_program import (
    SourceBoundShearDemand,
    VS6P7DirectionRun,
    run_vs6_p7_direction,
)

BOTH_SIGNS_CONSERVATIVE_MAX_CAPACITY_REF = "BOTH_SIGNS_CONSERVATIVE_MAX_CAPACITY"
BOTH_SIGNS_CONSERVATIVE_MIN_EFFECTIVE_DEPTH_REF = "BOTH_SIGNS_CONSERVATIVE_MIN_EFFECTIVE_DEPTH"
ENGINE_SELECTED_REBAR_REF = ENGINE_SELECTED_REBAR_AUTHORITY


class VS6P7IntegrationError(ValueError):
    """Fail-closed production integration error."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise VS6P7IntegrationError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    items = tuple(_text(item, label) for item in values)
    if not items or len(items) != len(set(items)):
        raise VS6P7IntegrationError(f"{label} must be a nonempty unique sequence")
    return items


def _direction(value: str) -> str:
    value = _text(value, "direction")
    if value not in {"V2", "V3"}:
        raise VS6P7IntegrationError("direction must be V2 or V3")
    return value


def _finite_nonnegative(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VS6P7IntegrationError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise VS6P7IntegrationError(f"{label} must be finite and >= 0")
    return number


def _basis_ref(label: str, refs: Sequence[str]) -> str:
    return json.dumps([label, list(refs)], ensure_ascii=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class ColumnShearDemandSelection:
    """Reviewed exact-row selector; it carries identity, never a shear value."""

    component_id: str
    column_unique_name: str
    direction: str
    evidence_epoch_id: str
    source_identity: str
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        object.__setattr__(self, "column_unique_name", _text(self.column_unique_name, "column_unique_name"))
        object.__setattr__(self, "direction", _direction(self.direction))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        object.__setattr__(self, "source_identity", _text(self.source_identity, "source_identity"))
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "review_ref"))


@dataclass(frozen=True, slots=True)
class ColumnShearCapacityStateSelection:
    """Reviewed exact #145 demand-state identities for the two physical ends."""

    component_id: str
    direction: str
    bottom_state_id: str
    top_state_id: str
    response_spectrum_concurrency_proven: bool
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        object.__setattr__(self, "direction", _direction(self.direction))
        object.__setattr__(self, "bottom_state_id", _text(self.bottom_state_id, "bottom_state_id"))
        object.__setattr__(self, "top_state_id", _text(self.top_state_id, "top_state_id"))
        if self.bottom_state_id == self.top_state_id:
            raise VS6P7IntegrationError("bottom_state_id and top_state_id must differ")
        if type(self.response_spectrum_concurrency_proven) is not bool:
            raise TypeError("response_spectrum_concurrency_proven must be bool")
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "review_ref"))


@dataclass(frozen=True, slots=True)
class ReviewedDAmplifiedShearAuthority:
    """Explicit reviewed D-amplified candidate authority; no default D exists."""

    component_id: str
    direction: str
    availability: AvailabilityState
    candidate_kn: float | None
    authority_ref: str
    review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        object.__setattr__(self, "direction", _direction(self.direction))
        if not isinstance(self.availability, AvailabilityState):
            raise TypeError("availability must be AvailabilityState")
        object.__setattr__(self, "authority_ref", _text(self.authority_ref, "authority_ref"))
        object.__setattr__(self, "review_refs", _refs(self.review_refs, "review_ref"))
        if self.availability is AvailabilityState.RESOLVED:
            if self.candidate_kn is None:
                raise VS6P7IntegrationError("resolved D-amplified authority requires candidate_kn")
            object.__setattr__(self, "candidate_kn", _finite_nonnegative(self.candidate_kn, "candidate_kn"))
        elif self.candidate_kn is not None:
            raise VS6P7IntegrationError("unresolved D-amplified authority may not carry a candidate value")

    @property
    def resolved(self) -> bool:
        return self.availability is AvailabilityState.RESOLVED


@dataclass(frozen=True, slots=True)
class ResolvedProductionShearDemand:
    demand: SourceBoundShearDemand
    signed_value_kn: float
    source_row: Mapping[str, object]


def resolve_exact_source_bound_shear_demand(
    *,
    bundle: ColumnShearDemandEvidenceBundle,
    selection: ColumnShearDemandSelection,
) -> ResolvedProductionShearDemand:
    """Resolve one exact factual local-axis V2/V3 row and normalize it to kN."""
    if not isinstance(bundle, ColumnShearDemandEvidenceBundle):
        raise TypeError("bundle must be ColumnShearDemandEvidenceBundle")
    if not isinstance(selection, ColumnShearDemandSelection):
        raise TypeError("selection must be ColumnShearDemandSelection")
    if selection.evidence_epoch_id != bundle.evidence_epoch_id:
        raise VS6P7IntegrationError("shear selection evidence epoch does not match the factual bundle")

    matches = tuple(
        row
        for row in bundle.rows
        if str(row.get("UniqueName")) == selection.column_unique_name
        and column_shear_source_identity(row) == selection.source_identity
    )
    if len(matches) != 1:
        raise VS6P7IntegrationError(
            f"exact shear source identity must resolve once; got {len(matches)}"
        )
    row = matches[0]
    output_case = _text(row.get("OutputCase"), "OutputCase")
    if output_case not in bundle.output_names:
        raise VS6P7IntegrationError("selected shear row output case is outside the reviewed bundle population")
    case_type = _text(row.get("CaseType"), "CaseType")
    signed_kn = force_to_kn(
        SourceBoundScalar(
            float(row[selection.direction]),
            bundle.force_unit,
            f"{bundle.source_table}:{selection.source_identity}:{selection.direction}",
        )
    )
    refs = tuple(
        dict.fromkeys(
            (
                f"ETABS:{bundle.source_table}:{selection.source_identity}",
                f"EVIDENCE_EPOCH:{bundle.evidence_epoch_id}",
                f"MODEL_FINGERPRINT:{bundle.model_fingerprint}",
                f"LOCAL_AXIS_COMPONENT:{selection.direction}",
                *bundle.unit_provenance_refs,
                *selection.review_refs,
            )
        )
    )
    demand = SourceBoundShearDemand(
        demand_kn=abs(signed_kn),
        source_identity=selection.source_identity,
        output_case=output_case,
        case_type=case_type,
        evidence_epoch_id=bundle.evidence_epoch_id,
        source_refs=refs,
    )
    return ResolvedProductionShearDemand(demand=demand, signed_value_kn=signed_kn, source_row=row)


def _physical_end_tags(topology: ColumnTopologyEvidence) -> tuple[str, str]:
    point_i = _text(topology.connectivity_row.get("UniquePtI"), "topology.UniquePtI")
    point_j = _text(topology.connectivity_row.get("UniquePtJ"), "topology.UniquePtJ")
    if topology.joint_bottom == point_i and topology.joint_top == point_j:
        return "I_END", "J_END"
    if topology.joint_bottom == point_j and topology.joint_top == point_i:
        return "J_END", "I_END"
    raise VS6P7IntegrationError("strict topology bottom/top joints do not reconcile to exact I/J connectivity")


def _state_by_id(design: ColumnDesignEngineResult, state_id: str) -> ColumnDemandState:
    matches = tuple(item for item in design.design_demands.promoted_states if item.state_id == state_id)
    if len(matches) != 1:
        raise VS6P7IntegrationError(f"exact column demand state_id must resolve once: {state_id}")
    return matches[0]


def _moment_for_direction(state: ColumnDemandState, direction: str) -> float:
    return float(state.m3_nmm if direction == "V2" else state.m2_nmm)


def _blocked_capacity(
    *,
    state: ColumnDemandState,
    end_tag: str,
    direction: str,
    refs: Sequence[str],
) -> ColumnEndMomentCapacityBasis:
    n_kn = float(state.nd_compression_n) / 1000.0
    if not math.isfinite(n_kn) or n_kn < 0.0:
        raise VS6P7IntegrationError(
            "bounded P7 capacity adapter cannot promote a tensile/invalid axial state"
        )
    moment = _moment_for_direction(state, direction)
    sign = -1 if moment < 0.0 else 1
    return ColumnEndMomentCapacityBasis(
        component_id=state.component_id,
        end_tag=end_tag,
        direction=direction,
        moment_axis=associated_moment_axis(direction),
        moment_sign=sign,
        nd_compression_kn=n_kn,
        capacity_knm=None,
        status=CAPACITY_BLOCKED,
        source_refs=tuple(dict.fromkeys(refs)),
    )


def _resolve_end_capacity(
    *,
    state: ColumnDemandState,
    physical_end_tag: str,
    direction: str,
    width_mm: float,
    depth_mm: float,
    selected_candidate: ColumnRebarGeometryCandidate | None,
    rebar_inputs: ColumnRebarDesignInputs,
    review_refs: Sequence[str],
) -> ColumnEndMomentCapacityBasis:
    refs = tuple(
        dict.fromkeys(
            (
                f"COLUMN_DEMAND_STATE:{state.state_id}",
                f"COLUMN_DEMAND_SOURCE:{state.source_identity}",
                *review_refs,
            )
        )
    )
    if selected_candidate is None:
        return _blocked_capacity(
            state=state,
            end_tag=physical_end_tag,
            direction=direction,
            refs=(*refs, "BLOCKED_ENGINE_SELECTED_REBAR"),
        )

    n_kn = float(state.nd_compression_n) / 1000.0
    if not math.isfinite(n_kn) or n_kn < 0.0:
        raise VS6P7IntegrationError(
            "bounded P7 capacity adapter cannot promote a tensile/invalid axial state"
        )
    refs = tuple(dict.fromkeys((*refs, f"{ENGINE_SELECTED_REBAR_REF}:{selected_candidate.candidate_id}")))
    moment = _moment_for_direction(state, direction)
    if abs(moment) > 1e-12:
        sign = 1 if moment > 0.0 else -1
        return resolve_exact_column_end_moment_capacity(
            component_id=state.component_id,
            end_tag=physical_end_tag,
            direction=direction,
            moment_sign=sign,
            nd_compression_kn=n_kn,
            width_mm=width_mm,
            depth_mm=depth_mm,
            bars=selected_candidate.bars,
            material=rebar_inputs.material,
            source_refs=refs,
        )

    plus = resolve_exact_column_end_moment_capacity(
        component_id=state.component_id,
        end_tag=physical_end_tag,
        direction=direction,
        moment_sign=1,
        nd_compression_kn=n_kn,
        width_mm=width_mm,
        depth_mm=depth_mm,
        bars=selected_candidate.bars,
        material=rebar_inputs.material,
        source_refs=refs,
    )
    minus = resolve_exact_column_end_moment_capacity(
        component_id=state.component_id,
        end_tag=physical_end_tag,
        direction=direction,
        moment_sign=-1,
        nd_compression_kn=n_kn,
        width_mm=width_mm,
        depth_mm=depth_mm,
        bars=selected_candidate.bars,
        material=rebar_inputs.material,
        source_refs=refs,
    )
    if not (plus.resolved and minus.resolved):
        return _blocked_capacity(
            state=state,
            end_tag=physical_end_tag,
            direction=direction,
            refs=(*plus.source_refs, *minus.source_refs, "BLOCKED_BOTH_SIGN_COLUMN_END_CAPACITY"),
        )
    chosen = max((plus, minus), key=lambda item: float(item.capacity_knm))
    return ColumnEndMomentCapacityBasis(
        component_id=chosen.component_id,
        end_tag=chosen.end_tag,
        direction=chosen.direction,
        moment_axis=chosen.moment_axis,
        moment_sign=chosen.moment_sign,
        nd_compression_kn=chosen.nd_compression_kn,
        capacity_knm=chosen.capacity_knm,
        status=CAPACITY_PROVEN,
        source_refs=tuple(
            dict.fromkeys(
                (*plus.source_refs, *minus.source_refs, BOTH_SIGNS_CONSERVATIVE_MAX_CAPACITY_REF)
            )
        ),
    )


def _selected_candidate(
    selected_rebar: CanonicalEngineSelectedRebar | None,
    *,
    component_id: str,
) -> ColumnRebarGeometryCandidate | None:
    """Resolve only the canonical COL-4 selected-rebar artifact."""

    if selected_rebar is None:
        return None

    if not isinstance(
        selected_rebar,
        CanonicalEngineSelectedRebar,
    ):
        raise TypeError(
            "selected_rebar must be CanonicalEngineSelectedRebar"
        )

    if selected_rebar.authority != ENGINE_SELECTED_REBAR_REF:
        raise VS6P7IntegrationError(
            "P7 selected rebar does not carry canonical "
            "ENGINE_SELECTED_REBAR authority"
        )

    if selected_rebar.component_id != component_id:
        raise VS6P7IntegrationError(
            "selected rebar component identity mismatch"
        )

    if (
        selected_rebar.selected_candidate.candidate_id
        != selected_rebar.candidate_id
    ):
        raise VS6P7IntegrationError(
            "canonical selected-rebar candidate identity mismatch"
        )

    return selected_rebar.selected_candidate


def _resolve_conservative_effective_depth(
    *,
    component_id: str,
    direction: str,
    width_mm: float,
    depth_mm: float,
    selected_candidate: ColumnRebarGeometryCandidate | None,
    refs: Sequence[str],
) -> ColumnEffectiveDepthResolution:
    if selected_candidate is None:
        return ColumnEffectiveDepthResolution(
            component_id=component_id,
            direction=direction,
            moment_axis=associated_moment_axis(direction),
            moment_sign=1,
            effective_depth_d_mm=None,
            web_width_bw_mm=None,
            tension_bar_coordinate_mm=None,
            status=EFFECTIVE_DEPTH_BLOCKED,
            source_refs=tuple(dict.fromkeys((*refs, "BLOCKED_ENGINE_SELECTED_REBAR"))),
        )

    plus = resolve_exact_rectangular_column_effective_depth(
        component_id=component_id,
        direction=direction,
        moment_sign=1,
        width_mm=width_mm,
        depth_mm=depth_mm,
        bars=selected_candidate.bars,
        source_refs=refs,
    )
    minus = resolve_exact_rectangular_column_effective_depth(
        component_id=component_id,
        direction=direction,
        moment_sign=-1,
        width_mm=width_mm,
        depth_mm=depth_mm,
        bars=selected_candidate.bars,
        source_refs=refs,
    )
    if not (plus.resolved and minus.resolved):
        return ColumnEffectiveDepthResolution(
            component_id=component_id,
            direction=direction,
            moment_axis=associated_moment_axis(direction),
            moment_sign=1,
            effective_depth_d_mm=None,
            web_width_bw_mm=None,
            tension_bar_coordinate_mm=None,
            status=EFFECTIVE_DEPTH_BLOCKED,
            source_refs=tuple(
                dict.fromkeys((*plus.source_refs, *minus.source_refs, "BLOCKED_BOTH_SIGN_EFFECTIVE_DEPTH"))
            ),
        )
    chosen = min((plus, minus), key=lambda item: float(item.effective_depth_d_mm))
    return ColumnEffectiveDepthResolution(
        component_id=chosen.component_id,
        direction=chosen.direction,
        moment_axis=chosen.moment_axis,
        moment_sign=chosen.moment_sign,
        effective_depth_d_mm=chosen.effective_depth_d_mm,
        web_width_bw_mm=chosen.web_width_bw_mm,
        tension_bar_coordinate_mm=chosen.tension_bar_coordinate_mm,
        status=EFFECTIVE_DEPTH_PROVEN,
        source_refs=tuple(
            dict.fromkeys(
                (*plus.source_refs, *minus.source_refs, BOTH_SIGNS_CONSERVATIVE_MIN_EFFECTIVE_DEPTH_REF)
            )
        ),
    )


def run_vs6_p7_from_production_evidence(
    *,
    column_design: ColumnDesignEngineResult,
    rebar_inputs: ColumnRebarDesignInputs,
    selected_rebar: CanonicalEngineSelectedRebar | None,
    topology: ColumnTopologyEvidence,
    free_length: ColumnFreeLengthResolution,
    shear_evidence: ColumnShearDemandEvidenceBundle,
    tbdy_vd_selection: ColumnShearDemandSelection,
    ts500_vd_selection: ColumnShearDemandSelection,
    capacity_state_selection: ColumnShearCapacityStateSelection,
    d_amplified_authority: ReviewedDAmplifiedShearAuthority,
    tbdy_high_ductility_applies: bool | None,
    ts500_rc_applies: bool | None,
    material_source_refs: Sequence[str],
) -> VS6P7DirectionRun:
    """Close one P7 direction from typed production evidence into canonical F0."""
    if not isinstance(column_design, ColumnDesignEngineResult):
        raise TypeError("column_design must be ColumnDesignEngineResult")
    if not isinstance(rebar_inputs, ColumnRebarDesignInputs):
        raise TypeError("rebar_inputs must be ColumnRebarDesignInputs")
    if not isinstance(topology, ColumnTopologyEvidence):
        raise TypeError("topology must be ColumnTopologyEvidence")
    if not isinstance(free_length, ColumnFreeLengthResolution):
        raise TypeError("free_length must be ColumnFreeLengthResolution")
    if not isinstance(d_amplified_authority, ReviewedDAmplifiedShearAuthority):
        raise TypeError("d_amplified_authority must be ReviewedDAmplifiedShearAuthority")

    component_id = topology.component_id
    direction = capacity_state_selection.direction
    identities = (
        column_design.component_id,
        rebar_inputs.component_id,
        free_length.component_id,
        tbdy_vd_selection.component_id,
        ts500_vd_selection.component_id,
        capacity_state_selection.component_id,
        d_amplified_authority.component_id,
    )
    if any(item != component_id for item in identities):
        raise VS6P7IntegrationError("P7 production component identities do not reconcile")
    if any(
        item != direction
        for item in (
            tbdy_vd_selection.direction,
            ts500_vd_selection.direction,
            d_amplified_authority.direction,
        )
    ):
        raise VS6P7IntegrationError("P7 production local-axis directions do not reconcile")
    if tbdy_vd_selection.column_unique_name != topology.unique_name or ts500_vd_selection.column_unique_name != topology.unique_name:
        raise VS6P7IntegrationError("shear selection UniqueName differs from strict topology")

    width_mm = float(topology.width_t2_m) * 1000.0
    depth_mm = float(topology.depth_t3_m) * 1000.0
    if not math.isclose(width_mm, float(rebar_inputs.width_mm), rel_tol=0.0, abs_tol=1e-6):
        raise VS6P7IntegrationError("topology t2 and selected-rebar width do not reconcile")
    if not math.isclose(depth_mm, float(rebar_inputs.depth_mm), rel_tol=0.0, abs_tol=1e-6):
        raise VS6P7IntegrationError("topology t3 and selected-rebar depth do not reconcile")
    if not math.isclose(
        float(free_length.factual_candidate_mm),
        float(topology.analysis_clear_length_candidate_m) * 1000.0,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise VS6P7IntegrationError("free-length factual candidate differs from strict topology")

    tbdy_resolved = resolve_exact_source_bound_shear_demand(
        bundle=shear_evidence,
        selection=tbdy_vd_selection,
    )
    ts500_resolved = resolve_exact_source_bound_shear_demand(
        bundle=shear_evidence,
        selection=ts500_vd_selection,
    )

    bottom_end_tag, top_end_tag = _physical_end_tags(topology)
    bottom_state = _state_by_id(column_design, capacity_state_selection.bottom_state_id)
    top_state = _state_by_id(column_design, capacity_state_selection.top_state_id)
    if bottom_state.component_id != component_id or top_state.component_id != component_id:
        raise VS6P7IntegrationError("selected capacity states contain a different component")
    if bottom_state.end_tag != bottom_end_tag or top_state.end_tag != top_end_tag:
        raise VS6P7IntegrationError("selected capacity state does not match physical bottom/top end")
    if bottom_state.output_case != tbdy_resolved.demand.output_case or top_state.output_case != tbdy_resolved.demand.output_case:
        raise VS6P7IntegrationError("selected capacity states do not match the exact TBDY shear output case")

    rs_required = any(
        state.case_type == "DesignResponseSpectrumPermutation"
        for state in (bottom_state, top_state)
    )
    selected_candidate = _selected_candidate(
        selected_rebar,
        component_id=component_id,
    )

    canonical_selection_refs = (
        (
            selected_rebar.selected_rebar_ref,
            *selected_rebar.provenance_refs,
        )
        if selected_rebar is not None
        else ()
    )

    selection_refs = tuple(
        dict.fromkeys(
            (
                *capacity_state_selection.review_refs,
                *canonical_selection_refs,
            )
        )
    )
    bottom_capacity = _resolve_end_capacity(
        state=bottom_state,
        physical_end_tag="BOTTOM",
        direction=direction,
        width_mm=width_mm,
        depth_mm=depth_mm,
        selected_candidate=selected_candidate,
        rebar_inputs=rebar_inputs,
        review_refs=selection_refs,
    )
    top_capacity = _resolve_end_capacity(
        state=top_state,
        physical_end_tag="TOP",
        direction=direction,
        width_mm=width_mm,
        depth_mm=depth_mm,
        selected_candidate=selected_candidate,
        rebar_inputs=rebar_inputs,
        review_refs=selection_refs,
    )

    effective_refs = tuple(
        dict.fromkeys(
            (
                f"STRICT_TOPOLOGY:{component_id}",
                *(selection_refs or ("ENGINE_SELECTED_REBAR_BASIS_UNAVAILABLE",)),
                *material_source_refs,
            )
        )
    )
    effective_depth = _resolve_conservative_effective_depth(
        component_id=component_id,
        direction=direction,
        width_mm=width_mm,
        depth_mm=depth_mm,
        selected_candidate=selected_candidate,
        refs=effective_refs,
    )

    free_length_ln_mm = free_length.free_length_ln_mm if free_length.resolved else None
    free_length_basis_ref = (
        _basis_ref(free_length.authority, free_length.source_refs)
        if free_length.resolved
        else None
    )
    d_candidate_kn = d_amplified_authority.candidate_kn if d_amplified_authority.resolved else None
    d_basis_ref = (
        _basis_ref(
            d_amplified_authority.authority_ref,
            d_amplified_authority.review_refs,
        )
        if d_amplified_authority.resolved
        else None
    )
    material_refs = _refs(material_source_refs, "material_source_ref")

    return run_vs6_p7_direction(
        component_id=component_id,
        story=topology.story,
        section=topology.section,
        direction=direction,
        tbdy_high_ductility_applies=tbdy_high_ductility_applies,
        ts500_rc_applies=ts500_rc_applies,
        free_length_ln_mm=free_length_ln_mm,
        free_length_basis_ref=free_length_basis_ref,
        bottom_capacity=bottom_capacity,
        top_capacity=top_capacity,
        d_amplified_candidate_kn=d_candidate_kn,
        d_amplified_basis_ref=d_basis_ref,
        tbdy_vd=tbdy_resolved.demand,
        ts500_vd=ts500_resolved.demand,
        response_spectrum_concurrency_required=rs_required,
        response_spectrum_concurrency_proven=capacity_state_selection.response_spectrum_concurrency_proven,
        width_mm=width_mm,
        depth_mm=depth_mm,
        geometry_source_ref=f"STRICT_TOPOLOGY:{component_id}",
        fck_mpa=float(rebar_inputs.material.fck_mpa),
        fcd_mpa=float(rebar_inputs.material.fcd_mpa),
        material_source_refs=material_refs,
        effective_depth=effective_depth,
    )


__all__ = [
    "BOTH_SIGNS_CONSERVATIVE_MAX_CAPACITY_REF",
    "BOTH_SIGNS_CONSERVATIVE_MIN_EFFECTIVE_DEPTH_REF",
    "ColumnShearCapacityStateSelection",
    "ColumnShearDemandSelection",
    "ResolvedProductionShearDemand",
    "ReviewedDAmplifiedShearAuthority",
    "VS6P7IntegrationError",
    "resolve_exact_source_bound_shear_demand",
    "run_vs6_p7_from_production_evidence",
]
