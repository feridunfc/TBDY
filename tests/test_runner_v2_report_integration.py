from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Mapping

from tbdy_engine.runner_v2 import TBDYEngineV2


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


class FakeSchedulerResult:
    def to_eval_results(self) -> dict[str, object]:
        return {
            "results": {"BEAM_DESIGN": {"geometry": {"status": "OK"}}},
            "errors": {},
            "skipped": {},
            "execution_order": ["BEAM_DESIGN"],
            "cache_stats": {"hits": 0},
        }


class FakeCheckAdapter:
    def __init__(self, checks: list[FakeCheckResult]) -> None:
        self._checks = checks

    def adapt_all(self, eval_results: dict[str, object]) -> list[FakeCheckResult]:
        assert "results" in eval_results
        return self._checks


def test_runner_passes_only_check_results_to_reporting_facade(monkeypatch, tmp_path: Path) -> None:
    checks = [
        FakeCheckResult("beam_geometry:B1", "B1", "beam_geometry", "OK", 1.0, 1.0, 1.0, {}, ("ok",)),
        FakeCheckResult("beam_shear:B2", "B2", "beam_shear", "FAIL", 2.0, 1.0, 2.0, {}, ("fail",)),
    ]
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class FakeReportingFacade:
        def __init__(self, report_dir: Path) -> None:
            self.report_dir = report_dir

        def generate(self, *args: object, **kwargs: object) -> SimpleNamespace:
            calls.append((args, kwargs))
            return SimpleNamespace(json_report="engine_report.json", excel_report="engine_report.xlsx")

    monkeypatch.setattr("tbdy_engine.runner_v2.ReportingFacade", FakeReportingFacade)

    engine = object.__new__(TBDYEngineV2)
    engine.ctx = object()
    engine.report_dir = tmp_path
    engine.runtime_catalog = object()
    engine.check_adapter = FakeCheckAdapter(checks)

    monkeypatch.setattr(engine, "validate", lambda: [])
    monkeypatch.setattr(engine, "_run_scheduler", lambda: FakeSchedulerResult())

    result = engine.run()

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == (checks,)
    assert kwargs == {}

    assert result["reports"] == {
        "json": "engine_report.json",
        "excel": "engine_report.xlsx",
    }
    assert "json_snapshot" not in result["reports"]
    assert "excel_snapshot" not in result["reports"]
    assert "action_summary" not in result["reports"]
    assert result["summary"]["total_checks"] == 2
    assert result["summary"]["ok"] == 1
    assert result["summary"]["fail"] == 1
