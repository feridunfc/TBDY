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


def test_missing_identity_columns_emit_diagnostic_rows():
    rows = normalize_beam_flexure_envelope(
        pd.DataFrame([{"Story": "S1", "M3": 10.0}]),
        source_table=BEAM_FLEXURE_TABLE,
    )

    assert rows[0]["status"] == "NO_DATA"
    assert rows[0]["diagnostic"] == DIAGNOSTIC_REASON_MISSING_LABEL
    assert rows[0]["key"] == "S1|"


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


def test_ductility_missing_fields_emit_no_data_diagnostic():
    rows = normalize_beam_design_summary(
        pd.DataFrame([{"Story": "S1", "Frame": "B1", "DesignSect": "B30x60"}]),
        source_table=BEAM_SUMMARY_TABLE,
    )

    assert rows[0]["ductility_status"] == "NO_DATA"
    assert rows[0]["diagnostic"] == DIAGNOSTIC_REASON_DUCTILITY_FIELDS_MISSING


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
