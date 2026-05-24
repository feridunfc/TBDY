
from tools.run_genesis_final_v1 import build_summary, format_summary

def test_format_summary_contains_expected_sections(tmp_path, monkeypatch):
    steps = [
        {"script": "tools/run_final_engine_report_v1.py", "args": [], "returncode": 0, "ok": True},
        {"script": "tools/apply_provenance_fields_v1.py", "args": [], "returncode": 0, "ok": True},
    ]
    summary = {
        "ok": True,
        "final_report": {
            "total_checks": 4791,
            "column_confinement_FAIL": 0,
            "column_confinement_WARNING": 262,
            "scwb_resolver_rows": 846,
            "source_empty": 0,
            "not_evaluated": 0,
        },
        "provenance": {
            "source_table_count": 4791,
            "source_field_count": 4791,
            "raw_combo_count": 3868,
            "governing_combo_count": 3868,
            "raw_unit_count": 4788,
            "canonical_unit_count": 4788,
            "display_unit_count": 4788,
            "combo_provenance_level": {"required_family_only": 3868},
        },
        "combo_alias": {
            "rows_resolved": 3868,
            "rows_fallback_marker": 3868,
            "rows_mismatch": 0,
            "resolved_by": {"required_family_fallback": 3868},
            "resolved_family": {"S_E": 2948, "K_E": 920},
        },
        "input_audit_v1_1": {
            "combo_audit_source": "combo_alias_summary_v1",
            "unique_raw_combo_count": 2,
            "mapped_unique": 2,
            "unmapped_unique": 0,
            "fallback_unique": 2,
            "actual_unique": 0,
            "rows_resolved": 3868,
            "rows_fallback_marker": 3868,
            "rows_mismatch": 0,
            "governing_combo_count": 3868,
            "raw_units_seen": ["kN"],
            "canonical_units_seen": ["kN"],
            "display_units_seen": ["kN"],
        },
    }
    text = format_summary(summary, steps)
    assert "GENESIS CONSOLIDATED FINAL RUNNER V1" in text
    assert "column_confinement_FAIL: 0" in text
    assert "rows_mismatch: 0" in text
    assert "Actual ETABS Governing Combo Extraction v1" in text
