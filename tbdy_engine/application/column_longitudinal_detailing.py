"""A35 longitudinal-detailing composition after canonical rebar selection.

This module owns no detailing formula and creates no second regulatory authority.
It binds the canonical ``ENGINE_SELECTED_REBAR`` artifact to the already reviewed
FND-COL-1 source authority and reports, separately, which detailing facts are
still missing. Unsupported shortcuts are never manufactured: until exact
source-bound lap-location, lap-section population, anchorage, transition,
splice-applicability and continuity/corner evidence exists, the truthful product
outcome is ``FINAL_DETAILING_REQUIRED``.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from hashlib import sha256
import json
from tbdy_engine.design.columns.column_pmm_assessment import ColumnPmmMaterialContextBinding
from tbdy_engine.regulatory.column_detailing_checks import DetailingFacts, SOURCE_HASHES, evaluate_detailing_facts, validate_detailing_fact_types
from decimal import Decimal
from typing import Sequence

from tbdy_engine.design.columns.column_longitudinal_selection import (
    CanonicalEngineSelectedRebar,
    ENGINE_SELECTED_REBAR_AUTHORITY,
)
from tbdy_engine.integration.etabs_design_lineage import (
    DESIGN_LINEAGE_REF_PREFIX,
    DESIGN_RESULT_REF_PREFIX,
)
from tbdy_engine.regulatory.authority import (
    RegulatoryAuthorityCatalog,
    validate_rule_authority,
)
from tbdy_engine.regulatory.column_longitudinal_rebar import FND_COL_1_CHECK_SPEC
from tbdy_engine.regulatory.sources.fnd_col_1_longitudinal import (
    FND_COL_1_AUTHORITY_CATALOG,
)


A35_AUTHORITY = "COLUMN_R1_A35_LONGITUDINAL_DETAILING_COMPOSITION"
FINAL_DETAILING_REQUIRED = "FINAL_DETAILING_REQUIRED"
DETAILING_PROVEN = "DETAILING_PROVEN"
OUTCOME_UNRESOLVED = "UNRESOLVED"
OUTCOME_PROVEN = "PROVEN"
OUTCOME_FAIL = "FAIL"
OUTCOME_NOT_APPLICABLE = "NOT_APPLICABLE"
DETAILING_FAILED = "DETAILING_FAILED"

LAP_SPLICE_LOCATION_REGION = "LAP_SPLICE_LOCATION_REGION"
LAP_SECTION_RHO = "LAP_SECTION_RHO"
ANCHORAGE = "ANCHORAGE"
SECTION_TRANSITION = "SECTION_TRANSITION"
MECHANICAL_WELDED_SPLICE_APPLICABILITY = "MECHANICAL_WELDED_SPLICE_APPLICABILITY"
CONTINUITY_CORNER_REQUIREMENTS = "CONTINUITY_CORNER_REQUIREMENTS"

LAP_RHO_CLAIM = "TBDY2018_COLUMN_LAP_SPLICE_TOTAL_RHO_MAX_6"


class ColumnLongitudinalDetailingError(ValueError):
    """Malformed or causally unbound A35 detailing composition."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnLongitudinalDetailingError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _refs(values: Sequence[str]) -> tuple[str, ...]:
    refs = tuple(
        dict.fromkeys(
            _text(value, "source_ref")
            for value in values
        )
    )
    if not refs:
        raise ColumnLongitudinalDetailingError("source_refs must be nonempty")
    return refs


def _single_provenance_ref(
    values: Sequence[str],
    *,
    prefix: str,
    label: str,
) -> str:
    matches = tuple(sorted({value for value in values if value.startswith(prefix)}))
    if len(matches) != 1:
        raise ColumnLongitudinalDetailingError(
            f"A35 {label} requires exactly one {prefix}<sha256> ref; got {len(matches)}"
        )
    return matches[0]


