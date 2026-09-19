"""Coverage and project reconciliation foundations.

Coverage discovery assesses availability/runnability only. Project reconciliation
accounts canonical compiled/runtime/report/action identities without executing
checks, computing ratios, or emitting engineering OK/FAIL decisions.
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
from tbdy_engine.coverage.column_denominator import (
    ColumnDenominatorError,
    ColumnDenominatorLeafIdentity,
    ColumnExpectedLeaf,
    ColumnLeafApplicability,
    ColumnLeafOutcome,
    ColumnLeafOutcomeStatus,
    SupportedColumnDenominator,
    canonical_column_leaf_source_ref,
    compose_supported_column_denominator,
)
from tbdy_engine.coverage.project_reconciliation import (
    ActionBindingRef,
    AnalysisBasisRef,
    ProjectCoverageReconciliation,
    ProjectCoverageReconciler,
    ProjectReconciliationError,
    ReportBindingIdentityBlocked,
    ReportBindingRef,
    ReportContributionRef,
    canonical_closure_report_source_ref,
    canonical_quantity_report_source_ref,
)

__all__ = [
    "ActionBindingRef",
    "ColumnDenominatorError",
    "ColumnDenominatorLeafIdentity",
    "ColumnExpectedLeaf",
    "ColumnLeafApplicability",
    "ColumnLeafOutcome",
    "ColumnLeafOutcomeStatus",
    "SupportedColumnDenominator",
    "canonical_column_leaf_source_ref",
    "compose_supported_column_denominator",
    "AnalysisBasisRef",
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
    "ProjectCoverageReconciliation",
    "ProjectCoverageReconciler",
    "ProjectReconciliationError",
    "ReportBindingIdentityBlocked",
    "ReportBindingRef",
    "ReportContributionRef",
    "canonical_closure_report_source_ref",
    "canonical_quantity_report_source_ref",
]
