"""Production F0 composition seam for VS6-P7 column shear.

All P7 regulatory derivation/verdict authority is executed by the canonical F0
RegulatoryCompiler/RegulatoryEngine using the reviewed F0.9 source catalog.
Upstream inputs are promoted factual/context quantities; this module does not
recalculate TBDY/TS500 formulas or create parallel PASS/FAIL authority.

Working units: kN, kN*m, mm, MPa.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Sequence

from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.design.columns.column_shear_demand import ColumnEndMomentCapacityBasis
from tbdy_engine.design.columns.column_shear_upper_bounds import ColumnEffectiveDepthResolution
from tbdy_engine.regulatory.column_shear_p7 import (
    BOTTOM_CAPACITY_KNM_KEY,
    COLUMN_DEPTH_MM_KEY,
    COLUMN_WIDTH_MM_KEY,
    CONCRETE_FCK_MPA_KEY,
    D_AMPLIFIED_KN_KEY,
    EFFECTIVE_DEPTH_MM_KEY,
    EVIDENCE_TRACE_KEY,
    FREE_LENGTH_MM_KEY,
    SECTION_KEY,
    STORY_KEY,
    TBDY_BRITTLE_RULE_ID,
    TBDY_VD_KN_KEY,
    TOP_CAPACITY_KNM_KEY,
    TS500_FCD_MPA_KEY,
    TS500_VD_KN_KEY,
    TS500_WEB_RULE_ID,
    VE_KN_KEY,
    VE_RULE_ID,
    ColumnShearP7ApplicabilityInput,
    VS6_COLUMN_SHEAR_P7_REGISTRY,
)
from tbdy_engine.regulatory.contracts import (
    AvailabilityState,
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    AssessmentEngine,
    ExternalDependencyAuthority,
    PopulationCompleteness,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryEngine,
    RegulatoryStoreSnapshot,
    RuleScopeTarget,
    StructuralAssessment,
)
from tbdy_engine.regulatory.sources.vs6_column_shear_p7 import (
    build_vs6_column_shear_p7_authority_catalog,
)
from tbdy_engine.regulatory.units import (
    UNIT_DIMENSIONLESS,
    UNIT_ENUM_STATE,
    UNIT_KN,
    UNIT_KN_M,
    UNIT_MM,
    UNIT_MPA,
)


class VS6P7ProgramError(ValueError):
    """Raised when promoted P7 input identities/authorities are inconsistent."""


class ColumnShearVrClosureStatus(StrEnum):
    BLOCKED_BY_TRANSVERSE_REBAR_SLICE = "BLOCKED_BY_TRANSVERSE_REBAR_SLICE"


@dataclass(frozen=True, slots=True)
class SourceBoundShearDemand:
    demand_kn: float
    source_identity: str
    output_case: str
    case_type: str
    evidence_epoch_id: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        value = float(self.demand_kn)
        if not math.isfinite(value) or value < 0.0:
            raise VS6P7ProgramError("demand_kn must be finite and >= 0")
        object.__setattr__(self, "demand_kn", value)
        for name in ("source_identity", "output_case", "case_type", "evidence_epoch_id"):
            text = getattr(self, name)
            if not isinstance(text, str) or not text.strip() or text != text.strip():
                raise VS6P7ProgramError(f"{name} must be a nonblank canonical string")
        refs = tuple(self.source_refs)
        if not refs or len(refs) != len(set(refs)) or any(
            not isinstance(item, str) or not item.strip() for item in refs
        ):
            raise VS6P7ProgramError("source_refs must be nonempty unique strings")
        object.__setattr__(self, "source_refs", refs)


@dataclass(frozen=True, slots=True)
class VS6P7DirectionRun:
    component_id: str
    story: str
    section: str
    direction: str
    tbdy_vd: SourceBoundShearDemand
    ts500_vd: SourceBoundShearDemand
    bottom_capacity: ColumnEndMomentCapacityBasis
    top_capacity: ColumnEndMomentCapacityBasis
    effective_depth: ColumnEffectiveDepthResolution
    ve_quantity_value_kn: float | None
    tbdy_brittle_result: CheckResult | None
    ts500_web_result: CheckResult | None
    regulatory_snapshot: RegulatoryStoreSnapshot
    structural_assessment: StructuralAssessment
    full_vr_closure_status: ColumnShearVrClosureStatus
    analysis_basis_status: AnalysisBasisStatus
    applicability_status: str

    @property
    def ve_kn(self) -> float | None:
        return self.ve_quantity_value_kn


@dataclass(frozen=True, slots=True)
class VS6P7ColumnShearRun:
    component_id: str
    directions: tuple[VS6P7DirectionRun, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, str) or not self.component_id.strip():
            raise VS6P7ProgramError("component_id must be nonblank")
        directions = tuple(sorted(self.directions, key=lambda item: item.direction))
        if any(item.component_id != self.component_id for item in directions):
            raise VS6P7ProgramError("direction run component identity mismatch")
        if len({item.direction for item in directions}) != len(directions):
            raise VS6P7ProgramError("duplicate direction run")
        object.__setattr__(self, "directions", directions)


def _availability(resolved: bool) -> AvailabilityState:
    return AvailabilityState.RESOLVED if resolved else AvailabilityState.BLOCKED


def _ext(
    *,
    authority_id: str,
    key,
    source_kind: DependencySourceKind,
    semantic_type: SemanticType,
    dimension: PhysicalDimension,
    grain: Grain,
    scope_ref: str,
    direction: str | None,
    unit,
    availability: AvailabilityState,
    value: object,
    provenance_refs: Sequence[str],
) -> ExternalDependencyAuthority:
    return ExternalDependencyAuthority(
        authority_id=authority_id,
        key=key,
        source_kind=source_kind,
        semantic_type=semantic_type,
        physical_dimension=dimension,
        grain=grain,
        scope_ref=scope_ref,
        direction=direction,
        unit=unit,
        availability=availability,
        population_completeness=PopulationCompleteness.FULL,
        value=value,
        provenance_refs=tuple(provenance_refs),
    )


def _result(snapshot: RegulatoryStoreSnapshot, instance_id) -> CheckResult | None:
    items = snapshot.formal_results_for(instance_id)
    if len(items) > 1:
        raise VS6P7ProgramError("duplicate canonical CheckResult for P7 instance")
    return items[0] if items else None


def run_vs6_p7_direction(
    *,
    component_id: str,
    story: str,
    section: str,
    direction: str,
    tbdy_high_ductility_applies: bool | None,
    ts500_rc_applies: bool | None,
    free_length_ln_mm: float | None,
    free_length_basis_ref: str | None,
    bottom_capacity: ColumnEndMomentCapacityBasis,
    top_capacity: ColumnEndMomentCapacityBasis,
    d_amplified_candidate_kn: float | None,
    d_amplified_basis_ref: str | None,
    tbdy_vd: SourceBoundShearDemand,
    ts500_vd: SourceBoundShearDemand,
    response_spectrum_concurrency_required: bool,
    response_spectrum_concurrency_proven: bool,
    width_mm: float,
    depth_mm: float,
    geometry_source_ref: str,
    fck_mpa: float,
    fcd_mpa: float,
    material_source_refs: Sequence[str],
    effective_depth: ColumnEffectiveDepthResolution,
) -> VS6P7DirectionRun:
    """Compile and execute one local shear direction through canonical F0."""
    if direction not in {"V2", "V3"}:
        raise VS6P7ProgramError("direction must be V2 or V3")
    if tbdy_high_ductility_applies is not None and type(tbdy_high_ductility_applies) is not bool:
        raise VS6P7ProgramError("tbdy_high_ductility_applies must be bool or None")
    if ts500_rc_applies is not None and type(ts500_rc_applies) is not bool:
        raise VS6P7ProgramError("ts500_rc_applies must be bool or None")
    if type(response_spectrum_concurrency_required) is not bool or type(response_spectrum_concurrency_proven) is not bool:
        raise VS6P7ProgramError("response-spectrum concurrency flags must be bool")
    width = float(width_mm)
    depth = float(depth_mm)
    fck = float(fck_mpa)
    fcd = float(fcd_mpa)
    if any(not math.isfinite(value) or value <= 0.0 for value in (width, depth, fck, fcd)):
        raise VS6P7ProgramError("geometry/material scalars must be finite and > 0")
    if not isinstance(geometry_source_ref, str) or not geometry_source_ref.strip():
        raise VS6P7ProgramError("geometry_source_ref must be nonblank")
    material_refs = tuple(material_source_refs)
    if not material_refs or any(not isinstance(item, str) or not item.strip() for item in material_refs):
        raise VS6P7ProgramError("material_source_refs must be nonempty strings")

    for capacity, expected_end in ((bottom_capacity, "BOTTOM"), (top_capacity, "TOP")):
        if capacity.component_id != component_id or capacity.direction != direction or capacity.end_tag != expected_end:
            raise VS6P7ProgramError("column-end capacity identity mismatch")
    if effective_depth.component_id != component_id or effective_depth.direction != direction:
        raise VS6P7ProgramError("effective-depth identity mismatch")

    evidence = tuple(
        dict.fromkeys(
            (
                *tbdy_vd.source_refs,
                *ts500_vd.source_refs,
                *bottom_capacity.source_refs,
                *top_capacity.source_refs,
                *effective_depth.source_refs,
                geometry_source_ref,
                *material_refs,
            )
        )
    )

    common_app = ColumnShearP7ApplicabilityInput(
        component_type="column",
        reinforced_concrete=ts500_rc_applies,
        tbdy_737_high_ductility_applies=tbdy_high_ductility_applies,
    )
    targets = tuple(
        RuleScopeTarget(
            rule_id=rule_id,
            grain=Grain.COMPONENT_DIRECTION,
            scope_ref=component_id,
            direction=direction,
            mandatory=True,
            applicability_input=common_app,
        )
        for rule_id in (VE_RULE_ID, TBDY_BRITTLE_RULE_ID, TS500_WEB_RULE_ID)
    )

    bottom_ok = bottom_capacity.resolved
    top_ok = top_capacity.resolved
    ln_ok = (
        free_length_ln_mm is not None
        and free_length_basis_ref is not None
        and math.isfinite(float(free_length_ln_mm))
        and float(free_length_ln_mm) > 0.0
    )
    d_ok = (
        d_amplified_candidate_kn is not None
        and d_amplified_basis_ref is not None
        and math.isfinite(float(d_amplified_candidate_kn))
        and float(d_amplified_candidate_kn) >= 0.0
        and (
            not response_spectrum_concurrency_required
            or response_spectrum_concurrency_proven
        )
    )
    eff_ok = effective_depth.resolved

    authorities = (
        _ext(
            authority_id=f"P7:{component_id}:{direction}:BOTTOM_CAPACITY",
            key=BOTTOM_CAPACITY_KNM_KEY,
            source_kind=DependencySourceKind.SELECTED_SOURCE_QUANTITY,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.MOMENT,
            grain=Grain.COMPONENT_DIRECTION,
            scope_ref=component_id,
            direction=direction,
            unit=UNIT_KN_M,
            availability=_availability(bottom_ok),
            value=bottom_capacity.capacity_knm if bottom_ok else None,
            provenance_refs=bottom_capacity.source_refs,
        ),
        _ext(
            authority_id=f"P7:{component_id}:{direction}:TOP_CAPACITY",
            key=TOP_CAPACITY_KNM_KEY,
            source_kind=DependencySourceKind.SELECTED_SOURCE_QUANTITY,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.MOMENT,
            grain=Grain.COMPONENT_DIRECTION,
            scope_ref=component_id,
            direction=direction,
            unit=UNIT_KN_M,
            availability=_availability(top_ok),
            value=top_capacity.capacity_knm if top_ok else None,
            provenance_refs=top_capacity.source_refs,
        ),
        _ext(
            authority_id=f"P7:{component_id}:FREE_LENGTH",
            key=FREE_LENGTH_MM_KEY,
            source_kind=DependencySourceKind.SELECTED_SOURCE_QUANTITY,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_MM,
            availability=_availability(ln_ok),
            value=float(free_length_ln_mm) if ln_ok else None,
            provenance_refs=((free_length_basis_ref or "BLOCKED_FREE_LENGTH_BASIS"),),
        ),
        _ext(
            authority_id=f"P7:{component_id}:{direction}:D_AMPLIFIED",
            key=D_AMPLIFIED_KN_KEY,
            source_kind=DependencySourceKind.SELECTED_SOURCE_QUANTITY,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.FORCE,
            grain=Grain.COMPONENT_DIRECTION,
            scope_ref=component_id,
            direction=direction,
            unit=UNIT_KN,
            availability=_availability(d_ok),
            value=float(d_amplified_candidate_kn) if d_ok else None,
            provenance_refs=((
                "BLOCKED_RESPONSE_SPECTRUM_SHEAR_CONCURRENCY"
                if response_spectrum_concurrency_required and not response_spectrum_concurrency_proven
                else d_amplified_basis_ref or "BLOCKED_D_AMPLIFIED_SHEAR_BASIS"
            ),),
        ),
        _ext(
            authority_id=f"P7:{component_id}:{direction}:TBDY_VD",
            key=TBDY_VD_KN_KEY,
            source_kind=DependencySourceKind.SELECTED_SOURCE_QUANTITY,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.FORCE,
            grain=Grain.COMPONENT_DIRECTION,
            scope_ref=component_id,
            direction=direction,
            unit=UNIT_KN,
            availability=AvailabilityState.RESOLVED,
            value=tbdy_vd.demand_kn,
            provenance_refs=tbdy_vd.source_refs,
        ),
        _ext(
            authority_id=f"P7:{component_id}:{direction}:TS500_VD",
            key=TS500_VD_KN_KEY,
            source_kind=DependencySourceKind.SELECTED_SOURCE_QUANTITY,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.FORCE,
            grain=Grain.COMPONENT_DIRECTION,
            scope_ref=component_id,
            direction=direction,
            unit=UNIT_KN,
            availability=AvailabilityState.RESOLVED,
            value=ts500_vd.demand_kn,
            provenance_refs=ts500_vd.source_refs,
        ),
        _ext(
            authority_id=f"P7:{component_id}:WIDTH",
            key=COLUMN_WIDTH_MM_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.COLUMN_WIDTH,
            dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_MM,
            availability=AvailabilityState.RESOLVED,
            value=width,
            provenance_refs=(geometry_source_ref,),
        ),
        _ext(
            authority_id=f"P7:{component_id}:DEPTH",
            key=COLUMN_DEPTH_MM_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.COLUMN_DEPTH,
            dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_MM,
            availability=AvailabilityState.RESOLVED,
            value=depth,
            provenance_refs=(geometry_source_ref,),
        ),
        _ext(
            authority_id=f"P7:{component_id}:FCK",
            key=CONCRETE_FCK_MPA_KEY,
            source_kind=DependencySourceKind.FACT,
            semantic_type=SemanticType.CONCRETE_FCK,
            dimension=PhysicalDimension.STRESS,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_MPA,
            availability=AvailabilityState.RESOLVED,
            value=fck,
            provenance_refs=material_refs,
        ),
        _ext(
            authority_id=f"P7:{component_id}:FCD",
            key=TS500_FCD_MPA_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.STRESS,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_MPA,
            availability=AvailabilityState.RESOLVED,
            value=fcd,
            provenance_refs=material_refs,
        ),
        _ext(
            authority_id=f"P7:{component_id}:{direction}:EFFECTIVE_DEPTH",
            key=EFFECTIVE_DEPTH_MM_KEY,
            source_kind=DependencySourceKind.SELECTED_SOURCE_QUANTITY,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.LENGTH,
            grain=Grain.COMPONENT_DIRECTION,
            scope_ref=component_id,
            direction=direction,
            unit=UNIT_MM,
            availability=_availability(eff_ok),
            value=effective_depth.effective_depth_d_mm if eff_ok else None,
            provenance_refs=effective_depth.source_refs,
        ),
        _ext(
            authority_id=f"P7:{component_id}:STORY",
            key=STORY_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_STORY,
            dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_ENUM_STATE,
            availability=AvailabilityState.RESOLVED,
            value=story,
            provenance_refs=(f"STORY:{story}",),
        ),
        _ext(
            authority_id=f"P7:{component_id}:SECTION",
            key=SECTION_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.COMPONENT_SECTION,
            dimension=PhysicalDimension.ENUM_STATE,
            grain=Grain.COMPONENT,
            scope_ref=component_id,
            direction=None,
            unit=UNIT_ENUM_STATE,
            availability=AvailabilityState.RESOLVED,
            value=section,
            provenance_refs=(geometry_source_ref,),
        ),
        _ext(
            authority_id=f"P7:{component_id}:{direction}:EVIDENCE",
            key=EVIDENCE_TRACE_KEY,
            source_kind=DependencySourceKind.CONTEXT,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.DIMENSIONLESS,
            grain=Grain.COMPONENT_DIRECTION,
            scope_ref=component_id,
            direction=direction,
            unit=UNIT_DIMENSIONLESS,
            availability=AvailabilityState.RESOLVED,
            value=evidence,
            provenance_refs=evidence,
        ),
    )

    compiled = RegulatoryCompiler.compile(
        VS6_COLUMN_SHEAR_P7_REGISTRY,
        RegulatoryCompileInputs(
            rule_targets=targets,
            external_authorities=authorities,
            regulatory_authority_catalog=build_vs6_column_shear_p7_authority_catalog(),
        ),
    )
    snapshot = RegulatoryEngine.execute(compiled)
    assessment = AssessmentEngine.reconcile(compiled, snapshot)

    ve_instance = targets[0].instance_id
    tbdy_instance = targets[1].instance_id
    ts500_instance = targets[2].instance_id
    quantities = tuple(
        item for item in snapshot.quantities_for(ve_instance)
        if item.quantity_key == VE_KN_KEY
    )
    if len(quantities) > 1:
        raise VS6P7ProgramError("duplicate canonical Ve quantity")
    ve_kn = float(quantities[0].value) if quantities else None
    tbdy_result = _result(snapshot, tbdy_instance)
    ts500_result = _result(snapshot, ts500_instance)

    tbdy_outcome = snapshot.outcome_for(tbdy_instance)
    if tbdy_result is not None and tbdy_result.status is CheckStatus.FAIL:
        analysis_basis = AnalysisBasisStatus.REANALYSIS_REQUIRED
    elif tbdy_outcome is not None and tbdy_outcome.execution_status.value in {
        "BLOCKED", "NO_DATA", "INVALID", "MISSING", "DUPLICATE"
    }:
        analysis_basis = AnalysisBasisStatus.UNRESOLVED
    else:
        analysis_basis = AnalysisBasisStatus.MATCH

    applicability = compiled.node(ve_instance).closure_record.applicability.value
    return VS6P7DirectionRun(
        component_id=component_id,
        story=story,
        section=section,
        direction=direction,
        tbdy_vd=tbdy_vd,
        ts500_vd=ts500_vd,
        bottom_capacity=bottom_capacity,
        top_capacity=top_capacity,
        effective_depth=effective_depth,
        ve_quantity_value_kn=ve_kn,
        tbdy_brittle_result=tbdy_result,
        ts500_web_result=ts500_result,
        regulatory_snapshot=snapshot,
        structural_assessment=assessment,
        full_vr_closure_status=ColumnShearVrClosureStatus.BLOCKED_BY_TRANSVERSE_REBAR_SLICE,
        analysis_basis_status=analysis_basis,
        applicability_status=applicability,
    )


def build_vs6_p7_column_shear_run(
    *,
    component_id: str,
    directions: Sequence[VS6P7DirectionRun],
) -> VS6P7ColumnShearRun:
    return VS6P7ColumnShearRun(component_id=component_id, directions=tuple(directions))


__all__ = [
    "ColumnShearVrClosureStatus",
    "SourceBoundShearDemand",
    "VS6P7DirectionRun",
    "VS6P7ColumnShearRun",
    "VS6P7ProgramError",
    "build_vs6_p7_column_shear_run",
    "run_vs6_p7_direction",
]
