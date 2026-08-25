"""VS5 source-bound dual-code RC column axial composition path."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Mapping, Sequence

from tbdy_engine.checks.column_axial_selection import (
    ColumnDemandAvailability,
    ReviewedColumnNdmLoadBinding,
    ReviewedColumnNdmPolicy,
    ReviewedTs500ColumnDemandPolicy,
    ResolvedColumnDemand,
    Ts498ReductionPolicyState,
    select_tbdy_column_ndm,
    select_ts500_column_nd,
)
from tbdy_engine.checks.result import CheckResult, CheckStatus
from tbdy_engine.features.etabs_column_axial_evidence import ColumnGeometryEvidence, LiveColumnAxialEvidenceBundle
from tbdy_engine.regulatory.column_axial_dual_code import (
    COLUMN_DEPTH_M_KEY,
    COLUMN_WIDTH_M_KEY,
    CONCRETE_FCK_MPA_KEY,
    EVIDENCE_TRACE_KEY,
    SECTION_KEY,
    STORY_KEY,
    TBDY_NDM_KN_KEY,
    TBDY_RULE_ID,
    TS500_GAMMA_MC_KEY,
    TS500_ND_KN_KEY,
    TS500_RULE_ID,
    VS5_COLUMN_AXIAL_REGISTRY,
    ColumnAxialApplicabilityInput,
)
from tbdy_engine.regulatory.contracts import (
    AvailabilityState,
    ClosureExecutionStatus,
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
from tbdy_engine.regulatory.sources.vs5_column_axial import build_vs5_column_axial_authority_catalog
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE, UNIT_KN, UNIT_M, UNIT_MPA


class CombinedColumnAxialStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    NO_DATA = "NO_DATA"
    INCOMPLETE = "INCOMPLETE"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{label} must be a sequence")
    out = tuple(_text(item, label) for item in values)
    if not out:
        raise ValueError(f"{label} must not be empty")
    return out


@dataclass(frozen=True, slots=True)
class ReviewedVs5ColumnAxialContext:
    ndm_binding: ReviewedColumnNdmLoadBinding
    tbdy_7312_high_ductility_applies: bool | None
    ts498_reduction_state: Ts498ReductionPolicyState | str
    q_target_coefficients: Mapping[str, float]
    s_target_coefficients: Mapping[str, float]
    linear_superposition_reviewed: bool
    compression_sign: int
    ndm_regulatory_authority_ids: tuple[str, ...]
    ndm_review_refs: tuple[str, ...]
    ts500_combination_ids: tuple[str, ...]
    ts500_gamma_mc: float
    ts500_review_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.ndm_binding, ReviewedColumnNdmLoadBinding):
            raise TypeError("ndm_binding must be ReviewedColumnNdmLoadBinding")
        if self.tbdy_7312_high_ductility_applies is not None and type(self.tbdy_7312_high_ductility_applies) is not bool:
            raise TypeError("tbdy_7312_high_ductility_applies must be bool or None")
        object.__setattr__(self, "ts498_reduction_state", Ts498ReductionPolicyState(self.ts498_reduction_state))
        if type(self.linear_superposition_reviewed) is not bool:
            raise TypeError("linear_superposition_reviewed must be bool")
        if self.compression_sign not in {-1, 1}:
            raise ValueError("compression_sign must be -1 or +1")
        object.__setattr__(self, "ndm_regulatory_authority_ids", _refs(self.ndm_regulatory_authority_ids, "ndm_regulatory_authority_id"))
        object.__setattr__(self, "ndm_review_refs", _refs(self.ndm_review_refs, "ndm_review_ref"))
        combos = tuple(_text(item, "ts500_combination_id") for item in self.ts500_combination_ids)
        if not combos or len(combos) != len(set(combos)):
            raise ValueError("ts500_combination_ids must be nonempty and unique")
        object.__setattr__(self, "ts500_combination_ids", combos)
        if isinstance(self.ts500_gamma_mc, bool) or not isinstance(self.ts500_gamma_mc, (int, float)) or float(self.ts500_gamma_mc) <= 0:
            raise ValueError("ts500_gamma_mc must be numeric and > 0")
        object.__setattr__(self, "ts500_gamma_mc", float(self.ts500_gamma_mc))
        object.__setattr__(self, "ts500_review_refs", _refs(self.ts500_review_refs, "ts500_review_ref"))


@dataclass(frozen=True, slots=True)
class VS5ColumnAxialRun:
    column: ColumnGeometryEvidence
    tbdy_demand: ResolvedColumnDemand
    ts500_demand: ResolvedColumnDemand
    store: RegulatoryStoreSnapshot
    assessment: StructuralAssessment
    tbdy_result: CheckResult | None
    ts500_result: CheckResult | None
    combined_status: CombinedColumnAxialStatus

    def as_dict(self) -> dict[str, object]:
        return {
            "component_id": self.column.component_id,
            "column": self.column.as_dict(),
            "tbdy_demand": self.tbdy_demand.as_dict(),
            "ts500_demand": self.ts500_demand.as_dict(),
            "tbdy_result": None if self.tbdy_result is None else self.tbdy_result.as_dict(),
            "ts500_result": None if self.ts500_result is None else self.ts500_result.as_dict(),
            "combined_status": self.combined_status.value,
            "plan_identity": self.store.plan_identity,
            "structural_assessment_status": self.assessment.structural_status.value,
            "closure_outcomes": [
                {"instance_id": x.compiled_record_ref.value, "execution_status": x.execution_status.value, "formal_result_ref": x.formal_result_ref}
                for x in self.assessment.closure_outcomes
            ],
        }


def _availability(value: ColumnDemandAvailability) -> AvailabilityState:
    return {
        ColumnDemandAvailability.RESOLVED: AvailabilityState.RESOLVED,
        ColumnDemandAvailability.NO_DATA: AvailabilityState.NO_DATA,
        ColumnDemandAvailability.BLOCKED: AvailabilityState.BLOCKED,
    }[value]


def _authority(*, authority_id: str, key, semantic: SemanticType, dimension: PhysicalDimension, unit, source_kind: DependencySourceKind, scope: str, value: object, refs: Sequence[str], availability: AvailabilityState = AvailabilityState.RESOLVED) -> ExternalDependencyAuthority:
    return ExternalDependencyAuthority(
        authority_id=authority_id,
        key=key,
        source_kind=source_kind,
        semantic_type=semantic,
        physical_dimension=dimension,
        grain=Grain.COMPONENT,
        scope_ref=scope,
        direction=None,
        unit=unit,
        availability=availability,
        population_completeness=PopulationCompleteness.FULL,
        value=value,
        provenance_refs=tuple(refs),
    )


def _formal(store: RegulatoryStoreSnapshot, rule_id, scope: str) -> CheckResult | None:
    items = tuple(x.result for x in store.formal_results if x.instance_id.rule_id == rule_id and x.instance_id.scope_ref == scope)
    if len(items) > 1:
        raise RuntimeError(f"duplicate formal result for {rule_id.value}/{scope}")
    return items[0] if items else None


def _closure(assessment: StructuralAssessment, rule_id, scope: str) -> ClosureExecutionStatus:
    items = tuple(x.execution_status for x in assessment.closure_outcomes if x.compiled_record_ref.rule_id == rule_id and x.compiled_record_ref.scope_ref == scope)
    if len(items) != 1:
        raise RuntimeError(f"expected one closure for {rule_id.value}/{scope}")
    return items[0]


def _combined(tbdy: CheckResult | None, ts500: CheckResult | None, tc: ClosureExecutionStatus, sc: ClosureExecutionStatus) -> CombinedColumnAxialStatus:
    if any(x is not None and x.status is CheckStatus.FAIL for x in (tbdy, ts500)):
        return CombinedColumnAxialStatus.FAIL
    if tbdy is not None and ts500 is not None and tbdy.status is CheckStatus.OK and ts500.status is CheckStatus.OK:
        return CombinedColumnAxialStatus.PASS
    if ClosureExecutionStatus.BLOCKED in (tc, sc):
        return CombinedColumnAxialStatus.BLOCKED
    if ClosureExecutionStatus.NO_DATA in (tc, sc):
        return CombinedColumnAxialStatus.NO_DATA
    return CombinedColumnAxialStatus.INCOMPLETE


def run_vs5_column_axial(*, evidence: LiveColumnAxialEvidenceBundle, reviewed: ReviewedVs5ColumnAxialContext, unique_name: str) -> VS5ColumnAxialRun:
    if not isinstance(evidence, LiveColumnAxialEvidenceBundle) or not isinstance(reviewed, ReviewedVs5ColumnAxialContext):
        raise TypeError("VS5 run requires typed factual evidence and reviewed context")
    column = evidence.column(unique_name)
    ndm_policy = ReviewedColumnNdmPolicy(
        policy_id=f"vs5:ndm:{column.unique_name}", version="v1", target_unique_name=column.unique_name,
        ts498_reduction_state=reviewed.ts498_reduction_state,
        q_target_coefficients=reviewed.q_target_coefficients, s_target_coefficients=reviewed.s_target_coefficients,
        linear_superposition_reviewed=reviewed.linear_superposition_reviewed,
        compression_sign=reviewed.compression_sign,
        regulatory_authority_ids=reviewed.ndm_regulatory_authority_ids, review_refs=reviewed.ndm_review_refs,
    )
    ts_policy = ReviewedTs500ColumnDemandPolicy(
        policy_id=f"vs5:ts500-nd:{column.unique_name}", version="v1", target_unique_name=column.unique_name,
        combination_ids=reviewed.ts500_combination_ids, compression_sign=reviewed.compression_sign,
        review_refs=reviewed.ts500_review_refs,
    )
    ndm = select_tbdy_column_ndm(evidence, reviewed.ndm_binding, ndm_policy)
    nd = select_ts500_column_nd(evidence, ts_policy)
    scope = column.component_id
    factual_refs = (f"evidence_epoch:{evidence.evidence_epoch_id}", evidence.model_fingerprint, *evidence.review_refs, *evidence.provenance_refs)
    trace = ({
        "evidence_epoch_id": evidence.evidence_epoch_id,
        "model_fingerprint": evidence.model_fingerprint,
        "column_unique_name": column.unique_name,
        "tbdy_governing": None if ndm.governing_row_identity is None else dict(ndm.governing_row_identity),
        "ts500_governing": None if nd.governing_row_identity is None else dict(nd.governing_row_identity),
    },)
    A = lambda suffix, key, semantic, dim, unit, kind, value, refs=factual_refs, availability=AvailabilityState.RESOLVED: _authority(
        authority_id=f"vs5:{scope}:{suffix}", key=key, semantic=semantic, dimension=dim, unit=unit,
        source_kind=kind, scope=scope, value=value, refs=refs, availability=availability,
    )
    authorities = (
        A("width", COLUMN_WIDTH_M_KEY, SemanticType.COLUMN_WIDTH, PhysicalDimension.LENGTH, UNIT_M, DependencySourceKind.FACT, column.width_m),
        A("depth", COLUMN_DEPTH_M_KEY, SemanticType.COLUMN_DEPTH, PhysicalDimension.LENGTH, UNIT_M, DependencySourceKind.FACT, column.depth_m),
        A("fck", CONCRETE_FCK_MPA_KEY, SemanticType.CONCRETE_FCK, PhysicalDimension.STRESS, UNIT_MPA, DependencySourceKind.FACT, column.fck_mpa),
        A("story", STORY_KEY, SemanticType.COMPONENT_STORY, PhysicalDimension.ENUM_STATE, UNIT_ENUM_STATE, DependencySourceKind.CONTEXT, column.story),
        A("section", SECTION_KEY, SemanticType.COMPONENT_SECTION, PhysicalDimension.ENUM_STATE, UNIT_ENUM_STATE, DependencySourceKind.CONTEXT, column.section),
        A("trace", EVIDENCE_TRACE_KEY, SemanticType.CHECK_EVIDENCE_TRACE, PhysicalDimension.DIMENSIONLESS, UNIT_DIMENSIONLESS, DependencySourceKind.CONTEXT, trace),
        A("ndm", TBDY_NDM_KN_KEY, SemanticType.CHECK_EVIDENCE_TRACE, PhysicalDimension.FORCE, UNIT_KN, DependencySourceKind.SELECTED_SOURCE_QUANTITY, ndm.demand_kn, ndm.provenance or factual_refs, _availability(ndm.availability)),
        A("nd", TS500_ND_KN_KEY, SemanticType.CHECK_EVIDENCE_TRACE, PhysicalDimension.FORCE, UNIT_KN, DependencySourceKind.SELECTED_SOURCE_QUANTITY, nd.demand_kn, nd.provenance or factual_refs, _availability(nd.availability)),
        A("gamma_mc", TS500_GAMMA_MC_KEY, SemanticType.CHECK_EVIDENCE_TRACE, PhysicalDimension.DIMENSIONLESS, UNIT_DIMENSIONLESS, DependencySourceKind.CONTEXT, reviewed.ts500_gamma_mc, reviewed.ts500_review_refs),
    )
    applicability = ColumnAxialApplicabilityInput(
        component_type="column", reinforced_concrete=True,
        tbdy_7312_high_ductility_applies=reviewed.tbdy_7312_high_ductility_applies,
    )
    targets = tuple(
        RuleScopeTarget(rule_id=rid, grain=Grain.COMPONENT, scope_ref=scope, mandatory=True,
                        applicability_input=applicability, analysis_basis_status=AnalysisBasisStatus.MATCH)
        for rid in (TBDY_RULE_ID, TS500_RULE_ID)
    )
    program = RegulatoryCompiler.compile(
        VS5_COLUMN_AXIAL_REGISTRY,
        RegulatoryCompileInputs(rule_targets=targets, external_authorities=authorities,
                                regulatory_authority_catalog=build_vs5_column_axial_authority_catalog()),
    )
    store = RegulatoryEngine.execute(program)
    assessment = AssessmentEngine.reconcile(program, store)
    tbdy = _formal(store, TBDY_RULE_ID, scope)
    ts500 = _formal(store, TS500_RULE_ID, scope)
    return VS5ColumnAxialRun(
        column=column, tbdy_demand=ndm, ts500_demand=nd, store=store, assessment=assessment,
        tbdy_result=tbdy, ts500_result=ts500,
        combined_status=_combined(tbdy, ts500, _closure(assessment, TBDY_RULE_ID, scope), _closure(assessment, TS500_RULE_ID, scope)),
    )


def run_vs5_column_axial_population(*, evidence: LiveColumnAxialEvidenceBundle, reviewed: ReviewedVs5ColumnAxialContext) -> tuple[VS5ColumnAxialRun, ...]:
    return tuple(run_vs5_column_axial(evidence=evidence, reviewed=reviewed, unique_name=x.unique_name) for x in evidence.columns)


__all__ = [
    "CombinedColumnAxialStatus", "ReviewedVs5ColumnAxialContext", "VS5ColumnAxialRun",
    "run_vs5_column_axial", "run_vs5_column_axial_population",
]
