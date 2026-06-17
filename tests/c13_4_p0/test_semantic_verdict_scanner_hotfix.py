from __future__ import annotations

from tbdy_engine.features.semantic_source_review import (
    FORBIDDEN_ENGINEERING_VERDICT_TERMS,
    build_semantic_source_review_report,
    classify_semantic_source_table,
    scan_semantic_outputs_for_forbidden_verdicts,
)


def _term_a() -> str:
    return FORBIDDEN_ENGINEERING_VERDICT_TERMS[0]


def _term_b() -> str:
    return FORBIDDEN_ENGINEERING_VERDICT_TERMS[1]


def _term_c() -> str:
    return FORBIDDEN_ENGINEERING_VERDICT_TERMS[-1]


def _raw_item():
    return classify_semantic_source_table(
        source_family="frame_forces",
        table_name="Element Forces - Beams",
        fetch_status="FETCHED",
        columns=["Story", "Frame", "UniqueName", "Station", "OutputCase", "P", "V2", "M3"],
        rows=[{"Story": _term_a(), "Frame": _term_b(), "UniqueName": "297", "Station": 0.0, "OutputCase": "EQX", "P": 1.0, "V2": 2.0, "M3": 3.0}],
    )


def test_generated_notes_and_blockers_are_still_scanned():
    payload = {"source_tables": [{"notes": ["generated note " + _term_a()], "blockers": ["generated blocker " + _term_c()], "sample_rows_limited": [{"Status": _term_a()}]}]}
    result = scan_semantic_outputs_for_forbidden_verdicts(payload)
    assert {item["term"] for item in result["forbidden_terms_found"]} == {_term_a(), _term_c()}
    assert {item["term"] for item in result["raw_source_forbidden_like_terms"]} == {_term_a()}
    assert result["raw_source_terms_are_not_generated_verdicts"] is True
    assert result["engineering_verdicts_emitted"] is True


def test_scan_output_and_summary_payload_are_not_self_scanned():
    payload = {
        "forbidden_verdict_scan_report.json": {
            "forbidden_terms_found": [{"term": _term_b(), "count": 1}],
            "raw_source_forbidden_like_terms": [{"term": _term_a(), "count": 1}],
        },
        "semantic_source_review_summary.json": {
            "forbidden_terms_found": [{"term": _term_b(), "count": 1}],
            "raw_source_forbidden_like_terms": [{"term": _term_a(), "count": 1}],
        },
    }
    result = scan_semantic_outputs_for_forbidden_verdicts(payload)
    assert result["forbidden_terms_found"] == []
    assert result["raw_source_forbidden_like_terms"] == []
    assert result["engineering_verdicts_emitted"] is False


def test_raw_source_values_are_diagnostic_not_generated_verdicts():
    item = _raw_item()
    scan = scan_semantic_outputs_for_forbidden_verdicts([item])
    assert scan["forbidden_terms_found"] == []
    assert {entry["term"] for entry in scan["raw_source_forbidden_like_terms"]} == {_term_a(), _term_b()}
    assert scan["raw_source_terms_are_not_generated_verdicts"] is True
    assert scan["engineering_verdicts_emitted"] is False
    summary = build_semantic_source_review_report(classifications=[item], generated_at="2026-06-17T00:00:00+00:00", live_etabs_requested=True, live_etabs_connected=True, target_family="all")
    assert summary["forbidden_terms_found"] == []
    assert {entry["term"] for entry in summary["raw_source_forbidden_like_terms"]} == {_term_a(), _term_b()}
    assert summary["raw_source_terms_are_not_generated_verdicts"] is True
    assert summary["safe_to_implement_checks_now"] is False
    assert summary["check_unlock_allowed"] is False
    assert summary["diagnostic_only"] is True
    assert summary["check_engine_invoked"] is False
