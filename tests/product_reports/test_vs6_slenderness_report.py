from tbdy_engine.design.columns.slenderness import (
    ColumnSlendernessAxisBasis,
    ColumnSlendernessBasis,
    SWAY_PREVENTED,
    evaluate_ts500_column_slenderness,
)
from tbdy_engine.product_reports.vs6_slenderness_report import build_vs6_slenderness_report


COMP = "+0.00:C2:236"


def _axis(axis):
    return ColumnSlendernessAxisBasis(
        axis=axis,
        section_dimension_mm=800.0,
        free_length_ln_mm=3000.0,
        effective_length_factor_k=1.0,
        sway_classification=SWAY_PREVENTED,
        moment_ratio_m1_over_m2=0.0,
        source_refs=(f"fixture:{axis}",),
    )


def test_slenderness_report_projects_canonical_result_without_recalculation():
    result = evaluate_ts500_column_slenderness(
        component_id=COMP,
        basis=ColumnSlendernessBasis(
            component_id=COMP,
            m2=_axis("M2"),
            m3=_axis("M3"),
            source_refs=("fixture:basis",),
        ),
    )
    report = build_vs6_slenderness_report(result)
    assert report.slice_id == "VS6-P6-TS500-COLUMN-SLENDERNESS"
    assert report.status == "PROVEN"
    assert report.component_id == COMP
    payload = report.as_dict()
    assert payload["presentation_contract"]["engineering_recalculation_allowed"] is False
    assert payload["presentation_contract"]["renderer_may_change_status"] is False
    assert payload["presentation_contract"]["renderer_may_change_governing_selection"] is False
    assert len(payload["detail_tables"][0]["rows"]) == 2


def test_blocked_basis_reports_truthfully_as_blocked():
    result = evaluate_ts500_column_slenderness(component_id=COMP, basis=None)
    report = build_vs6_slenderness_report(result)
    assert report.status == "BLOCKED"
    assert report.warnings
