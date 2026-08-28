"""Typed P8A component x design-combination eligibility projection.

This module closes the semantic gap between component-scoped FND-COL-2
readiness and downstream P8A per-combination eligibility. It performs no ETABS
access, no reinforcement promotion, no section-capacity work and no selection.

A projection may be ELIGIBLE only when all of the following bind exactly:

* one component-scoped ColumnDesignDemandReadiness result is READY;
* one concrete-design combination identity is reconciled by exact
  (design_combo_type, combo_name) identity;
* the same factual definition fingerprint is preserved;
* the component demand engine contains a proven result for that exact combo
  name, including factual leaf case types and reconstruction semantics;
* a separate combo-grain analysis-basis binding matches the same identity,
  definition fingerprint, model fingerprint and EvidenceEpoch.

Component-level MATCH is never broadcast to combinations. Same-name design
combinations across multiple design types are intentionally ambiguous for later
PMMCombo name-only binding and therefore remain blocked here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
import hashlib
import json
from typing import Mapping, Sequence

from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    AnalysisBasisEligibilityEvidence,
    ConcreteDesignComboReconciliation,
    DesignComboIdentity,
)
from tbdy_engine.design.columns.column_design_readiness import (
    ANALYSIS_BASIS_MATCH,
    READY,
    ColumnDesignDemandReadiness,
)
from tbdy_engine.design.columns.design_demand_states import (
    DESIGN_AUTHORITY_RESPONSE_SPECTRUM,
    DESIGN_AUTHORITY_STATIC,
)

AUTHORITY = "P8A_COLUMN_COMBO_ELIGIBILITY_PROJECTION"

BLOCKER_COMPONENT_NOT_READY = "COMPONENT_READINESS_NOT_READY"
BLOCKER_COMPONENT_ANALYSIS_BASIS = "COMPONENT_ANALYSIS_BASIS_NOT_MATCH"
BLOCKER_RECONCILIATION_NOT_CLOSED = "CONCRETE_DESIGN_COMBO_RECONCILIATION_NOT_CLOSED"
BLOCKER_IDENTITY_NOT_MATCHED = "DESIGN_COMBO_IDENTITY_NOT_MATCHED"
BLOCKER_AMBIGUOUS_NAME = "AMBIGUOUS_DESIGN_COMBO_NAME_ACROSS_TYPES"
BLOCKER_MISSING_DEFINITION_FINGERPRINT = "MISSING_CURRENT_DEFINITION_FINGERPRINT"
BLOCKER_MISSING_DEMAND_RESULT = "MISSING_COMPONENT_COMBO_DEMAND_RESULT"
BLOCKER_DEMAND_RESULT_NOT_PROVEN = "COMPONENT_COMBO_DEMAND_RESULT_NOT_PROVEN"
BLOCKER_MISSING_ANALYSIS_BASIS = "MISSING_EXACT_COMBO_ANALYSIS_BASIS_BINDING"
BLOCKER_ANALYSIS_BASIS_NOT_MATCH = "EXACT_COMBO_ANALYSIS_BASIS_NOT_MATCH"
BLOCKER_ANALYSIS_BASIS_DEFINITION = "EXACT_COMBO_ANALYSIS_BASIS_DEFINITION_MISMATCH"
BLOCKER_UNSUPPORTED_CONSTITUENT = "UNSUPPORTED_OR_UNTYPED_COMBO_CONSTITUENT"
BLOCKER_RS_RECONSTRUCTION = "RESPONSE_SPECTRUM_RECONSTRUCTION_NOT_PROVEN"
BLOCKER_STATIC_RECONSTRUCTION = "STATIC_RECONSTRUCTION_NOT_PROVEN"


class ColumnComboEligibilityProjectionError(ValueError):
    """Raised when typed projection inputs are malformed or cross-epoch."""


class ColumnComboEligibilityState(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    BLOCKED_COMPONENT = "BLOCKED_COMPONENT"
    BLOCKED_COMBO = "BLOCKED_COMBO"
    BLOCKED_ANALYSIS_BASIS = "BLOCKED_ANALYSIS_BASIS"
    BLOCKED_AMBIGUOUS_DESIGN_COMBO_IDENTITY = "BLOCKED_AMBIGUOUS_DESIGN_COMBO_IDENTITY"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnComboEligibilityProjectionError(f"{label} must be a nonblank canonical string")
    return value


def _identity(value: DesignComboIdentity, label: str) -> DesignComboIdentity:
    if not isinstance(value, tuple) or len(value) != 2:
        raise ColumnComboEligibilityProjectionError(f"{label} must be exact (design_combo_type, combo_name)")
    return (_text(value[0], f"{label}.design_combo_type"), _text(value[1], f"{label}.combo_name"))


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    refs = tuple(_text(value, label) for value in values)
    if not refs or len(refs) != len(set(refs)):
        raise ColumnComboEligibilityProjectionError(f"{label} must be nonempty and unique")
    return refs


def _canonical_factor(value: object) -> str:
    if value is None or isinstance(value, bool):
        raise ColumnComboEligibilityProjectionError("constituent scale factor must be finite numeric")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ColumnComboEligibilityProjectionError("constituent scale factor must be finite numeric") from exc
    if not decimal_value.is_finite():
        raise ColumnComboEligibilityProjectionError("constituent scale factor must be finite numeric")
    if decimal_value == 0:
        return "0"
    return format(decimal_value.normalize(), "f")


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


@dataclass(frozen=True, slots=True)
class ComponentReadinessBinding:
    """Same-context binding for one component-scoped FND-COL-2 readiness result."""

    readiness: ColumnDesignDemandReadiness
    model_fingerprint: str
    evidence_epoch_id: str
    readiness_ref: str
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.readiness, ColumnDesignDemandReadiness):
            raise TypeError("readiness must be ColumnDesignDemandReadiness")
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        object.__setattr__(self, "readiness_ref", _text(self.readiness_ref, "readiness_ref"))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "readiness.provenance_ref"))
        if self.readiness.design_demands.component_id != self.readiness.component_id:
            raise ColumnComboEligibilityProjectionError(
                "readiness component_id differs from its design-demand component_id"
            )
        if any(state.component_id != self.readiness.component_id for state in self.readiness.demand_states):
            raise ColumnComboEligibilityProjectionError(
                "readiness demand-state population contains a different component_id"
            )

    @property
    def component_id(self) -> str:
        return self.readiness.component_id


@dataclass(frozen=True, slots=True)
class ComboAnalysisBasisBinding:
    """Explicit exact-combo binding around the existing analysis-basis primitive."""

    design_combo_identity: DesignComboIdentity
    evidence: AnalysisBasisEligibilityEvidence
    normalized_definition_fingerprint: str
    model_fingerprint: str
    evidence_epoch_id: str
    provenance_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "design_combo_identity",
            _identity(self.design_combo_identity, "design_combo_identity"),
        )
        if not isinstance(self.evidence, AnalysisBasisEligibilityEvidence):
            raise TypeError("evidence must be AnalysisBasisEligibilityEvidence")
        object.__setattr__(
            self,
            "normalized_definition_fingerprint",
            _text(self.normalized_definition_fingerprint, "normalized_definition_fingerprint"),
        )
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "analysis_basis.provenance_ref"))


@dataclass(frozen=True, slots=True)
class ComboConstituentEligibilityFact:
    name: str
    scale_factor: str
    cname_type: str
    case_type: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "constituent.name"))
        object.__setattr__(self, "scale_factor", _text(self.scale_factor, "constituent.scale_factor"))
        object.__setattr__(self, "cname_type", _text(self.cname_type, "constituent.cname_type"))
        if self.case_type is not None:
            object.__setattr__(self, "case_type", _text(self.case_type, "constituent.case_type"))


@dataclass(frozen=True, slots=True)
class ColumnComboEligibilityProjection:
    projection_id: str
    component_id: str
    design_combo_identity: DesignComboIdentity
    normalized_definition_fingerprint: str | None
    constituent_facts: tuple[ComboConstituentEligibilityFact, ...]
    combo_pattern: str | None
    reconstruction_authority: str | None
    reconstruction_behavior_refs: tuple[str, ...]
    analysis_basis_status: str | None
    analysis_basis_ref: str | None
    component_readiness_status: str
    component_readiness_ref: str
    model_fingerprint: str
    evidence_epoch_id: str
    eligibility_state: ColumnComboEligibilityState
    blockers: tuple[str, ...]
    provenance_refs: tuple[str, ...]
    authority: str = AUTHORITY

    def __post_init__(self) -> None:
        object.__setattr__(self, "projection_id", _text(self.projection_id, "projection_id"))
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        object.__setattr__(
            self,
            "design_combo_identity",
            _identity(self.design_combo_identity, "design_combo_identity"),
        )
        if self.normalized_definition_fingerprint is not None:
            object.__setattr__(
                self,
                "normalized_definition_fingerprint",
                _text(self.normalized_definition_fingerprint, "normalized_definition_fingerprint"),
            )
        facts = tuple(self.constituent_facts)
        if any(not isinstance(item, ComboConstituentEligibilityFact) for item in facts):
            raise TypeError("constituent_facts must contain ComboConstituentEligibilityFact")
        object.__setattr__(self, "constituent_facts", facts)
        if self.combo_pattern is not None:
            object.__setattr__(self, "combo_pattern", _text(self.combo_pattern, "combo_pattern"))
        if self.reconstruction_authority is not None:
            object.__setattr__(
                self,
                "reconstruction_authority",
                _text(self.reconstruction_authority, "reconstruction_authority"),
            )
        object.__setattr__(
            self,
            "reconstruction_behavior_refs",
            tuple(_text(item, "reconstruction_behavior_ref") for item in self.reconstruction_behavior_refs),
        )
        if self.analysis_basis_status is not None:
            object.__setattr__(
                self,
                "analysis_basis_status",
                _text(self.analysis_basis_status, "analysis_basis_status"),
            )
        if self.analysis_basis_ref is not None:
            object.__setattr__(self, "analysis_basis_ref", _text(self.analysis_basis_ref, "analysis_basis_ref"))
        object.__setattr__(
            self,
            "component_readiness_status",
            _text(self.component_readiness_status, "component_readiness_status"),
        )
        object.__setattr__(
            self,
            "component_readiness_ref",
            _text(self.component_readiness_ref, "component_readiness_ref"),
        )
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        if not isinstance(self.eligibility_state, ColumnComboEligibilityState):
            raise TypeError("eligibility_state must be ColumnComboEligibilityState")
        object.__setattr__(self, "blockers", tuple(_text(item, "blocker") for item in self.blockers))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "provenance_ref"))
        if self.authority != AUTHORITY:
            raise ColumnComboEligibilityProjectionError("projection authority label mismatch")
        if self.eligible and self.blockers:
            raise ColumnComboEligibilityProjectionError("ELIGIBLE projection cannot carry blockers")
        if not self.eligible and not self.blockers:
            raise ColumnComboEligibilityProjectionError("blocked projection must carry blocker evidence")

    @property
    def eligible(self) -> bool:
        return self.eligibility_state is ColumnComboEligibilityState.ELIGIBLE


def _definition_fingerprint(
    reconciliation: ConcreteDesignComboReconciliation,
    identity: DesignComboIdentity,
) -> str | None:
    matches = tuple(
        fingerprint
        for design_type, combo_name, fingerprint in reconciliation.definition_fingerprints
        if (design_type, combo_name) == identity
    )
    if len(matches) > 1:
        raise ColumnComboEligibilityProjectionError(
            f"multiple current definition fingerprints for identity={identity!r}"
        )
    return matches[0] if matches else None


def _constituent_facts(combo_result: object) -> tuple[ComboConstituentEligibilityFact, ...]:
    classification = combo_result.classification
    static_names = set(classification.static_case_names)
    spectrum_names = set(classification.response_spectrum_case_names)
    facts: list[ComboConstituentEligibilityFact] = []
    for term in combo_result.definition.constituents:
        case_type: str | None = None
        if term.name in static_names:
            case_type = "LinStatic"
        elif term.name in spectrum_names:
            case_type = "LinRespSpec"
        facts.append(
            ComboConstituentEligibilityFact(
                name=term.name,
                scale_factor=_canonical_factor(term.scale_factor),
                cname_type=term.cname_type,
                case_type=case_type,
            )
        )
    return tuple(facts)


def _projection_state(blockers: tuple[str, ...]) -> ColumnComboEligibilityState:
    if not blockers:
        return ColumnComboEligibilityState.ELIGIBLE
    if BLOCKER_AMBIGUOUS_NAME in blockers:
        return ColumnComboEligibilityState.BLOCKED_AMBIGUOUS_DESIGN_COMBO_IDENTITY
    if BLOCKER_COMPONENT_NOT_READY in blockers or BLOCKER_COMPONENT_ANALYSIS_BASIS in blockers:
        return ColumnComboEligibilityState.BLOCKED_COMPONENT
    if (
        BLOCKER_MISSING_ANALYSIS_BASIS in blockers
        or BLOCKER_ANALYSIS_BASIS_NOT_MATCH in blockers
        or BLOCKER_ANALYSIS_BASIS_DEFINITION in blockers
    ):
        return ColumnComboEligibilityState.BLOCKED_ANALYSIS_BASIS
    return ColumnComboEligibilityState.BLOCKED_COMBO


def _projection_id(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "column-combo-eligibility:sha256:" + hashlib.sha256(encoded).hexdigest()


def project_column_combo_eligibility(
    *,
    readiness_binding: ComponentReadinessBinding,
    reconciliation: ConcreteDesignComboReconciliation,
    analysis_basis_bindings: Mapping[DesignComboIdentity, ComboAnalysisBasisBinding],
) -> tuple[ColumnComboEligibilityProjection, ...]:
    """Project exact P8A eligibility without component-to-combo broadcasting."""
    if not isinstance(readiness_binding, ComponentReadinessBinding):
        raise TypeError("readiness_binding must be ComponentReadinessBinding")
    if not isinstance(reconciliation, ConcreteDesignComboReconciliation):
        raise TypeError("reconciliation must be ConcreteDesignComboReconciliation")

    if (
        readiness_binding.model_fingerprint != reconciliation.model_fingerprint
        or readiness_binding.evidence_epoch_id != reconciliation.evidence_epoch_id
    ):
        raise ColumnComboEligibilityProjectionError(
            "component readiness and combo reconciliation do not share model fingerprint/EvidenceEpoch"
        )

    normalized_basis: dict[DesignComboIdentity, ComboAnalysisBasisBinding] = {}
    for raw_identity, binding in analysis_basis_bindings.items():
        identity = _identity(raw_identity, "analysis_basis_bindings key")
        if not isinstance(binding, ComboAnalysisBasisBinding):
            raise TypeError("analysis_basis_bindings values must be ComboAnalysisBasisBinding")
        if binding.design_combo_identity != identity:
            raise ColumnComboEligibilityProjectionError(
                "analysis-basis mapping key differs from binding design_combo_identity"
            )
        if (
            binding.model_fingerprint != reconciliation.model_fingerprint
            or binding.evidence_epoch_id != reconciliation.evidence_epoch_id
        ):
            raise ColumnComboEligibilityProjectionError(
                "analysis-basis binding does not share reconciliation model fingerprint/EvidenceEpoch"
            )
        normalized_basis[identity] = binding

    identities = tuple(sorted(set(reconciliation.expected) | set(reconciliation.actual_selected)))
    if not identities:
        raise ColumnComboEligibilityProjectionError("reconciliation contains no design-combo identities")

    name_counts: dict[str, int] = {}
    for _, combo_name in identities:
        name_counts[combo_name] = name_counts.get(combo_name, 0) + 1

    demand_by_name = {
        item.definition.name: item
        for item in readiness_binding.readiness.design_demands.combo_results
    }
    if len(demand_by_name) != len(readiness_binding.readiness.design_demands.combo_results):
        raise ColumnComboEligibilityProjectionError("component readiness contains duplicate combo demand names")

    projections: list[ColumnComboEligibilityProjection] = []
    for identity in identities:
        design_combo_type, combo_name = identity
        blockers: list[str] = []

        if readiness_binding.readiness.status != READY:
            blockers.append(BLOCKER_COMPONENT_NOT_READY)
        if readiness_binding.readiness.analysis_basis_status != ANALYSIS_BASIS_MATCH:
            blockers.append(BLOCKER_COMPONENT_ANALYSIS_BASIS)
        if not reconciliation.closed:
            blockers.append(BLOCKER_RECONCILIATION_NOT_CLOSED)
        if identity not in reconciliation.matched:
            blockers.append(BLOCKER_IDENTITY_NOT_MATCHED)
        if name_counts[combo_name] != 1:
            blockers.append(BLOCKER_AMBIGUOUS_NAME)

        definition_fingerprint = _definition_fingerprint(reconciliation, identity)
        if definition_fingerprint is None:
            blockers.append(BLOCKER_MISSING_DEFINITION_FINGERPRINT)

        combo_result = demand_by_name.get(combo_name)
        constituent_facts: tuple[ComboConstituentEligibilityFact, ...] = ()
        combo_pattern: str | None = None
        reconstruction_authority: str | None = None
        behavior_refs: tuple[str, ...] = ()
        if combo_result is None:
            blockers.append(BLOCKER_MISSING_DEMAND_RESULT)
        else:
            constituent_facts = _constituent_facts(combo_result)
            combo_pattern = combo_result.classification.pattern
            if (
                combo_result.status != "PROVEN_PROMOTED_DESIGN_DEMAND"
                or not combo_result.classification.supported
                or combo_result.build is None
                or combo_result.build.status != "PROVEN_DESIGN_DEMAND_STATES"
            ):
                blockers.append(BLOCKER_DEMAND_RESULT_NOT_PROVEN)
            else:
                reconstruction_authority = combo_result.build.authority
                behavior_refs = tuple(combo_result.build.behavior_refs)
                if any(
                    item.cname_type != "LOAD_CASE" or item.case_type not in {"LinStatic", "LinRespSpec"}
                    for item in constituent_facts
                ):
                    blockers.append(BLOCKER_UNSUPPORTED_CONSTITUENT)
                if combo_result.classification.response_spectrum_case_names:
                    if (
                        reconstruction_authority != DESIGN_AUTHORITY_RESPONSE_SPECTRUM
                        or not behavior_refs
                    ):
                        blockers.append(BLOCKER_RS_RECONSTRUCTION)
                elif reconstruction_authority != DESIGN_AUTHORITY_STATIC:
                    blockers.append(BLOCKER_STATIC_RECONSTRUCTION)

        analysis_binding = normalized_basis.get(identity)
        analysis_status: str | None = None
        analysis_ref: str | None = None
        if analysis_binding is None:
            blockers.append(BLOCKER_MISSING_ANALYSIS_BASIS)
        else:
            analysis_status = analysis_binding.evidence.status_value
            analysis_ref = analysis_binding.evidence.compatibility_ref
            if not analysis_binding.evidence.acceptable:
                blockers.append(BLOCKER_ANALYSIS_BASIS_NOT_MATCH)
            if (
                definition_fingerprint is None
                or analysis_binding.normalized_definition_fingerprint != definition_fingerprint
            ):
                blockers.append(BLOCKER_ANALYSIS_BASIS_DEFINITION)

        blockers_tuple = _unique(blockers)
        state = _projection_state(blockers_tuple)

        provenance_parts: list[str] = [
            readiness_binding.readiness_ref,
            *readiness_binding.provenance_refs,
            *reconciliation.source_refs,
        ]
        if analysis_binding is not None:
            provenance_parts.extend(
                (
                    analysis_binding.evidence.compatibility_ref,
                    *analysis_binding.evidence.provenance_refs,
                    *analysis_binding.provenance_refs,
                )
            )
        provenance_parts.extend(behavior_refs)
        provenance_refs = _unique(provenance_parts)

        id_payload = {
            "component_id": readiness_binding.component_id,
            "design_combo_identity": identity,
            "definition_fingerprint": definition_fingerprint,
            "constituents": tuple(
                (item.name, item.scale_factor, item.cname_type, item.case_type)
                for item in constituent_facts
            ),
            "combo_pattern": combo_pattern,
            "reconstruction_authority": reconstruction_authority,
            "behavior_refs": behavior_refs,
            "analysis_basis_status": analysis_status,
            "analysis_basis_ref": analysis_ref,
            "component_readiness_status": readiness_binding.readiness.status,
            "model_fingerprint": reconciliation.model_fingerprint,
            "evidence_epoch_id": reconciliation.evidence_epoch_id,
            "eligibility_state": state.value,
            "blockers": blockers_tuple,
        }
        projections.append(
            ColumnComboEligibilityProjection(
                projection_id=_projection_id(id_payload),
                component_id=readiness_binding.component_id,
                design_combo_identity=(design_combo_type, combo_name),
                normalized_definition_fingerprint=definition_fingerprint,
                constituent_facts=constituent_facts,
                combo_pattern=combo_pattern,
                reconstruction_authority=reconstruction_authority,
                reconstruction_behavior_refs=behavior_refs,
                analysis_basis_status=analysis_status,
                analysis_basis_ref=analysis_ref,
                component_readiness_status=readiness_binding.readiness.status,
                component_readiness_ref=readiness_binding.readiness_ref,
                model_fingerprint=reconciliation.model_fingerprint,
                evidence_epoch_id=reconciliation.evidence_epoch_id,
                eligibility_state=state,
                blockers=blockers_tuple,
                provenance_refs=provenance_refs,
            )
        )

    return tuple(sorted(projections, key=lambda item: item.design_combo_identity))


__all__ = [
    "AUTHORITY",
    "BLOCKER_AMBIGUOUS_NAME",
    "BLOCKER_ANALYSIS_BASIS_DEFINITION",
    "BLOCKER_ANALYSIS_BASIS_NOT_MATCH",
    "BLOCKER_COMPONENT_ANALYSIS_BASIS",
    "BLOCKER_COMPONENT_NOT_READY",
    "BLOCKER_DEMAND_RESULT_NOT_PROVEN",
    "BLOCKER_IDENTITY_NOT_MATCHED",
    "BLOCKER_MISSING_ANALYSIS_BASIS",
    "BLOCKER_MISSING_DEFINITION_FINGERPRINT",
    "BLOCKER_MISSING_DEMAND_RESULT",
    "BLOCKER_RECONCILIATION_NOT_CLOSED",
    "BLOCKER_RS_RECONSTRUCTION",
    "BLOCKER_STATIC_RECONSTRUCTION",
    "BLOCKER_UNSUPPORTED_CONSTITUENT",
    "ColumnComboEligibilityProjection",
    "ColumnComboEligibilityProjectionError",
    "ColumnComboEligibilityState",
    "ComboAnalysisBasisBinding",
    "ComboConstituentEligibilityFact",
    "ComponentReadinessBinding",
    "project_column_combo_eligibility",
]
