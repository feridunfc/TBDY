"""Single bounded composition path for VS-4B-A A15 post-analysis qualification.

ETABS interpretation is completed before this module is entered.  This module
accepts reviewed VS-4A context plus a directional factual MDEV/Mo evidence
contract, enforces the analysis/result-population gate, then delegates the
regulatory calculation to the existing F0 RegulatoryCompiler/RegulatoryEngine.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from tbdy_engine.features.etabs_mdev_mo_evidence import (
    BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH,
    BLOCKED_RESULT_OPERATOR_AMBIGUITY,
    DirectionalMdevMoEvidence,
    MdevMoEvidenceBlockedError,
)
from tbdy_engine.regulatory import structural_system as ss
from tbdy_engine.regulatory.contracts import (
    AvailabilityState,
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    CompiledRegulatoryProgram,
    ExternalDependencyAuthority,
    PopulationCompleteness,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RegulatoryEngine,
    RegulatoryStoreSnapshot,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.rc_a15_wall_share import (
    A15ApplicabilityInput,
    A15_ANALYSIS_BASIS_STATUS_KEY,
    A15_EFFECTIVE_POLICY_KEY,
    A15_MDEV_MO_EVIDENCE_KEY,
    RC_A15_4345_ANALYSIS_BASIS_COMPATIBILITY,
    RC_A15_4345_EFFECTIVE_POLICY,
    VS4B_A15_REGISTRY,
)
from tbdy_engine.regulatory.sources.tbdy2018_vs4b import build_vs4b_a15_authority_catalog
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_ENUM_STATE

STATUS_RESOLVED = "RESOLVED"
STATUS_PROVEN_NOT_APPLICABLE = "PROVEN_NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class VS4BA15DirectionRun:
    direction: str
    status: str
    factual_evidence: DirectionalMdevMoEvidence
    program: CompiledRegulatoryProgram | None = None
    store: RegulatoryStoreSnapshot | None = None
    effective_policy: object | None = None
    analysis_basis_status: AnalysisBasisStatus | None = None

    @property
    def regulatory_resolved(self) -> bool:
        return self.status == STATUS_RESOLVED

    def as_dict(self) -> dict[str, object]:
        return {
            "direction": self.direction,
            "status": self.status,
            "regulatory_resolved": self.regulatory_resolved,
            "factual_evidence": self.factual_evidence.as_dict(),
            "effective_policy": self.effective_policy,
            "analysis_basis_status": (
                None if self.analysis_basis_status is None else self.analysis_basis_status.value
            ),
            "plan_identity": None if self.program is None else self.program.plan.plan_identity,
        }


def _refs(*groups: Sequence[str]) -> tuple[str, ...]:
    refs = tuple(sorted({item for group in groups for item in group}))
    if not refs:
        raise ValueError("VS-4B reviewed input requires real provenance/review refs")
    if any(not isinstance(item, str) or not item.strip() or item != item.strip() for item in refs):
        raise ValueError("VS-4B reviewed refs must be nonblank canonical strings")
    return refs


def _external(
    *,
    authority_id: str,
    key,
    semantic: SemanticType,
    value: object,
    direction: str,
    provenance_refs: Sequence[str],
    unit=UNIT_ENUM_STATE,
    dimension: PhysicalDimension = PhysicalDimension.ENUM_STATE,
) -> ExternalDependencyAuthority:
    refs = tuple(provenance_refs)
    if not refs:
        raise ValueError(f"{authority_id} requires provenance/review refs")
    return ExternalDependencyAuthority(
        authority_id=authority_id,
        key=key,
        source_kind=DependencySourceKind.CONTEXT,
        semantic_type=semantic,
        physical_dimension=dimension,
        grain=Grain.DIRECTION,
        scope_ref=ss.BUILDING_SCOPE,
        direction=direction,
        unit=unit,
        availability=AvailabilityState.RESOLVED,
        population_completeness=PopulationCompleteness.FULL,
        value=value,
        provenance_refs=refs,
    )


def _blocked_status(evidence: DirectionalMdevMoEvidence) -> str | None:
    if evidence.regulatory_ready:
        return None
    status = evidence.blocking_status or BLOCKED_RESULT_OPERATOR_AMBIGUITY
    if status not in {
        BLOCKED_ANALYSIS_METHOD_RESULT_POPULATION_MISMATCH,
        BLOCKED_RESULT_OPERATOR_AMBIGUITY,
    }:
        return status
    return status


def compile_vs4b_a15_direction_program(
    *,
    declaration: ss.ReviewedDirectionalRcSystemDeclaration,
    seismic: ss.ReviewedSeismicClassificationContext,
    analysis_assumption: ss.DirectionalAnalysisSystemAssumption,
    evidence: DirectionalMdevMoEvidence,
) -> CompiledRegulatoryProgram:
    """Compile only a regulatory-ready A15 direction.

    A LinStatic factual population reviewed as MODAL_COMBINATION is rejected by
    the factual evidence contract unless an explicit reviewed ETABS population
    mapping is present.  Therefore the modal source authority can never be used
    merely because a requested case name resembles a response-spectrum case.
    """
    if not isinstance(declaration, ss.ReviewedDirectionalRcSystemDeclaration):
        raise TypeError("declaration must be ReviewedDirectionalRcSystemDeclaration")
    if not isinstance(seismic, ss.ReviewedSeismicClassificationContext):
        raise TypeError("seismic must be ReviewedSeismicClassificationContext")
    if not isinstance(analysis_assumption, ss.DirectionalAnalysisSystemAssumption):
        raise TypeError("analysis_assumption must be DirectionalAnalysisSystemAssumption")
    if not isinstance(evidence, DirectionalMdevMoEvidence):
        raise TypeError("evidence must be DirectionalMdevMoEvidence")
    direction = declaration.direction
    if evidence.direction != direction or analysis_assumption.direction != direction:
        raise ValueError("declaration, assumption and MDEV/Mo evidence directions must match exactly")
    if declaration.table_4_1_row != "A15":
        raise ValueError("VS-4B-A bounded production slice supports A15 only")
    status = _blocked_status(evidence)
    if status is not None:
        raise MdevMoEvidenceBlockedError(status, status=status)
    payload = evidence.regulatory_payload()

    declaration_refs = _refs(declaration.review_refs, declaration.provenance_refs)
    seismic_refs = _refs(seismic.review_refs, seismic.provenance_refs)
    assumption_refs = _refs(
        analysis_assumption.analysis_evidence_refs,
        analysis_assumption.provenance_refs,
    )
    evidence_refs = _refs(
        evidence.review_refs,
        evidence.provenance_refs,
        (
            f"evidence_epoch:{evidence.evidence_epoch_id}",
            evidence.model_fingerprint,
            f"reviewed_regulatory_base:{evidence.reviewed_base_elevation_m}",
        ),
    )

    authorities = (
        _external(
            authority_id=f"vs4b:{direction}:declared_row",
            key=ss.DECLARED_ROW_KEY,
            semantic=SemanticType.RC_TABLE_4_1_ROW,
            value=declaration.table_4_1_row,
            direction=direction,
            provenance_refs=declaration_refs,
        ),
        _external(
            authority_id=f"vs4b:{direction}:mdev_mo_evidence",
            key=A15_MDEV_MO_EVIDENCE_KEY,
            semantic=SemanticType.CHECK_EVIDENCE_TRACE,
            value=payload,
            direction=direction,
            provenance_refs=evidence_refs,
        ),
        _external(
            authority_id=f"vs4b:{direction}:assumed_row",
            key=ss.ASSUMED_ROW_KEY,
            semantic=SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION,
            value=analysis_assumption.assumed_table_4_1_row,
            direction=direction,
            provenance_refs=assumption_refs,
        ),
        _external(
            authority_id=f"vs4b:{direction}:assumed_r",
            key=ss.ASSUMED_R_KEY,
            semantic=SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION,
            value=analysis_assumption.assumed_r,
            direction=direction,
            provenance_refs=assumption_refs,
            unit=UNIT_DIMENSIONLESS,
            dimension=PhysicalDimension.DIMENSIONLESS,
        ),
        _external(
            authority_id=f"vs4b:{direction}:assumed_d",
            key=ss.ASSUMED_D_KEY,
            semantic=SemanticType.RC_ANALYSIS_SYSTEM_ASSUMPTION,
            value=analysis_assumption.assumed_d,
            direction=direction,
            provenance_refs=assumption_refs,
            unit=UNIT_DIMENSIONLESS,
            dimension=PhysicalDimension.DIMENSIONLESS,
        ),
        _external(
            authority_id=f"vs4b:{direction}:bys",
            key=ss.BYS_KEY,
            semantic=SemanticType.RC_BYS,
            value=seismic.bys,
            direction=direction,
            provenance_refs=seismic_refs,
        ),
    )
    targets = tuple(
        RuleScopeTarget(
            rule_id=rule_id,
            grain=Grain.DIRECTION,
            scope_ref=ss.BUILDING_SCOPE,
            direction=direction,
            applicability_input=A15ApplicabilityInput(declaration.table_4_1_row),
            analysis_basis_status=AnalysisBasisStatus.MATCH,
        )
        for rule_id in (
            RC_A15_4345_EFFECTIVE_POLICY,
            RC_A15_4345_ANALYSIS_BASIS_COMPATIBILITY,
        )
    )
    return RegulatoryCompiler.compile(
        VS4B_A15_REGISTRY,
        RegulatoryCompileInputs(
            rule_targets=targets,
            external_authorities=authorities,
            regulatory_authority_catalog=build_vs4b_a15_authority_catalog(),
        ),
    )


def _quantity_value(store: RegulatoryStoreSnapshot, key) -> object:
    matches = tuple(item for item in store.regulatory_quantities if item.quantity_key == key)
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one regulatory quantity {key.value}, got {len(matches)}")
    return matches[0].value


def run_vs4b_a15_direction(
    *,
    declaration: ss.ReviewedDirectionalRcSystemDeclaration,
    seismic: ss.ReviewedSeismicClassificationContext,
    analysis_assumption: ss.DirectionalAnalysisSystemAssumption,
    evidence: DirectionalMdevMoEvidence,
) -> VS4BA15DirectionRun:
    """Return a truthful resolved/blocked A15 direction product.

    When factual acquisition is valid but the analysis/result-population method
    is incompatible, this returns the blocker directly and emits no alphaM,
    branch or analysis-basis conclusion.
    """
    if not isinstance(evidence, DirectionalMdevMoEvidence):
        raise TypeError("evidence must be DirectionalMdevMoEvidence")
    if declaration.direction != evidence.direction:
        raise ValueError("declaration and evidence direction mismatch")
    if declaration.table_4_1_row != "A15":
        return VS4BA15DirectionRun(
            direction=declaration.direction,
            status=STATUS_PROVEN_NOT_APPLICABLE,
            factual_evidence=evidence,
        )
    blocked = _blocked_status(evidence)
    if blocked is not None:
        return VS4BA15DirectionRun(
            direction=declaration.direction,
            status=blocked,
            factual_evidence=evidence,
        )
    program = compile_vs4b_a15_direction_program(
        declaration=declaration,
        seismic=seismic,
        analysis_assumption=analysis_assumption,
        evidence=evidence,
    )
    store = RegulatoryEngine.execute(program)
    effective = _quantity_value(store, A15_EFFECTIVE_POLICY_KEY)
    raw_status = _quantity_value(store, A15_ANALYSIS_BASIS_STATUS_KEY)
    status = AnalysisBasisStatus(str(raw_status))
    return VS4BA15DirectionRun(
        direction=declaration.direction,
        status=STATUS_RESOLVED,
        factual_evidence=evidence,
        program=program,
        store=store,
        effective_policy=effective,
        analysis_basis_status=status,
    )


__all__ = [
    "STATUS_RESOLVED",
    "STATUS_PROVEN_NOT_APPLICABLE",
    "VS4BA15DirectionRun",
    "compile_vs4b_a15_direction_program",
    "run_vs4b_a15_direction",
]
