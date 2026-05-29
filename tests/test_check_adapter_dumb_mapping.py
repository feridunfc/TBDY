from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from tbdy_engine.adapters.check_adapter import CheckAdapter, CheckResult


@dataclass(frozen=True)
class FakeBeamCheckEvaluation:
    check_type: str
    status: str
    demand: float | None
    capacity: float | None
    ratio: float | None
    unit: str | None = None
    code_ref: str | None = None
    messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class FakeBeamEvaluationPackage:
    component: str
    checks: tuple[FakeBeamCheckEvaluation, ...]
    evidence: Mapping[str, object]
    messages: tuple[str, ...] = ()
    story: str | None = None
    section: str | None = None


def test_check_adapter_maps_package_like_input_directly_to_check_results() -> None:
    evidence = {"source_table": "beam_design_summary", "source_row": 4}
    package = FakeBeamEvaluationPackage(
        component="B1",
        story="S1",
        section="B25x50",
        evidence=evidence,
        messages=("package message",),
        checks=(
            FakeBeamCheckEvaluation(
                check_type="beam_geometry",
                status="OK",
                demand=300.0,
                capacity=250.0,
                ratio=1.2,
                unit="mm",
                code_ref="TBDY 2018 §7.4.1",
                messages=("geometry ok",),
            ),
            FakeBeamCheckEvaluation(
                check_type="beam_flexure",
                status="OK",
                demand=100.0,
                capacity=125.0,
                ratio=0.8,
                unit="kNm",
                code_ref="TBDY 2018 §7.4.2",
                messages=("screening source text must not downgrade status",),
            ),
        ),
    )

    results = CheckAdapter().adapt(package)

    assert all(isinstance(result, CheckResult) for result in results)
    assert [result.id for result in results] == ["B1:S1:beam_geometry", "B1:S1:beam_flexure"]
    assert [result.component for result in results] == ["B1", "B1"]
    assert [result.check_type for result in results] == ["beam_geometry", "beam_flexure"]
    assert [result.status for result in results] == ["OK", "OK"]
    assert [result.demand for result in results] == [300.0, 100.0]
    assert [result.capacity for result in results] == [250.0, 125.0]
    assert [result.ratio for result in results] == [1.2, 0.8]
    assert [result.evidence for result in results] == [evidence, evidence]
    assert [result.messages for result in results] == [
        ("package message", "geometry ok"),
        ("package message", "screening source text must not downgrade status"),
    ]
    assert [result.story for result in results] == ["S1", "S1"]
    assert [result.section for result in results] == ["B25x50", "B25x50"]
    assert [result.unit for result in results] == ["mm", "kNm"]
    assert [result.code_ref for result in results] == ["TBDY 2018 §7.4.1", "TBDY 2018 §7.4.2"]


def test_check_adapter_does_not_require_runtime_catalog() -> None:
    package = FakeBeamEvaluationPackage(
        component="B2",
        evidence={},
        checks=(FakeBeamCheckEvaluation("beam_shear", "FAIL", 20.0, 10.0, 2.0),),
    )

    assert CheckAdapter(object()).adapt(package)[0].status == "FAIL"
    assert CheckAdapter(runtime_catalog=object()).adapt(package)[0].status == "FAIL"


def test_check_adapter_adapt_all_is_thin_package_seam() -> None:
    package = FakeBeamEvaluationPackage(
        component="B3",
        evidence={"source_table": "beam_shear_envelope"},
        checks=(FakeBeamCheckEvaluation("beam_shear", "NO_DATA", None, None, None),),
    )

    results = CheckAdapter().adapt_all({"packages": [package]})

    assert len(results) == 1
    assert results[0].id == "B3:beam_shear"
    assert results[0].status == "NO_DATA"


def test_check_adapter_source_guard_removes_discovery_and_inference_logic() -> None:
    source = Path("tbdy_engine/adapters/check_adapter.py").read_text(encoding="utf-8")
    forbidden = [
        "runtime_catalog",
        "checks_by_eval",
        "_index_enabled_checks",
        "fallback_fields",
        "_extract_field",
        "_infer_source",
        "_infer_evaluation_level",
        "evaluation_level",
        "screening_fallback",
        "Approximate/screening OK downgraded",
        "report_tables",
        "_error_result",
        "_no_data_result",
        "_SOURCE_RE",
    ]
    for text in forbidden:
        assert text not in source
