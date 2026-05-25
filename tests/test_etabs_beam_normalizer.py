from __future__ import annotations

import json

import pandas as pd

from tbdy_engine.etabs.normalizers.beam_design import (
    build_beam_context_from_tables,
    normalize_beam_design_summary,
    normalize_beam_flexure_envelope,
    normalize_beam_shear_envelope,
    to_context_namespace,
)


BEAM_SUMMARY_TABLE = "Concrete Beam Design Summary - TS 500-2000(R2018)"
BEAM_FLEXURE_TABLE = "Concrete Beam Flexure Envelope - TS 500-2000(R2018)"
BEAM_SHEAR_TABLE = "Concrete Beam Shear Envelope - TS 500-2000(R2018)"


def test_beam_design_summary_normalizes_representative_rows():
    df = pd.DataFrame(
        [
            {
                "Story": "S1",
                "Frame": "B1",
                "DesignSect": "B30x60",
                "Status": "OK",
                "TotTopRebar": 0.0012,
                "TotBotRebar": 0.0010,
                "TotTrnRebar": 0.0002,
            }
        ]
    )

    rows = normalize_beam_design_summary(df, source_table=BEAM_SUMMARY_TABLE)
    row = rows[0]

    assert row["label"] == "B1"
    assert row["beam_label"] == "B1"
    assert row["frame"] == "B1"
    assert row["story"] == "S1"
    assert row["section"] == "B30x60"
    assert row["designsect"] == "B30x60"
    assert row["status"] == "OK"
    assert row["ratio"] is None
    assert row["as_top"] == 0.0012
    assert row["astop"] == 0.0012
    assert row["as_bottom"] == 0.0010
    assert row["asbot"] == 0.0010
    assert row["asw_per_m"] == 0.0002
    assert row["vrebar"] == 0.0002
    assert row["source_table"] == BEAM_SUMMARY_TABLE
    assert row["source_row"] == 0
    assert row["source_columns"] == [
        "Story",
        "Frame",
        "DesignSect",
        "Status",
        "TotTopRebar",
        "TotBotRebar",
        "TotTrnRebar",
    ]


def test_beam_flexure_envelope_normalizes_representative_rows():
    df = pd.DataFrame(
        [
            {"Story": "S1", "Frame": "B1", "Location": "Middle", "OutputCase": "EQX", "M3": 120.5},
            {"Story": "S1", "Frame": "B1", "Location": "End-I", "OutputCase": "EQY", "M3": -95.0},
        ]
    )

    rows = normalize_beam_flexure_envelope(df, source_table=BEAM_FLEXURE_TABLE)

    assert [row["label"] for row in rows] == ["B1", "B1"]
    assert [row["location"] for row in rows] == ["Middle", "End-I"]
    assert [row["combo"] for row in rows] == ["EQX", "EQY"]
    assert [row["moment"] for row in rows] == [120.5, -95.0]
    assert all(row["source_table"] == BEAM_FLEXURE_TABLE for row in rows)
    assert rows[1]["source_row"] == 1
    assert "M3" in rows[0]["source_columns"]


def test_beam_shear_envelope_normalizes_representative_rows():
    df = pd.DataFrame(
        [
            {"Story": "S1", "Frame": "B1", "Location": "End-J", "VCombo": "EQX", "Shear": -210.0},
        ]
    )

    rows = normalize_beam_shear_envelope(df, source_table=BEAM_SHEAR_TABLE)

    assert rows[0]["label"] == "B1"
    assert rows[0]["story"] == "S1"
    assert rows[0]["location"] == "End-J"
    assert rows[0]["combo"] == "EQX"
    assert rows[0]["shear"] == -210.0
    assert rows[0]["source_table"] == BEAM_SHEAR_TABLE
    assert rows[0]["source_row"] == 0
    assert rows[0]["source_columns"] == ["Story", "Frame", "Location", "VCombo", "Shear"]


def test_empty_input_returns_empty_without_fabricated_rows():
    empty = pd.DataFrame(columns=["Story", "Frame", "M3"])

    assert normalize_beam_design_summary(empty, source_table=BEAM_SUMMARY_TABLE) == []
    assert normalize_beam_flexure_envelope(empty, source_table=BEAM_FLEXURE_TABLE) == []
    assert normalize_beam_shear_envelope(empty, source_table=BEAM_SHEAR_TABLE) == []


