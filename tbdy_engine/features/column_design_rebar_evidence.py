"""Role-preserving promotion of exact ETABS column design rows.

``ETABS_REQUIRED_REBAR`` is factual design evidence only. Promotion is row-wise:
no first/last/max/envelope heuristic is used and no row population is collapsed.
Every accepted design row must bind to the accepted F0 component, section,
combo-definition/drift and analysis-basis authority seams.

Rows carrying an ETABS ErrorSummary, a non-empty WarningSummary, a missing PMM
combo, or a PMM combo that cannot bind exactly to one reconciled F0 combo are
retained as explicit blocked factual rows. They are never silently promoted.
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
ETABS_REQUIRED_REBAR_PROMOTION_RESULT = "ETABS_REQUIRED_REBAR_PROMOTION_RESULT"

BLOCKED_ETABS_ERROR_SUMMARY = "BLOCKED_ETABS_ERROR_SUMMARY"
BLOCKED_ETABS_WARNING_SUMMARY = "BLOCKED_ETABS_WARNING_SUMMARY"
BLOCKED_MISSING_PMM_COMBO = "BLOCKED_MISSING_PMM_COMBO"
BLOCKED_UNBINDABLE_PMM_COMBO = "BLOCKED_UNBINDABLE_PMM_COMBO"


class ColumnDesignRebarEvidenceError(ValueError):
    """Raised when global factual design authority cannot be established."""


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
        if not isinstance(self.design_combo_identity, tuple) or len(self.design_combo_identity) != 2:
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
class BlockedEtabsRequiredRebarRow:
    """Exact design row retained when promotion is not authorized."""

    source_row_id: str
    component_id: str
    unique_name: str
    story: str
    label: str
    assigned_section: str
    design_section: str
    pmm_combo: str | None
    location_mm: Decimal
    required_as_mm2: Decimal
    error_summary: str
    warning_summary: str
    reason_code: str
    reason_detail: str
    model_fingerprint: str
    evidence_epoch_id: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "source_row_id",
            "component_id",
            "unique_name",
            "story",
            "label",
            "assigned_section",
            "design_section",
            "reason_code",
            "reason_detail",
            "model_fingerprint",
            "evidence_epoch_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.pmm_combo is not None:
            object.__setattr__(self, "pmm_combo", _text(self.pmm_combo, "pmm_combo"))
        if not isinstance(self.error_summary, str) or not isinstance(self.warning_summary, str):
            raise ColumnDesignRebarEvidenceError("blocked summaries must preserve exact ETABS strings")
        if not isinstance(self.location_mm, Decimal) or not self.location_mm.is_finite() or self.location_mm < 0:
            raise ColumnDesignRebarEvidenceError("blocked location_mm must be finite and >= 0")
        if not isinstance(self.required_as_mm2, Decimal) or not self.required_as_mm2.is_finite() or self.required_as_mm2 < 0:
            raise ColumnDesignRebarEvidenceError("blocked required_as_mm2 must be finite and >= 0")
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))


@dataclass(frozen=True, slots=True)
class EtabsRequiredRebarComponent:
    """Promotion result for all exact design rows of one canonical column."""

    component_id: str
    unique_name: str
    story: str
    label: str
    assigned_section: str
    design_section: str
    requirements: tuple[EtabsRequiredRebarEvidence, ...]
    blocked_rows: tuple[BlockedEtabsRequiredRebarRow, ...]
    source_design_row_count: int
    promoted_requirement_count: int
    blocked_requirement_count: int
    model_fingerprint: str
    evidence_epoch_id: str
    source_refs: tuple[str, ...]
    authority: str = ETABS_REQUIRED_REBAR_PROMOTION_RESULT

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
        blocked = tuple(self.blocked_rows)
        if any(not isinstance(item, EtabsRequiredRebarEvidence) for item in requirements):
            raise ColumnDesignRebarEvidenceError("requirements must contain typed ETABS_REQUIRED_REBAR rows")
        if any(not isinstance(item, BlockedEtabsRequiredRebarRow) for item in blocked):
            raise ColumnDesignRebarEvidenceError("blocked_rows must contain typed blocked factual rows")
        if not requirements and not blocked:
            raise ColumnDesignRebarEvidenceError("component must retain at least one exact design row")
        all_rows = (*requirements, *blocked)
        if any(
            item.component_id != self.component_id
            or item.unique_name != self.unique_name
            or item.design_section != self.design_section
            or item.model_fingerprint != self.model_fingerprint
            or item.evidence_epoch_id != self.evidence_epoch_id
            for item in all_rows
        ):
            raise ColumnDesignRebarEvidenceError("promotion row identity/model/epoch mismatch")
        row_ids = tuple(item.source_row_id for item in all_rows)
        if len(row_ids) != len(set(row_ids)):
            raise ColumnDesignRebarEvidenceError("source design row identities must be unique")
        requirement_ids = tuple(item.requirement_id for item in requirements)
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ColumnDesignRebarEvidenceError("promoted requirement identities must be unique")
        if (
            self.source_design_row_count != len(all_rows)
            or self.promoted_requirement_count != len(requirements)
            or self.blocked_requirement_count != len(blocked)
            or self.source_design_row_count != self.promoted_requirement_count + self.blocked_requirement_count
        ):
            raise ColumnDesignRebarEvidenceError("source/promoted/blocked row counters must reconcile exactly")
        object.__setattr__(self, "requirements", tuple(sorted(requirements, key=lambda item: item.requirement_id)))
        object.__setattr__(self, "blocked_rows", tuple(sorted(blocked, key=lambda item: item.source_row_id)))
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))
        if self.authority != ETABS_REQUIRED_REBAR_PROMOTION_RESULT:
            raise ColumnDesignRebarEvidenceError("component promotion-result authority label mismatch")

    @property
    def promotion_complete(self) -> bool:
        return self.blocked_requirement_count == 0


@dataclass(frozen=True, slots=True)
class EtabsRequiredRebarPopulation:
    """Complete row accounting for one F0-authorized design-result epoch."""

    model_fingerprint: str
    evidence_epoch_id: str
    expected_component_count: int
    source_result_row_count: int
    source_design_row_count: int
    promoted_requirement_count: int
    blocked_requirement_count: int
    components: tuple[EtabsRequiredRebarComponent, ...]
    combo_reconciliation_source_refs: tuple[str, ...]
    source_refs: tuple[str, ...]
    authority: str = ETABS_REQUIRED_REBAR_PROMOTION_RESULT

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        components = tuple(sorted(self.components, key=lambda item: item.component_id))
        if not components or len(components) != self.expected_component_count:
            raise ColumnDesignRebarEvidenceError("promotion component population is incomplete")
        component_ids = tuple(item.component_id for item in components)
        if len(component_ids) != len(set(component_ids)):
            raise ColumnDesignRebarEvidenceError("promotion component identities must be unique")
        if any(
            item.model_fingerprint != self.model_fingerprint
            or item.evidence_epoch_id != self.evidence_epoch_id
            for item in components
        ):
            raise ColumnDesignRebarEvidenceError("promotion component model/evidence epoch mismatch")
        source_design = sum(item.source_design_row_count for item in components)
        promoted = sum(item.promoted_requirement_count for item in components)
        blocked = sum(item.blocked_requirement_count for item in components)
        if (
            self.source_design_row_count != source_design
            or self.promoted_requirement_count != promoted
            or self.blocked_requirement_count != blocked
            or source_design != promoted + blocked
        ):
            raise ColumnDesignRebarEvidenceError("promotion population counters do not reconcile")
        if self.source_result_row_count < self.source_design_row_count:
            raise ColumnDesignRebarEvidenceError("source result count cannot be smaller than design row count")
        object.__setattr__(self, "components", components)
        object.__setattr__(
            self,
            "combo_reconciliation_source_refs",
            _refs(self.combo_reconciliation_source_refs, "combo_reconciliation_source_ref"),
        )
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))
        if self.authority != ETABS_REQUIRED_REBAR_PROMOTION_RESULT:
            raise ColumnDesignRebarEvidenceError("population promotion-result authority label mismatch")

    @property
    def promotion_complete(self) -> bool:
        return self.blocked_requirement_count == 0

    @property
    def blocked_rows(self) -> tuple[BlockedEtabsRequiredRebarRow, ...]:
        return tuple(row for component in self.components for row in component.blocked_rows)

    @property
    def requirements(self) -> tuple[EtabsRequiredRebarEvidence, ...]:
        return tuple(row for component in self.components for row in component.requirements)

    def by_component_id(self, component_id: str) -> EtabsRequiredRebarComponent:
        key = _text(component_id, "component_id")
        matches = tuple(item for item in self.components if item.component_id == key)
        if len(matches) != 1:
            raise KeyError(f"expected one promotion component_id={key}, got {len(matches)}")
        return matches[0]


def _exact_combo_identity(
    row: ConcreteColumnDesignResultRow,
    *,
    reconciliation: ConcreteDesignComboReconciliation,
) -> tuple[DesignComboIdentity | None, str | None, str | None]:
    if row.pmm_combo is None:
        return None, BLOCKED_MISSING_PMM_COMBO, "design row has no exact PMMCombo identity"
    matches = tuple(identity for identity in reconciliation.matched if identity[1] == row.pmm_combo)
    if len(matches) != 1:
        return (
            None,
            BLOCKED_UNBINDABLE_PMM_COMBO,
            f"PMMCombo={row.pmm_combo!r} resolved to {len(matches)} exact F0 matched combo identities",
        )
    return matches[0], None, None


def _blocked_row(
    *,
    component: CapturedConcreteColumnDesignResult,
    row: ConcreteColumnDesignResultRow,
    reason_code: str,
    reason_detail: str,
    authority_source_refs: Sequence[str],
) -> BlockedEtabsRequiredRebarRow:
    refs = tuple(dict.fromkeys((*component.source_refs, *authority_source_refs, row.source_ref)))
    return BlockedEtabsRequiredRebarRow(
        source_row_id=row.source_row_id,
        component_id=component.component_id,
        unique_name=component.unique_name,
        story=component.story,
        label=component.label,
        assigned_section=component.assigned_section,
        design_section=component.design_section,
        pmm_combo=row.pmm_combo,
        location_mm=row.location_mm,
        required_as_mm2=row.pmm_area_mm2,
        error_summary=row.error_summary,
        warning_summary=row.warning_summary,
        reason_code=reason_code,
        reason_detail=reason_detail,
        model_fingerprint=component.model_fingerprint,
        evidence_epoch_id=component.evidence_epoch_id,
        source_refs=refs,
    )


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
    blocked_rows: list[BlockedEtabsRequiredRebarRow] = []
    for row in design_rows:
        if row.error_summary != "":
            blocked_rows.append(
                _blocked_row(
                    component=component,
                    row=row,
                    reason_code=BLOCKED_ETABS_ERROR_SUMMARY,
                    reason_detail="nonempty ETABS ErrorSummary blocks ETABS_REQUIRED_REBAR promotion",
                    authority_source_refs=authority.source_refs,
                )
            )
            continue
        if row.warning_summary != "":
            blocked_rows.append(
                _blocked_row(
                    component=component,
                    row=row,
                    reason_code=BLOCKED_ETABS_WARNING_SUMMARY,
                    reason_detail="nonempty ETABS WarningSummary has no reviewed eligibility policy",
                    authority_source_refs=authority.source_refs,
                )
            )
            continue
        combo_identity, reason_code, reason_detail = _exact_combo_identity(row, reconciliation=reconciliation)
        if combo_identity is None:
            blocked_rows.append(
                _blocked_row(
                    component=component,
                    row=row,
                    reason_code=reason_code or BLOCKED_UNBINDABLE_PMM_COMBO,
                    reason_detail=reason_detail or "exact PMMCombo binding failed",
                    authority_source_refs=authority.source_refs,
                )
            )
            continue

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
                *(ref for item in blocked_rows for ref in item.source_refs),
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
        blocked_rows=tuple(blocked_rows),
        source_design_row_count=len(design_rows),
        promoted_requirement_count=len(requirements),
        blocked_requirement_count=len(blocked_rows),
        model_fingerprint=component.model_fingerprint,
        evidence_epoch_id=component.evidence_epoch_id,
        source_refs=refs,
    )


def promote_etabs_required_rebar(
    results: ConcreteColumnDesignResultPopulation,
    *,
    combo_reconciliation: ConcreteDesignComboReconciliation,
) -> EtabsRequiredRebarPopulation:
    """Classify every exact design row and promote only source-authorized rows.

    Global authority failures (incomplete capture, model/epoch mismatch, or an
    unclosed F0 combo reconciliation) fail closed by exception. Row-local ETABS
    warnings/errors or exact-combo binding failures remain explicit blockers so
    live acceptance can report the complete accepted/blocked population without
    inventing equivalence or discarding source evidence.
    """
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
        promoted_requirement_count=sum(item.promoted_requirement_count for item in components),
        blocked_requirement_count=sum(item.blocked_requirement_count for item in components),
        components=components,
        combo_reconciliation_source_refs=combo_reconciliation.source_refs,
        source_refs=source_refs,
    )


__all__ = [
    "BLOCKED_ETABS_ERROR_SUMMARY",
    "BLOCKED_ETABS_WARNING_SUMMARY",
    "BLOCKED_MISSING_PMM_COMBO",
    "BLOCKED_UNBINDABLE_PMM_COMBO",
    "ETABS_REQUIRED_REBAR",
    "ETABS_REQUIRED_REBAR_PROMOTION_RESULT",
    "BlockedEtabsRequiredRebarRow",
    "ColumnDesignRebarEvidenceError",
    "EtabsRequiredRebarComponent",
    "EtabsRequiredRebarEvidence",
    "EtabsRequiredRebarPopulation",
    "promote_etabs_required_rebar",
]
