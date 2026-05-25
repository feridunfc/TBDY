from __future__ import annotations

from types import SimpleNamespace

import tbdy_engine.runner_v2 as runner_v2
from tbdy_engine.runner_v2 import TBDYEngineV2


def test_runner_v2_report_payload_keys_remain_backward_compatible(tmp_path, monkeypatch):
    class DummySchedulerResult:
        def to_eval_results(self):
            return {
                "results": {},
                "errors": {},
                "skipped": {},
                "execution_order": ["COLUMN_DESIGN"],
                "cache_stats": {"hits": 0, "misses": 1},
            }

    class DummyScheduler:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self, context):
            return DummySchedulerResult()

    class DummyCheckAdapter:
        def __init__(self, runtime_catalog):
            pass

        def adapt_all(self, eval_results):
            return [SimpleNamespace(status="OK")]

    class DummyReportingFacade:
        def __init__(self, report_dir):
            self.report_dir = report_dir

        def generate(self, checks, eval_results, *, runtime_catalog):
            return SimpleNamespace(
                json_report=str(self.report_dir / "engine_report.json"),
                json_snapshot=str(self.report_dir / "history" / "snapshot_engine_report.json"),
                excel_report=str(self.report_dir / "engine_report.xlsx"),
                excel_snapshot=str(self.report_dir / "history" / "snapshot_engine_report.xlsx"),
                action_summary=[{"check_id": "c1"}],
            )

    monkeypatch.setattr(runner_v2, "RuntimeScheduler", DummyScheduler)
    monkeypatch.setattr(runner_v2, "CheckAdapter", DummyCheckAdapter)
    monkeypatch.setattr(runner_v2, "ReportingFacade", DummyReportingFacade)

    engine = TBDYEngineV2(object(), report_dir=tmp_path)
    result = engine.run()

    assert result["status"] == "OK"
    assert set(result["reports"]) == {
        "json",
        "json_snapshot",
        "excel",
        "excel_snapshot",
        "action_summary",
    }
    assert result["reports"]["json"].endswith("engine_report.json")
    assert result["reports"]["excel"].endswith("engine_report.xlsx")
    assert result["reports"]["action_summary"] == [{"check_id": "c1"}]
    assert set(result) == {
        "status",
        "summary",
        "reports",
        "evaluation_errors",
        "evaluation_skipped",
        "execution_order",
        "cache_stats",
    }
