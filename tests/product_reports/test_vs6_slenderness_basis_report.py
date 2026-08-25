from tbdy_engine.design.columns.slenderness import SWAY_PREVENTED
from tbdy_engine.design.columns.slenderness_basis import (
    ColumnSlendernessAxisEvidence,
    ColumnSlendernessEvidence,
    REGULATORY_FREE_LENGTH_AUTHORITY,
    SWAY_CLASSIFICATION_AUTHORITY,
    resolve_ts500_column_slenderness_basis,
)
from tbdy_engine.product_reports.vs6_slenderness_basis_report import (
    build_vs6_slenderness_basis_report,
)


COMP = "+0.00:C2:236"


def _axis(axis):
    return ColumnSlendernessAxisEvidence(
        axis=axis,
        section_dimension_mm=800.0,
        regulatory_free_length_ln_mm=3000.0,
        regulatory_free_length_source_ref=f"reviewed:{axis}:ln",
        regulatory_free_length_authority=REGULATORY_FREE_LENGTH_AUTHORITY,
        sway_classification=SWAY_PREVENTED,
        sway_source_ref=f"reviewed:{axis}:sway",
        sway_authority=SWAY_CLASSIFICATION_AUTHORITY,
    )


def test_report_projects_basis_resolution_without_recalculation():
    result = resolve_ts500_column_slenderness_basis(
        ColumnSlendernessEvidence(
            component_id=COMP,
            m2=_axis("M2"),
            m3=_axis("M3"),
            source_refs=("fixture:basis",),
        ),
        component_id=COMP,
    )
    report = build_vs6_slenderness_basis_report(result)
    assert report.slice_id == "VS6-P6-TS500-SLENDERNESS-BASIS"
    assert report.status == "PROVEN"
    payload = report.as_dict()
    assert payload["presentation_contract"]["engineering_recalculation_allowed"] is False
    assert payload["presentation_contract"]["renderer_may_change_status"] is False
    assert payload["presentation_contract"]["renderer_may_change_governing_selection"] is False


def test_missing_evidence_projects_blocked_not_fail():
    result = resolve_ts500_column_slenderness_basis(None, component_id=COMP)
    report = build_vs6_slenderness_basis_report(result)
    assert report.status == "BLOCKED"
    assert "MISSING_SLENDERNESS_EVIDENCE" in report.warnings
