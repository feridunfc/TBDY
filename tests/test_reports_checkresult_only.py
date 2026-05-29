from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

import pytest

from tbdy_engine.reports.facade import ReportingFacade


EXPECTED_SHEETS = {"Summary", "Kiriş Kesme", "Kiriş Donatı Seçimi", "Beam Checks", "Evidence"}
SHEAR_COLUMNS = [
    "Kat",
    "Kiriş",
    "Kesit",
    "Tasarım Kuvveti Vd (kN)",
    "Eksenel Kuvvet P (kN)",
    "Minimum Kol Adedi",
    "Seçilen Kol Adedi",
    "Kesme Donatı Çapı (mm)",
    "Kol Adet - Çap",
    "B (m)",
    "H (m)",
    "d (m)",
    "Asmin (cm²)",
    "Asw (cm²)",
    "Vmax (kN)",
    "Kesit Kontrol (%)",
    "Vc (kN)",
    "Vw (kN)",
    "Vr (kN)",
    "Oran (%)",
    "Durum",
    "Check ID",
]
FLEXURE_COLUMNS = [
    "Kat",
    "Kiriş",
    "Kesit",
    "I Üst - Seçilen Donatı",
    "I Üst - Gerekli Alan (cm²)",
    "I Üst - Seçilen Alan (cm²)",
    "Üst Açıklık - Seçilen Donatı",
    "Üst Açıklık - Gerekli Alan (cm²)",
    "Üst Açıklık - Seçilen Alan (cm²)",
    "J Üst - Seçilen Donatı",
    "J Üst - Gerekli Alan (cm²)",
    "J Üst - Seçilen Alan (cm²)",
    "Alt - Seçilen Donatı",
    "Alt - Gerekli Alan (cm²)",
    "Alt - Seçilen Alan (cm²)",
    "B (m)",
    "H (m)",
    "L (m)",
    "Toplam Gerekli Alan (cm²)",
    "Seçilen Toplam Alan (cm²)",
    "Fark (%)",
    "Durum",
    "Check ID",
]


@dataclass(frozen=True)
class FakeCheckResult:
    id: str
    component: str
    check_type: str
    status: str
    demand: float | None
    capacity: float | None
    ratio: float | None
    evidence: Mapping[str, object]
    messages: tuple[str, ...]
    story: str | None = None
    section: str | None = None
    unit: str | None = None
    code_ref: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _checks() -> list[FakeCheckResult]:
    return [
        FakeCheckResult(
            id="beam_geometry:B1:S1",
            component="B1",
            check_type="beam_geometry",
            story="S1",
            section="B30x60",
            status="OK",
            ratio=0.75,
            demand=300.0,
            capacity=250.0,
            unit="mm",
            messages=("geometry ok",),
            evidence={"source_table": "beam_design_summary", "source_row": 1, "source_columns": ["Story", "Frame"]},
        ),
        FakeCheckResult(
            id="beam_flexure:B1:S1",
            component="B1",
            check_type="beam_flexure",
            story="S1",
            section="B30x60",
            status="FAIL",
            ratio=1.2,
            demand=120.0,
            capacity=100.0,
            unit="cm²",
            messages=("flexure fail",),
            evidence={
                "source_table": "beam_flexure_envelope",
                "source_row": 2,
                "i_top_selected_rebar": "4Ø14",
                "i_top_required_area": 5.59,
                "i_top_selected_area": 6.16,
                "B": 0.30,
                "H": 0.60,
                "L": 5.60,
                "total_required_area": 12.0,
                "total_selected_area": 13.0,
            },
        ),
        FakeCheckResult(
            id="beam_shear:B2:S1",
            component="B2",
            check_type="beam_shear",
            story="S1",
            section="B25x50",
            status="OK",
            ratio=0.91,
            demand=44.0,
            capacity=80.0,
            unit="kN",
            messages=("shear ok",),
            evidence={
                "source_table": "beam_shear_envelope",
                "source_row": 3,
                "Vd": 44.0,
                "P": 0.0,
                "min_leg_count": 2,
                "selected_leg_count": 2,
                "stirrup_diameter": 10,
                "leg_diameter_label": "2Φ10",
                "B": 0.25,
                "H": 0.50,
                "d": 0.46,
                "Asmin_cm2": 1.20,
                "Asw_cm2": 1.57,
                "Vmax": 180.0,
                "section_control_ratio": 0.24,
                "Vc": 20.0,
                "Vw": 60.0,
                "Vr": 80.0,
            },
        ),
        FakeCheckResult(
            id="beam_shear:B3:S1",
            component="B3",
            check_type="beam_shear",
            story="S1",
            section="B25x50",
            status="NO_DATA",
            ratio=None,
            demand=None,
            capacity=None,
            unit="kN",
            messages=("missing shear",),
            evidence={"source_table": "beam_shear_envelope", "missing_inputs": ["shear"]},
        ),
    ]