def test_build_beam_context_targets_existing_beam_design_shape():
    tables = {
        "beam_design_summary": pd.DataFrame(
            [{"Story": "S1", "Frame": "B1", "DesignSect": "B30x60", "TotTopRebar": 0.0012, "TotBotRebar": 0.0010, "TotTrnRebar": 0.0002}]
        ),
        "beam_design_summary_source_table": BEAM_SUMMARY_TABLE,
        "beam_flexure_envelope": pd.DataFrame(
            [{"Story": "S1", "Frame": "B1", "Location": "Middle", "OutputCase": "EQX", "M3": 120.0}]
        ),
        "beam_flexure_envelope_source_table": BEAM_FLEXURE_TABLE,
        "beam_shear_envelope": pd.DataFrame(
            [{"Story": "S1", "Frame": "B1", "Location": "End-I", "VCombo": "EQX", "Shear": 80.0}]
        ),
        "beam_shear_envelope_source_table": BEAM_SHEAR_TABLE,
    }

    context = build_beam_context_from_tables(tables)
    ctx = to_context_namespace(context)

    assert set(context) == {"tables", "design_metadata", "envelopes", "geometry", "topology", "design_basis", "flags", "diagnostics"}
    assert not ctx.tables["beam_design_summary"].empty
    assert ctx.design_metadata["beam_design_summary"] is ctx.tables["beam_design_summary"]
    assert "frame" in ctx.tables["beam_design_summary"].columns
    assert "designsect" in ctx.tables["beam_design_summary"].columns
    assert "astop" in ctx.tables["beam_design_summary"].columns
    assert "asbot" in ctx.tables["beam_design_summary"].columns
    assert "vrebar" in ctx.tables["beam_design_summary"].columns
    assert ctx.envelopes["beam_forces_map"]["B1"]["M_pos"] == 120.0
    assert ctx.envelopes["beam_forces_map"]["B1"]["V_max"] == 80.0
    assert ctx.geometry["beam_sections"]["B1"] == "B30x60"
    assert ctx.geometry["section_dims"]["B30x60"] == {"width_mm": 300.0, "depth_mm": 600.0, "source": "section_name_parse"}
    assert context["diagnostics"] == {
        "beam_design_summary_row_count": 1,
        "beam_flexure_row_count": 1,
        "beam_shear_row_count": 1,
    }


def test_source_provenance_is_preserved_in_force_map():
    context = build_beam_context_from_tables(
        {
            "beam_design_summary": pd.DataFrame([{ "Story": "S1", "Frame": "B1", "DesignSect": "B30x60" }]),
            "beam_design_summary_source_table": BEAM_SUMMARY_TABLE,
            "beam_flexure_envelope": pd.DataFrame([{ "Frame": "B1", "OutputCase": "EQX", "M3": 1.0 }]),
            "beam_flexure_envelope_source_table": BEAM_FLEXURE_TABLE,
            "beam_shear_envelope": pd.DataFrame([{ "Frame": "B1", "VCombo": "EQY", "Shear": 2.0 }]),
            "beam_shear_envelope_source_table": BEAM_SHEAR_TABLE,
        }
    )

    evidence = context["envelopes"]["beam_forces_map"]["B1"]["evidence"]

    assert evidence["flexure"]["source_table"] == BEAM_FLEXURE_TABLE
    assert evidence["flexure"]["source_row"] == 0
    assert "M3" in evidence["flexure"]["source_columns"]
    assert evidence["shear"]["source_table"] == BEAM_SHEAR_TABLE
    assert evidence["shear"]["source_row"] == 0
    assert "Shear" in evidence["shear"]["source_columns"]
    assert evidence["shear"]["unit_conversion_status"] == "not_normalized"
    assert evidence["shear"]["combo_family_status"] == "not_inferred"


def test_no_combo_family_inference_unit_normalization_or_message_parsing():
    context = build_beam_context_from_tables(
        {
            "beam_design_summary": pd.DataFrame([{ "Frame": "B1", "DesignSect": "B30x60" }]),
            "beam_flexure_envelope": pd.DataFrame([{ "Frame": "B1", "OutputCase": "EQX", "M3": 1.0 }]),
            "beam_shear_envelope": pd.DataFrame([{ "Frame": "B1", "VCombo": "EQY", "Shear": 2.0 }]),
        }
    )
    encoded = json.dumps(context, default=str, ensure_ascii=False)

    assert "combo_family" not in encoded
    assert "uses_combo" not in encoded
    assert "message_text" not in encoded
    assert "not_normalized" in encoded
    assert "not_inferred" in encoded


def test_normalized_output_is_json_serializable():
    context = build_beam_context_from_tables(
        {
            "beam_design_summary": pd.DataFrame([{ "Frame": "B1", "DesignSect": "B30x60" }]),
            "beam_flexure_envelope": pd.DataFrame([{ "Frame": "B1", "OutputCase": "EQX", "M3": 1.0 }]),
            "beam_shear_envelope": pd.DataFrame([{ "Frame": "B1", "VCombo": "EQY", "Shear": 2.0 }]),
        }
    )

    json.dumps(context["design_metadata"]["beam_design_summary_rows"], ensure_ascii=False)
    json.dumps(context["design_metadata"]["beam_flexure_envelope_rows"], ensure_ascii=False)
    json.dumps(context["design_metadata"]["beam_shear_envelope_rows"], ensure_ascii=False)
    json.dumps(context["envelopes"]["beam_forces_map"], ensure_ascii=False)
