from __future__ import annotations

import json
from pathlib import Path

import pytest

from tbdy_engine.design.beams.evaluation_package import BeamDesignModule, BeamEvaluationPackage
from tbdy_engine.runner_v2 import TBDYEngineV2


CANONICAL_CHECK_FIELDS = {
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
}

FORBIDDEN_REPORT_FIELDS = {
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


class FakeSchedulerResult:
    def __init__(self, context: dict[str, object]) -> None:
        self.context = context

    def to_eval_results(self) -> dict[str, object]:
        packages = BeamDesignModule(self.context).run()
        assert isinstance(packages, tuple)
        assert all(isinstance(package, BeamEvaluationPackage) for package in packages)
        return {
            "results": {
                "BEAM_DESIGN": packages,
            },
            "errors": {},
            "skipped": {},
            "execution_order": ["BEAM_DESIGN"],
            "cache_stats": {},
        }


def _minimal_context() -> dict[str, object]:
    return {
        "design_metadata": {
            "beam_design_summary_rows": [
                {
                    "key": "S1|B1",
                    "label": "B1",
                    "story": "S1",
                    "section": "B30x60",
                    "source_table": "Concrete Beam Design Summary",
                    "source_row": 0,
                    "source_columns": ["Story", "Frame", "DesignSect", "Status"],
                }
            ],
            "beam_flexure_grouped": {
                "S1|B1": {
                    "governing_ratio": {
                        "moment": 120.0,
                        "ratio": 0.84,
                        "status": "OK",
                    }
                }
            },
            "beam_shear_grouped": {
                "S1|B1": {
                    "governing_ratio": {
                        "shear": 44.0,
                        "ratio": 0.91,
                        "status": "OK",
                    }
                }
            },
        }
    }


def test_runner_v2_produces_json_and_excel_artifacts_from_minimal_beam_context(monkeypatch, tmp_path: Path) -> None:
    context = _minimal_context()
    engine = object.__new__(TBDYEngineV2)
    engine.ctx = context
    engine.report_dir = tmp_path
    engine.runtime_catalog = object()
    engine.check_adapter = __import__("tbdy_engine.adapters.check_adapter", fromlist=["CheckAdapter"]).CheckAdapter()

    monkeypatch.setattr(engine, "validate", lambda: [])
    monkeypatch.setattr(engine, "_run_scheduler", lambda: FakeSchedulerResult(context))

    result = engine.run()

    assert result["status"] == "OK"
    assert result["summary"] == {
        "total_checks": 3,
        "ok": 3,
        "fail": 0,
        "warning": 0,
        "no_data": 0,
        "error": 0,
    }
    assert set(result["reports"]) == {"json", "excel"}
    assert "json_snapshot" not in result["reports"]
    assert "excel_snapshot" not in result["reports"]
    assert "action_summary" not in result["reports"]

    json_path = Path(result["reports"]["json"])
    assert json_path.exists()
    assert json_path.name == "engine_report.json"

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert set(payload) == {"summary", "checks"}
    assert FORBIDDEN_REPORT_FIELDS.isdisjoint(payload)
    assert payload["summary"]["total_checks"] == 3
    assert [check["check_type"] for check in payload["checks"]] == ["beam_geometry", "beam_flexure", "beam_shear"]
    assert [check["component"] for check in payload["checks"]] == ["B1", "B1", "B1"]
    assert [check["status"] for check in payload["checks"]] == ["OK", "OK", "OK"]
    assert [check["demand"] for check in payload["checks"]] == [None, 120.0, 44.0]
    assert [check["ratio"] for check in payload["checks"]] == [None, 0.84, 0.91]
    assert all(set(check) == CANONICAL_CHECK_FIELDS for check in payload["checks"])
    assert all(FORBIDDEN_REPORT_FIELDS.isdisjoint(check) for check in payload["checks"])

    excel_report = result["reports"]["excel"]
    if excel_report is None:
        pytest.skip("openpyxl is not available")

    openpyxl = pytest.importorskip("openpyxl")
    excel_path = Path(excel_report)
    assert excel_path.exists()
    assert excel_path.name == "engine_report.xlsx"

    workbook = openpyxl.load_workbook(excel_path)
    assert set(workbook.sheetnames) == {"Summary", "Checks"}
    assert "Eval_Skipped" not in workbook.sheetnames
    assert "Eval_Errors" not in workbook.sheetnames
    assert "Report_Contract" not in workbook.sheetnames
