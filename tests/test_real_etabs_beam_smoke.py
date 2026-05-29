from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tbdy_engine.etabs.table_access import read_etabs_table_on_demand
from tbdy_engine.etabs.normalizers.beam_design import build_beam_context_from_tables
from tbdy_engine.runner_v2 import run_engine_v2


BEAM_DESIGN_SUMMARY_TABLE = "Concrete Beam Design Summary - TS 500-2000(R2018)"
BEAM_FLEXURE_TABLE = "Concrete Beam Flexure Envelope - TS 500-2000(R2018)"
BEAM_SHEAR_TABLE = "Concrete Beam Shear Envelope - TS 500-2000(R2018)"

FORBIDDEN_JSON_FIELDS = {
    "report_metadata",
    "runtime_bridge",
    "report_contract",
    "evaluation_errors",
    "evaluation_skipped",
    "execution_order",
    "cache_stats",
    "coverage",
    "distributions",
    "json_snapshot",
    "excel_snapshot",
    "action_summary",
}


def _require_real_etabs_enabled() -> None:
    if os.environ.get("RUN_REAL_ETABS_BEAM_SMOKE") != "1":
        pytest.skip("Set RUN_REAL_ETABS_BEAM_SMOKE=1 on a Windows/ETABS machine to execute the live smoke.")


def _read_required_table(table_name: str):
    result = read_etabs_table_on_demand(table_name)
    assert result.ok, f"{table_name} read failed: status={result.status} error={result.error}"
    assert result.has_data, f"{table_name} returned no rows"
    return result


@pytest.mark.real_etabs
def test_real_etabs_beam_smoke_produces_json_and_excel_reports(tmp_path: Path) -> None:
    _require_real_etabs_enabled()
    pytest.importorskip("openpyxl")

    design_summary = _read_required_table(BEAM_DESIGN_SUMMARY_TABLE)
    flexure = _read_required_table(BEAM_FLEXURE_TABLE)
    shear = _read_required_table(BEAM_SHEAR_TABLE)

    context = build_beam_context_from_tables(
        {
            "beam_design_summary": design_summary.df,
            "beam_design_summary_source_table": BEAM_DESIGN_SUMMARY_TABLE,
            "beam_flexure_envelope": flexure.df,
            "beam_flexure_envelope_source_table": BEAM_FLEXURE_TABLE,
            "beam_shear_envelope": shear.df,
            "beam_shear_envelope_source_table": BEAM_SHEAR_TABLE,
        }
    )

    design_metadata = context.get("design_metadata", {})
    assert design_metadata.get("beam_design_summary_rows")
    assert "beam_flexure_grouped" in design_metadata
    assert "beam_shear_grouped" in design_metadata

    result = run_engine_v2(context, report_dir=tmp_path)

    assert result["reports"].keys() == {"json", "excel"}
    assert "json_snapshot" not in result["reports"]
    assert "excel_snapshot" not in result["reports"]
    assert "action_summary" not in result["reports"]

    json_path = Path(result["reports"]["json"])
    assert json_path.exists()
    assert json_path.name == "engine_report.json"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert set(payload) == {"summary", "checks"}
    assert FORBIDDEN_JSON_FIELDS.isdisjoint(payload)

    check_types = {row["check_type"] for row in payload["checks"]}
    assert {"beam_geometry", "beam_flexure", "beam_shear"}.issubset(check_types)

    for row in payload["checks"]:
        assert {
            "id",
            "component",
            "check_type",
            "status",
            "demand",
            "capacity",
            "ratio",
            "evidence",
            "messages",
            "story",
            "section",
            "unit",
            "code_ref",
        } == set(row)
        assert FORBIDDEN_JSON_FIELDS.isdisjoint(row)

    excel_path = Path(result["reports"]["excel"])
    assert excel_path.exists()
    assert excel_path.name == "engine_report.xlsx"

    import openpyxl

    workbook = openpyxl.load_workbook(excel_path)
    assert set(workbook.sheetnames) == {"Summary", "Checks"}
    assert "Eval_Skipped" not in workbook.sheetnames
    assert "Eval_Errors" not in workbook.sheetnames
    assert "Report_Contract" not in workbook.sheetnames
    assert "Details" not in workbook.sheetnames