def test_reporting_facade_generates_checkresult_only_reports(tmp_path: Path) -> None:
    checks = _checks()

    result = ReportingFacade(tmp_path).generate(checks)

    json_path = Path(result.json_report)
    assert json_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert set(payload) == {"summary", "checks"}
    assert payload["summary"] == {
        "total_checks": 4,
        "ok": 2,
        "fail": 1,
        "warning": 0,
        "no_data": 1,
        "error": 0,
        "unique_components": 3,
        "duplicate_check_ids": 0,
        "beam_shear_checks": 2,
        "beam_flexure_checks": 1,
        "beam_geometry_checks": 1,
    }
    assert [row["check_type"] for row in payload["checks"]] == ["beam_geometry", "beam_flexure", "beam_shear", "beam_shear"]

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
        "json_snapshot",
        "excel_snapshot",
        "action_summary",
    }
    assert forbidden_json_fields.isdisjoint(payload)
    assert not (tmp_path / "history").exists()

    if result.excel_report is None:
        pytest.skip("openpyxl is not available")

    openpyxl = pytest.importorskip("openpyxl")
    excel_path = Path(result.excel_report)
    assert excel_path.exists()
    wb = openpyxl.load_workbook(excel_path)
    assert set(wb.sheetnames) == EXPECTED_SHEETS
    assert "Eval_Skipped" not in wb.sheetnames
    assert "Eval_Errors" not in wb.sheetnames
    assert "Report_Contract" not in wb.sheetnames
    assert "Details" not in wb.sheetnames

    shear = wb["Kiriş Kesme"]
    assert shear["A1"].value == "KİRİŞ KESME KAPASİTE HESABI"
    assert [shear.cell(row=16, column=i).value for i in range(1, len(SHEAR_COLUMNS) + 1)] == SHEAR_COLUMNS
    assert shear.cell(row=17, column=2).value == "B2"
    assert shear.cell(row=17, column=4).value == 44.0
    assert shear.cell(row=17, column=20).value == 91.0
    assert shear.cell(row=17, column=21).value == "✓"
    assert shear.cell(row=18, column=4).value == "NO_DATA"

    flexure = wb["Kiriş Donatı Seçimi"]
    assert flexure["A1"].value == "KİRİŞ DONATI SEÇİMİ"
    assert [flexure.cell(row=15, column=i).value for i in range(1, len(FLEXURE_COLUMNS) + 1)] == FLEXURE_COLUMNS
    assert flexure.cell(row=16, column=2).value == "B1"
    assert flexure.cell(row=16, column=4).value == "4Ø14"
    assert flexure.cell(row=16, column=21).value == 120.0
    assert flexure.cell(row=16, column=22).value == "✗"

    beam_checks = wb["Beam Checks"]
    assert beam_checks.cell(row=4, column=5).value == "✓"

    evidence = wb["Evidence"]
    assert evidence.cell(row=3, column=1).value == "Check ID"
    assert evidence.cell(row=4, column=4).value == "beam_design_summary"
    assert evidence.cell(row=5, column=4).value == "beam_flexure_envelope"
