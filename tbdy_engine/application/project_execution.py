"""First supported project application root for PRODUCT-SPINE-COL-1.

``execute_project`` owns lifecycle/composition only.  Runtime capability is a
keyword dependency, not user/project intent.  A1 does not run ETABS analysis or
design and, because current-main lacks a qualified LIVE FND-COL-2 input builder,
truthfully stops before FND-COL-2X.
"""
from __future__ import annotations

from dataclasses import dataclass

from tbdy_engine.application.column_execution import ColumnDomainArtifact, execute_column_domain
from tbdy_engine.application.contracts import ProjectExecutionRequest
from tbdy_engine.coverage.project_reconciliation import (
    AnalysisBasisRef,
    ProjectCoverageReconciliation,
    ProjectCoverageReconciler,
    ReportBindingRef,
    ReportContributionRef,
    canonical_closure_report_source_ref,
    canonical_quantity_report_source_ref,
)
from tbdy_engine.etabs.safety import EtabsVerifiedSession
from tbdy_engine.integration.live_etabs_acquisition_context import (
    TrustedLiveAcquisitionContext,
    create_trusted_live_acquisition_context,
)
from tbdy_engine.product_reports.slice_report_contribution import ReportField, SliceReportContribution
from tbdy_engine.product_reports.unified_building_report import (
    BuildingReportModel,
    ProjectBasisEntry,
    ProjectBasisLedger,
    ReportSourceKind,
    SourceManifest,
    SourceManifestEntry,
)
from tbdy_engine.regulatory.fnd_col_2 import READINESS_KEY
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus, StructuralAssessment


class ProjectExecutionContractError(ValueError):
    """Raised when project composition cannot preserve canonical identity."""


@dataclass(frozen=True, slots=True)
class ProjectExecutionArtifact:
    """Bounded application result; absence of FCR/report means no rule execution occurred."""

    project_id: str
    report_id: str
    status: str
    acquisition_context_ref: str
    column: ColumnDomainArtifact
    structural_assessment: StructuralAssessment | None = None
    reconciliation: ProjectCoverageReconciliation | None = None
    building_report_model: BuildingReportModel | None = None


def _report_status(column: ColumnDomainArtifact) -> str:
    if column.fnd_col_2_execution is None or column.fnd_col_2_execution.readiness is None:
        return "BLOCKED"
    readiness = column.fnd_col_2_execution.readiness
    return {
        "READY": "PROVEN",
        "REANALYSIS_REQUIRED": "REANALYSIS_REQUIRED",
        "BLOCKED": "BLOCKED",
        "UNRESOLVED": "NOT_EVALUATED",
    }.get(readiness.status, "NOT_EVALUATED")


def _report_contribution(column: ColumnDomainArtifact) -> SliceReportContribution:
    if column.fnd_col_2_execution is None:
        raise ProjectExecutionContractError("report contribution requires canonical FND-COL-2 execution")
    readiness = column.fnd_col_2_execution.readiness
    fields = [
        ReportField(
            key="application_status",
            label="Column application status",
            value=column.status,
            role="STATUS",
        )
    ]
    evidence_refs: tuple[str, ...] = ()
    if readiness is not None:
        fields.extend(
            (
                ReportField(
                    key="design_readiness_status",
                    label="FND-COL-2 design readiness",
                    value=readiness.status,
                    role="STATUS",
                ),
                ReportField(
                    key="second_order_treatment",
                    label="Second-order treatment",
                    value=readiness.second_order_treatment,
                    role="STATUS",
                ),
            )
        )
        evidence_refs = tuple(readiness.source_refs)
    return SliceReportContribution(
        slice_id=f"product-spine-col-1:readiness:{column.component_id}",
        title="Column design readiness",
        contribution_kind="REGULATORY",
        status=_report_status(column),
        component_type="COLUMN",
        component_id=column.component_id,
        summary_fields=tuple(fields),
        evidence_refs=evidence_refs,
        warnings=tuple(column.blockers),
    )


def _report_binding(
    column: ColumnDomainArtifact,
    contribution: SliceReportContribution,
) -> ReportBindingRef:
    if column.fnd_col_2_program is None or column.fnd_col_2_execution is None:
        raise ProjectExecutionContractError("report binding requires canonical FND-COL-2 artifacts")
    inventory = tuple(column.fnd_col_2_program.plan.compiled_closure_inventory)
    if len(inventory) != 1:
        raise ProjectExecutionContractError(
            "PRODUCT-SPINE-COL-1 expects exactly one FND-COL-2 closure instance"
        )
    instance_id = inventory[0].instance_id
    if column.fnd_col_2_execution.readiness is None:
        source_ref = canonical_closure_report_source_ref(instance_id)
    else:
        source_ref = canonical_quantity_report_source_ref(instance_id, READINESS_KEY)
    return ReportBindingRef(source_ref, ReportContributionRef.from_contribution(contribution))


