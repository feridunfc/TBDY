"""Recovered original example is reproducible evidence, never FC09 authority."""
from copy import deepcopy
from decimal import Decimal
import json
import os
from pathlib import Path
import shutil

import pytest

from tools import column_r1_m6_reference_recovery as recovery


def reference():
    return json.loads(recovery.FIXTURE.read_text())


@pytest.mark.parametrize("story,direction,prota,etabs", [
    ("ST1", "X", "587.796", "877.5327"),
    ("ST2", "X", "295.072", "401.6103"),
    ("ST1", "Y", "587.797", "877.5320"),
    ("ST2", "Y", "295.070", "401.6092"),
])
def test_raw_column_totals_reproduce_previous_member_extrema_discrepancy(story, direction, prota, etabs):
    row = next(r for r in recovery.compare(reference())["comparison"]
               if (r["story"], r["direction"]) == (story, direction))
    assert row["column_count"] == 16
    assert row["rounded_Prota_NBot_sum_tonf"] == prota
    assert row["ETABS_independent_Min_P_sum_tonf"] == etabs
    assert abs(Decimal(row["Prota_rounding_difference_tonf"])) <= Decimal("0.002")
    assert Decimal(row["ETABS_difference_tonf"]) > 100


def test_reference_preserves_reported_phi_and_average_drift_without_claiming_exact_precision():
    rows = reference()["sway_rows"]
    assert [r["delta_mm"] for r in rows] == ["1.44", "1.76", "1.44", "1.76"]
    assert [r["reported_phi"] for r in rows] == ["0.010308", "0.012086"] * 2
    assert all(r["reported_status"] == "Prevented" for r in rows)
    # Printed drift/force rounding prevents exact reproduction of printed phi;
    # do not repair the original inputs by inventing extra decimal places.
    r = rows[0]
    phi = Decimal("1.5") * Decimal(r["delta_mm"]) * Decimal(r["sum_Nd_tonf"]) / (
        Decimal(r["Vf_tonf"]) * Decimal(r["height_cm"]) * 10)
    assert phi != Decimal(r["reported_phi"])


def test_recovered_comparison_cannot_be_consumed_as_current_modal_or_physical_authority():
    result = recovery.compare(reference())
    assert result["scope"] == recovery.REFERENCE_SCOPE
    assert result["qualified_modal_aggregate"] is False
    assert result["current_FC09_qualification"] is False
    assert result["physical_concurrency_proven"] is False
    assert "AnalysisResultIdentity" not in json.dumps(result)
    assert "READY" not in json.dumps(result)


@pytest.mark.parametrize("change", ["missing_column", "duplicate_column", "wrong_story", "wrong_column",
                                   "source_hash", "source_ref", "scope", "full_count"])
def test_missing_or_rebound_reference_population_fails_closed(change):
    raw = reference()
    if change == "missing_column": raw["columns"].pop()
    elif change == "duplicate_column": raw["columns"][-1] = deepcopy(raw["columns"][0])
    elif change == "wrong_story": raw["columns"][0]["story"] = "+0.00"
    elif change == "wrong_column": raw["columns"][0]["column"] = "C10"
    elif change == "scope": raw["scope"] = "FC09"
    elif change == "full_count": raw["original_etabs_result_row_count"] -= 1
    else:
        field = "original_sha256" if change == "source_hash" else "library_file_id"
        raw["source_files"]["tr1-ColSln.docx"][field] = "other-source"
    with pytest.raises(ValueError): recovery.compare(raw)


@pytest.mark.parametrize("change", ["missing_force", "duplicate_force", "physical_sign", "wrong_station",
                                   "wrong_case", "wrong_step", "wrong_type", "nonfinite", "wrong_design_combo"])
def test_capture_steps_and_row_identity_cannot_be_relabelled_to_physical_states(change):
    raw = reference()
    column = raw["columns"][0]
    row = next(r for r in column["etabs_export_rows"] if r[5] == "Min")
    if change == "missing_force": column["etabs_export_rows"].remove(row)
    elif change == "duplicate_force": column["etabs_export_rows"].append(deepcopy(row))
    elif change == "physical_sign": row[5] = "Single Value"
    elif change == "wrong_station": row[6] = "3.5"
    elif change == "wrong_case": row[3] = "GQE"
    elif change == "wrong_step": row[5] = "Max"
    elif change == "wrong_type": row[4] = "LinStatic"
    elif change == "nonfinite": row[7] = "NaN"
    else: column["prota_design_rows"][1][0] = "7"
    with pytest.raises(ValueError): recovery.compare(raw)


@pytest.mark.parametrize("change", ["missing", "duplicate", "critical_combo"])
def test_report_direction_and_governing_identity_are_retained(change):
    raw = reference()
    if change == "missing": raw["sway_rows"].pop()
    elif change == "duplicate": raw["sway_rows"][-1] = deepcopy(raw["sway_rows"][0])
    else: raw["sway_rows"][0]["combo_number"] = "10"
    with pytest.raises(ValueError): recovery.compare(raw)


def test_signed_comparison_does_not_clip_tension_or_use_absolute_member_P():
    raw = reference()
    row = next(r for r in raw["columns"][0]["etabs_export_rows"]
               if (r[3], r[5], r[6]) == (recovery.X_EXPORT_LABEL, "Min", "0"))
    old = Decimal(row[7])
    row[7] = "100"
    comparison = recovery.compare(raw)
    result = comparison["comparison"][0]
    assert Decimal(result["ETABS_independent_Min_P_sum_tonf"]) == Decimal("877.5327") + old - 100
    assert comparison["qualified_modal_aggregate"] is False


def test_exact_original_files_reproduce_bounded_projection_without_changes(tmp_path):
    source = os.environ.get("COLUMN_R1_M6_REFERENCE_SOURCE_DIR")
    if not source:
        pytest.skip("Original historical files are held separately; provide exact bytes for reproduction")
    original = {name: (Path(source) / name).read_bytes() for name in recovery.SOURCE_FILES}
    assert recovery.recover(source) == reference()
    assert {name: (Path(source) / name).read_bytes() for name in recovery.SOURCE_FILES} == original
    for name in recovery.SOURCE_FILES:
        shutil.copyfile(Path(source) / name, tmp_path / name)
    name = "Pasted text(20261001-041302).txt"
    with (tmp_path / name).open("ab") as stream: stream.write(b"changed")
    with pytest.raises(ValueError, match="original reference SHA256 mismatch"):
        recovery.recover(tmp_path)


def test_default_cli_is_offline_and_returns_unqualified_comparison(capsys):
    assert recovery.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result["comparison"]) == 4
    assert result["current_FC09_qualification"] is False
