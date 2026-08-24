"""VS5 composition path for source-bound dual-code RC column axial checks.

Factual ETABS acquisition and reviewed demand selection occur before formal
regulatory evaluation. The two code checks execute only through the existing
RegulatoryCompiler/RegulatoryEngine.
"""
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
from tbdy_engine.features.etabs_column_axial_evidence import (
    ColumnGeometryEvidence,
    LiveColumnAxialEvidenceBundle,
)
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
from tbdy_engine.regulatory.units import (
    UNIT_DIMENSIONLESS,
    UNIT_ENUM_STATE,
    UNIT_KN,
    UNIT_M,
    UNIT_MPA,
)

STATUS_PASS = "PASS"
STATUS_FAIL = "FAIL"
STATUS_BLOCKED = "BLOCKED"
STATUS_NO_DATA = "NO_DATA"
STATUS_INCOMPLETE = "INCOMPLETE"


class CombinedColumnAxialStatus(StrEnum):
    PASS = STATUS_PASS
    FAIL = STATUS_FAIL
    BLOCKED = STATUS_BLOCKED
    NO_DATA = STATUS_NO_DATA
    INCOMPLETE = STATUS_INCOMPLETE


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes, bytearray)):
        raise TypeError(f"{label} must be a sequence of strings")
    result = tuple(_text(item, label) for item in values)
    if not result:
        raise ValueError(f"{label} must contain at least one reference")
    return result


@dataclass(frozen=True, slots=True)
class ReviewedVs5ColumnAxialContext:
    ndm_binding: ReviewedColumnNdmLoadBinding
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
        object.__setattr__(self, "ts498_reduction_state", Ts498ReductionPolicyState(self.ts498_reduction_state))
        if type(self.linear_superposition_reviewed) is not bool:
            raise TypeError("linear_superposition_reviewed must be bool")
        if self.compression_sign not in {-1, 1}:
            raise ValueError("compression_sign must be -1 or +1")
        object.__setattr__(
            self,
            "ndm_regulatory_authority_ids",
            _refs(self.ndm_regulatory_authority_ids, "ndm_regulatory_authority_id"),
        )
        object.__setattr__(self, "ndm_review_refs", _refs(self.ndm_review_refs, "ndm_review_ref"))
        combos = tuple(_text(item, "ts500_combination_id") for item in self.ts500_combination_ids)
        if not combos or len(combos) != len(set(combos)):
            raise ValueError("ts500_combination_ids must be a nonempty unique sequence")
        object.__setattr__(self, "ts500_combination_ids", combos)
        if isinstance(self.ts500_gamma_mc, bool) or not isinstance(self.ts500_gamma_mc, (int, float)):
            raise TypeError("ts500_gamma_mc must be numeric")
        gamma = float(self.ts500_gamma_mc)
        if gamma <= 0.0:
            raise ValueError("ts500_gamma_mc must be > 0")
        object.__setattr__(self, "ts500_gamma_mc", gamma)
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
                {
                    "instance_id": item.compiled_record_ref.value,
                    "execution_status": item.execution_status.value,
                    "formal_result_ref": item.formal_result_ref,
                }
                for item in self.assessment.closure_outcomes
            ],
        }


def _availability(value: ColumnDemandAvailability) -> AvailabilityState:
    if value is ColumnDemandAvailability.RESOLVED:
        return AvailabilityState.RESOLVED
    if value is ColumnDemandAvailability.NO_DATA:
        return AvailabilityState.NO_DATA
    return AvailabilityState.BLOCKED


def _external(
    *,
    authority_id: str,
    key,
    semantic_type: SemanticType,
    dimension: PhysicalDimension,
    unit,
    source_kind: DependencySourceKind,
    scope_ref: str,
    value: object,
    provenance_refs: Sequence[str],
    availability: AvailabilityState = AvailabilityState.RESOLVED,
    population: PopulationCompleteness = PopulationCompleteness.FULL,
) -> ExternalDependencyAuthority:
    return ExternalDependencyAuthority(
        authority_id=authority_id,
        key=key,
        source_kind=source_kind,
        semantic_type=semantic_type,
        physical_dimension=dimension,
        grain=Grain.COMPONENT,
        scope_ref=scope_ref,
        direction=None,
        unit=unit,
        availability=availability,
        population_completeness=population,
        value=value,
        provenance_refs=tuple(provenance_refs),
    )


def _result_for(store: RegulatoryStoreSnapshot, rule_id, scope_ref: str) -> CheckResult | None:
    matches = tuple(
        record.result
        for record in store.formal_results
        if record.instance_id.rule_id == rule_id and record.instance_id.scope_ref == scope_ref
    )
    if len(matches) > 1:
        raise RuntimeError(f"duplicate formal result for {rule_id.value}/{scope_ref}")
    return matches[0] if matches else None


def _closure_status(
    assessment: StructuralAssessment, rule_id, scope_ref: str
) -> ClosureExecutionStatus:
    matches = tuple(
        item.execution_status
        for item in assessment.closure_outcomes
        if item.compiled_record_ref.rule_id == rule_id
        and item.compiled_record_ref.scope_ref == scope_ref
    )
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one closure outcome for {rule_id.value}/{scope_ref}")
    return matches[0]


