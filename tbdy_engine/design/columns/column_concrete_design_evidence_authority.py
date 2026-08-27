"""Column concrete-design evidence eligibility authority foundation.

PASS-2 reconciles reviewed expected design-combo identity with the accepted
PASS-1 factual selected population. Existing ETABS combo-definition evidence
and the existing name-blind classifier remain the semantic authorities. No
PMMArea promotion, reinforcement selection or capacity logic lives here.

Analysis-basis eligibility is consumed through a tiny immutable join artifact
containing the already-resolved canonical status value plus its source ref. We
do not import ``regulatory`` here: importing that package merely to compare a
resolved status would recreate the package-initialization cycle that this
foundation is required to avoid. This module defines no second analysis-basis
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
    ActualConcreteDesignComboPopulation,
    ActualSelectedConcreteDesignCombo,
    ColumnDesignComponentBinding,
    ComponentBindingStatus,
    ExpectedConcreteDesignComboPolicy,
)
from tbdy_engine.providers.etabs_combo_definition_provider import EtabsComboDefinitionEvidence
from tbdy_engine.providers.etabs_concrete_design_combo_selection_probe import (
    ActualConcreteDesignComboSelectionPopulation,
)

DesignComboIdentity = tuple[str, str]


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


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    refs = tuple(_text(item, label) for item in values)
    if len(refs) != len(set(refs)):
        raise ColumnConcreteDesignEvidenceAuthorityError(f"{label} values must be unique")
    return refs


@dataclass(frozen=True, slots=True)
class AnalysisBasisEligibilityEvidence:
    """Join-only projection of an existing canonical analysis-basis decision.

    ``status_value`` is expected to be ``AnalysisBasisStatus.value`` from the
    accepted analysis-basis authority. This artifact does not reinterpret or
    resolve that status; it only preserves the value/ref needed by this
    downstream reconciliation. Fail-closed consumption means only ``MATCH``
    can pass.
    """

    status_value: str
    compatibility_ref: str
    provenance_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status_value", _text(self.status_value, "analysis_basis.status_value"))
        object.__setattr__(self, "compatibility_ref", _text(self.compatibility_ref, "analysis_basis.compatibility_ref"))
        object.__setattr__(self, "provenance_refs", _refs(self.provenance_refs, "analysis_basis.provenance_ref"))

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
    encoded = json.dumps(
        _definition_payload(definition),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "combo-definition:sha256:" + hashlib.sha256(encoded).hexdigest()


def build_actual_selected_combo_population(
    *,
    selected_population: ActualConcreteDesignComboSelectionPopulation,
    definitions: Sequence[EtabsComboDefinitionEvidence],
    definition_model_fingerprint: str,
    definition_evidence_epoch_id: str,
    definition_capture_refs: Sequence[str],
) -> ActualConcreteDesignComboPopulation:
    """Enrich every accepted PASS-1 selected row with one factual definition.

    There is intentionally no free-form selected-name/source-row input. The
    PASS-1 typed population is the sole actual-selection authority. Because the
    existing combo-definition DTO has no epoch fields, this narrow join requires
    explicit model/epoch identity and provenance for the definition capture and
    rejects any mismatch before enrichment.
    """
    if not isinstance(selected_population, ActualConcreteDesignComboSelectionPopulation):
        raise TypeError("selected_population must be ActualConcreteDesignComboSelectionPopulation")
    if not selected_population.capture_complete:
        raise ColumnConcreteDesignEvidenceAuthorityError("PASS-1 selected population must be a complete FULL capture")

    definition_model = _text(definition_model_fingerprint, "definition_model_fingerprint")
    definition_epoch = _text(definition_evidence_epoch_id, "definition_evidence_epoch_id")
    if definition_model != selected_population.model_fingerprint or definition_epoch != selected_population.evidence_epoch_id:
        raise ColumnConcreteDesignEvidenceAuthorityError(
            "combo-definition capture model/evidence epoch does not match PASS-1 selected population"
        )
    capture_refs = _refs(definition_capture_refs, "definition_capture_ref")
    if not capture_refs:
        raise ColumnConcreteDesignEvidenceAuthorityError("combo-definition capture requires provenance refs")

    defs = tuple(definitions)
    if any(not isinstance(item, EtabsComboDefinitionEvidence) for item in defs):
        raise TypeError("definitions must contain EtabsComboDefinitionEvidence")
    definition_by_name = {item.name: item for item in defs}
    if len(definition_by_name) != len(defs):
        raise ColumnConcreteDesignEvidenceAuthorityError("definition names must be unique")

    records: list[ActualSelectedConcreteDesignCombo] = []
    for row in selected_population.rows:
        definition = definition_by_name.get(row.combo_name)
        if definition is None:
            raise ColumnConcreteDesignEvidenceAuthorityError(
                f"selected combo {row.identity if hasattr(row, 'identity') else (row.combo_type, row.combo_name)!r} has no same-epoch factual ETABS definition"
            )
        fingerprint = normalized_combo_definition_fingerprint(definition)
        records.append(
            ActualSelectedConcreteDesignCombo(
                design_combo_type=row.combo_type,
                combo_name=row.combo_name,
                selected_row_id=row.row_id,
                normalized_definition_fingerprint=fingerprint,
                source_row_ref=row.source_row_ref,
                provenance_refs=(f"definition:{row.combo_name}:{fingerprint}",),
            )
        )

    return ActualConcreteDesignComboPopulation(
        model_fingerprint=selected_population.model_fingerprint,
        evidence_epoch_id=selected_population.evidence_epoch_id,
        selected_population_source_refs=selected_population.source_refs,
        definition_capture_refs=capture_refs,
        combos=tuple(records),
    )


@dataclass(frozen=True, slots=True)
class ConcreteDesignComboReconciliation:
    model_fingerprint: str
    evidence_epoch_id: str
    expected: tuple[DesignComboIdentity, ...]
    actual_selected: tuple[DesignComboIdentity, ...]
    matched: tuple[DesignComboIdentity, ...]
    missing_expected: tuple[DesignComboIdentity, ...]
    unexpected_selected: tuple[DesignComboIdentity, ...]
    definition_mismatch: tuple[DesignComboIdentity, ...]
    unsupported_definition: tuple[DesignComboIdentity, ...]
    analysis_basis_blocked: tuple[DesignComboIdentity, ...]
    definition_fingerprints: tuple[tuple[str, str, str], ...]
    source_refs: tuple[str, ...]

    @property
    def closed(self) -> bool:
        return not (
            self.missing_expected
            or self.unexpected_selected
            or self.definition_mismatch
            or self.unsupported_definition
            or self.analysis_basis_blocked
        ) and self.matched == self.expected == self.actual_selected


def reconcile_concrete_design_combos(
    *,
    expected_policy: ExpectedConcreteDesignComboPolicy,
    actual_population: ActualConcreteDesignComboPopulation,
    current_definitions: Sequence[EtabsComboDefinitionEvidence],
    current_definition_model_fingerprint: str,
    current_definition_evidence_epoch_id: str,
    current_definition_capture_refs: Sequence[str],
    case_types: Mapping[str, str],
    analysis_basis_by_combo: Mapping[DesignComboIdentity, AnalysisBasisEligibilityEvidence],
) -> ConcreteDesignComboReconciliation:
    if not isinstance(expected_policy, ExpectedConcreteDesignComboPolicy):
        raise TypeError("expected_policy must be ExpectedConcreteDesignComboPolicy")
    if not isinstance(actual_population, ActualConcreteDesignComboPopulation):
        raise TypeError("actual_population must be ActualConcreteDesignComboPopulation")
    if any(not isinstance(value, AnalysisBasisEligibilityEvidence) for value in analysis_basis_by_combo.values()):
        raise TypeError("analysis_basis_by_combo values must be AnalysisBasisEligibilityEvidence")

    current_model = _text(current_definition_model_fingerprint, "current_definition_model_fingerprint")
    current_epoch = _text(current_definition_evidence_epoch_id, "current_definition_evidence_epoch_id")
    if current_model != actual_population.model_fingerprint or current_epoch != actual_population.evidence_epoch_id:
        raise ColumnConcreteDesignEvidenceAuthorityError(
            "current combo definitions do not share the PASS-1 model/evidence epoch"
        )
    current_refs = _refs(current_definition_capture_refs, "current_definition_capture_ref")
    if not current_refs:
        raise ColumnConcreteDesignEvidenceAuthorityError("current combo-definition capture requires provenance refs")

    expected = tuple(sorted(expected_policy.identities))
    actual = tuple(sorted(actual_population.identities))
    expected_set, actual_set = set(expected), set(actual)
    missing = tuple(sorted(expected_set - actual_set))
    unexpected = tuple(sorted(actual_set - expected_set))

    defs = tuple(current_definitions)
    if any(not isinstance(item, EtabsComboDefinitionEvidence) for item in defs):
        raise TypeError("current_definitions must contain EtabsComboDefinitionEvidence")
    definition_by_name = {item.name: item for item in defs}
    if len(definition_by_name) != len(defs):
        raise ColumnConcreteDesignEvidenceAuthorityError("current definition names must be unique")
    selected_by_identity = {item.identity: item for item in actual_population.combos}

    mismatch: list[DesignComboIdentity] = []
    unsupported: list[DesignComboIdentity] = []
    analysis_blocked: list[DesignComboIdentity] = []
    matched: list[DesignComboIdentity] = []
    fingerprints: list[tuple[str, str, str]] = []

    for identity in sorted(expected_set & actual_set):
        design_combo_type, combo_name = identity
        current = definition_by_name.get(combo_name)
        if current is None:
            mismatch.append(identity)
            continue
        fingerprint = normalized_combo_definition_fingerprint(current)
        fingerprints.append((design_combo_type, combo_name, fingerprint))
        if selected_by_identity[identity].normalized_definition_fingerprint != fingerprint:
            mismatch.append(identity)
            continue
        classification = classify_combo_pattern(
            combo_name=current.name,
            combo_type=current.combo_type,
            constituents=tuple(
                ComboPatternConstituent(item.name, item.scale_factor, item.cname_type)
                for item in current.constituents
            ),
            case_types=case_types,
        )
        if not classification.supported:
            unsupported.append(identity)
            continue
        basis = analysis_basis_by_combo.get(identity)
        if basis is None or not basis.acceptable:
            analysis_blocked.append(identity)
            continue
        matched.append(identity)

    basis_refs = tuple(
        ref
        for identity in sorted(expected_set & actual_set)
        for evidence in (analysis_basis_by_combo.get(identity),)
        if evidence is not None
        for ref in (evidence.compatibility_ref, *evidence.provenance_refs)
    )
    refs = tuple(dict.fromkeys((
        f"expected-policy:{expected_policy.policy_id}",
        *expected_policy.review_provenance_refs,
        *actual_population.source_refs,
        *current_refs,
        *basis_refs,
    )))
    return ConcreteDesignComboReconciliation(
        model_fingerprint=actual_population.model_fingerprint,
        evidence_epoch_id=actual_population.evidence_epoch_id,
        expected=expected,
        actual_selected=actual,
        matched=tuple(sorted(matched)),
        missing_expected=missing,
        unexpected_selected=unexpected,
        definition_mismatch=tuple(sorted(mismatch)),
        unsupported_definition=tuple(sorted(unsupported)),
        analysis_basis_blocked=tuple(sorted(analysis_blocked)),
        definition_fingerprints=tuple(sorted(fingerprints)),
        source_refs=refs,
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


def build_column_concrete_design_evidence_authority(
    *,
    combo_reconciliation: ConcreteDesignComboReconciliation | None,
    component_binding: ColumnDesignComponentBinding | None,
) -> ColumnConcreteDesignEvidenceAuthority:
    if combo_reconciliation is None or component_binding is None:
        return ColumnConcreteDesignEvidenceAuthority(
            ColumnConcreteDesignEligibilityStatus.NO_DATA,
            combo_reconciliation,
            component_binding,
            None,
            None,
            (),
            ("required evidence artifact is absent",),
        )
    if (
        combo_reconciliation.model_fingerprint != component_binding.model_fingerprint
        or combo_reconciliation.evidence_epoch_id != component_binding.evidence_epoch_id
    ):
        status = ColumnConcreteDesignEligibilityStatus.BLOCKED_EVIDENCE_EPOCH
    elif component_binding.status is ComponentBindingStatus.BLOCKED_EVIDENCE_EPOCH:
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
    return ColumnConcreteDesignEvidenceAuthority(
        status,
        combo_reconciliation,
        component_binding,
        component_binding.model_fingerprint,
        component_binding.evidence_epoch_id,
        refs,
        tuple(component_binding.reasons),
    )


__all__ = [
    "AnalysisBasisEligibilityEvidence",
    "ColumnConcreteDesignEvidenceAuthority",
    "ColumnConcreteDesignEvidenceAuthorityError",
    "ColumnConcreteDesignEligibilityStatus",
    "ConcreteDesignComboReconciliation",
    "DesignComboIdentity",
    "build_actual_selected_combo_population",
    "build_column_concrete_design_evidence_authority",
    "normalized_combo_definition_fingerprint",
    "reconcile_concrete_design_combos",
]
