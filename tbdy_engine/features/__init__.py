"""FeatureSnapshot foundation exports for C4/C13 proof layers."""
from tbdy_engine.features.check_preflight_diagnostics import build_check_preflight_diagnostic_report
from tbdy_engine.features.diagnostics import FeatureDiagnostic, FeatureDiagnosticCode, FeatureDiagnosticSeverity
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.feature_snapshot_artifact_validator import (
    scan_for_forbidden_engineering_verdicts,
    validate_artifact_file_set,
    validate_check_preflight_diagnostic_report,
    validate_feature_snapshot_artifact_manifest,
    validate_feature_snapshot_report_payload,
)
from tbdy_engine.features.feature_snapshot_artifacts import (
    build_feature_snapshot_artifact_manifest,
    build_feature_snapshot_report_payload,
    render_feature_snapshot_html_report,
    render_feature_snapshot_markdown_report,
)
from tbdy_engine.features.gateway_check_input_preflight import (
    CheckInputFeatureRequirement,
    CheckInputPreflightAssessment,
    CheckInputPreflightSpec,
    CheckInputReadiness,
    FeatureRequirementAssessment,
    FeatureRequirementState,
    evaluate_check_input_preflight,
    evaluate_check_input_preflights,
)
from tbdy_engine.features.readiness import FeatureProofStatus, ReadinessStatus
from tbdy_engine.features.resolver_feature_snapshot import (
    build_c13_3_p1_feature_snapshot,
    build_feature_snapshot_from_source_rows,
    source_family_projection_report,
)
from tbdy_engine.features.semantic_source_review import (
    build_combo_semantic_review,
    build_design_output_semantic_review,
    build_drift_story_semantic_review,
    build_force_result_semantic_review,
    build_rebar_role_semantic_review,
    build_semantic_source_review_report,
    classify_semantic_source_table,
    scan_semantic_outputs_for_forbidden_verdicts,
)
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.source_feature_snapshot_builder import build_c13_3_p0_feature_snapshot
from tbdy_engine.features.unit_metadata import UnitNormalization, normalize_value
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus

__all__ = [
    "FeatureDiagnostic",
    "FeatureDiagnosticCode",
    "FeatureDiagnosticSeverity",
    "FeatureEvidence",
    "FeatureEvidenceStatus",
    "CheckInputFeatureRequirement",
    "CheckInputPreflightAssessment",
    "CheckInputPreflightSpec",
    "CheckInputReadiness",
    "FeatureRequirementAssessment",
    "FeatureRequirementState",
    "FeatureProofStatus",
    "FeatureSnapshot",
    "FeatureValue",
    "FeatureValueStatus",
    "ReadinessStatus",
    "UnitNormalization",
    "evaluate_check_input_preflight",
    "evaluate_check_input_preflights",
    "build_c13_3_p0_feature_snapshot",
    "build_c13_3_p1_feature_snapshot",
    "build_check_preflight_diagnostic_report",
    "build_combo_semantic_review",
    "build_design_output_semantic_review",
    "build_drift_story_semantic_review",
    "build_feature_snapshot_artifact_manifest",
    "build_feature_snapshot_from_source_rows",
    "build_feature_snapshot_report_payload",
    "build_force_result_semantic_review",
    "build_rebar_role_semantic_review",
    "build_semantic_source_review_report",
    "classify_semantic_source_table",
    "normalize_value",
    "render_feature_snapshot_html_report",
    "render_feature_snapshot_markdown_report",
    "scan_for_forbidden_engineering_verdicts",
    "scan_semantic_outputs_for_forbidden_verdicts",
    "source_family_projection_report",
    "validate_artifact_file_set",
    "validate_check_preflight_diagnostic_report",
    "validate_feature_snapshot_artifact_manifest",
    "validate_feature_snapshot_report_payload",
]
