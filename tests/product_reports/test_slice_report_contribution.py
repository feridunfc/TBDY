import pytest

from tbdy_engine.product_reports.slice_report_contribution import (
    ReportCalculation,
    ReportField,
    ReportTable,
    SliceReportContribution,
    SliceReportContributionError,
)


def test_slice_report_contribution_serializes_without_engineering_authority():
    contribution = SliceReportContribution(
        slice_id="EXAMPLE",
        title="Example Slice",
        contribution_kind="CHECK",
        status="PASS",
        component_type="COLUMN",
        component_id="L1:C1:1",
        summary_fields=(
            ReportField("ratio", "Utilization", 0.72, role="RESULT"),
        ),
        calculations=(
            ReportCalculation(
                calculation_id="already_resolved_capacity",
                title="Already-resolved capacity projection",
                formula="R = supplied_result",
                inputs=(ReportField("input", "Input", 1.0, role="INPUT"),),
                outputs=(ReportField("result", "Result", 2.0, role="RESULT"),),
                authority_refs=("CODE:CLAUSE",),
                evidence_refs=("EVIDENCE:ROW",),
                governing_ref="CASE:1",
            ),
        ),
    )

    payload = contribution.as_dict()
    assert payload["schema_version"] == "slice_report_contribution.v1"
    assert payload["presentation_contract"] == {
        "engineering_recalculation_allowed": False,
        "renderer_may_change_status": False,
        "renderer_may_change_governing_selection": False,
    }
    assert payload["status"] == "PASS"
    assert payload["calculations"][0]["authority_refs"] == ["CODE:CLAUSE"]


def test_report_table_rejects_undeclared_columns():
    with pytest.raises(SliceReportContributionError, match="undeclared columns"):
        ReportTable(
            table_id="t",
            title="T",
            columns=("a",),
            rows=({"a": 1, "b": 2},),
        )


def test_report_contract_rejects_nonfinite_values():
    with pytest.raises(SliceReportContributionError, match="must be finite"):
        ReportField("ratio", "Ratio", float("nan"))


def test_renderer_views_are_explicit_and_unique():
    with pytest.raises(SliceReportContributionError, match="render_views"):
        SliceReportContribution(
            slice_id="EXAMPLE",
            title="Example",
            contribution_kind="FACTUAL",
            status="PROVEN",
            render_views=("ENGINEERING", "ENGINEERING"),
        )
