"""P8A exact component x design-combo required-rebar promotion authority.

Consumes provider-neutral factual concrete-column design-result rows together
with typed component x exact-design-combo eligibility projections. Promotion is
row-wise and deterministic: no first/last/max/envelope collapse is permitted
and no source design row may disappear.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from typing import Sequence

from tbdy_engine.design.columns.column_combo_eligibility_projection import (
    AUTHORITY as COMBO_ELIGIBILITY_AUTHORITY,
    ColumnComboEligibilityProjection,
)
from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    DesignComboIdentity,
)
from tbdy_engine.features.column_design_rebar_evidence import (
    ColumnDesignRebarEvidenceError,
    FactualColumnDesignResultPopulation,
    FactualColumnDesignResultRow,
)

ETABS_REQUIRED_REBAR = "ETABS_REQUIRED_REBAR"
ETABS_REQUIRED_REBAR_PROMOTION_RESULT = "ETABS_REQUIRED_REBAR_PROMOTION_RESULT"

BLOCKED_ETABS_ERROR_SUMMARY = "BLOCKED_ETABS_ERROR_SUMMARY"
BLOCKED_ETABS_WARNING_SUMMARY = "BLOCKED_ETABS_WARNING_SUMMARY"
BLOCKED_MISSING_PMM_COMBO = "BLOCKED_MISSING_PMM_COMBO"
BLOCKED_UNBINDABLE_PMM_COMBO = "BLOCKED_UNBINDABLE_PMM_COMBO"
BLOCKED_AMBIGUOUS_PMM_COMBO = "BLOCKED_AMBIGUOUS_PMM_COMBO"
BLOCKED_COMBO_NOT_ELIGIBLE = "BLOCKED_COMBO_NOT_ELIGIBLE"

def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnDesignRebarEvidenceError(f"{label} must be a nonblank canonical string")
    return value


def _optional_text(value: str | None, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _decimal(value: Decimal, label: str, *, nonnegative: bool = True) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ColumnDesignRebarEvidenceError(f"{label} must be a finite Decimal")
    if nonnegative and value < 0:
        raise ColumnDesignRebarEvidenceError(f"{label} must be >= 0")
    return Decimal(0) if value == 0 else value.normalize()


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    refs = tuple(sorted({_text(value, label) for value in values}))
    if not refs:
        raise ColumnDesignRebarEvidenceError(f"{label} must be nonempty")
    return refs


def _ids(values: Sequence[str], label: str) -> tuple[str, ...]:
    result = tuple(sorted(_text(value, label) for value in values))
    if not result or len(result) != len(set(result)):
        raise ColumnDesignRebarEvidenceError(f"{label} must be nonempty and unique")
    return result


def _identity(value: DesignComboIdentity) -> DesignComboIdentity:
    if not isinstance(value, tuple) or len(value) != 2:
        raise ColumnDesignRebarEvidenceError("design_combo_identity must be exact (type, name)")
    return (_text(value[0], "design_combo_type"), _text(value[1], "design_combo_name"))


def _stable_id(prefix: str, payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return prefix + hashlib.sha256(encoded).hexdigest()

@dataclass(frozen=True, slots=True)
class EtabsRequiredRebarEvidence:
    requirement_id: str
    component_id: str
    unique_name: str
    story: str
    label: str
    assigned_section: str
    design_section: str
    design_combo_identity: DesignComboIdentity
    combo_eligibility_projection_id: str
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
            "combo_eligibility_projection_id",
            "source_row_id",
            "model_fingerprint",
            "evidence_epoch_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "design_combo_identity", _identity(self.design_combo_identity))
        object.__setattr__(self, "location_mm", _decimal(self.location_mm, "location_mm"))
        object.__setattr__(self, "required_as_mm2", _decimal(self.required_as_mm2, "required_as_mm2"))
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))
        if self.authority != ETABS_REQUIRED_REBAR:
            raise ColumnDesignRebarEvidenceError("ETABS_REQUIRED_REBAR authority label mismatch")


@dataclass(frozen=True, slots=True)
class BlockedEtabsRequiredRebarRow:
    source_row_id: str
    component_id: str
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
            "reason_code",
            "reason_detail",
            "model_fingerprint",
            "evidence_epoch_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "pmm_combo", _optional_text(self.pmm_combo, "pmm_combo"))
        object.__setattr__(self, "location_mm", _decimal(self.location_mm, "location_mm"))
        object.__setattr__(self, "required_as_mm2", _decimal(self.required_as_mm2, "required_as_mm2"))
        if not isinstance(self.error_summary, str) or not isinstance(self.warning_summary, str):
            raise ColumnDesignRebarEvidenceError("blocked summaries must preserve exact strings")
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))


@dataclass(frozen=True, slots=True)
class EtabsRequiredRebarComponent:
    component_id: str
    requirements: tuple[EtabsRequiredRebarEvidence, ...]
    blocked_rows: tuple[BlockedEtabsRequiredRebarRow, ...]
    source_design_row_count: int
    promoted_requirement_count: int
    blocked_requirement_count: int
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))
        requirements = tuple(sorted(self.requirements, key=lambda item: item.requirement_id))
        blocked = tuple(sorted(self.blocked_rows, key=lambda item: item.source_row_id))
        if any(not isinstance(item, EtabsRequiredRebarEvidence) for item in requirements):
            raise TypeError("requirements must contain EtabsRequiredRebarEvidence")
        if any(not isinstance(item, BlockedEtabsRequiredRebarRow) for item in blocked):
            raise TypeError("blocked_rows must contain BlockedEtabsRequiredRebarRow")
        if any(item.component_id != self.component_id for item in (*requirements, *blocked)):
            raise ColumnDesignRebarEvidenceError("component promotion contains another component_id")
        if self.source_design_row_count != len(requirements) + len(blocked):
            raise ColumnDesignRebarEvidenceError("every design row must be promoted or explicitly blocked")
        if self.promoted_requirement_count != len(requirements):
            raise ColumnDesignRebarEvidenceError("promoted requirement count mismatch")
        if self.blocked_requirement_count != len(blocked):
            raise ColumnDesignRebarEvidenceError("blocked requirement count mismatch")
        row_ids = tuple(item.source_row_id for item in (*requirements, *blocked))
        if len(row_ids) != len(set(row_ids)):
            raise ColumnDesignRebarEvidenceError("one source design row cannot appear twice")
        object.__setattr__(self, "requirements", requirements)
        object.__setattr__(self, "blocked_rows", blocked)
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))

    @property
    def promotion_complete(self) -> bool:
        return self.blocked_requirement_count == 0


@dataclass(frozen=True, slots=True)
class EtabsRequiredRebarPopulation:
    model_fingerprint: str
    evidence_epoch_id: str
    expected_component_ids: tuple[str, ...]
    source_result_row_count: int
    source_design_row_count: int
    promoted_requirement_count: int
    blocked_requirement_count: int
    components: tuple[EtabsRequiredRebarComponent, ...]
    projection_authority: str
    source_refs: tuple[str, ...]
    authority: str = ETABS_REQUIRED_REBAR_PROMOTION_RESULT

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        expected = _ids(self.expected_component_ids, "expected_component_id")
        object.__setattr__(self, "expected_component_ids", expected)
        components = tuple(sorted(self.components, key=lambda item: item.component_id))
        if tuple(item.component_id for item in components) != expected:
            raise ColumnDesignRebarEvidenceError("promotion components must exactly cover expected components")
        if self.source_design_row_count != sum(item.source_design_row_count for item in components):
            raise ColumnDesignRebarEvidenceError("source design-row count mismatch")
        if self.promoted_requirement_count != sum(item.promoted_requirement_count for item in components):
            raise ColumnDesignRebarEvidenceError("promoted requirement count mismatch")
        if self.blocked_requirement_count != sum(item.blocked_requirement_count for item in components):
            raise ColumnDesignRebarEvidenceError("blocked requirement count mismatch")
        if self.source_design_row_count != self.promoted_requirement_count + self.blocked_requirement_count:
            raise ColumnDesignRebarEvidenceError("every source design row must be accounted exactly once")
        if self.source_result_row_count < self.source_design_row_count:
            raise ColumnDesignRebarEvidenceError("source result-row count cannot be smaller than design-row count")
        object.__setattr__(self, "components", components)
        if self.projection_authority != COMBO_ELIGIBILITY_AUTHORITY:
            raise ColumnDesignRebarEvidenceError("promotion requires P8A combo eligibility authority")
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))
        if self.authority != ETABS_REQUIRED_REBAR_PROMOTION_RESULT:
            raise ColumnDesignRebarEvidenceError("promotion-result authority label mismatch")

    @property
    def promotion_complete(self) -> bool:
        return self.blocked_requirement_count == 0

    @property
    def requirements(self) -> tuple[EtabsRequiredRebarEvidence, ...]:
        return tuple(row for component in self.components for row in component.requirements)

    @property
    def blocked_rows(self) -> tuple[BlockedEtabsRequiredRebarRow, ...]:
        return tuple(row for component in self.components for row in component.blocked_rows)


def _blocked(
    row: FactualColumnDesignResultRow,
    *,
    reason_code: str,
    reason_detail: str,
    projection_refs: Sequence[str] = (),
) -> BlockedEtabsRequiredRebarRow:
    refs = _refs((*row.source_refs, *projection_refs), "blocked.source_ref")
    return BlockedEtabsRequiredRebarRow(
        source_row_id=row.source_row_id,
        component_id=row.component_id,
        pmm_combo=row.pmm_combo,
        location_mm=row.location_mm,
        required_as_mm2=row.pmm_area_mm2,
        error_summary=row.error_summary,
        warning_summary=row.warning_summary,
        reason_code=reason_code,
        reason_detail=reason_detail,
        model_fingerprint=row.model_fingerprint,
        evidence_epoch_id=row.evidence_epoch_id,
        source_refs=refs,
    )


def _promote_row(
    row: FactualColumnDesignResultRow,
    *,
    projections: tuple[ColumnComboEligibilityProjection, ...],
) -> EtabsRequiredRebarEvidence | BlockedEtabsRequiredRebarRow:
    if row.error_summary != "":
        return _blocked(
            row,
            reason_code=BLOCKED_ETABS_ERROR_SUMMARY,
            reason_detail="nonempty ETABS ErrorSummary blocks ETABS_REQUIRED_REBAR promotion",
        )
    if row.warning_summary != "":
        return _blocked(
            row,
            reason_code=BLOCKED_ETABS_WARNING_SUMMARY,
            reason_detail="nonempty ETABS WarningSummary has no reviewed promotion policy",
        )
    if row.pmm_combo is None:
        return _blocked(
            row,
            reason_code=BLOCKED_MISSING_PMM_COMBO,
            reason_detail="design row has no exact PMMCombo identity",
        )

    matches = tuple(
        item
        for item in projections
        if item.component_id == row.component_id and item.design_combo_identity[1] == row.pmm_combo
    )
    projection_refs = tuple(item.projection_id for item in matches)
    if not matches:
        return _blocked(
            row,
            reason_code=BLOCKED_UNBINDABLE_PMM_COMBO,
            reason_detail=f"PMMCombo={row.pmm_combo!r} has no component-specific P8A combo projection",
        )
    if len(matches) != 1:
        return _blocked(
            row,
            reason_code=BLOCKED_AMBIGUOUS_PMM_COMBO,
            reason_detail=f"PMMCombo={row.pmm_combo!r} binds to {len(matches)} component-specific design-combo identities",
            projection_refs=projection_refs,
        )
    projection = matches[0]
    if not projection.eligible:
        return _blocked(
            row,
            reason_code=BLOCKED_COMBO_NOT_ELIGIBLE,
            reason_detail="exact component x combo projection is not ELIGIBLE: " + ",".join(projection.blockers),
            projection_refs=(projection.projection_id, *projection.provenance_refs),
        )

    requirement_id = _stable_id(
        "etabs-required-rebar:sha256:",
        {
            "source_row_id": row.source_row_id,
            "component_id": row.component_id,
            "design_combo_identity": projection.design_combo_identity,
            "projection_id": projection.projection_id,
            "location_mm": format(row.location_mm, "f"),
            "required_as_mm2": format(row.pmm_area_mm2, "f"),
            "model_fingerprint": row.model_fingerprint,
            "evidence_epoch_id": row.evidence_epoch_id,
        },
    )
    return EtabsRequiredRebarEvidence(
        requirement_id=requirement_id,
        component_id=row.component_id,
        unique_name=row.unique_name,
        story=row.story,
        label=row.label,
        assigned_section=row.assigned_section,
        design_section=row.design_section,
        design_combo_identity=projection.design_combo_identity,
        combo_eligibility_projection_id=projection.projection_id,
        location_mm=row.location_mm,
        required_as_mm2=row.pmm_area_mm2,
        source_row_id=row.source_row_id,
        model_fingerprint=row.model_fingerprint,
        evidence_epoch_id=row.evidence_epoch_id,
        source_refs=_refs(
            (*row.source_refs, projection.projection_id, *projection.provenance_refs),
            "requirement.source_ref",
        ),
    )


def promote_etabs_required_rebar(
    results: FactualColumnDesignResultPopulation,
    *,
    combo_eligibility_projections: Sequence[ColumnComboEligibilityProjection],
) -> EtabsRequiredRebarPopulation:
    """Promote every exact design row only through component x combo eligibility."""
    if not isinstance(results, FactualColumnDesignResultPopulation):
        raise TypeError("results must be FactualColumnDesignResultPopulation")
    if not results.capture_complete:
        raise ColumnDesignRebarEvidenceError("factual design-result population is not complete")

    projections = tuple(sorted(combo_eligibility_projections, key=lambda item: (item.component_id, item.design_combo_identity)))
    if not projections or any(not isinstance(item, ColumnComboEligibilityProjection) for item in projections):
        raise TypeError("combo_eligibility_projections must be nonempty typed projections")
    projection_keys = tuple((item.component_id, item.design_combo_identity) for item in projections)
    if len(projection_keys) != len(set(projection_keys)):
        raise ColumnDesignRebarEvidenceError("component x design-combo projection identities must be unique")
    if any(
        item.model_fingerprint != results.model_fingerprint
        or item.evidence_epoch_id != results.evidence_epoch_id
        for item in projections
    ):
        raise ColumnDesignRebarEvidenceError("design results and combo projections do not share model/EvidenceEpoch")
    projected_components = tuple(sorted({item.component_id for item in projections}))
    if projected_components != results.expected_component_ids:
        raise ColumnDesignRebarEvidenceError("combo projections must cover the exact expected component population")

    components: list[EtabsRequiredRebarComponent] = []
    for component_id in results.expected_component_ids:
        design_rows = tuple(row for row in results.design_rows if row.component_id == component_id)
        if not design_rows:
            raise ColumnDesignRebarEvidenceError(
                f"canonical column {component_id} has no MyOption=2 design rows"
            )
        component_projections = tuple(item for item in projections if item.component_id == component_id)
        requirements: list[EtabsRequiredRebarEvidence] = []
        blocked: list[BlockedEtabsRequiredRebarRow] = []
        for row in design_rows:
            promoted = _promote_row(row, projections=component_projections)
            if isinstance(promoted, EtabsRequiredRebarEvidence):
                requirements.append(promoted)
            else:
                blocked.append(promoted)
        refs = _refs(
            (
                *results.source_refs,
                *(ref for item in component_projections for ref in (item.projection_id, *item.provenance_refs)),
                *(ref for item in requirements for ref in item.source_refs),
                *(ref for item in blocked for ref in item.source_refs),
            ),
            "component.source_ref",
        )
        components.append(
            EtabsRequiredRebarComponent(
                component_id=component_id,
                requirements=tuple(requirements),
                blocked_rows=tuple(blocked),
                source_design_row_count=len(design_rows),
                promoted_requirement_count=len(requirements),
                blocked_requirement_count=len(blocked),
                source_refs=refs,
            )
        )

    population_refs = _refs(
        (
            *results.source_refs,
            *(ref for item in projections for ref in (item.projection_id, *item.provenance_refs)),
            *(ref for item in components for ref in item.source_refs),
        ),
        "population.source_ref",
    )
    return EtabsRequiredRebarPopulation(
        model_fingerprint=results.model_fingerprint,
        evidence_epoch_id=results.evidence_epoch_id,
        expected_component_ids=results.expected_component_ids,
        source_result_row_count=len(results.rows),
        source_design_row_count=len(results.design_rows),
        promoted_requirement_count=sum(item.promoted_requirement_count for item in components),
        blocked_requirement_count=sum(item.blocked_requirement_count for item in components),
        components=tuple(components),
        projection_authority=COMBO_ELIGIBILITY_AUTHORITY,
        source_refs=population_refs,
    )

__all__ = [
    "BLOCKED_AMBIGUOUS_PMM_COMBO",
    "BLOCKED_COMBO_NOT_ELIGIBLE",
    "BLOCKED_ETABS_ERROR_SUMMARY",
    "BLOCKED_ETABS_WARNING_SUMMARY",
    "BLOCKED_MISSING_PMM_COMBO",
    "BLOCKED_UNBINDABLE_PMM_COMBO",
    "ETABS_REQUIRED_REBAR",
    "ETABS_REQUIRED_REBAR_PROMOTION_RESULT",
    "BlockedEtabsRequiredRebarRow",
    "EtabsRequiredRebarComponent",
    "EtabsRequiredRebarEvidence",
    "EtabsRequiredRebarPopulation",
    "promote_etabs_required_rebar",
]
