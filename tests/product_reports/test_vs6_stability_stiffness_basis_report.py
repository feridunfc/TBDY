from tbdy_engine.design.columns.stability_stiffness_basis import (
    AssignedFrameBendingModifierEvidence,
    STATUS_REANALYSIS_REQUIRED,
    assess_ts500_eq713_stiffness_basis,
)
from tbdy_engine.product_reports.vs6_stability_stiffness_basis_report import (
    build_vs6_stability_stiffness_basis_report,
)


def test_stiffness_basis_report_projects_reanalysis_without_recalculation():
    resolution = assess_ts500_eq713_stiffness_basis(
        (
            AssignedFrameBendingModifierEvidence(
                section_name="Column_80x80",
                member_kind="COLUMN",
                i2_modifier=0.7,
                i3_modifier=0.7,
                source_refs=("ETABS:Column_80x80:I2Mod/I3Mod",),
            ),
            AssignedFrameBendingModifierEvidence(
                section_name="B60x70",
                member_kind="BEAM",
                i2_modifier=0.35,
                i3_modifier=0.35,
                source_refs=("ETABS:B60x70:I2Mod/I3Mod",),
            ),
        )
    )
    report = build_vs6_stability_stiffness_basis_report(
        resolution,
        component_id="+0.00:C2:236",
    )

    assert resolution.status == STATUS_REANALYSIS_REQUIRED
    assert report.slice_id == "VS6-P6-TS500-STABILITY-STIFFNESS-BASIS"
    assert report.status == "REANALYSIS_REQUIRED"
    assert report.component_id == "+0.00:C2:236"
    assert len(report.tables) == 1
    assert len(report.tables[0].rows) == 2

    projected = report.as_dict()
    fields = {item["key"]: item["value"] for item in projected["summary_fields"]}
    assert fields["source_status"] == STATUS_REANALYSIS_REQUIRED
    assert fields["reanalysis_required"] is True
    assert fields["nonunit_section_count"] == 2
    assert projected["presentation_contract"]["engineering_recalculation_allowed"] is False
    assert projected["presentation_contract"]["renderer_may_change_status"] is False
    assert projected["presentation_contract"]["renderer_may_change_governing_selection"] is False
