from __future__ import annotations

import json

import pandas as pd

from tbdy_engine.etabs.normalizers.beam_design import (
    DIAGNOSTIC_REASON_DUCTILITY_FIELDS_MISSING,
    DIAGNOSTIC_REASON_MISSING_LABEL,
    build_beam_context_from_tables,
    group_beam_flexure_rows,
    group_beam_shear_rows,
    normalize_beam_design_summary,
    normalize_beam_flexure_envelope,
    normalize_beam_shear_envelope,
)


BEAM_SUMMARY_TABLE = "Concrete Beam Design Summary - TS 500-2000(R2018)"
BEAM_FLEXURE_TABLE = "Concrete Beam Flexure Envelope - TS 500-2000(R2018)"
BEAM_SHEAR_TABLE = "Concrete Beam Shear Envelope - TS 500-2000(R2018)"
REQUIRED_EVIDENCE_KEYS = {
    "source_table",
    "source_row",
    "source_rows",
    "source_columns",
    "evidence_type",
    "confidence",
    "unit_conversion_status",
    "combo_family_status",
    "logical_table",
    "attempted_candidates",
    "notes",
}


def _assert_standard_evidence(evidence: dict[str, object], *, logical_table: str) -> None:
    assert REQUIRED_EVIDENCE_KEYS.issubset(evidence)
    assert evidence["logical_table"] == logical_table
    assert evidence["evidence_type"] in {"live_etabs_table", "diagnostic_helper"}
    assert evidence["confidence"] in {"HIGH", "MEDIUM", "LOW"}
    assert evidence["unit_conversion_status"] in {"not_required", "not_required_ratio", "not_normalized", "blocked_until_unit_contract", "unknown"}
    assert evidence["combo_family_status"] in {"not_applicable", "not_classified", "combo_name_present_family_unclassified", "heuristic_deferred"}
    assert isinstance(evidence["source_columns"], list)
    assert isinstance(evidence["attempted_candidates"], list)
    assert isinstance(evidence["notes"], list)


def test_identity_aliases_use_story_beam_key_and_preserve_sources():
    rows = normalize_beam_design_summary(
        pd.DataFrame([
            {"Story": "S1", "Frame": "B1", "DesignSect": "B30x60", "Status": "OK", "TotTopRebar": 0.0012}
        ]),
        source_table=BEAM_SUMMARY_TABLE,
    )

    row = rows[0]
    assert row["key"] == "S1|B1"
    assert row["label"] == "B1"
    assert row["story"] == "S1"
    assert row["section"] == "B30x60"
    assert row["astop"] == 0.0012
    assert row["source_table"] == BEAM_SUMMARY_TABLE
    assert row["source_row"] == 0
    assert row["source_columns"] == ["Story", "Frame", "DesignSect", "Status", "TotTopRebar"]
    _assert_standard_evidence(row["evidence"], logical_table="beam_design_summary")


def test_missing_identity_columns_emit_diagnostic_rows():
    rows = normalize_beam_flexure_envelope(
        pd.DataFrame([{"Story": "S1", "M3": 10.0}]),
        source_table=BEAM_FLEXURE_TABLE,
    )

    assert rows[0]["status"] == "NO_DATA"
    assert rows[0]["diagnostic"] == DIAGNOSTIC_REASON_MISSING_LABEL
    assert rows[0]["key"] == "S1|"
    _assert_standard_evidence(rows[0]["evidence"], logical_table="beam_flexure_envelope")
    assert rows[0]["evidence"]["evidence_type"] == "diagnostic_helper"
    assert rows[0]["evidence"]["notes"] == [DIAGNOSTIC_REASON_MISSING_LABEL]


def test_flexure_grouping_preserves_all_rows_and_selects_governing_rows():
    rows = normalize_beam_flexure_envelope(
        pd.DataFrame([
            {"Story": "S1", "Frame": "B1", "OutputCase": "EQ1", "M3": 10.0},
            {"Story": "S1", "Frame": "B1", "OutputCase": "EQ2", "M3": 25.0},
            {"Story": "S1", "Frame": "B1", "OutputCase": "EQ3", "M3": -30.0},
        ]),
        source_table=BEAM_FLEXURE_TABLE,
    )

    grouped = group_beam_flexure_rows(rows)["S1|B1"]
    assert len(grouped["rows"]) == 3
    assert grouped["governing_positive"]["combo"] == "EQ2"
    assert grouped["governing_negative"]["combo"] == "EQ3"
    _assert_standard_evidence(grouped["governing_positive"]["evidence"], logical_table="beam_flexure_envelope")
    assert grouped["governing_positive"]["evidence"]["combo_family_status"] == "combo_name_present_family_unclassified"


def test_shear_grouping_preserves_all_rows_and_selects_governing_rows():
    rows = normalize_beam_shear_envelope(
        pd.DataFrame([
            {"Story": "S1", "Frame": "B1", "VCombo": "EQ1", "Shear": 10.0},
            {"Story": "S1", "Frame": "B1", "VCombo": "EQ2", "Shear": -35.0},
        ]),
        source_table=BEAM_SHEAR_TABLE,
    )

    grouped = group_beam_shear_rows(rows)["S1|B1"]
    assert len(grouped["rows"]) == 2
    assert grouped["governing_shear"]["combo"] == "EQ2"
    _assert_standard_evidence(grouped["governing_shear"]["evidence"], logical_table="beam_shear_envelope")


def test_ductility_missing_fields_emit_no_data_diagnostic():
    rows = normalize_beam_design_summary(
        pd.DataFrame([{"Story": "S1", "Frame": "B1", "DesignSect": "B30x60"}]),
        source_table=BEAM_SUMMARY_TABLE,
    )

    assert rows[0]["ductility_status"] == "NO_DATA"
    assert rows[0]["diagnostic"] == DIAGNOSTIC_REASON_DUCTILITY_FIELDS_MISSING
    assert rows[0]["evidence"]["evidence_type"] == "live_etabs_table"


def test_context_shape_contains_no_check_ids_or_report_rows():
    context = build_beam_context_from_tables(
        {
            "beam_design_summary": pd.DataFrame([{"Story": "S1", "Frame": "B1", "DesignSect": "B30x60", "Status": "OK"}]),
            "beam_design_summary_source_table": BEAM_SUMMARY_TABLE,
            "beam_flexure_envelope": pd.DataFrame([{"Story": "S1", "Frame": "B1", "OutputCase": "EQX", "M3": 12.0}]),
            "beam_flexure_envelope_source_table": BEAM_FLEXURE_TABLE,
            "beam_shear_envelope": pd.DataFrame([{"Story": "S1", "Frame": "B1", "VCombo": "EQY", "Shear": 20.0}]),
            "beam_shear_envelope_source_table": BEAM_SHEAR_TABLE,
        }
    )

    encoded = json.dumps(context, default=str, ensure_ascii=False)
    forbidden_check_ids = {"beam_geometry", "beam_ductility"}
    for check_id in forbidden_check_ids:
        assert check_id not in encoded
    assert "\"check_id\"" not in encoded
    assert "report_section" not in encoded
    assert "severity" not in encoded
    assert "uses_combo" not in encoded
    assert "message_text" not in encoded
    assert context["diagnostics"]["beam_design_summary_row_count"] == 1
    assert context["diagnostics"]["beam_flexure_row_count"] == 1
    assert context["diagnostics"]["beam_shear_row_count"] == 1