@dataclass(frozen=True, slots=True)
class ColumnLongitudinalDetailingOutcome:
    item: str
    status: str
    reason: str
    source_refs: tuple[str, ...]
    values_json: str = "{}"

    def __post_init__(self) -> None:
        object.__setattr__(self, "item", _text(self.item, "item"))
        status = _text(self.status, "status")
        if status not in {OUTCOME_UNRESOLVED, OUTCOME_PROVEN, OUTCOME_FAIL, OUTCOME_NOT_APPLICABLE}:
            raise ColumnLongitudinalDetailingError(
                f"unsupported detailing outcome status {status!r}"
            )
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason", _text(self.reason, "reason"))
        object.__setattr__(self, "source_refs", _refs(self.source_refs))

    @property
    def resolved(self) -> bool:
        return self.status != OUTCOME_UNRESOLVED


@dataclass(frozen=True, slots=True)
class ColumnLongitudinalDetailingResolution:
    component_id: str
    selected_rebar_ref: str
    model_fingerprint: str
    evidence_epoch_id: str
    engine_selected_rebar: CanonicalEngineSelectedRebar
    status: str
    outcomes: tuple[ColumnLongitudinalDetailingOutcome, ...]
    source_refs: tuple[str, ...]
    authority: str = A35_AUTHORITY

    def __post_init__(self) -> None:
        for name in (
            "component_id",
            "selected_rebar_ref",
            "model_fingerprint",
            "evidence_epoch_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))

        selected = self.engine_selected_rebar
        if not isinstance(selected, CanonicalEngineSelectedRebar):
            raise ColumnLongitudinalDetailingError(
                "A35 engine_selected_rebar must be CanonicalEngineSelectedRebar"
            )
        if selected.authority != ENGINE_SELECTED_REBAR_AUTHORITY:
            raise ColumnLongitudinalDetailingError(
                "A35 requires canonical ENGINE_SELECTED_REBAR authority"
            )
        if selected.selected_rebar_ref != self.selected_rebar_ref:
            raise ColumnLongitudinalDetailingError(
                "A35 selected-rebar reference does not match ENGINE_SELECTED_REBAR"
            )
        if selected.component_id != self.component_id:
            raise ColumnLongitudinalDetailingError(
                "A35 component identity does not match ENGINE_SELECTED_REBAR"
            )
        if selected.model_fingerprint != self.model_fingerprint:
            raise ColumnLongitudinalDetailingError(
                "A35 model fingerprint does not match ENGINE_SELECTED_REBAR"
            )
        if selected.evidence_epoch_id != self.evidence_epoch_id:
            raise ColumnLongitudinalDetailingError(
                "A35 EvidenceEpoch does not match ENGINE_SELECTED_REBAR"
            )

        design_result_ref = _single_provenance_ref(
            selected.provenance_refs,
            prefix=DESIGN_RESULT_REF_PREFIX,
            label="DesignResultIdentity parentage",
        )
        design_lineage_ref = _single_provenance_ref(
            selected.provenance_refs,
            prefix=DESIGN_LINEAGE_REF_PREFIX,
            label="DesignLineageQualification",
        )

        status = _text(self.status, "status")
        if status not in {FINAL_DETAILING_REQUIRED, DETAILING_PROVEN, DETAILING_FAILED}:
            raise ColumnLongitudinalDetailingError(
                f"unsupported A35 detailing status {status!r}"
            )
        object.__setattr__(self, "status", status)
        outcomes = tuple(self.outcomes)
        expected = (
            LAP_SPLICE_LOCATION_REGION,
            LAP_SECTION_RHO,
            ANCHORAGE,
            SECTION_TRANSITION,
            MECHANICAL_WELDED_SPLICE_APPLICABILITY,
            CONTINUITY_CORNER_REQUIREMENTS,
        )
        if tuple(item.item for item in outcomes) != expected:
            raise ColumnLongitudinalDetailingError(
                "A35 detailing outcome population is incomplete or out of canonical order"
            )
        if status == DETAILING_PROVEN and not all(item.status in {OUTCOME_PROVEN, OUTCOME_NOT_APPLICABLE} for item in outcomes):
            raise ColumnLongitudinalDetailingError(
                "DETAILING_PROVEN requires every A35 outcome to be PROVEN"
            )
        if status == DETAILING_FAILED and not any(item.status == OUTCOME_FAIL for item in outcomes):
            raise ColumnLongitudinalDetailingError("DETAILING_FAILED requires an actual failed rule")
        if status == FINAL_DETAILING_REQUIRED and all(item.resolved for item in outcomes):
            raise ColumnLongitudinalDetailingError(
                "FINAL_DETAILING_REQUIRED cannot contain an entirely proven outcome population"
            )
        object.__setattr__(self, "outcomes", outcomes)

        refs = _refs(self.source_refs)
        required_refs = {
            selected.selected_rebar_ref,
            selected.candidate_adequacy_ref,
            design_result_ref,
            design_lineage_ref,
        }
        if not required_refs.issubset(set(refs)):
            raise ColumnLongitudinalDetailingError(
                "A35 source refs lost selection/adequacy/design-result lineage provenance"
            )
        object.__setattr__(self, "source_refs", refs)

    @property
    def complete(self) -> bool:
        return self.status == DETAILING_PROVEN

    @property
    def unresolved_items(self) -> tuple[str, ...]:
        return tuple(item.item for item in self.outcomes if not item.resolved)

    @property
    def selected_candidate_identity(self) -> str:
        return self.engine_selected_rebar.candidate_id

    @property
    def selected_candidate(self):
        return self.engine_selected_rebar.selected_candidate

    @property
    def selected_bar_diameter_mm(self) -> float:
        return self.engine_selected_rebar.selected_candidate.bar_diameter_mm

    @property
    def selected_bar_count(self) -> int:
        return self.engine_selected_rebar.selected_candidate.bar_count

    @property
    def selected_total_area_mm2(self) -> Decimal:
        return self.engine_selected_rebar.as_total_mm2

    @property
    def candidate_adequacy_ref(self) -> str:
        return self.engine_selected_rebar.candidate_adequacy_ref

    @property
    def design_result_parent_ref(self) -> str:
        return _single_provenance_ref(
            self.engine_selected_rebar.provenance_refs,
            prefix=DESIGN_RESULT_REF_PREFIX,
            label="DesignResultIdentity parentage",
        )

    @property
    def design_lineage_qualification_ref(self) -> str:
        return _single_provenance_ref(
            self.engine_selected_rebar.provenance_refs,
            prefix=DESIGN_LINEAGE_REF_PREFIX,
            label="DesignLineageQualification",
        )


def detailing_facts_digest(facts):
    return sha256(json.dumps(asdict(facts),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ReviewedColumnDetailingEvidence:
    component_id: str
    selected_rebar_ref: str
    model_fingerprint: str
    evidence_epoch_id: str
    material_context_ref: str
    design_result_ref: str
    design_lineage_ref: str
    source_hashes: tuple[tuple[str,str],...]
    applicability: str
    reviewer: str
    reviewed_at: str
    source_refs: tuple[str,...]
    facts: DetailingFacts
    reviewed_facts_sha256: str
    material_context: ColumnPmmMaterialContextBinding

    def validate_for(self, selected):
        for field in ('component_id','selected_rebar_ref','model_fingerprint','evidence_epoch_id','material_context_ref'):
            if getattr(self,field)!=getattr(selected,field):raise ColumnLongitudinalDetailingError('A35 evidence identity mismatch: '+field)
        if type(self.facts) is not DetailingFacts:raise TypeError('DetailingFacts required')
        validate_detailing_fact_types(self.facts)
        context=self.material_context
        if type(context) is not ColumnPmmMaterialContextBinding or (context.component_id,context.model_fingerprint,context.evidence_epoch_id,context.binding_ref)!=(self.component_id,self.model_fingerprint,self.evidence_epoch_id,self.material_context_ref):raise ColumnLongitudinalDetailingError('Original selected material context required')
        for bond in (None if self.facts.lap is None else self.facts.lap.bond,None if self.facts.anchorage is None else self.facts.anchorage.bond):
            if bond is not None and abs(bond.fyd_mpa-context.material.fyd_mpa)>1e-9:raise ColumnLongitudinalDetailingError('Anchorage steel design strength differs from selected material context')
        if self.design_result_ref!=_single_provenance_ref(selected.provenance_refs,prefix=DESIGN_RESULT_REF_PREFIX,label='result') or self.design_lineage_ref!=_single_provenance_ref(selected.provenance_refs,prefix=DESIGN_LINEAGE_REF_PREFIX,label='lineage'):
            raise ColumnLongitudinalDetailingError('A35 evidence design parentage differs')
        if self.source_hashes!=SOURCE_HASHES:raise ColumnLongitudinalDetailingError('Original regulatory source hashes differ')
        if self.applicability!='TBDY_HIGH_DUCTILITY_RECTANGULAR_SINGLE_DEFORMED_BARS':raise ColumnLongitudinalDetailingError('Reviewed supported detailing applicability required')
        _text(self.reviewer,'reviewer');_refs(self.source_refs)
        if datetime.fromisoformat(self.reviewed_at).tzinfo is None:raise ColumnLongitudinalDetailingError('Zoned review date required')
        if type(self.facts) is not DetailingFacts or self.reviewed_facts_sha256!=detailing_facts_digest(self.facts):raise ColumnLongitudinalDetailingError('Detailing review facts changed')


def materialize_selected_column_longitudinal_detailing(
    selected_rebar: CanonicalEngineSelectedRebar,
    *,
    authority_catalog: RegulatoryAuthorityCatalog = FND_COL_1_AUTHORITY_CATALOG,
    reviewed_evidence: ReviewedColumnDetailingEvidence | None = None,
) -> ColumnLongitudinalDetailingResolution:
    """Evaluate source-bound detailing facts while retaining original selection.

    Missing optional evidence preserves the existing unresolved contract. Only
    reviewed factual populations for the supported scope can resolve a rule;
    a resolved failed rule never yields DETAILING_PROVEN.
    """
    if not isinstance(selected_rebar, CanonicalEngineSelectedRebar):
        raise TypeError("selected_rebar must be CanonicalEngineSelectedRebar")
    if selected_rebar.authority != ENGINE_SELECTED_REBAR_AUTHORITY:
        raise ColumnLongitudinalDetailingError(
            "A35 requires canonical ENGINE_SELECTED_REBAR authority"
        )
    if not isinstance(authority_catalog, RegulatoryAuthorityCatalog):
        raise TypeError("authority_catalog must be RegulatoryAuthorityCatalog")

    validated = validate_rule_authority(FND_COL_1_CHECK_SPEC, authority_catalog)
    if LAP_RHO_CLAIM not in validated.claim_refs:
        raise ColumnLongitudinalDetailingError(
            "validated FND-COL-1 authority is missing lap-section rho claim"
        )
    lap_review_refs = tuple(
        review.review_id
        for review in authority_catalog.review_records
        if review.claim_id == LAP_RHO_CLAIM
    )
    if not lap_review_refs:
        raise ColumnLongitudinalDetailingError(
            "lap-section rho claim has no reviewed authority reference"
        )

    selected_refs = _refs(
        (
            selected_rebar.selected_rebar_ref,
            selected_rebar.candidate_adequacy_ref,
            *selected_rebar.required_area_decision_ids,
            *selected_rebar.pmm_decision_ids,
            selected_rebar.material_context_ref,
            *selected_rebar.provenance_refs,
            validated.binding_ref,
            validated.fingerprint_ref,
        )
    )
    lap_refs = _refs((*selected_refs, LAP_RHO_CLAIM, *lap_review_refs))

    outcomes = (
        ColumnLongitudinalDetailingOutcome(
            item=LAP_SPLICE_LOCATION_REGION,
            status=OUTCOME_UNRESOLVED,
            reason="SOURCE_BOUND_LAP_SPLICE_LOCATION_REGION_NOT_MATERIALIZED",
            source_refs=selected_refs,
        ),
        ColumnLongitudinalDetailingOutcome(
            item=LAP_SECTION_RHO,
            status=OUTCOME_UNRESOLVED,
            reason="SOURCE_BOUND_LAP_SECTION_REINFORCEMENT_POPULATION_NOT_MATERIALIZED",
            source_refs=lap_refs,
        ),
        ColumnLongitudinalDetailingOutcome(
            item=ANCHORAGE,
            status=OUTCOME_UNRESOLVED,
            reason="SOURCE_BOUND_ANCHORAGE_DETAILING_NOT_MATERIALIZED",
            source_refs=selected_refs,
        ),
        ColumnLongitudinalDetailingOutcome(
            item=SECTION_TRANSITION,
            status=OUTCOME_UNRESOLVED,
            reason="SOURCE_BOUND_SECTION_TRANSITION_DETAILING_NOT_MATERIALIZED",
            source_refs=selected_refs,
        ),
        ColumnLongitudinalDetailingOutcome(
            item=MECHANICAL_WELDED_SPLICE_APPLICABILITY,
            status=OUTCOME_UNRESOLVED,
            reason="SOURCE_BOUND_MECHANICAL_WELDED_SPLICE_APPLICABILITY_NOT_MATERIALIZED",
            source_refs=selected_refs,
        ),
        ColumnLongitudinalDetailingOutcome(
            item=CONTINUITY_CORNER_REQUIREMENTS,
            status=OUTCOME_UNRESOLVED,
            reason="SOURCE_BOUND_CONTINUITY_CORNER_DETAILING_NOT_MATERIALIZED",
            source_refs=selected_refs,
        ),
    )
    if reviewed_evidence is not None:
        if type(reviewed_evidence) is not ReviewedColumnDetailingEvidence:raise TypeError('Original typed detailing evidence required.')
        reviewed_evidence.validate_for(selected_rebar)
        candidate=selected_rebar.selected_candidate
        calculated=evaluate_detailing_facts(reviewed_evidence.facts,bars=candidate.bars,
            gross_area_mm2=float(candidate.as_total_mm2)/float(candidate.rho))
        outcomes=tuple(ColumnLongitudinalDetailingOutcome(x['item'],x['status'],x['reason'],
            _refs((*selected_refs,*reviewed_evidence.source_refs,x['clause'],
                *[value for key,value in SOURCE_HASHES],reviewed_evidence.reviewed_facts_sha256)),
            json.dumps(x['values'],ensure_ascii=False,sort_keys=True,allow_nan=False)) for x in calculated)
    status=(DETAILING_FAILED if any(o.status==OUTCOME_FAIL for o in outcomes) else
            DETAILING_PROVEN if all(o.status in {OUTCOME_PROVEN,OUTCOME_NOT_APPLICABLE} for o in outcomes) else FINAL_DETAILING_REQUIRED)
    return ColumnLongitudinalDetailingResolution(
        component_id=selected_rebar.component_id,
        selected_rebar_ref=selected_rebar.selected_rebar_ref,
        model_fingerprint=selected_rebar.model_fingerprint,
        evidence_epoch_id=selected_rebar.evidence_epoch_id,
        engine_selected_rebar=selected_rebar,
        status=status,
        outcomes=outcomes,
        source_refs=_refs(
            (
                A35_AUTHORITY,
                *selected_refs,
                LAP_RHO_CLAIM,
                *lap_review_refs,
                *(ref for outcome in outcomes for ref in outcome.source_refs),
            )
        ),
    )


__all__ = [
    "ReviewedColumnDetailingEvidence",
    "detailing_facts_digest",
    "DETAILING_FAILED",
    "OUTCOME_FAIL",
    "OUTCOME_NOT_APPLICABLE",
    "A35_AUTHORITY",
    "ANCHORAGE",
    "CONTINUITY_CORNER_REQUIREMENTS",
    "ColumnLongitudinalDetailingError",
    "ColumnLongitudinalDetailingOutcome",
    "ColumnLongitudinalDetailingResolution",
    "DETAILING_PROVEN",
    "FINAL_DETAILING_REQUIRED",
    "LAP_SECTION_RHO",
    "LAP_SPLICE_LOCATION_REGION",
    "MECHANICAL_WELDED_SPLICE_APPLICABILITY",
    "OUTCOME_PROVEN",
    "OUTCOME_UNRESOLVED",
    "SECTION_TRANSITION",
    "materialize_selected_column_longitudinal_detailing",
]
