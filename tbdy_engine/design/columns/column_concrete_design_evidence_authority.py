"""Column concrete-design evidence eligibility authority foundation.

Reconciles reviewed expected design-combo membership with a proven read-only
selected Concrete Frame Design population. Existing ETABS combo-definition
evidence and the existing name-blind classifier remain the semantic authority.
No PMMArea promotion, reinforcement selection or capacity logic lives here.

Analysis-basis eligibility is consumed through a tiny immutable join artifact
containing the already-resolved canonical status value plus its source ref.  We
do not import ``regulatory`` here: importing that package merely to compare a
resolved status would recreate the package-initialization cycle that this
foundation is required to avoid.  This module defines no second analysis-basis
enum and treats every value other than the exact canonical ``MATCH`` value as
blocked.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from typing import Mapping, Sequence

from tbdy_engine.design.columns.combo_pattern_engine import ComboPatternConstituent, classify_combo_pattern
from tbdy_engine.features.column_concrete_design_evidence import (
    ActualConcreteDesignComboPopulation, ActualConcreteDesignComboSourceProof,
    ActualSelectedConcreteDesignCombo, ColumnDesignComponentBinding,
    ComponentBindingStatus, ExpectedConcreteDesignComboPolicy,
)
from tbdy_engine.providers.etabs_combo_definition_provider import EtabsComboDefinitionEvidence


class ColumnConcreteDesignEvidenceAuthorityError(ValueError):
    pass


class ColumnConcreteDesignEligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    BLOCKED_COMBO_POPULATION = "BLOCKED_COMBO_POPULATION"
    BLOCKED_COMBO_DEFINITION = "BLOCKED_COMBO_DEFINITION"
    BLOCKED_ANALYSIS_BASIS = "BLOCKED_ANALYSIS_BASIS"
    BLOCKED_COMPONENT_IDENTITY = "BLOCKED_COMPONENT_IDENTITY"
    BLOCKED_SECTION_IDENTITY = "BLOCKED_SECTION_IDENTITY"
    BLOCKED_EVIDENCE_EPOCH = "BLOCKED_EVIDENCE_EPOCH"
    NO_DATA = "NO_DATA"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnConcreteDesignEvidenceAuthorityError(f"{label} must be a nonblank canonical string")
    return value


@dataclass(frozen=True, slots=True)
class AnalysisBasisEligibilityEvidence:
    """Join-only projection of an existing canonical analysis-basis decision.

    ``status_value`` is expected to be ``AnalysisBasisStatus.value`` from the
    accepted analysis-basis authority.  This artifact does not reinterpret or
    resolve that status; it only preserves the value/ref needed by this
    downstream reconciliation.  Fail-closed consumption means only ``MATCH``
    can pass.
    """

    status_value: str
    compatibility_ref: str
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status_value", _text(self.status_value, "analysis_basis.status_value"))
        object.__setattr__(self, "compatibility_ref", _text(self.compatibility_ref, "analysis_basis.compatibility_ref"))
        refs = tuple(_text(item, "analysis_basis.provenance_ref") for item in self.provenance_refs)
        if len(refs) != len(set(refs)):
            raise ColumnConcreteDesignEvidenceAuthorityError("analysis-basis provenance refs must be unique")
        object.__setattr__(self, "provenance_refs", refs)

    @property
    def acceptable(self) -> bool:
        return self.status_value == "MATCH"


def _definition_payload(definition: EtabsComboDefinitionEvidence) -> dict[str, object]:
    if not isinstance(definition, EtabsComboDefinitionEvidence):
        raise TypeError("definition must be EtabsComboDefinitionEvidence")
    nested_by_name = {item.name: item for item in definition.nested_combos}
    return {
        "name": definition.name,
        "combo_type_code": definition.combo_type_code,
        "combo_type": definition.combo_type,
        "constituents": [
            {
                "index": item.index,
                "cname_type_code": item.cname_type_code,
                "cname_type": item.cname_type,
                "name": item.name,
                "scale_factor": format(float(item.scale_factor), ".17g"),
                "nested": _definition_payload(nested_by_name[item.name])
                if item.cname_type == "LOAD_COMBO" and item.name in nested_by_name else None,
            }
            for item in definition.constituents
        ],
    }


def normalized_combo_definition_fingerprint(definition: EtabsComboDefinitionEvidence) -> str:
    encoded = json.dumps(_definition_payload(definition), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "combo-definition:sha256:" + hashlib.sha256(encoded).hexdigest()


def build_actual_selected_combo_population(
    *, source_proof: ActualConcreteDesignComboSourceProof, model_fingerprint: str,
    evidence_epoch_id: str, selected_combo_names: Sequence[str],
    definitions: Sequence[EtabsComboDefinitionEvidence], source_row_refs: Mapping[str, str],
) -> ActualConcreteDesignComboPopulation:
    names = tuple(_text(item, "selected_combo_name") for item in selected_combo_names)
    if not names or len(names) != len(set(names)):
        raise ColumnConcreteDesignEvidenceAuthorityError("selected combo names must be nonempty and unique")
    defs = tuple(definitions)
    definition_by_name = {item.name: item for item in defs}
    if len(definition_by_name) != len(defs):
        raise ColumnConcreteDesignEvidenceAuthorityError("definition names must be unique")
    records = []
    for name in names:
        definition = definition_by_name.get(name)
        if definition is None:
            raise ColumnConcreteDesignEvidenceAuthorityError(f"selected combo {name!r} has no same-epoch factual ETABS definition")
        source_row_ref = source_row_refs.get(name)
        if source_row_ref is None:
            raise ColumnConcreteDesignEvidenceAuthorityError(f"selected combo {name!r} has no source row ref")
        fingerprint = normalized_combo_definition_fingerprint(definition)
        records.append(ActualSelectedConcreteDesignCombo(name, fingerprint, source_row_ref, (f"definition:{name}:{fingerprint}",)))
    return ActualConcreteDesignComboPopulation(source_proof, model_fingerprint, evidence_epoch_id, tuple(records))


@dataclass(frozen=True, slots=True)
class ConcreteDesignComboReconciliation:
    expected: tuple[str, ...]
    actual_selected: tuple[str, ...]
    matched: tuple[str, ...]
    missing_expected: tuple[str, ...]
    unexpected_selected: tuple[str, ...]
    definition_mismatch: tuple[str, ...]
    unsupported_definition: tuple[str, ...]
    analysis_basis_blocked: tuple[str, ...]
    blocked_governing_combos: tuple[str, ...]
    definition_fingerprints: tuple[tuple[str, str], ...]
    source_refs: tuple[str, ...]

    @property
    def closed(self) -> bool:
        return not (self.missing_expected or self.unexpected_selected or self.definition_mismatch or self.unsupported_definition or self.analysis_basis_blocked) and self.matched == self.expected == self.actual_selected


def reconcile_concrete_design_combos(
    *, expected_policy: ExpectedConcreteDesignComboPolicy,
    actual_population: ActualConcreteDesignComboPopulation,
    current_definitions: Sequence[EtabsComboDefinitionEvidence],
    case_types: Mapping[str, str],
    analysis_basis_by_combo: Mapping[str, AnalysisBasisEligibilityEvidence],
) -> ConcreteDesignComboReconciliation:
    if not isinstance(expected_policy, ExpectedConcreteDesignComboPolicy):
        raise TypeError("expected_policy must be ExpectedConcreteDesignComboPolicy")
    if not isinstance(actual_population, ActualConcreteDesignComboPopulation):
        raise TypeError("actual_population must be ActualConcreteDesignComboPopulation")
    if any(not isinstance(value, AnalysisBasisEligibilityEvidence) for value in analysis_basis_by_combo.values()):
        raise TypeError("analysis_basis_by_combo values must be AnalysisBasisEligibilityEvidence")
    expected = tuple(sorted(expected_policy.names))
    actual = tuple(sorted(actual_population.names))
    expected_set, actual_set = set(expected), set(actual)
    missing = tuple(sorted(expected_set - actual_set))
    unexpected = tuple(sorted(actual_set - expected_set))
    defs = tuple(current_definitions)
    definition_by_name = {item.name: item for item in defs}
    if len(definition_by_name) != len(defs):
        raise ColumnConcreteDesignEvidenceAuthorityError("current definition names must be unique")
    selected_by_name = {item.combo_name: item for item in actual_population.combos}
    mismatch, unsupported, analysis_blocked, matched, fingerprints = [], [], [], [], []
    for name in sorted(expected_set & actual_set):
        current = definition_by_name.get(name)
        if current is None:
            mismatch.append(name)
            continue
        fingerprint = normalized_combo_definition_fingerprint(current)
        fingerprints.append((name, fingerprint))
        if selected_by_name[name].normalized_definition_fingerprint != fingerprint:
            mismatch.append(name)
            continue
        classification = classify_combo_pattern(
            combo_name=current.name, combo_type=current.combo_type,
            constituents=tuple(ComboPatternConstituent(item.name, item.scale_factor, item.cname_type) for item in current.constituents),
            case_types=case_types,
        )
        if not classification.supported:
            unsupported.append(name)
            continue
        basis = analysis_basis_by_combo.get(name)
        if basis is None or not basis.acceptable:
            analysis_blocked.append(name)
            continue
        matched.append(name)
    blocked = tuple(sorted(set(missing + unexpected + tuple(mismatch) + tuple(unsupported) + tuple(analysis_blocked))))
    basis_refs = tuple(
        ref
        for name in sorted(expected_set & actual_set)
        for evidence in (analysis_basis_by_combo.get(name),)
        if evidence is not None
        for ref in (evidence.compatibility_ref, *evidence.provenance_refs)
    )
    refs = tuple(dict.fromkeys((f"expected-policy:{expected_policy.policy_id}", *expected_policy.review_provenance_refs, *actual_population.source_proof.provenance_refs, *(item.source_row_ref for item in actual_population.combos), *basis_refs)))
    return ConcreteDesignComboReconciliation(
        expected, actual, tuple(sorted(matched)), missing, unexpected,
        tuple(sorted(mismatch)), tuple(sorted(unsupported)), tuple(sorted(analysis_blocked)),
        blocked, tuple(sorted(fingerprints)), refs,
    )


@dataclass(frozen=True, slots=True)
class ColumnConcreteDesignEvidenceAuthority:
    status: ColumnConcreteDesignEligibilityStatus
    combo_reconciliation: ConcreteDesignComboReconciliation | None
    component_binding: ColumnDesignComponentBinding | None
    model_fingerprint: str | None
    evidence_epoch_id: str | None
    source_refs: tuple[str, ...]
    reasons: tuple[str, ...]

    def governing_combo_eligibility(self, combo_name: str) -> ColumnConcreteDesignEligibilityStatus:
        name = _text(combo_name, "governing_combo")
        if self.status is not ColumnConcreteDesignEligibilityStatus.ELIGIBLE:
            return self.status
        assert self.combo_reconciliation is not None
        return ColumnConcreteDesignEligibilityStatus.ELIGIBLE if name in self.combo_reconciliation.matched else ColumnConcreteDesignEligibilityStatus.BLOCKED_COMBO_POPULATION


def build_column_concrete_design_evidence_authority(*, combo_reconciliation: ConcreteDesignComboReconciliation | None, component_binding: ColumnDesignComponentBinding | None) -> ColumnConcreteDesignEvidenceAuthority:
    if combo_reconciliation is None or component_binding is None:
        return ColumnConcreteDesignEvidenceAuthority(ColumnConcreteDesignEligibilityStatus.NO_DATA, combo_reconciliation, component_binding, None, None, (), ("required evidence artifact is absent",))
    if component_binding.status is ComponentBindingStatus.BLOCKED_EVIDENCE_EPOCH:
        status = ColumnConcreteDesignEligibilityStatus.BLOCKED_EVIDENCE_EPOCH
    elif component_binding.status is ComponentBindingStatus.BLOCKED_COMPONENT_IDENTITY:
        status = ColumnConcreteDesignEligibilityStatus.BLOCKED_COMPONENT_IDENTITY
    elif component_binding.status is ComponentBindingStatus.BLOCKED_SECTION_IDENTITY:
        status = ColumnConcreteDesignEligibilityStatus.BLOCKED_SECTION_IDENTITY
    elif combo_reconciliation.missing_expected or combo_reconciliation.unexpected_selected:
        status = ColumnConcreteDesignEligibilityStatus.BLOCKED_COMBO_POPULATION
    elif combo_reconciliation.definition_mismatch or combo_reconciliation.unsupported_definition:
        status = ColumnConcreteDesignEligibilityStatus.BLOCKED_COMBO_DEFINITION
    elif combo_reconciliation.analysis_basis_blocked:
        status = ColumnConcreteDesignEligibilityStatus.BLOCKED_ANALYSIS_BASIS
    elif combo_reconciliation.closed:
        status = ColumnConcreteDesignEligibilityStatus.ELIGIBLE
    else:
        status = ColumnConcreteDesignEligibilityStatus.BLOCKED_COMBO_POPULATION
    refs = tuple(dict.fromkeys((*combo_reconciliation.source_refs, *component_binding.source_refs)))
    return ColumnConcreteDesignEvidenceAuthority(status, combo_reconciliation, component_binding, component_binding.model_fingerprint, component_binding.evidence_epoch_id, refs, tuple(component_binding.reasons))


__all__ = [
    "AnalysisBasisEligibilityEvidence",
    "ColumnConcreteDesignEvidenceAuthority", "ColumnConcreteDesignEvidenceAuthorityError",
    "ColumnConcreteDesignEligibilityStatus", "ConcreteDesignComboReconciliation",
    "build_actual_selected_combo_population", "build_column_concrete_design_evidence_authority",
    "normalized_combo_definition_fingerprint", "reconcile_concrete_design_combos",
]
