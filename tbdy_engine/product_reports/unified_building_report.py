"""Canonical render-neutral unified building report model for UR-1A.

This module is a reporting-integrity boundary only.  It consumes already
resolved canonical artifacts and never executes regulatory or engineering
logic.  In particular it does not calculate demand/capacity, determine
applicability, choose governing cases, or emit a project compliance PASS.

The model binds every mandatory compiled rule instance to an exact canonical
report source through FCR-1A before any renderer is allowed to consume it.
Engineering and audit projections therefore share one immutable truth model.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json
import math
from typing import Any, Sequence

from tbdy_engine.coverage.project_reconciliation import (
    ProjectCoverageReconciliation,
    ReportBindingRef,
    ReportContributionRef,
    canonical_closure_report_source_ref,
    canonical_quantity_report_source_ref,
)
from tbdy_engine.product_reports.slice_report_contribution import SliceReportContribution


class BuildingReportIntegrityError(ValueError):
    """Raised when canonical report identity/provenance does not reconcile."""


class ReportSourceKind(StrEnum):
    ETABS_MODEL = "ETABS_MODEL"
    ETABS_EVIDENCE = "ETABS_EVIDENCE"
    REGULATORY_DOCUMENT = "REGULATORY_DOCUMENT"
    REGULATORY_AUTHORITY = "REGULATORY_AUTHORITY"
    REVIEWED_DECLARATION = "REVIEWED_DECLARATION"
    ENGINE_ARTIFACT = "ENGINE_ARTIFACT"


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise BuildingReportIntegrityError(f"{label} must be a nonblank canonical string")
    return value


def _optional_text(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)


def _scalar(value: Any, label: str) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BuildingReportIntegrityError(f"{label} must be finite")
        return value
    raise BuildingReportIntegrityError(
        f"{label} must be a report scalar (str/int/float/bool/null), got {type(value).__name__}"
    )


def _unique_texts(values: Sequence[str], label: str, *, require_nonempty: bool = False) -> tuple[str, ...]:
    frozen = tuple(_text(value, f"{label}[]") for value in values)
    if require_nonempty and not frozen:
        raise BuildingReportIntegrityError(f"{label} must not be empty")
    if len(set(frozen)) != len(frozen):
        raise BuildingReportIntegrityError(f"{label} must not contain duplicates")
    return tuple(sorted(frozen))


@dataclass(frozen=True, slots=True)
class ProjectBasisEntry:
    """One reviewed project/design basis fact with explicit source identity."""

    key: str
    label: str
    value: str | int | float | bool | None
    source_ids: tuple[str, ...]
    unit: str | None = None
    note: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _text(self.key, "basis.key"))
        object.__setattr__(self, "label", _text(self.label, "basis.label"))
        object.__setattr__(self, "value", _scalar(self.value, f"basis {self.key}.value"))
        object.__setattr__(self, "source_ids", _unique_texts(self.source_ids, f"basis {self.key}.source_ids", require_nonempty=True))
        object.__setattr__(self, "unit", _optional_text(self.unit, f"basis {self.key}.unit"))
        object.__setattr__(self, "note", _optional_text(self.note, f"basis {self.key}.note"))

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "unit": self.unit,
            "source_ids": list(self.source_ids),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class ProjectBasisLedger:
    """Deterministic project/input provenance ledger; no engineering decisions."""

    entries: tuple[ProjectBasisEntry, ...]

    def __init__(self, entries: Sequence[ProjectBasisEntry]) -> None:
        frozen = tuple(entries)
        if any(not isinstance(item, ProjectBasisEntry) for item in frozen):
            raise TypeError("entries must contain ProjectBasisEntry")
        keys = tuple(item.key for item in frozen)
        if len(keys) != len(set(keys)):
            raise BuildingReportIntegrityError("project basis keys must be unique")
        object.__setattr__(self, "entries", tuple(sorted(frozen, key=lambda item: item.key)))

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "project_basis_ledger.ur_1a.v1",
            "entries": [item.as_dict() for item in self.entries],
        }


@dataclass(frozen=True, slots=True)
class SourceManifestEntry:
    """One exact factual/regulatory/reviewed source available to the report."""

    source_id: str
    source_kind: ReportSourceKind
    title: str
    fingerprint: str | None = None
    locator: str | None = None
    authority_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _text(self.source_id, "source.source_id"))
        if not isinstance(self.source_kind, ReportSourceKind):
            raise TypeError("source_kind must be ReportSourceKind")
        object.__setattr__(self, "title", _text(self.title, "source.title"))
        object.__setattr__(self, "fingerprint", _optional_text(self.fingerprint, "source.fingerprint"))
        object.__setattr__(self, "locator", _optional_text(self.locator, "source.locator"))
        object.__setattr__(self, "authority_refs", _unique_texts(self.authority_refs, "source.authority_refs"))
        object.__setattr__(self, "evidence_refs", _unique_texts(self.evidence_refs, "source.evidence_refs"))

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind.value,
            "title": self.title,
            "fingerprint": self.fingerprint,
            "locator": self.locator,
            "authority_refs": list(self.authority_refs),
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class SourceManifest:
    """Deterministic source manifest referenced by the project basis ledger."""

    entries: tuple[SourceManifestEntry, ...]

    def __init__(self, entries: Sequence[SourceManifestEntry]) -> None:
        frozen = tuple(entries)
        if any(not isinstance(item, SourceManifestEntry) for item in frozen):
            raise TypeError("entries must contain SourceManifestEntry")
        ids = tuple(item.source_id for item in frozen)
        if len(ids) != len(set(ids)):
            raise BuildingReportIntegrityError("source manifest source_id values must be unique")
        object.__setattr__(self, "entries", tuple(sorted(frozen, key=lambda item: item.source_id)))

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(item.source_id for item in self.entries)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "source_manifest.ur_1a.v1",
            "entries": [item.as_dict() for item in self.entries],
        }


def mandatory_report_source_refs(
    reconciliation: ProjectCoverageReconciliation,
) -> tuple[str, ...]:
    """Derive the exact report-source denominator from canonical FCR closure.

    This is reporting accounting, not engineering authority. Executed canonical
    artifacts bind by their exact artifact identity. Any mandatory instance
    without such an artifact (PNA/BLOCKED/NO_DATA/unresolved closure) binds by
    its exact RuleClosureOutcome identity so it cannot disappear from a report.
    """

    if not isinstance(reconciliation, ProjectCoverageReconciliation):
        raise TypeError("reconciliation must be ProjectCoverageReconciliation")

    outcomes: dict[object, object] = {}
    for outcome in reconciliation.structural_assessment.closure_outcomes:
        key = outcome.compiled_record_ref
        if key in outcomes:
            raise BuildingReportIntegrityError(
                f"duplicate structural-assessment closure identity: {key.value}"
            )
        outcomes[key] = outcome

    refs: list[str] = []
    for instance_id in reconciliation.expected_mandatory_ids:
        outcome = outcomes.get(instance_id)
        if outcome is None:
            raise BuildingReportIntegrityError(
                f"mandatory instance has no canonical closure outcome: {instance_id.value}"
            )
        if outcome.formal_result_ref is not None and outcome.regulatory_quantity_refs:
            raise BuildingReportIntegrityError(
                f"closure cannot bind both CheckResult and RegulatoryQuantity artifacts: {instance_id.value}"
            )
        if outcome.formal_result_ref is not None:
            refs.append(_text(outcome.formal_result_ref, "formal_result_ref"))
        elif outcome.regulatory_quantity_refs:
            refs.extend(
                canonical_quantity_report_source_ref(instance_id, quantity_key)
                for quantity_key in outcome.regulatory_quantity_refs
            )
        else:
            refs.append(canonical_closure_report_source_ref(instance_id))

    if len(refs) != len(set(refs)):
        raise BuildingReportIntegrityError("mandatory canonical report-source identities must be unique")
    return tuple(sorted(refs))


@dataclass(frozen=True, slots=True)
class BuildingReportModel:
    """Single canonical render-neutral truth model for the building report."""

    report_id: str
    project_id: str
    title: str
    reconciliation: ProjectCoverageReconciliation
    project_basis: ProjectBasisLedger
    source_manifest: SourceManifest
    contributions: tuple[SliceReportContribution, ...]
    report_bindings: tuple[ReportBindingRef, ...]

    def __init__(
        self,
        *,
        report_id: str,
        project_id: str,
        title: str,
        reconciliation: ProjectCoverageReconciliation,
        project_basis: ProjectBasisLedger,
        source_manifest: SourceManifest,
        contributions: Sequence[SliceReportContribution],
        report_bindings: Sequence[ReportBindingRef],
    ) -> None:
        object.__setattr__(self, "report_id", _text(report_id, "report_id"))
        object.__setattr__(self, "project_id", _text(project_id, "project_id"))
        object.__setattr__(self, "title", _text(title, "title"))
        if not isinstance(reconciliation, ProjectCoverageReconciliation):
            raise TypeError("reconciliation must be ProjectCoverageReconciliation")
        if not isinstance(project_basis, ProjectBasisLedger):
            raise TypeError("project_basis must be ProjectBasisLedger")
        if not isinstance(source_manifest, SourceManifest):
            raise TypeError("source_manifest must be SourceManifest")

        mandatory_refs = mandatory_report_source_refs(reconciliation)
        declared_required_refs = tuple(sorted(reconciliation.required_report_source_refs))
        if declared_required_refs != mandatory_refs:
            raise BuildingReportIntegrityError(
                "FCR required report-source population must equal the canonical mandatory closure/artifact population"
            )
        if not reconciliation.report_reconciled:
            raise BuildingReportIntegrityError("FCR report reconciliation must be complete before building report assembly")
        if (
            reconciliation.missing_report_source_refs
            or reconciliation.duplicate_report_source_refs
            or reconciliation.orphan_report_binding_source_refs
            or reconciliation.orphan_report_target_refs
        ):
            raise BuildingReportIntegrityError("FCR report binding diagnostics must be empty")

        frozen_contributions = tuple(contributions)
        if any(not isinstance(item, SliceReportContribution) for item in frozen_contributions):
            raise TypeError("contributions must contain SliceReportContribution")
        contribution_refs = tuple(ReportContributionRef.from_contribution(item) for item in frozen_contributions)
        contribution_values = tuple(item.value for item in contribution_refs)
        if len(contribution_values) != len(set(contribution_values)):
            raise BuildingReportIntegrityError("report contribution identity must be exact and unique")

        frozen_bindings = tuple(report_bindings)
        if any(not isinstance(item, ReportBindingRef) for item in frozen_bindings):
            raise TypeError("report_bindings must contain ReportBindingRef")
        binding_source_refs = tuple(item.source_ref for item in frozen_bindings)
        if len(binding_source_refs) != len(set(binding_source_refs)):
            raise BuildingReportIntegrityError("each mandatory report source must bind exactly once")
        if tuple(sorted(binding_source_refs)) != mandatory_refs:
            raise BuildingReportIntegrityError("building report bindings must exactly cover mandatory report sources")

        known_targets = set(contribution_values)
        bound_targets = {item.contribution_ref.value for item in frozen_bindings}
        unknown_targets = tuple(sorted(bound_targets - known_targets))
        if unknown_targets:
            raise BuildingReportIntegrityError(
                "report binding targets unknown contribution identity: " + ",".join(unknown_targets)
            )
        unbound_targets = tuple(sorted(known_targets - bound_targets))
        if unbound_targets:
            raise BuildingReportIntegrityError(
                "report contributions without canonical source binding are forbidden: " + ",".join(unbound_targets)
            )

        manifest_ids = set(source_manifest.source_ids)
        missing_basis_sources = tuple(sorted({source_id for item in project_basis.entries for source_id in item.source_ids} - manifest_ids))
        if missing_basis_sources:
            raise BuildingReportIntegrityError(
                "project basis references missing source manifest entries: " + ",".join(missing_basis_sources)
            )

        sorted_contributions = tuple(
            item
            for _, item in sorted(
                zip(contribution_refs, frozen_contributions),
                key=lambda pair: pair[0].sort_key,
            )
        )
        sorted_bindings = tuple(
            sorted(
                frozen_bindings,
                key=lambda item: (item.source_ref, item.contribution_ref.sort_key),
            )
        )

        object.__setattr__(self, "reconciliation", reconciliation)
        object.__setattr__(self, "project_basis", project_basis)
        object.__setattr__(self, "source_manifest", source_manifest)
        object.__setattr__(self, "contributions", sorted_contributions)
        object.__setattr__(self, "report_bindings", sorted_bindings)

    @property
    def report_integrity_status(self) -> str:
        """Reporting integrity only. This is deliberately not a compliance verdict."""
        return "RECONCILED"

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": "building_report_model.ur_1a.v1",
            "artifact_type": "BUILDING_REPORT_MODEL",
            "report_id": self.report_id,
            "project_id": self.project_id,
            "title": self.title,
            "report_integrity_status": self.report_integrity_status,
            "project_basis": self.project_basis.as_dict(),
            "source_manifest": self.source_manifest.as_dict(),
            "coverage_reconciliation": self.reconciliation.as_dict(),
            "report_bindings": [
                {
                    "source_ref": item.source_ref,
                    "contribution_ref": item.contribution_ref.value,
                }
                for item in self.report_bindings
            ],
            "contributions": [item.as_dict() for item in self.contributions],
            "presentation_contract": {
                "default_view": "ENGINEERING",
                "supported_views": ["ENGINEERING", "AUDIT"],
                "renderer_may_recalculate_engineering": False,
                "renderer_may_change_status": False,
                "renderer_may_change_governing_selection": False,
                "global_compliance_verdict_emitted": False,
            },
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"


__all__ = [
    "BuildingReportIntegrityError",
    "BuildingReportModel",
    "ProjectBasisEntry",
    "ProjectBasisLedger",
    "ReportSourceKind",
    "SourceManifest",
    "SourceManifestEntry",
    "mandatory_report_source_refs",
]
