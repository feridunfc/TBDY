"""Canonical render-neutral Engineering/Audit projections for UR-1B.

This module projects an already-valid :class:`BuildingReportModel` for two
canonical professional views.  It owns no engineering, regulatory, closure,
or compliance authority.  Values and statuses are copied from the canonical
report model without recalculation or reinterpretation.
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
    """Copy the existing FCR summary; do not derive a compliance summary."""

    payload = model.reconciliation.as_dict()
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ReportProjectionIntegrityError("canonical FCR summary is missing or invalid")
    return dict(summary)


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


@dataclass(frozen=True, slots=True)
class BuildingReportProjection:
    """Immutable deterministic projection of one canonical BuildingReportModel.

    The private model reference is itself immutable and is the sole source of
    projected truth.  ``as_dict`` exposes only data permitted for the selected
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

    def _common_dict(self) -> dict[str, object]:
        contributions = _sorted_contributions(self._model)
        return {
            "schema_version": "building_report_projection.ur_1b.v1",
            "artifact_type": "BUILDING_REPORT_PROJECTION",
            "view": self.view.value,
            "report_id": self._model.report_id,
            "project_id": self._model.project_id,
            "title": self._model.title,
            "report_integrity_status": self._model.report_integrity_status,
            "project_basis": self._model.project_basis.as_dict(),
            "coverage_summary": _coverage_summary(self._model),
            "contributions": [item.as_dict() for item in contributions],
            "presentation_contract": {
                "projection_only": True,
                "engineering_recalculation_allowed": False,
                "status_reinterpretation_allowed": False,
                "governing_selection_change_allowed": False,
                "global_compliance_verdict_emitted": False,
            },
        }

    def as_dict(self) -> dict[str, object]:
        payload = self._common_dict()

        basis_refs = tuple(
            sorted(
                self._model.reconciliation.analysis_basis_refs,
                key=lambda item: item.instance_id.value,
            )
        )

        if self.view is ReportView.ENGINEERING:
            # These are exact upstream states requiring professional attention;
            # no warning text or PASS/FAIL mapping is manufactured here.
            payload["analysis_basis_warnings"] = [
                _analysis_basis_row(item)
                for item in basis_refs
                if item.status is not AnalysisBasisStatus.MATCH
            ]
            return payload

        if self.view is ReportView.AUDIT:
            payload["analysis_basis_refs"] = [_analysis_basis_row(item) for item in basis_refs]
            payload["coverage_reconciliation"] = self._model.reconciliation.as_dict()
            payload["report_bindings"] = [
                {
                    "source_ref": item.source_ref,
                    "contribution_ref": item.contribution_ref.value,
                }
                for item in self._model.report_bindings
            ]
            payload["source_manifest"] = self._model.source_manifest.as_dict()
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
