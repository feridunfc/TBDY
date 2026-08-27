"""Role-preserving promotion of exact ETABS column design rows.

``ETABS_REQUIRED_REBAR`` is factual design evidence only.  Promotion is row-wise:
no first/last/max/envelope heuristic is used and no row population is collapsed.
Every promoted design row must bind to the accepted F0 component, section,
combo-definition/drift and analysis-basis authority seams.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    ColumnConcreteDesignEligibilityStatus,
    ConcreteDesignComboReconciliation,
    DesignComboIdentity,
    build_column_concrete_design_evidence_authority,
)
from tbdy_engine.providers.etabs_concrete_column_design_result_provider import (
    CapturedConcreteColumnDesignResult,
    ConcreteColumnDesignResultPopulation,
    ConcreteColumnDesignResultRow,
)


ETABS_REQUIRED_REBAR = "ETABS_REQUIRED_REBAR"


class ColumnDesignRebarEvidenceError(ValueError):
    """Raised when factual design rows cannot be promoted without guessing."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnDesignRebarEvidenceError(f"{label} must be a nonblank canonical string")
    return value


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    refs = tuple(_text(item, label) for item in values)
    if not refs or len(refs) != len(set(refs)):
        raise ColumnDesignRebarEvidenceError(f"{label} must be nonempty and unique")
    return refs


@dataclass(frozen=True, slots=True)
class EtabsRequiredRebarEvidence:
    """One exact ETABS design-location longitudinal-area requirement."""

    requirement_id: str
    component_id: str
    unique_name: str
    story: str
    label: str
    assigned_section: str
    design_section: str
    design_combo_identity: DesignComboIdentity
    location_mm: Decimal
    required_as_mm2: Decimal
    source_row_id: str
    model_fingerprint: str
    evidence_epoch_id: str
    source_refs: tuple[str, ...]
    authority: str = ETABS_REQUIRED_REBAR

    def __post_init__(self) -> None:
        for name in (
            "requirement_id",
            "component_id",
            "unique_name",
            "story",
            "label",
            "assigned_section",
            "design_section",
            "source_row_id",
            "model_fingerprint",
            "evidence_epoch_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.authority != ETABS_REQUIRED_REBAR:
            raise ColumnDesignRebarEvidenceError("ETABS required rebar authority label mismatch")
        if (
            not isinstance(self.design_combo_identity, tuple)
            or len(self.design_combo_identity) != 2
        ):
            raise ColumnDesignRebarEvidenceError("design_combo_identity must be exact (ComboType, ComboName)")
        combo_type, combo_name = self.design_combo_identity
        object.__setattr__(
            self,
            "design_combo_identity",
            (_text(combo_type, "design_combo_type"), _text(combo_name, "design_combo_name")),
        )
        if not isinstance(self.location_mm, Decimal) or not self.location_mm.is_finite() or self.location_mm < 0:
            raise ColumnDesignRebarEvidenceError("location_mm must be finite and >= 0")
        if not isinstance(self.required_as_mm2, Decimal) or not self.required_as_mm2.is_finite() or self.required_as_mm2 < 0:
            raise ColumnDesignRebarEvidenceError("required_as_mm2 must be finite and >= 0")
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))


@dataclass(frozen=True, slots=True)
class EtabsRequiredRebarComponent:
    """All promoted longitudinal-area requirements for one canonical column."""

    component_id: str
    unique_name: str
    story: str
    label: str
    assigned_section: str
    design_section: str
    requirements: tuple[EtabsRequiredRebarEvidence, ...]
    source_design_row_count: int
    promoted_requirement_count: int
    model_fingerprint: str
    evidence_epoch_id: str
    source_refs: tuple[str, ...]
    authority: str = ETABS_REQUIRED_REBAR

    def __post_init__(self) -> None:
        for name in (
            "component_id",
            "unique_name",
            "story",
            "label",
            "assigned_section",
            "design_section",
            "model_fingerprint",
            "evidence_epoch_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        requirements = tuple(self.requirements)
        if not requirements or any(not isinstance(item, EtabsRequiredRebarEvidence) for item in requirements):
            raise ColumnDesignRebarEvidenceError("component requires typed ETABS_REQUIRED_REBAR rows")
        if any(
            item.component_id != self.component_id
            or item.unique_name != self.unique_name
            or item.design_section != self.design_section
            or item.model_fingerprint != self.model_fingerprint
            or item.evidence_epoch_id != self.evidence_epoch_id
            for item in requirements
        ):
            raise ColumnDesignRebarEvidenceError("promoted requirement identity/model/epoch mismatch")
        ids = tuple(item.requirement_id for item in requirements)
        if len(ids) != len(set(ids)):
            raise ColumnDesignRebarEvidenceError("promoted requirement identities must be unique")
        if (
            self.source_design_row_count != len(requirements)
            or self.promoted_requirement_count != len(requirements)
        ):
            raise ColumnDesignRebarEvidenceError(
                "source/promoted row counters must prove no design-row omission"
            )
        object.__setattr__(self, "requirements", tuple(sorted(requirements, key=lambda item: item.requirement_id)))
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))
        if self.authority != ETABS_REQUIRED_REBAR:
            raise ColumnDesignRebarEvidenceError("component authority label mismatch")


