
from tools.enrich_engine_report_v1_2 import enrich_report

def test_report_enrichment_v1_2_fills_source_level_and_reason():
    report = {
        "report_metadata": {"schema": "engine_report.v1.1"},
        "summary": {"error": 0},
        "checks": [
            {
                "check_id": "column_capacity_hierarchy",
                "status": "WARNING",
                "message": "SCWB approximate result; reason_code=approximate_capacity; source=scwb_resolver",
                "evaluation_level": "NOT_EVALUATED",
                "source": "",
                "category": "DESIGN_SCWB",
            },
            {
                "check_id": "beam_ductility",
                "status": "WARNING",
                "message": "Ductility/detailing requires final provided beam rebar schedule.",
                "evaluation_level": "NOT_EVALUATED",
                "source": "",
                "category": "DESIGN_BEAM",
            },
        ],
    }

    enriched = enrich_report(report)
    rows = enriched["checks"]

    assert rows[0]["source"] == "scwb_resolver"
    assert rows[0]["evaluation_level"] == "APPROXIMATE"
    assert rows[0]["reason_code"] == "approximate_capacity"

    assert rows[1]["source"] == "etabs"
    assert rows[1]["evaluation_level"] == "SCREENING"
    assert rows[1]["reason_code"] == "requires_final_rebar_schedule"

    assert enriched["report_metadata"]["schema"] == "engine_report.v1.2"
    assert enriched["enrichment_summary"]["source_empty_after"] == 0
    assert enriched["enrichment_summary"]["not_evaluated_after"] == 0
