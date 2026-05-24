from tools.run_final_engine_report_v1 import build_final_report

def test_final_report_pipeline_applies_enrichment_and_confinement_policy():
    raw = {
        "report_metadata": {"schema": "engine_report.v1.1", "runtime_bridge": "Genesis Runtime Bridge v1.1"},
        "summary": {"error": 0},
        "checks": [
            {
                "check_id": "column_confinement",
                "element_label": "C1",
                "status": "FAIL",
                "evaluation_level": "ETABS_DESIGN_RESULT",
                "source": "etabs_design_summary.",
                "message": "Confinement FAIL: Ash=236mm2 < required=567mm2. provided=Phi10@150mm, legs=3/3, source=etabs_design_summary. Proposal: use at least 12 legs Phi8",
                "category": "DESIGN_COLUMN",
            },
            {
                "check_id": "column_geometry",
                "element_label": "C1",
                "status": "OK",
                "evaluation_level": "NOT_EVALUATED",
                "source": "",
                "message": "geometry ok",
                "category": "GEOMETRY",
            },
            {
                "check_id": "beam_capacity_hierarchy",
                "element_label": "J1",
                "status": "WARNING",
                "evaluation_level": "APPROXIMATE",
                "source": "scwb_resolver",
                "reason_code": "approximate_capacity",
                "message": "SCWB beam projection; source=scwb_resolver; reason_code=approximate_capacity",
                "category": "HIERARCHY",
            },
        ],
    }
    final = build_final_report(raw)
    rows = final["checks"]
    conf = [r for r in rows if r["check_id"] == "column_confinement"][0]
    geom = [r for r in rows if r["check_id"] == "column_geometry"][0]
    assert final["report_metadata"]["schema"] == "final_engine_report.v1"
    assert conf["status"] == "WARNING"
    assert conf["reason_code"] == "non_final_confinement_proposal"
    assert conf["Ash_required"] == 567
    assert geom["source"] == "geometry_context"
    assert geom["evaluation_level"] == "DESIGN_LEVEL"
    assert final["final_summary"]["column_confinement_FAIL"] == 0
    assert final["final_summary"]["source_empty"] == 0
    assert final["final_summary"]["scwb_resolver_rows"] == 1
