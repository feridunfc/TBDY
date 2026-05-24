from __future__ import annotations

import json
from types import SimpleNamespace

from tbdy_engine.reports.json_reporter import JSONReporter
from tbdy_engine.reports.report_plan import PlannedReport


class _Check:
    check_id = "column_geometry"
    status = "OK"
    evaluation_level = "DESIGN_LEVEL"
    source = "contract-test"
    category = "GEOMETRY"

    def to_dict(self):
        return {
            "check_id": self.check_id,
            "status": self.status,
            "evaluation_level": self.evaluation_level,
            "source": self.source,
            "category": self.category,
        }


def _planned_report():
    return PlannedReport(
        report_id="full_engine_report",
        formats=("json", "excel"),
        sections=("summary", "columns"),
        include_fields=("check_id", "status"),
        metrics=("total_checks_possible", "coverage_pct"),
    )


def _eval_results():
    return {
        "results": {"COLUMN_DESIGN": {}},
        "errors": {},
        "skipped": {},
        "execution_order": ["COLUMN_DESIGN"],
        "cache_stats": {"hits": 0},
    }


def test_json_reporter_accepts_planned_report_and_keeps_top_level_keys():
    payload = JSONReporter(write_history=False).build_payload(
        [_Check()],
        _eval_results(),
        runtime_catalog=SimpleNamespace(),
        planned_report=_planned_report(),
    )

    assert set(payload) == {
        "report_metadata",
        "summary",
        "checks",
        "evaluation_errors",
        "evaluation_skipped",
        "execution_order",
        "cache_stats",
        "coverage",
        "distributions",
    }


def test_json_reporter_includes_report_contract_metadata_when_planned_report_is_provided():
    payload = JSONReporter(write_history=False).build_payload(
        [_Check()],
        _eval_results(),
        planned_report=_planned_report(),
    )

    assert payload["report_metadata"]["report_contract"] == {
        "report_id": "full_engine_report",
        "formats": ["json", "excel"],
        "sections": ["summary", "columns"],
        "include_fields": ["check_id", "status"],
        "metrics": ["total_checks_possible", "coverage_pct"],
    }


def test_json_reporter_remains_backward_compatible_without_planned_report():
    payload = JSONReporter(write_history=False).build_payload([_Check()], _eval_results())

    assert "report_contract" not in payload["report_metadata"]
    assert payload["checks"] == [_Check().to_dict()]
    assert payload["summary"]["total_checks"] == 1


def test_json_reporter_generate_preserves_engine_report_filename(tmp_path):
    output_path = tmp_path / "engine_report.json"

    result_path = JSONReporter(write_history=False).generate(
        [_Check()],
        _eval_results(),
        output_path=str(output_path),
        planned_report=_planned_report(),
    )

    assert result_path == str(output_path)
    assert output_path.name == "engine_report.json"
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["report_metadata"]["report_contract"]["report_id"] == "full_engine_report"
