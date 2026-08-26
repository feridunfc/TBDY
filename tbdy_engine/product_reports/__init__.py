"""Product-level report builders and canonical render-neutral report models.

These modules assemble read-only projections of already-resolved product,
regulatory, design, and coverage artifacts. They do not attach to ETABS
directly, run analysis/design, or create engineering verdict authority.
"""

from .c13_1_report import build_c13_1_product_report, write_c13_1_product_report
from .unified_building_report import (
    BuildingReportIntegrityError,
    BuildingReportModel,
    ProjectBasisEntry,
    ProjectBasisLedger,
    ReportSourceKind,
    SourceManifest,
    SourceManifestEntry,
    mandatory_report_source_refs,
)

__all__ = [
    "BuildingReportIntegrityError",
    "BuildingReportModel",
    "ProjectBasisEntry",
    "ProjectBasisLedger",
    "ReportSourceKind",
    "SourceManifest",
    "SourceManifestEntry",
    "build_c13_1_product_report",
    "mandatory_report_source_refs",
    "write_c13_1_product_report",
]
