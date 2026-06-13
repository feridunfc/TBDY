import pytest

from tbdy_engine.coverage import (
    CoverageDiagnostic,
    CoverageDiagnosticCode,
    CoverageDiagnosticSeverity,
    CoverageEvidenceStatus,
    CoverageMatrix,
    CoverageExpectedSource,
    CoverageMissingFeature,
    CoveragePolicyStatus,
    CoverageRow,
    CoverageStatus,
    ExpectedSourceKind,
)


def test_coverage_row_required_fields_and_blocked_reason():
    row = CoverageRow(
        check_id="beam_geometry_min_width",
        component_type="beam",
        component_id="B1",
        required_features=["beam_width_mm"],
        missing_features=[CoverageMissingFeature("beam_width_mm", "not resolved")],
        combo_policy_status=CoveragePolicyStatus.NOT_APPLICABLE,
        section_state_status=CoveragePolicyStatus.NOT_APPLICABLE,
        ductility_context_status=CoveragePolicyStatus.RESOLVED,
        evidence_status=CoverageEvidenceStatus.MISSING,
        coverage_status=CoverageStatus.BLOCKED,
        reason="missing feature",
        missing_feature_sources={
            "beam_width_mm": CoverageExpectedSource(
                source_kind=ExpectedSourceKind.ETABS_TABLE,
                feature_name="beam_width_mm",
                table_key="frame_section_properties",
                table_aliases=["Frame Section Property Definitions - Concrete Rectangular"],
                field_aliases=["Width"],
                combo_family="NONE",
                aggregation="none",
                unit="mm",
                expected_evidence_fields=["source_table", "source_column"],
            )
        },
    )
    assert row.coverage_status == CoverageStatus.BLOCKED
    assert row.missing_features[0].feature_name == "beam_width_mm"


def test_coverage_row_cannot_contain_check_result_or_decision_status():
    with pytest.raises(ValueError):
        CoverageRow(
            check_id="beam_geometry_min_width",
            component_type="beam",
            component_id="B1",
            required_features=["beam_width_mm"],
            resolved_features=["beam_width_mm"],
            coverage_status=CoverageStatus.RUNNABLE,
            reason="CheckResult payload",
        )
    with pytest.raises(ValueError):
        CoverageRow(
            check_id="beam_geometry_min_width",
            component_type="beam",
            component_id="B1",
            required_features=["beam_width_mm"],
            resolved_features=["beam_width_mm"],
            coverage_status=CoverageStatus.RUNNABLE,
            reason="'OK'",
        )


def test_coverage_matrix_is_not_check_result_and_has_diagnostics():
    diagnostic = CoverageDiagnostic(
        severity=CoverageDiagnosticSeverity.INFO,
        code=CoverageDiagnosticCode.CONTRACT_ALIGNMENT_MISSING,
        message="alignment note",
    )
    row = CoverageRow(
        check_id="beam_geometry_min_width",
        component_type="beam",
        component_id="B1",
        required_features=["beam_width_mm"],
        resolved_features=["beam_width_mm"],
        coverage_status=CoverageStatus.RUNNABLE,
    )
    matrix = CoverageMatrix(rows=[row], diagnostics=[diagnostic])
    payload = matrix.as_dict()
    text = repr(payload)
    assert "CheckResult" not in text
    assert "'OK'" not in text
    assert "'FAIL'" not in text
    assert payload["diagnostics"][0]["code"] == "CONTRACT_ALIGNMENT_MISSING"
