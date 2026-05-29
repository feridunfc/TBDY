from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tbdy_engine.adapters.check_adapter import CheckAdapter, CheckResult
from tbdy_engine.design.beams.evaluation_package import BeamCheckEvaluation, BeamEvaluationPackage
from tbdy_engine.runner_v2 import TBDYEngineV2, _packages_for_adapter, _preserve_package_output


class FakeSchedulerResult:
    def __init__(self, packages: tuple[BeamEvaluationPackage, ...]) -> None:
        self.packages = packages

    def to_eval_results(self) -> dict[str, object]:
        return {
            "results": {
                "BEAM_DESIGN": self.packages,
            },
            "errors": {},
            "skipped": {},
            "execution_order": ["BEAM_DESIGN"],
            "cache_stats": {},
        }


def _package() -> BeamEvaluationPackage:
    return BeamEvaluationPackage(
        component="B1",
        story="S1",
        section="B30x60",
        evidence={"source_table": "beam_design_summary", "source_row": 1},
        messages=("package ok",),
        checks=(
            BeamCheckEvaluation(
                check_type="beam_geometry",
                status="OK",
                demand=None,
                capacity=None,
                ratio=None,
                unit="mm",
                code_ref="TBDY 2018 §7.4.1",
                messages=("geometry ok",),
            ),
            BeamCheckEvaluation(
                check_type="beam_flexure",
                status="OK",
                demand=120.0,
                capacity=None,
                ratio=0.84,
                unit="kNm",
                code_ref="TBDY 2018 §7.4.2",
                messages=("flexure ok",),
            ),
            BeamCheckEvaluation(
                check_type="beam_shear",
                status="NO_DATA",
                demand=None,
                capacity=None,
                ratio=None,
                unit="kN",
                code_ref="TBDY 2018 §7.4.5",
                messages=("missing shear",),
            ),
        ),
    )


def test_runner_preserves_package_tuple_from_evaluator() -> None:
    packages = (_package(),)

    assert _preserve_package_output(packages) is packages
    assert _packages_for_adapter({"results": {"BEAM_DESIGN": packages}}) == {"packages": list(packages)}


def test_runner_beam_package_output_reaches_adapter_and_reports(monkeypatch, tmp_path: Path) -> None:
    packages = (_package(),)
    adapter_inputs: list[dict[str, object]] = []
    report_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class RecordingCheckAdapter(CheckAdapter):
        def adapt_all(self, evaluation_results: dict[str, object]) -> list[CheckResult]:
            adapter_inputs.append(evaluation_results)
            return super().adapt_all(evaluation_results)

    class FakeReportingFacade:
        def __init__(self, report_dir: Path) -> None:
            self.report_dir = report_dir

        def generate(self, *args: object, **kwargs: object) -> SimpleNamespace:
            report_calls.append((args, kwargs))
            return SimpleNamespace(json_report="engine_report.json", excel_report="engine_report.xlsx")

    monkeypatch.setattr("tbdy_engine.runner_v2.ReportingFacade", FakeReportingFacade)

    engine = object.__new__(TBDYEngineV2)
    engine.ctx = object()
    engine.report_dir = tmp_path
    engine.runtime_catalog = object()
    engine.check_adapter = RecordingCheckAdapter()

    monkeypatch.setattr(engine, "validate", lambda: [])
    monkeypatch.setattr(engine, "_run_scheduler", lambda: FakeSchedulerResult(packages))

    result = engine.run()

    assert adapter_inputs == [{"packages": list(packages)}]

    assert len(report_calls) == 1
    args, kwargs = report_calls[0]
    assert kwargs == {}
    assert len(args) == 1
    checks = args[0]
    assert isinstance(checks, list)
    assert all(isinstance(check, CheckResult) for check in checks)
    assert [check.check_type for check in checks] == ["beam_geometry", "beam_flexure", "beam_shear"]
    assert [check.status for check in checks] == ["OK", "OK", "NO_DATA"]
    assert [check.id for check in checks] == [
        "B1:S1:beam_geometry",
        "B1:S1:beam_flexure",
        "B1:S1:beam_shear",
    ]

    assert result["reports"] == {
        "json": "engine_report.json",
        "excel": "engine_report.xlsx",
    }
    assert "json_snapshot" not in result["reports"]
    assert "excel_snapshot" not in result["reports"]
    assert "action_summary" not in result["reports"]
    assert result["summary"]["total_checks"] == 3
    assert result["summary"]["ok"] == 2
    assert result["summary"]["no_data"] == 1