@dataclass(frozen=True, slots=True)
class EtabsRequiredRebarPopulation:
    """Complete ETABS_REQUIRED_REBAR promotion for one F0-authorized epoch."""

    model_fingerprint: str
    evidence_epoch_id: str
    expected_component_count: int
    source_result_row_count: int
    source_design_row_count: int
    promoted_requirement_count: int
    components: tuple[EtabsRequiredRebarComponent, ...]
    combo_reconciliation_source_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    authority: str = ETABS_REQUIRED_REBAR

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        components = tuple(sorted(self.components, key=lambda item: item.component_id))
        if not components or len(components) != self.expected_component_count:
            raise ColumnDesignRebarEvidenceError("promoted component population is incomplete")
        component_ids = tuple(item.component_id for item in components)
        if len(component_ids) != len(set(component_ids)):
            raise ColumnDesignRebarEvidenceError("promoted component identities must be unique")
        if any(
            item.model_fingerprint != self.model_fingerprint
            or item.evidence_epoch_id != self.evidence_epoch_id
            for item in components
        ):
            raise ColumnDesignRebarEvidenceError("promoted component model/evidence epoch mismatch")
        source_design = sum(item.source_design_row_count for item in components)
        promoted = sum(item.promoted_requirement_count for item in components)
        if self.source_design_row_count != source_design or self.promoted_requirement_count != promoted:
            raise ColumnDesignRebarEvidenceError("promoted population counters do not reconcile")
        if source_design != promoted:
            raise ColumnDesignRebarEvidenceError("not every exact design row became factual ETABS_REQUIRED_REBAR")
        if self.source_result_row_count < self.source_design_row_count:
            raise ColumnDesignRebarEvidenceError("source result count cannot be smaller than design row count")
        object.__setattr__(self, "components", components)
        object.__setattr__(
            self,
            "combo_reconciliation_source_refs",
            _refs(self.combo_reconciliation_source_refs, "combo_reconciliation_source_ref"),
        )
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))
        if self.authority != ETABS_REQUIRED_REBAR:
            raise ColumnDesignRebarEvidenceError("population authority label mismatch")

    def by_component_id(self, component_id: str) -> EtabsRequiredRebarComponent:
        key = _text(component_id, "component_id")
        matches = tuple(item for item in self.components if item.component_id == key)
        if len(matches) != 1:
            raise KeyError(f"expected one ETABS_REQUIRED_REBAR component_id={key}, got {len(matches)}")
        return matches[0]


def _resolve_exact_combo_identity(
    row: ConcreteColumnDesignResultRow,
    *,
    reconciliation: ConcreteDesignComboReconciliation,
) -> DesignComboIdentity:
    if row.pmm_combo is None:
        raise ColumnDesignRebarEvidenceError(
            f"design row {row.source_row_id} has no exact PMMCombo identity"
        )
    matches = tuple(identity for identity in reconciliation.matched if identity[1] == row.pmm_combo)
    if len(matches) != 1:
        raise ColumnDesignRebarEvidenceError(
            f"design row PMMCombo={row.pmm_combo!r} did not bind to exactly one F0 matched combo identity"
        )
    return matches[0]


