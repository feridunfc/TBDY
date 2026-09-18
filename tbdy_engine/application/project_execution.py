"""Sole public project application root for the supported Column vertical.

``execute_project`` owns lifecycle/composition only. Runtime capability and
reviewed engineering-basis objects are keyword dependencies, not project/request
truth. The request DTO therefore remains application intent while the same
public lifecycle may continue from qualified FND2/B6 into existing downstream
Column authorities.
"""
from __future__ import annotations

from dataclasses import dataclass

from tbdy_engine.application.column_design_basis import ReviewedColumnDesignBasis
from tbdy_engine.application.column_final_cage import ReviewedColumnFinalCageContext
from tbdy_engine.application.column_p7_runtime import ReviewedColumnP7RuntimeContext
from tbdy_engine.application.column_vc_runtime import ReviewedColumnVcRuntimeContext
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
from tbdy_engine.features.column_concrete_design_evidence import ExpectedConcreteDesignComboPolicy
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
from tbdy_engine.regulatory.vs5_column_axial_program import ReviewedVs5ColumnAxialContext


class ProjectExecutionContractError(ValueError):
    """Raised when project composition cannot preserve canonical identity."""


@dataclass(frozen=True, slots=True)
class ProjectExecutionArtifact:
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
    evidence_refs: list[str] = []
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
        evidence_refs.extend(readiness.source_refs)

    if column.design_result_identity is not None:
        fields.append(
            ReportField(
                key="design_result_identity",
                label="Controlled B6 design result",
                value=column.design_result_identity.identity_ref,
                role="IDENTITY",
            )
        )
        evidence_refs.append(column.design_result_identity.identity_ref)
    if column.longitudinal_selection is not None:
        fields.append(
            ReportField(
                key="longitudinal_selection_status",
                label="Canonical longitudinal selection",
                value=column.longitudinal_selection.status,
                role="STATUS",
            )
        )
        if column.selected_rebar is not None:
            fields.append(
                ReportField(
                    key="selected_rebar_ref",
                    label="ENGINE_SELECTED_REBAR",
                    value=column.selected_rebar.selected_rebar_ref,
                    role="IDENTITY",
                )
            )
            evidence_refs.append(column.selected_rebar.selected_rebar_ref)
            material_context_ref = getattr(column.selected_rebar, "material_context_ref", None)
            if material_context_ref:
                evidence_refs.append(material_context_ref)
    if column.transverse_confinement is not None:
        fields.append(
            ReportField(
                key="transverse_confinement_complete",
                label="Column transverse/confinement accounting",
                value=column.transverse_confinement.complete,
                role="STATUS",
            )
        )
        evidence_refs.extend(column.transverse_confinement.source_refs)

    return SliceReportContribution(
        slice_id=f"product-spine-col-1:readiness:{column.component_id}",
        title="Column product vertical",
        contribution_kind="REGULATORY",
        status=_report_status(column),
        component_type="COLUMN",
        component_id=column.component_id,
        summary_fields=tuple(fields),
        evidence_refs=tuple(dict.fromkeys(evidence_refs)),
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
    column_design_basis: ReviewedColumnDesignBasis | None = None,
    expected_combo_policy: ExpectedConcreteDesignComboPolicy | None = None,
    reviewed_vs5_column_axial_context: ReviewedVs5ColumnAxialContext | None = None,
    reviewed_column_p7_context: ReviewedColumnP7RuntimeContext | None = None,
    reviewed_column_final_cage_context: ReviewedColumnFinalCageContext | None = None,
    reviewed_column_vc_context: ReviewedColumnVcRuntimeContext | None = None,
) -> ProjectExecutionArtifact:
    """Execute the sole LIVE project lifecycle; downstream success remains FND2-gated."""
    if not isinstance(request, ProjectExecutionRequest):
        raise TypeError("request must be ProjectExecutionRequest")
    if not isinstance(verified_session, EtabsVerifiedSession):
        raise TypeError("verified_session must be EtabsVerifiedSession")
    if column_design_basis is not None and not isinstance(column_design_basis, ReviewedColumnDesignBasis):
        raise TypeError("column_design_basis must be ReviewedColumnDesignBasis or None")
    if expected_combo_policy is not None and not isinstance(expected_combo_policy, ExpectedConcreteDesignComboPolicy):
        raise TypeError("expected_combo_policy must be ExpectedConcreteDesignComboPolicy or None")
    if (
        reviewed_vs5_column_axial_context is not None
        and not isinstance(
            reviewed_vs5_column_axial_context,
            ReviewedVs5ColumnAxialContext,
        )
    ):
        raise TypeError(
            "reviewed_vs5_column_axial_context must be "
            "ReviewedVs5ColumnAxialContext or None"
        )

    if (
        reviewed_column_p7_context is not None
        and not isinstance(
            reviewed_column_p7_context,
            ReviewedColumnP7RuntimeContext,
        )
    ):
        raise TypeError(
            "reviewed_column_p7_context must be "
            "ReviewedColumnP7RuntimeContext or None"
        )
    if (
        reviewed_column_final_cage_context is not None
        and not isinstance(
            reviewed_column_final_cage_context,
            ReviewedColumnFinalCageContext,
        )
    ):
        raise TypeError(
            "reviewed_column_final_cage_context must be "
            "ReviewedColumnFinalCageContext or None"
        )

    if (
        reviewed_column_vc_context is not None
        and not isinstance(
            reviewed_column_vc_context,
            ReviewedColumnVcRuntimeContext,
        )
    ):
        raise TypeError(
            "reviewed_column_vc_context must be "
            "ReviewedColumnVcRuntimeContext or None"
        )

    context: TrustedLiveAcquisitionContext = create_trusted_live_acquisition_context(verified_session)

    column_kwargs = {
        "acquisition_context": context,
        "column_design_basis": column_design_basis,
        "expected_combo_policy": expected_combo_policy,
    }
    if reviewed_vs5_column_axial_context is not None:
        column_kwargs["reviewed_vs5_column_axial_context"] = (
            reviewed_vs5_column_axial_context
        )
    if reviewed_column_p7_context is not None:
        column_kwargs["reviewed_column_p7_context"] = reviewed_column_p7_context
    if reviewed_column_final_cage_context is not None:
        column_kwargs["reviewed_column_final_cage_context"] = (
            reviewed_column_final_cage_context
        )
    if reviewed_column_vc_context is not None:
        column_kwargs["reviewed_column_vc_context"] = (
            reviewed_column_vc_context
        )

    column = execute_column_domain(
        request.column,
        **column_kwargs,
    )

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
