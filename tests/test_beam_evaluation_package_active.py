from __future__ import annotations

from dataclasses import is_dataclass

from tbdy_engine.adapters.check_adapter import CheckAdapter, CheckResult
from tbdy_engine.design.beams import (
    BeamCheckEvaluation,
    BeamDesignModule,
    BeamEvaluationPackage,
    build_beam_evaluation_packages,
)


def _context() -> dict[str, object]:
    design_row = {
        "key": "S1|B1",
        "label": "B1",
        "story": "S1",
        "section": "B30x60",
        "source_table": "Concrete Beam Design Summary - TS 500-2000(R2018)",
        "source_row": 0,
        "source_columns": ["Story", "Frame", "DesignSect", "Status"],
    }
    flexure_row = {
        "key": "S1|B1",
        "label": "B1",
        "story": "S1",
        "moment": 125.0,
        "ratio": 0.82,
        "status": "OK",
        "source_table": "Concrete Beam Flexure Envelope - TS 500-2000(R2018)",
        "source_row": 1,
        "source_columns": ["Story", "Frame", "M3", "Ratio"],
    }
    shear_row = {
        "key": "S1|B1",
        "label": "B1",
        "story": "S1",
        "shear": 44.0,
        "ratio": 0.91,
        "status": "OK",
        "source_table": "Concrete Beam Shear Envelope - TS 500-2000(R2018)",
        "source_row": 2,
        "source_columns": ["Story", "Frame", "V2", "Ratio"],
    }
    return {
        "design_metadata": {
            "beam_design_summary_rows": [design_row],
            "beam_flexure_grouped": {"S1|B1": {"governing_ratio": flexure_row}},
            "beam_shear_grouped": {"S1|B1": {"governing_ratio": shear_row}},
        }
    }


def test_beam_evaluation_package_shape_is_active_and_minimal() -> None:
    assert is_dataclass(BeamCheckEvaluation)
    assert is_dataclass(BeamEvaluationPackage)
    assert BeamCheckEvaluation.__dataclass_params__.frozen is True
    assert BeamEvaluationPackage.__dataclass_params__.frozen is True

    packages = build_beam_evaluation_packages(_context())

    assert len(packages) == 1
    package = packages[0]
    assert package.component == "B1"
    assert package.story == "S1"
    assert package.section == "B30x60"
    assert package.messages == ()
    assert package.evidence == {
        "key": "S1|B1",
        "source_table": "Concrete Beam Design Summary - TS 500-2000(R2018)",
        "source_row": 0,
        "source_columns": ("Story", "Frame", "DesignSect", "Status"),
    }
    assert [check.check_type for check in package.checks] == ["beam_geometry", "beam_flexure", "beam_shear"]


def test_beam_evaluation_package_adapts_to_canonical_check_results() -> None:
    packages = build_beam_evaluation_packages(_context())
    checks = CheckAdapter().adapt(packages[0])

    assert all(isinstance(check, CheckResult) for check in checks)
    assert [check.id for check in checks] == [
        "B1:S1:beam_geometry",
        "B1:S1:beam_flexure",
        "B1:S1:beam_shear",
    ]
    assert [check.component for check in checks] == ["B1", "B1", "B1"]
    assert [check.check_type for check in checks] == ["beam_geometry", "beam_flexure", "beam_shear"]
    assert [check.status for check in checks] == ["OK", "OK", "OK"]
    assert [check.demand for check in checks] == [None, 125.0, 44.0]
    assert [check.capacity for check in checks] == [None, None, None]
    assert [check.ratio for check in checks] == [None, 0.82, 0.91]
    assert all(check.evidence["key"] == "S1|B1" for check in checks)
    assert [check.unit for check in checks] == ["mm", "kNm", "kN"]


def test_beam_design_module_returns_packages_not_check_results() -> None:
    result = BeamDesignModule(_context()).run()

    assert isinstance(result, tuple)
    assert result
    assert isinstance(result[0], BeamEvaluationPackage)
    assert not isinstance(result[0], CheckResult)


def test_beam_package_source_guard_has_no_archx_or_report_imports() -> None:
    import pathlib

    source = pathlib.Path("tbdy_engine/design/beams/evaluation_package.py").read_text(encoding="utf-8")
    forbidden = [
        "tbdy_engine.archx",
        "ReportingFacade",
        "JSONReporter",
        "ExcelReporter",
        "CheckAdapter",
        "CheckResult",
        "read_etabs_table_on_demand",
        "EngineContractLoader",
        "RuntimeScheduler",
        "EvaluationDAG",
    ]
    for text in forbidden:
        assert text not in source