def _analysis_basis_refs(column: ColumnDomainArtifact) -> tuple[AnalysisBasisRef, ...]:
    if column.fnd_col_2_execution is None or column.fnd_col_2_execution.readiness is None:
        return ()
    readiness = column.fnd_col_2_execution.readiness
    try:
        status = AnalysisBasisStatus(readiness.analysis_basis_status)
    except ValueError as exc:
        raise ProjectExecutionContractError(
            "FND-COL-2 emitted an unknown canonical analysis-basis status"
        ) from exc
    record = column.fnd_col_2_execution.readiness_records[0]
    if column.readiness_binding is None:
        raise ProjectExecutionContractError("typed readiness is missing its application binding")
    return (
        AnalysisBasisRef(
            instance_id=record.readiness_instance_ref,
            status=status,
            source_ref=column.readiness_binding.readiness_ref,
        ),
    )


def _build_closure_and_report(
    request: ProjectExecutionRequest,
    column: ColumnDomainArtifact,
    *,
    source_id: str,
    source_kind: ReportSourceKind,
    source_title: str,
    source_locator: str | None,
    execution_mode_label: str,
) -> tuple[StructuralAssessment, ProjectCoverageReconciliation, BuildingReportModel]:
    """Reuse existing Assessment/FCR/BuildingReportModel without engineering reinterpretation."""
    if column.fnd_col_2_program is None or column.fnd_col_2_execution is None:
        raise ProjectExecutionContractError("canonical closure requires FND-COL-2 program/execution")
    contribution = _report_contribution(column)
    binding = _report_binding(column, contribution)
    reconciliation = ProjectCoverageReconciler.reconcile(
        compiled_program=column.fnd_col_2_program,
        store_snapshot=column.fnd_col_2_execution.snapshot,
        report_contributions=(contribution,),
        required_report_source_refs=(binding.source_ref,),
        report_bindings=(binding,),
        analysis_basis_refs=_analysis_basis_refs(column),
    )
    basis = ProjectBasisLedger(
        (
            ProjectBasisEntry(
                key="execution_mode",
                label="Execution mode",
                value=execution_mode_label,
                source_ids=(source_id,),
            ),
            ProjectBasisEntry(
                key="model_fingerprint",
                label="Source model fingerprint",
                value=column.model_fingerprint,
                source_ids=(source_id,),
            ),
            ProjectBasisEntry(
                key="evidence_epoch_id",
                label="Factual acquisition epoch",
                value=column.evidence_epoch_id,
                source_ids=(source_id,),
            ),
        )
    )
    manifest = SourceManifest(
        (
            SourceManifestEntry(
                source_id=source_id,
                source_kind=source_kind,
                title=source_title,
                fingerprint=column.model_fingerprint,
                locator=source_locator,
            ),
        )
    )
    model = BuildingReportModel(
        report_id=request.report_id,
        project_id=request.project_id,
        title=request.title,
        reconciliation=reconciliation,
        project_basis=basis,
        source_manifest=manifest,
        contributions=(contribution,),
        report_bindings=(binding,),
    )
    return reconciliation.structural_assessment, reconciliation, model


def _complete_project_from_canonical_column(
    request: ProjectExecutionRequest,
    column: ColumnDomainArtifact,
    *,
    acquisition_context_ref: str,
    source_id: str,
    source_kind: ReportSourceKind,
    source_title: str,
    source_locator: str | None,
    execution_mode_label: str,
) -> ProjectExecutionArtifact:
    assessment, reconciliation, report = _build_closure_and_report(
        request,
        column,
        source_id=source_id,
        source_kind=source_kind,
        source_title=source_title,
        source_locator=source_locator,
        execution_mode_label=execution_mode_label,
    )
    return ProjectExecutionArtifact(
        project_id=request.project_id,
        report_id=request.report_id,
        status=column.status,
        acquisition_context_ref=acquisition_context_ref,
        column=column,
        structural_assessment=assessment,
        reconciliation=reconciliation,
        building_report_model=report,
    )


def execute_project(
    request: ProjectExecutionRequest,
    *,
    verified_session: EtabsVerifiedSession,
) -> ProjectExecutionArtifact:
    """Execute the legal LIVE A1 product boundary with one trusted acquisition generation."""
    if not isinstance(request, ProjectExecutionRequest):
        raise TypeError("request must be ProjectExecutionRequest")
    if not isinstance(verified_session, EtabsVerifiedSession):
        raise TypeError("verified_session must be EtabsVerifiedSession")
    context: TrustedLiveAcquisitionContext = create_trusted_live_acquisition_context(verified_session)
    column = execute_column_domain(request.column, acquisition_context=context)

    # A1 current-main has no legally-qualified FND-COL-2 compile-input builder.
    # Therefore no Assessment/FCR/report claim is created from this application blocker.
    if column.fnd_col_2_execution is None:
        return ProjectExecutionArtifact(
            project_id=request.project_id,
            report_id=request.report_id,
            status=column.status,
            acquisition_context_ref=context.acquisition_context_ref,
            column=column,
        )

    return _complete_project_from_canonical_column(
        request,
        column,
        acquisition_context_ref=context.acquisition_context_ref,
        source_id=context.source_model_identity.source_model_ref,
        source_kind=ReportSourceKind.ETABS_MODEL,
        source_title="Verified ETABS source model",
        source_locator=context.source_model_identity.normalized_model_reference,
        execution_mode_label="LIVE",
    )


__all__ = ["ProjectExecutionArtifact", "ProjectExecutionContractError", "execute_project"]
