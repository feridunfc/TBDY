"""Coverage matrix foundation for C5.

This package only assesses data availability/runnability. It does not execute
checks, compute ratios, or emit engineering OK/FAIL decisions.
"""
from tbdy_engine.coverage.builder import CoverageBuilder
from tbdy_engine.coverage.diagnostics import CoverageDiagnostic, CoverageDiagnosticCode, CoverageDiagnosticSeverity
from tbdy_engine.coverage.models import (
    CoverageEvidenceStatus,
    CoverageExpectedSource,
    CoverageMatrix,
    CoverageMissingDesignContext,
    CoverageMissingFeature,
    CoveragePolicyStatus,
    CoverageRow,
    CoverageStatus,
    ExpectedSourceKind,
)

__all__ = [
    "CoverageBuilder",
    "CoverageDiagnostic",
    "CoverageDiagnosticCode",
    "CoverageDiagnosticSeverity",
    "CoverageEvidenceStatus",
    "CoverageExpectedSource",
    "CoverageMatrix",
    "CoverageMissingDesignContext",
    "CoverageMissingFeature",
    "CoveragePolicyStatus",
    "CoverageRow",
    "CoverageStatus",
    "ExpectedSourceKind",
]