def _promote_component(
    component: CapturedConcreteColumnDesignResult,
    *,
    reconciliation: ConcreteDesignComboReconciliation,
) -> EtabsRequiredRebarComponent:
    authority = build_column_concrete_design_evidence_authority(
        combo_reconciliation=reconciliation,
        component_binding=component.binding,
    )
    if authority.status is not ColumnConcreteDesignEligibilityStatus.ELIGIBLE:
        raise ColumnDesignRebarEvidenceError(
            f"F0 concrete-design evidence authority blocked {component.component_id}: {authority.status.value}"
        )
    design_rows = component.design_rows
    if not design_rows:
        raise ColumnDesignRebarEvidenceError(
            f"canonical column {component.component_id} has no MyOption=2 design rows"
        )

    requirements: list[EtabsRequiredRebarEvidence] = []
    for row in design_rows:
        if row.error_summary != "":
            raise ColumnDesignRebarEvidenceError(
                f"design row {row.source_row_id} carries ETABS ErrorSummary and cannot be promoted"
            )
        combo_identity = _resolve_exact_combo_identity(row, reconciliation=reconciliation)
        requirement_id = "etabs-required-rebar:" + row.source_row_id.split(":", 1)[-1]
        refs = tuple(
            dict.fromkeys(
                (
                    *component.source_refs,
                    *authority.source_refs,
                    row.source_ref,
                    f"F0:matched-design-combo:{combo_identity[0]}:{combo_identity[1]}",
                )
            )
        )
        requirements.append(
            EtabsRequiredRebarEvidence(
                requirement_id=requirement_id,
                component_id=component.component_id,
                unique_name=component.unique_name,
                story=component.story,
                label=component.label,
                assigned_section=component.assigned_section,
                design_section=component.design_section,
                design_combo_identity=combo_identity,
                location_mm=row.location_mm,
                required_as_mm2=row.pmm_area_mm2,
                source_row_id=row.source_row_id,
                model_fingerprint=component.model_fingerprint,
                evidence_epoch_id=component.evidence_epoch_id,
                source_refs=refs,
            )
        )

    refs = tuple(
        dict.fromkeys(
            (
                *component.source_refs,
                *authority.source_refs,
                *(ref for item in requirements for ref in item.source_refs),
            )
        )
    )
    return EtabsRequiredRebarComponent(
        component_id=component.component_id,
        unique_name=component.unique_name,
        story=component.story,
        label=component.label,
        assigned_section=component.assigned_section,
        design_section=component.design_section,
        requirements=tuple(requirements),
        source_design_row_count=len(design_rows),
        promoted_requirement_count=len(requirements),
        model_fingerprint=component.model_fingerprint,
        evidence_epoch_id=component.evidence_epoch_id,
        source_refs=refs,
    )


def promote_etabs_required_rebar(
    results: ConcreteColumnDesignResultPopulation,
    *,
    combo_reconciliation: ConcreteDesignComboReconciliation,
) -> EtabsRequiredRebarPopulation:
    """Promote every exact design row without collapsing the row population."""
    if not isinstance(results, ConcreteColumnDesignResultPopulation):
        raise TypeError("results must be ConcreteColumnDesignResultPopulation")
    if not isinstance(combo_reconciliation, ConcreteDesignComboReconciliation):
        raise TypeError("combo_reconciliation must be ConcreteDesignComboReconciliation")
    if not results.capture_complete:
        raise ColumnDesignRebarEvidenceError("design-result factual population is not complete")
    if (
        combo_reconciliation.model_fingerprint != results.model_fingerprint
        or combo_reconciliation.evidence_epoch_id != results.evidence_epoch_id
    ):
        raise ColumnDesignRebarEvidenceError(
            "design results and F0 combo reconciliation do not share model/evidence epoch"
        )
    if not combo_reconciliation.closed:
        raise ColumnDesignRebarEvidenceError(
            "F0 combo/definition/drift/analysis-basis reconciliation is not closed"
        )

    components = tuple(
        _promote_component(item, reconciliation=combo_reconciliation)
        for item in results.components
    )
    source_refs = tuple(
        dict.fromkeys(
            (
                *results.source_refs,
                *combo_reconciliation.source_refs,
                *(ref for item in components for ref in item.source_refs),
            )
        )
    )
    return EtabsRequiredRebarPopulation(
        model_fingerprint=results.model_fingerprint,
        evidence_epoch_id=results.evidence_epoch_id,
        expected_component_count=results.expected_component_count,
        source_result_row_count=results.captured_result_row_count,
        source_design_row_count=results.design_result_row_count,
        promoted_requirement_count=sum(len(item.requirements) for item in components),
        components=components,
        combo_reconciliation_source_refs=combo_reconciliation.source_refs,
        source_refs=source_refs,
    )


__all__ = [
    "ETABS_REQUIRED_REBAR",
    "ColumnDesignRebarEvidenceError",
    "EtabsRequiredRebarComponent",
    "EtabsRequiredRebarEvidence",
    "EtabsRequiredRebarPopulation",
    "promote_etabs_required_rebar",
]
