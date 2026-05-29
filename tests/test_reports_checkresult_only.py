from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pytest

from tbdy_engine.reports.facade import ReportingFacade


@dataclass(frozen=True)
class FakeCheckResult:
    check_id: str
    element_label: str
    story: str
    status: str
    ratio: float | None
    value: float | None
    limit: float | None
    unit: str
    message: str
    evidence: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def test_reporting_facade_generates_checkresult_only_reports(tmp_path: Path) -> None:
    checks = [
        FakeCheckResult(
            check_id="beam_geometry",
            element_label="B1",
            story="S1",
            status="OK",
            ratio=0.75,
            value=300.0,
            limit=250.0,
            unit="mm",
            message="geometry ok",
            evidence={"source_table": "beam_design_summary", "source_row": 1},
        ),
        FakeCheckResult(
            check_id="beam_flexure",
            element_label="B1",
            story="S1",
            status="FAIL",
            ratio=1.2,
            value=120.0,
            limit=100.0,
            unit="kNm",
            message="flexure fail",
            evidence={"source_table": "beam_flexure_envelope", "source_row": 2},
        ),
        FakeCheckResult(
            check_id="beam_shear",
            element_label="B2",
            story="S1",
            status="NO_DATA",
            ratio=None,
            value=None,
            limit=None,
            unit="kN",
            message="missing shear",
            evidence={"source_table": "beam_shear_envelope", "missing_inputs": ["shear"]},
        ),
    ]

    result = ReportingFacade(tmp_path).generate(checks)

    json_path = Path(result.json_report)
    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert set(payload) == {"summary", "checks"}
    assert payload["summary"] == {
        "total_checks": 3,
        "ok": 1,
        "fail": 1,
        "warning": 0,
        "no_data": 1,
        "error": 0,
    }
    assert [row["check_id"] for row in payload["checks"]] == ["beam_geometry", "beam_flexure", "beam_shear"]

    forbidden_json_fields = {
        "report_metadata",
        "runtime_bridge",
        "report_contract",
        "evaluation_errors",
        "evaluation_skipped",
        "execution_order",
        "cache_stats",
        "coverage",
        "distributions",
    }
    assert forbidden_json_fields.isdisjoint(payload)
    assert not (tmp_path / "history").exists()

    if result.excel_report is None:
        pytest.skip("openpyxl is not available")

    openpyxl = pytest.importorskip("openpyxl")
    excel_path = Path(result.excel_report)
    assert excel_path.exists()
    wb = openpyxl.load_workbook(excel_path)
    assert set(wb.sheetnames) == {"Summary", "Checks"}
    assert "Eval_Skipped" not in wb.sheetnames
    assert "Eval_Errors" not in wb.sheetnames
    assert "Report_Contract" not in wb.sheetnames
