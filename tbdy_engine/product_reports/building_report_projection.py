"""Canonical render-neutral Engineering/Audit projections for UR-1B.

This module projects an already-valid :class:`BuildingReportModel` for two
canonical professional views. It owns no engineering, regulatory, closure,
or compliance authority. Values, statuses, identities, and trace references
are copied from the canonical report model without recalculation or
reinterpretation.

The projection shape is intentionally UI-ready but contains no renderer or
frontend logic. A future Unified Engineering Review UI may consume this read
model without rebuilding engineering identity from display text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import json

from tbdy_engine.coverage.project_reconciliation import ReportContributionRef
from tbdy_engine.product_reports.unified_building_report import BuildingReportModel
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus


class ReportView(StrEnum):
    """Canonical report views implemented by UR-1B."""

    ENGINEERING = "ENGINEERING"
    AUDIT = "AUDIT"


class ReportProjectionIntegrityError(ValueError):
    """Raised when a canonical view cannot preserve BuildingReportModel integrity."""


def _analysis_basis_row(item: object) -> dict[str, str]:
    """Copy one typed AnalysisBasisRef without interpreting its state."""

    return {
        "instance_id": item.instance_id.value,  # type: ignore[attr-defined]
        "status": item.status.value,  # type: ignore[attr-defined]
        "source_ref": item.source_ref,  # type: ignore[attr-defined]
    }


def _sorted_contributions(model: BuildingReportModel):
    return tuple(
        sorted(
            model.contributions,
            key=lambda item: ReportContributionRef.from_contribution(item).sort_key,
        )
    )


def _coverage_summary(model: BuildingReportModel) -> dict[str, object]:
    """Copy the existing FCR summary exactly; do not derive compliance metrics."""

    payload = model.reconciliation.as_dict()
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ReportProjectionIntegrityError("canonical FCR summary is missing or invalid")
    return dict(summary)


def _analysis_basis_summary(model: BuildingReportModel) -> dict[str, object]:
    """Expose exact FCR analysis-basis accounting needed for dashboard warnings."""

    instance_ids = tuple(
        sorted(item.value for item in model.reconciliation.reanalysis_required_instance_ids)
    )
    return {
        "reanalysis_required_count": len(instance_ids),
        "reanalysis_required_instance_ids": list(instance_ids),
    }


def _binding_sources_by_contribution(model: BuildingReportModel) -> dict[str, tuple[str, ...]]:
    grouped: dict[str, list[str]] = {}
    for binding in model.report_bindings:
        grouped.setdefault(binding.contribution_ref.value, []).append(binding.source_ref)
    return {key: tuple(sorted(values)) for key, values in grouped.items()}


def _projected_contributions(model: BuildingReportModel) -> list[dict[str, object]]:
    """Copy contribution content and attach exact canonical drill-down identity."""

    binding_sources = _binding_sources_by_contribution(model)
    projected: list[dict[str, object]] = []
    for contribution in _sorted_contributions(model):
        contribution_ref = ReportContributionRef.from_contribution(contribution)
        source_refs = binding_sources.get(contribution_ref.value)
        if not source_refs:
            # BuildingReportModel already forbids this. Keep the projection
            # boundary fail-closed rather than silently weakening that invariant.
            raise ReportProjectionIntegrityError(
                "canonical contribution has no report binding source identity: "
                + contribution_ref.value
            )
        payload = contribution.as_dict()
        payload["contribution_ref"] = contribution_ref.value
        payload["report_source_refs"] = list(source_refs)
        projected.append(payload)
    return projected


def _status_facets(model: BuildingReportModel) -> list[dict[str, object]]:
    """Count exact contribution statuses; never collapse or rank them."""

    counts: dict[str, int] = {}
    for contribution in model.contributions:
        counts[contribution.status] = counts.get(contribution.status, 0) + 1
    return [
        {"status": status, "count": counts[status]}
        for status in sorted(counts)
    ]


def _kind_facets(model: BuildingReportModel) -> list[dict[str, object]]:
    """Count exact canonical contribution kinds only."""

    counts: dict[str, int] = {}
    for contribution in model.contributions:
        counts[contribution.contribution_kind] = counts.get(contribution.contribution_kind, 0) + 1
    return [
        {"contribution_kind": kind, "count": counts[kind]}
        for kind in sorted(counts)
    ]


def _component_facets(model: BuildingReportModel) -> list[dict[str, object]]:
    """Group by exact component_type/component_id, preserving project-level None."""

    grouped: dict[tuple[str | None, str | None], list[str]] = {}
    for contribution in model.contributions:
        key = (contribution.component_type, contribution.component_id)
        grouped.setdefault(key, []).append(
            ReportContributionRef.from_contribution(contribution).value
        )

    def sort_key(item: tuple[tuple[str | None, str | None], list[str]]):
        (component_type, component_id), _ = item
        return (
            component_type is None,
            component_type or "",
            component_id is None,
            component_id or "",
        )

    return [
        {
            "component_type": component_type,
            "component_id": component_id,
            "contribution_count": len(refs),
            "contribution_refs": sorted(refs),
        }
        for (component_type, component_id), refs in sorted(grouped.items(), key=sort_key)
    ]


def _validate_view_accounting(model: BuildingReportModel, view: ReportView) -> None:
    """Fail closed if canonical view metadata would silently hide a bound contribution."""

    missing: list[str] = []
    for contribution in model.contributions:
        if view.value not in contribution.render_views:
            missing.append(ReportContributionRef.from_contribution(contribution).value)
    if missing:
        raise ReportProjectionIntegrityError(
            f"mandatory bound contribution excludes canonical {view.value} view: "
            + ", ".join(sorted(missing))
        )


def _presentation_contract() -> dict[str, object]:
    return {
        "projection_only": True,
        "renderer_neutral": True,
        "engineering_recalculation_allowed": False,
        "status_reinterpretation_allowed": False,
        "governing_selection_change_allowed": False,
        "global_compliance_verdict_emitted": False,
        "compliance_percentage_emitted": False,
    }


@dataclass(frozen=True, slots=True)
class BuildingReportProjection:
    """Immutable deterministic projection of one canonical BuildingReportModel.

    The private model reference is itself immutable and is the sole source of
    projected truth. ``as_dict`` exposes only data permitted for the selected
    canonical view.
    """

    view: ReportView
    _model: BuildingReportModel = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.view, ReportView):
            raise TypeError("view must be ReportView")
        if not isinstance(self._model, BuildingReportModel):
            raise TypeError("_model must be BuildingReportModel")
        _validate_view_accounting(self._model, self.view)

    @property
    def report_id(self) -> str:
        return self._model.report_id

    @property
    def project_id(self) -> str:
        return self._model.project_id

    @property
    def report_integrity_status(self) -> str:
        return self._model.report_integrity_status

    def _identity_dict(self) -> dict[str, object]:
        return {
            "schema_version": "building_report_projection.ur_1b.v1",
            "artifact_type": "BUILDING_REPORT_PROJECTION",
            "view": self.view.value,
            "report_id": self._model.report_id,
            "project_id": self._model.project_id,
            "title": self._model.title,
            "report_integrity_status": self._model.report_integrity_status,
        }

    def as_dict(self) -> dict[str, object]:
        basis_refs = tuple(
            sorted(
                self._model.reconciliation.analysis_basis_refs,
                key=lambda item: item.instance_id.value,
            )
        )
        contributions = _projected_contributions(self._model)
        status_facets = _status_facets(self._model)
        kind_facets = _kind_facets(self._model)
        component_facets = _component_facets(self._model)

        if self.view is ReportView.ENGINEERING:
            # Logical section order is renderer-neutral and intentionally
            # mirrors the future professional dashboard read model.
            payload = self._identity_dict()
            payload["project_basis"] = self._model.project_basis.as_dict()
            payload["coverage_summary"] = _coverage_summary(self._model)
            payload["analysis_basis_summary"] = _analysis_basis_summary(self._model)
            payload["analysis_basis_warnings"] = [
                _analysis_basis_row(item)
                for item in basis_refs
                if item.status is not AnalysisBasisStatus.MATCH
            ]
            payload["status_facets"] = status_facets
            payload["contribution_kind_facets"] = kind_facets
            payload["component_facets"] = component_facets
            payload["contributions"] = contributions
            payload["presentation_contract"] = _presentation_contract()
            return payload

        if self.view is ReportView.AUDIT:
            payload = self._identity_dict()
            payload["project_basis"] = self._model.project_basis.as_dict()
            payload["coverage_summary"] = _coverage_summary(self._model)
            payload["coverage_reconciliation"] = self._model.reconciliation.as_dict()
            payload["analysis_basis_summary"] = _analysis_basis_summary(self._model)
            payload["analysis_basis_refs"] = [_analysis_basis_row(item) for item in basis_refs]
            payload["report_bindings"] = [
                {
                    "source_ref": item.source_ref,
                    "contribution_ref": item.contribution_ref.value,
                }
                for item in self._model.report_bindings
            ]
            payload["source_manifest"] = self._model.source_manifest.as_dict()
            payload["status_facets"] = status_facets
            payload["contribution_kind_facets"] = kind_facets
            payload["component_facets"] = component_facets
            payload["contributions"] = contributions
            payload["presentation_contract"] = _presentation_contract()
            return payload

        # Defensive only; ReportView currently has exactly ENGINEERING/AUDIT.
        raise ReportProjectionIntegrityError(f"unsupported UR-1B report view: {self.view!r}")

    def to_json(self) -> str:
        return json.dumps(
            self.as_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ) + "\n"


def project_building_report_view(
    model: BuildingReportModel,
    view: ReportView,
) -> BuildingReportProjection:
    """Project one canonical BuildingReportModel into ENGINEERING or AUDIT.

    ``EXECUTIVE`` and renderer-specific views are intentionally outside UR-1B.
    """

    if not isinstance(model, BuildingReportModel):
        raise TypeError("model must be BuildingReportModel")
    if not isinstance(view, ReportView):
        raise ReportProjectionIntegrityError(
            "UR-1B supports only ReportView.ENGINEERING and ReportView.AUDIT"
        )
    return BuildingReportProjection(view=view, _model=model)


__all__ = [
    "BuildingReportProjection",
    "ReportProjectionIntegrityError",
    "ReportView",
    "project_building_report_view",
]