def _combined(
    *,
    tbdy_result: CheckResult | None,
    ts500_result: CheckResult | None,
    tbdy_closure: ClosureExecutionStatus,
    ts500_closure: ClosureExecutionStatus,
) -> CombinedColumnAxialStatus:
    results = tuple(item for item in (tbdy_result, ts500_result) if item is not None)
    if any(item.status is CheckStatus.FAIL for item in results):
        return CombinedColumnAxialStatus.FAIL
    if (
        tbdy_result is not None
        and ts500_result is not None
        and tbdy_result.status is CheckStatus.OK
        and ts500_result.status is CheckStatus.OK
    ):
        return CombinedColumnAxialStatus.PASS
    closures = (tbdy_closure, ts500_closure)
    if any(item is ClosureExecutionStatus.BLOCKED for item in closures):
        return CombinedColumnAxialStatus.BLOCKED
    if any(item is ClosureExecutionStatus.NO_DATA for item in closures):
        return CombinedColumnAxialStatus.NO_DATA
    return CombinedColumnAxialStatus.INCOMPLETE


def run_vs5_column_axial(
    *,
    evidence: LiveColumnAxialEvidenceBundle,
    reviewed: ReviewedVs5ColumnAxialContext,
    unique_name: str,
) -> VS5ColumnAxialRun:
    if not isinstance(evidence, LiveColumnAxialEvidenceBundle):
        raise TypeError("evidence must be LiveColumnAxialEvidenceBundle")
    if not isinstance(reviewed, ReviewedVs5ColumnAxialContext):
        raise TypeError("reviewed must be ReviewedVs5ColumnAxialContext")
    column = evidence.column(unique_name)

    ndm_policy = ReviewedColumnNdmPolicy(
        policy_id=f"vs5:ndm:{column.unique_name}",
        version="v1",
        target_unique_name=column.unique_name,
        ts498_reduction_state=reviewed.ts498_reduction_state,
        q_target_coefficients=reviewed.q_target_coefficients,
        s_target_coefficients=reviewed.s_target_coefficients,
        linear_superposition_reviewed=reviewed.linear_superposition_reviewed,
        compression_sign=reviewed.compression_sign,
        regulatory_authority_ids=reviewed.ndm_regulatory_authority_ids,
        review_refs=reviewed.ndm_review_refs,
    )
    ts500_policy = ReviewedTs500ColumnDemandPolicy(
        policy_id=f"vs5:ts500-nd:{column.unique_name}",
        version="v1",
        target_unique_name=column.unique_name,
        combination_ids=reviewed.ts500_combination_ids,
        compression_sign=reviewed.compression_sign,
        review_refs=reviewed.ts500_review_refs,
    )
    tbdy_demand = select_tbdy_column_ndm(evidence, reviewed.ndm_binding, ndm_policy)
    ts500_demand = select_ts500_column_nd(evidence, ts500_policy)

    scope = column.component_id
    factual_refs = (
        f"evidence_epoch:{evidence.evidence_epoch_id}",
        evidence.model_fingerprint,
        *evidence.review_refs,
        *evidence.provenance_refs,
    )
    evidence_trace = (
        {
            "evidence_epoch_id": evidence.evidence_epoch_id,
            "model_fingerprint": evidence.model_fingerprint,
            "column_unique_name": column.unique_name,
            "tbdy_governing": (
                None
                if tbdy_demand.governing_row_identity is None
                else dict(tbdy_demand.governing_row_identity)
            ),
            "ts500_governing": (
                None
                if ts500_demand.governing_row_identity is None
                else dict(ts500_demand.governing_row_identity)
            ),
        },
    )
    authorities = (
        _external(
            authority_id=f"vs5:{scope}:width",
            key=COLUMN_WIDTH_M_KEY,
            semantic_type=SemanticType.COLUMN_WIDTH,
            dimension=PhysicalDimension.LENGTH,
            unit=UNIT_M,
            source_kind=DependencySourceKind.FACT,
            scope_ref=scope,
            value=column.width_m,
            provenance_refs=factual_refs,
        ),
        _external(
            authority_id=f"vs5:{scope}:depth",
            key=COLUMN_DEPTH_M_KEY,
            semantic_type=SemanticType.COLUMN_DEPTH,
            dimension=PhysicalDimension.LENGTH,
            unit=UNIT_M,
            source_kind=DependencySourceKind.FACT,
            scope_ref=scope,
            value=column.depth_m,
            provenance_refs=factual_refs,
        ),
        _external(
            authority_id=f"vs5:{scope}:fck",
            key=CONCRETE_FCK_MPA_KEY,
            semantic_type=SemanticType.CONCRETE_FCK,
            dimension=PhysicalDimension.STRESS,
            unit=UNIT_MPA,
            source_kind=DependencySourceKind.FACT,
            scope_ref=scope,
            value=column.fck_mpa,
            provenance_refs=factual_refs,
        ),
        _external(
            authority_id=f"vs5:{scope}:story",
            key=STORY_KEY,
            semantic_type=SemanticType.COMPONENT_STORY,
            dimension=PhysicalDimension.ENUM_STATE,
            unit=UNIT_ENUM_STATE,
            source_kind=DependencySourceKind.CONTEXT,
            scope_ref=scope,
            value=column.story,
            provenance_refs=factual_refs,
        ),
        _external(
            authority_id=f"vs5:{scope}:section",
            key=SECTION_KEY,
            semantic_type=SemanticType.COMPONENT_SECTION,
            dimension=PhysicalDimension.ENUM_STATE,
            unit=UNIT_ENUM_STATE,
            source_kind=DependencySourceKind.CONTEXT,
            scope_ref=scope,
            value=column.section,
            provenance_refs=factual_refs,
        ),
        _external(
            authority_id=f"vs5:{scope}:trace",
            key=EVIDENCE_TRACE_KEY,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.DIMENSIONLESS,
            unit=UNIT_DIMENSIONLESS,
            source_kind=DependencySourceKind.CONTEXT,
            scope_ref=scope,
            value=evidence_trace,
            provenance_refs=factual_refs,
        ),
        _external(
            authority_id=f"vs5:{scope}:ndm",
            key=TBDY_NDM_KN_KEY,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.FORCE,
            unit=UNIT_KN,
            source_kind=DependencySourceKind.SELECTED_SOURCE_QUANTITY,
            scope_ref=scope,
            value=tbdy_demand.demand_kn,
            provenance_refs=tbdy_demand.provenance or factual_refs,
            availability=_availability(tbdy_demand.availability),
        ),
        _external(
            authority_id=f"vs5:{scope}:nd",
            key=TS500_ND_KN_KEY,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.FORCE,
            unit=UNIT_KN,
            source_kind=DependencySourceKind.SELECTED_SOURCE_QUANTITY,
            scope_ref=scope,
            value=ts500_demand.demand_kn,
            provenance_refs=ts500_demand.provenance or factual_refs,
            availability=_availability(ts500_demand.availability),
        ),
        _external(
            authority_id=f"vs5:{scope}:gamma_mc",
            key=TS500_GAMMA_MC_KEY,
            semantic_type=SemanticType.CHECK_EVIDENCE_TRACE,
            dimension=PhysicalDimension.DIMENSIONLESS,
            unit=UNIT_DIMENSIONLESS,
            source_kind=DependencySourceKind.CONTEXT,
            scope_ref=scope,
            value=reviewed.ts500_gamma_mc,
            provenance_refs=reviewed.ts500_review_refs,
        ),
    )
    applicability = ColumnAxialApplicabilityInput(
        component_type="column",
        reinforced_concrete=True,
    )
    targets = tuple(
        RuleScopeTarget(
            rule_id=rule_id,
            grain=Grain.COMPONENT,
            scope_ref=scope,
            direction=None,
            mandatory=True,
            applicability_input=applicability,
            analysis_basis_status=AnalysisBasisStatus.MATCH,
        )
        for rule_id in (TBDY_RULE_ID, TS500_RULE_ID)
    )
    program = RegulatoryCompiler.compile(
        VS5_COLUMN_AXIAL_REGISTRY,
        RegulatoryCompileInputs(
            rule_targets=targets,
            external_authorities=authorities,
            regulatory_authority_catalog=build_vs5_column_axial_authority_catalog(),
        ),
    )
    store = RegulatoryEngine.execute(program)
    assessment = AssessmentEngine.reconcile(program, store)
    tbdy_result = _result_for(store, TBDY_RULE_ID, scope)
    ts500_result = _result_for(store, TS500_RULE_ID, scope)
    tbdy_closure = _closure_status(assessment, TBDY_RULE_ID, scope)
    ts500_closure = _closure_status(assessment, TS500_RULE_ID, scope)
    return VS5ColumnAxialRun(
        column=column,
        tbdy_demand=tbdy_demand,
        ts500_demand=ts500_demand,
        store=store,
        assessment=assessment,
        tbdy_result=tbdy_result,
        ts500_result=ts500_result,
        combined_status=_combined(
            tbdy_result=tbdy_result,
            ts500_result=ts500_result,
            tbdy_closure=tbdy_closure,
            ts500_closure=ts500_closure,
        ),
    )


def run_vs5_column_axial_population(
    *,
    evidence: LiveColumnAxialEvidenceBundle,
    reviewed: ReviewedVs5ColumnAxialContext,
) -> tuple[VS5ColumnAxialRun, ...]:
    return tuple(
        run_vs5_column_axial(
            evidence=evidence,
            reviewed=reviewed,
            unique_name=column.unique_name,
        )
        for column in evidence.columns
    )


__all__ = [
    "STATUS_PASS",
    "STATUS_FAIL",
    "STATUS_BLOCKED",
    "STATUS_NO_DATA",
    "STATUS_INCOMPLETE",
    "CombinedColumnAxialStatus",
    "ReviewedVs5ColumnAxialContext",
    "VS5ColumnAxialRun",
    "run_vs5_column_axial",
    "run_vs5_column_axial_population",
]
