"""Column concrete-design evidence eligibility authority foundation.

PASS-2 reconciles independently reviewed expected design-combo mathematics
with the accepted PASS-1 factual selected population and current ETABS factual
mathematics. Existing ETABS definition acquisition and the existing name-blind
classifier remain the factual/semantic authorities. No PMMArea promotion,
reinforcement selection or capacity logic lives here.

Analysis-basis eligibility is consumed through a tiny immutable join artifact
containing the already-resolved canonical status value plus its source ref. We
do not import ``regulatory`` here: importing that package merely to compare a
resolved status would recreate the package-initialization cycle that this
foundation is required to avoid. This module defines no second analysis-basis
enum and treats every value other than exact canonical ``MATCH`` as blocked.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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
    ReviewedComboConstituentKind,
    ReviewedConcreteDesignComboDefinition,
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


def _canonical_factor(value: object) -> str:
    """Canonicalize exact numeric semantics without tolerances or float guessing.

    ETABS floats are converted through their shortest decimal transport string,
    so ordinary ``0.3`` canonicalizes to reviewed Decimal("0.3") while a real
    transported difference such as ``0.30000000000000004`` remains different.
    """
    if isinstance(value, bool):
        raise ColumnConcreteDesignEvidenceAuthorityError("scale factor must be finite numeric")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ColumnConcreteDesignEvidenceAuthorityError("scale factor must be finite numeric") from exc
    if not decimal_value.is_finite():
        raise ColumnConcreteDesignEvidenceAuthorityError("scale factor must be finite numeric")
    if decimal_value == 0:
        return "0"
    return format(decimal_value.normalize(), "f")


@dataclass(frozen=True, slots=True)
class AnalysisBasisEligibilityEvidence:
    """Join-only projection of an existing canonical analysis-basis decision."""

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


@dataclass(frozen=True, slots=True)
class NeutralComboMathConstituent:
    kind: str
    name: str
    scale_factor: str
    nested_definition: "NeutralComboMathDefinition | None" = None

    def payload(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "name": self.name,
            "scale_factor": self.scale_factor,
            "nested": None if self.nested_definition is None else self.nested_definition.payload(),
        }


@dataclass(frozen=True, slots=True)
class NeutralComboMathDefinition:
    """Dependency-light comparison representation shared by reviewed and ETABS sources."""

    name: str
    response_combo_type: str
    constituents: tuple[NeutralComboMathConstituent, ...]

    def payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "response_combo_type": self.response_combo_type,
            "constituents": [item.payload() for item in self.constituents],
        }


def _neutral_from_reviewed(definition: ReviewedConcreteDesignComboDefinition) -> NeutralComboMathDefinition:
    if not isinstance(definition, ReviewedConcreteDesignComboDefinition):
        raise TypeError("definition must be ReviewedConcreteDesignComboDefinition")
    return NeutralComboMathDefinition(
        name=definition.combo_name,
        response_combo_type=definition.response_combo_type,
        constituents=tuple(
            NeutralComboMathConstituent(
                kind=item.kind.value if isinstance(item.kind, ReviewedComboConstituentKind) else str(item.kind),
                name=item.name,
                scale_factor=_canonical_factor(item.scale_factor),
                nested_definition=(
                    _neutral_from_reviewed(item.nested_definition)
                    if item.nested_definition is not None
                    else None
                ),
            )
            for item in definition.constituents
        ),
    )


def _neutral_from_etabs(definition: EtabsComboDefinitionEvidence) -> NeutralComboMathDefinition:
    if not isinstance(definition, EtabsComboDefinitionEvidence):
        raise TypeError("definition must be EtabsComboDefinitionEvidence")
    nested_by_name: dict[str, list[EtabsComboDefinitionEvidence]] = {}
    for nested in definition.nested_combos:
        nested_by_name.setdefault(nested.name, []).append(nested)

    terms: list[NeutralComboMathConstituent] = []
    referenced_nested: list[str] = []
    for item in definition.constituents:
        kind = _text(item.cname_type, "etabs_definition.constituent_kind")
        if kind not in {"LOAD_CASE", "LOAD_COMBO"}:
            raise ColumnConcreteDesignEvidenceAuthorityError(
                f"unsupported factual ETABS constituent kind: {kind}"
            )
        nested_definition = None
        if kind == "LOAD_COMBO":
            matches = nested_by_name.get(item.name, [])
            if len(matches) != 1:
                raise ColumnConcreteDesignEvidenceAuthorityError(
                    f"factual nested combo {item.name!r} must have exactly one captured definition"
                )
            referenced_nested.append(item.name)
            nested_definition = _neutral_from_etabs(matches[0])
        terms.append(
            NeutralComboMathConstituent(
                kind=kind,
                name=_text(item.name, "etabs_definition.constituent_name"),
                scale_factor=_canonical_factor(item.scale_factor),
                nested_definition=nested_definition,
            )
        )
    if sorted(referenced_nested) != sorted(item.name for item in definition.nested_combos):
        raise ColumnConcreteDesignEvidenceAuthorityError(
            "factual ETABS nested-definition capture does not exactly match LOAD_COMBO constituents"
        )
    return NeutralComboMathDefinition(
        name=_text(definition.name, "etabs_definition.name"),
        response_combo_type=_text(definition.combo_type, "etabs_definition.combo_type"),
        constituents=tuple(terms),
    )


def neutral_combo_definition(
    definition: ReviewedConcreteDesignComboDefinition | EtabsComboDefinitionEvidence,
) -> NeutralComboMathDefinition:
    """Adapt reviewed or factual evidence into one neutral mathematical form."""
    if isinstance(definition, ReviewedConcreteDesignComboDefinition):
        return _neutral_from_reviewed(definition)
    if isinstance(definition, EtabsComboDefinitionEvidence):
        return _neutral_from_etabs(definition)
    raise TypeError(
        "definition must be ReviewedConcreteDesignComboDefinition or EtabsComboDefinitionEvidence"
    )


def normalized_combo_definition_fingerprint(
    definition: ReviewedConcreteDesignComboDefinition | EtabsComboDefinitionEvidence,
) -> str:
    encoded = json.dumps(
        neutral_combo_definition(definition).payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "combo-definition:sha256:" + hashlib.sha256(encoded).hexdigest()


def _reviewed_definition_refs(definition: ReviewedConcreteDesignComboDefinition) -> tuple[str, ...]:
    refs: list[str] = list(definition.review_provenance_refs)
    for item in definition.constituents:
        refs.extend(item.review_provenance_refs)
        if item.nested_definition is not None:
            refs.extend(_reviewed_definition_refs(item.nested_definition))
    return tuple(dict.fromkeys(refs))


def build_actual_selected_combo_population(
    *,
    selected_population: ActualConcreteDesignComboSelectionPopulation,
    definitions: Sequence[EtabsComboDefinitionEvidence],
    definition_model_fingerprint: str,
    definition_evidence_epoch_id: str,
    definition_capture_refs: Sequence[str],
) -> ActualConcreteDesignComboPopulation:
    """Enrich every accepted PASS-1 selected row with one factual definition."""
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
    actual_definition_drift: tuple[DesignComboIdentity, ...]
    unsupported_definition: tuple[DesignComboIdentity, ...]
    analysis_basis_blocked: tuple[DesignComboIdentity, ...]
    reviewed_definition_fingerprints: tuple[tuple[str, str, str], ...]
    actual_capture_definition_fingerprints: tuple[tuple[str, str, str], ...]
    definition_fingerprints: tuple[tuple[str, str, str], ...]
    source_refs: tuple[str, ...]

    @property
    def closed(self) -> bool:
        return not (
            self.missing_expected
            or self.unexpected_selected
            or self.definition_mismatch
            or self.actual_definition_drift
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

    expected_by_identity = {item.identity: item for item in expected_policy.combos}
    selected_by_identity = {item.identity: item for item in actual_population.combos}
    reviewed_fp_by_identity = {
        identity: normalized_combo_definition_fingerprint(item.reviewed_definition)
        for identity, item in expected_by_identity.items()
    }

    mismatch: list[DesignComboIdentity] = []
    drift: list[DesignComboIdentity] = []
    unsupported: list[DesignComboIdentity] = []
    analysis_blocked: list[DesignComboIdentity] = []
    matched: list[DesignComboIdentity] = []
    current_fingerprints: list[tuple[str, str, str]] = []

    for identity in sorted(expected_set & actual_set):
        design_combo_type, combo_name = identity
        current = definition_by_name.get(combo_name)
        if current is None:
            mismatch.append(identity)
            continue
        try:
            current_fingerprint = normalized_combo_definition_fingerprint(current)
        except ColumnConcreteDesignEvidenceAuthorityError:
            unsupported.append(identity)
            continue
        current_fingerprints.append((design_combo_type, combo_name, current_fingerprint))

        reviewed_mismatch = reviewed_fp_by_identity[identity] != current_fingerprint
        capture_drift = (
            selected_by_identity[identity].normalized_definition_fingerprint != current_fingerprint
        )
        if reviewed_mismatch:
            mismatch.append(identity)
        if capture_drift:
            drift.append(identity)
        if reviewed_mismatch or capture_drift:
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
    expected_refs = tuple(
        ref
        for item in expected_policy.combos
        for ref in (*item.provenance_refs, *_reviewed_definition_refs(item.reviewed_definition))
    )
    refs = tuple(dict.fromkeys((
        f"expected-policy:{expected_policy.policy_id}",
        *expected_policy.review_provenance_refs,
        *expected_refs,
        *actual_population.source_refs,
        *current_refs,
        *basis_refs,
    )))
    reviewed_fingerprints = tuple(
        sorted((identity[0], identity[1], fingerprint) for identity, fingerprint in reviewed_fp_by_identity.items())
    )
    capture_fingerprints = tuple(
        sorted(
            (item.design_combo_type, item.combo_name, item.normalized_definition_fingerprint)
            for item in actual_population.combos
        )
    )
    return ConcreteDesignComboReconciliation(
        model_fingerprint=actual_population.model_fingerprint,
        evidence_epoch_id=actual_population.evidence_epoch_id,
        expected=expected,
        actual_selected=actual,
        matched=tuple(sorted(matched)),
        missing_expected=missing,
        unexpected_selected=unexpected,
        definition_mismatch=tuple(sorted(mismatch)),
        actual_definition_drift=tuple(sorted(drift)),
        unsupported_definition=tuple(sorted(unsupported)),
        analysis_basis_blocked=tuple(sorted(analysis_blocked)),
        reviewed_definition_fingerprints=reviewed_fingerprints,
        actual_capture_definition_fingerprints=capture_fingerprints,
        definition_fingerprints=tuple(sorted(current_fingerprints)),
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


def _combo_reconciliation_reasons(
    reconciliation: ConcreteDesignComboReconciliation,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if reconciliation.missing_expected:
        reasons.append("expected design-combo identity is missing from PASS-1 actual selection")
    if reconciliation.unexpected_selected:
        reasons.append("PASS-1 actual selection contains an unexpected design-combo identity")
    if reconciliation.definition_mismatch:
        reasons.append("reviewed expected mathematical definition does not match current factual ETABS definition")
    if reconciliation.actual_definition_drift:
        reasons.append("current factual ETABS definition drifted from the accepted actual capture")
    if reconciliation.unsupported_definition:
        reasons.append("actual combo definition is not accepted by the existing combo-pattern engine")
    if reconciliation.analysis_basis_blocked:
        reasons.append("canonical analysis-basis status is not MATCH")
    return tuple(reasons)


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
    elif (
        combo_reconciliation.definition_mismatch
        or combo_reconciliation.actual_definition_drift
        or combo_reconciliation.unsupported_definition
    ):
        status = ColumnConcreteDesignEligibilityStatus.BLOCKED_COMBO_DEFINITION
    elif combo_reconciliation.analysis_basis_blocked:
        status = ColumnConcreteDesignEligibilityStatus.BLOCKED_ANALYSIS_BASIS
    elif combo_reconciliation.closed:
        status = ColumnConcreteDesignEligibilityStatus.ELIGIBLE
    else:
        status = ColumnConcreteDesignEligibilityStatus.BLOCKED_COMBO_POPULATION
    refs = tuple(dict.fromkeys((*combo_reconciliation.source_refs, *component_binding.source_refs)))
    reasons = tuple(dict.fromkeys((*component_binding.reasons, *_combo_reconciliation_reasons(combo_reconciliation))))
    return ColumnConcreteDesignEvidenceAuthority(
        status,
        combo_reconciliation,
        component_binding,
        component_binding.model_fingerprint,
        component_binding.evidence_epoch_id,
        refs,
        reasons,
    )


__all__ = [
    "AnalysisBasisEligibilityEvidence",
    "ColumnConcreteDesignEvidenceAuthority",
    "ColumnConcreteDesignEvidenceAuthorityError",
    "ColumnConcreteDesignEligibilityStatus",
    "ConcreteDesignComboReconciliation",
    "DesignComboIdentity",
    "NeutralComboMathConstituent",
    "NeutralComboMathDefinition",
    "build_actual_selected_combo_population",
    "build_column_concrete_design_evidence_authority",
    "neutral_combo_definition",
    "normalized_combo_definition_fingerprint",
    "reconcile_concrete_design_combos",
]
