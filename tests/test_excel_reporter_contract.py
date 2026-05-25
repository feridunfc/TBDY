from __future__ import annotations

from pathlib import Path

import pytest

from tbdy_engine.reports.excel_reporter import ExcelReporter
from tbdy_engine.reports.report_plan import PlannedReport


openpyxl = pytest.importorskip("openpyxl")


class _Check:
    check_id = "column_geometry"
    element_label = "C1"
    story = "Story1"
    status = "OK"
    ratio = 0.75
    value = 1.0
    limit = 2.0
    unit = "-"
    message = "ok"
    action = "none"
    tbdy_ref = "TBDY"
    evaluation_level = "DESIGN_LEVEL"
    source = "contract-test"
    severity = "LOW"
    category = "GEOMETRY"
    report_section = "columns"
    legacy_contract_id = ""


def _planned_report():
    return PlannedReport(
        report_id="full_engine_report",
        formats=("json", "excel"),
        sections=("summary", "columns", "actions"),
        include_fields=("check_id", "element_label", "status"),
        metrics=("total_checks_possible", "coverage_pct"),
    )


def _eval_results():
    return {
        "errors": {"WALL_DESIGN": "disabled"},
        "skipped": {"JOINT_DESIGN": "future"},
    }


def _sheet_names(path: Path) -> list[str]:
    workbook = openpyxl.load_workbook(path)
    return workbook.sheetnames


def test_excel_reporter_accepts_planned_report_and_keeps_existing_sheets(tmp_path):
    output_path = tmp_path / "engine_report.xlsx"

    result_path = ExcelReporter(write_history=False).generate(
        [_Check()],
        _eval_results(),
        output_path=str(output_path),
        planned_report=_planned_report(),
    )

    assert result_path == str(output_path)
    assert _sheet_names(output_path) == [
        "Summary",
        "Details",
        "Eval_Skipped",
        "Eval_Errors",
        "Report_Contract",
    ]


def test_excel_reporter_keeps_existing_detail_columns_with_planned_report(tmp_path):
    output_path = tmp_path / "engine_report.xlsx"

    ExcelReporter(write_history=False).generate(
        [_Check()],
        _eval_results(),
        output_path=str(output_path),
        planned_report=_planned_report(),
    )

    workbook = openpyxl.load_workbook(output_path)
    detail = workbook["Details"]
    assert [cell.value for cell in detail[1]] == [
        "check_id", "element_label", "story", "status", "ratio", "value", "limit", "unit",
        "message", "action", "tbdy_ref", "evaluation_level", "source", "severity", "category",
        "report_section", "legacy_contract_id", "evidence",
    ]


def test_excel_reporter_adds_report_contract_sheet_only_when_planned_report_is_provided(tmp_path):
    with_plan = tmp_path / "with_plan.xlsx"
    without_plan = tmp_path / "without_plan.xlsx"

    ExcelReporter(write_history=False).generate(
        [_Check()],
        _eval_results(),
        output_path=str(with_plan),
        planned_report=_planned_report(),
    )
    ExcelReporter(write_history=False).generate(
        [_Check()],
        _eval_results(),
        output_path=str(without_plan),
    )

    assert "Report_Contract" in _sheet_names(with_plan)
    assert "Report_Contract" not in _sheet_names(without_plan)


def test_excel_reporter_report_contract_sheet_contains_contract_metadata(tmp_path):
    output_path = tmp_path / "engine_report.xlsx"

    ExcelReporter(write_history=False).generate(
        [_Check()],
        _eval_results(),
        output_path=str(output_path),
        planned_report=_planned_report(),
    )

    workbook = openpyxl.load_workbook(output_path)
    sheet = workbook["Report_Contract"]
    rows = {sheet.cell(row=i, column=1).value: sheet.cell(row=i, column=2).value for i in range(2, 7)}

    assert rows == {
        "report_id": "full_engine_report",
        "formats": "json,excel",
        "sections": "summary,columns,actions",
        "include_fields": "check_id,element_label,status",
        "metrics": "total_checks_possible,coverage_pct",
    }


def test_excel_reporter_preserves_engine_report_xlsx_filename(tmp_path):
    output_path = tmp_path / "engine_report.xlsx"

    result_path = ExcelReporter(write_history=False).generate(
        [_Check()],
        _eval_results(),
        output_path=str(output_path),
        planned_report=_planned_report(),
    )

    assert result_path == str(output_path)
    assert output_path.name == "engine_report.xlsx"
