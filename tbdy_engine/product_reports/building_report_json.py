"""Deterministic canonical BuildingReportModel JSON export for UR-1E.

This module is delivery infrastructure only. It serializes the accepted
BuildingReportModel exactly and owns no engineering, regulatory, coverage,
applicability, governing-selection, compliance, or remediation authority.
"""
from __future__ import annotations

from hashlib import sha256

from tbdy_engine.product_reports.report_artifact import ReportArtifact
from tbdy_engine.product_reports.unified_building_report import (
    BuildingReportIntegrityError,
    BuildingReportModel,
)


CANONICAL_MODEL_JSON_FILENAME = "building_report_model.json"


def export_building_report_model_json(model: BuildingReportModel) -> ReportArtifact:
    """Export the full canonical report model as deterministic UTF-8 JSON bytes."""

    if not isinstance(model, BuildingReportModel):
        raise TypeError("model must be BuildingReportModel")
    if model.report_integrity_status != "RECONCILED":
        raise BuildingReportIntegrityError(
            "report_integrity_status must be canonical RECONCILED before export"
        )

    content = model.to_json().encode("utf-8")
    model_sha256 = sha256(content).hexdigest()
    return ReportArtifact(
        logical_role="CANONICAL_BUILDING_REPORT_MODEL",
        format="JSON",
        media_type="application/json",
        filename=CANONICAL_MODEL_JSON_FILENAME,
        content=content,
        view=None,
        source_report_id=model.report_id,
        source_project_id=model.project_id,
        source_model_sha256=model_sha256,
    )


__all__ = [
    "CANONICAL_MODEL_JSON_FILENAME",
    "export_building_report_model_json",
]
