from __future__ import annotations

from dataclasses import is_dataclass

import pytest

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
        "section": "B40x70",
        "source_table": "Concrete Beam Design Summary - TS 500-2000(R2018)",
        "source_row": 0,
        "source_columns": ["Story", "Label", "DesignSect"],
    }
    flexure_row = {
        "key": "S1|B1",
        "label": "B1",
        "story": "S1",
        "required_area": 8.25,
        "ratio": 0.82,
        "status": "OK",
        "source_table": "Concrete Beam Flexure Envelope - TS 500-2000(R2018)",
        "source_row": 2,
        "source_columns": ["AsTop", "AsBot", "Ratio"],
    }
    shear_row = {
        "key": "S1|B1",
        "label": "B1",
        "story": "S1",
        "shear": 145.0,
        "Vd": 145.0,
        "Vr": 220.0,
        "ratio": 0.66,
        "status": "OK",
        "source_table": "Concrete Beam Shear Envelope - TS 500-2000(R2018)",
        "source_row": 4,
        "source_columns": ["V", "Ratio"],
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
    assert package.section == "B40x70"
    assert package.messages == ()
    assert package.evidence["key"] == "S1|B1"
    assert package.evidence["source_table"] == "Concrete Beam Design Summary - TS 500-2000(R2018)"
    assert package.evidence["source_row"] == 0
    assert package.evidence["source_columns"] == ("Story", "Label", "DesignSect")
    assert [check.check_type for check in package.checks] == ["beam_geometry", "beam_flexure", "beam_shear"]


def test_beam_package_enriches_shear_evidence_from_normalized_rows() -> None:
    package = build_beam_evaluation_packages(_context())[0]
    evidence = package.evidence
    shear = package.checks[2]

    assert evidence["Vd"] == 145.0
    assert evidence["Vr"] == 220.0
    assert evidence["B"] == 0.40
    assert evidence["H"] == 0.70
    assert evidence["shear_source_table"] == "Concrete Beam Shear Envelope - TS 500-2000(R2018)"
    assert evidence["shear_source_row"] == 4
    assert evidence["shear_source_columns"] == ("V", "Ratio")
    assert shear.demand == 145.0
    assert shear.capacity == 220.0
    assert shear.ratio == pytest.approx(145.0 / 220.0)
    assert shear.unit == "kN"


def test_beam_package_enriches_flexure_evidence_from_normalized_rows() -> None:
    package = build_beam_evaluation_packages(_context())[0]
    evidence = package.evidence
    flexure = package.checks[1]

    assert evidence["total_required_area"] == 8.25
    assert evidence["B"] == 0.40
    assert evidence["H"] == 0.70
    assert evidence["flexure_source_table"] == "Concrete Beam Flexure Envelope - TS 500-2000(R2018)"
    assert evidence["flexure_source_row"] == 2
    assert evidence["flexure_source_columns"] == ("AsTop", "AsBot", "Ratio")
    assert flexure.demand == 8.25
    assert flexure.capacity is None
    assert flexure.ratio == 0.82
    assert flexure.unit == "cm²"


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
    assert [check.demand for check in checks] == [None, 8.25, 145.0]
    assert [check.capacity for check in checks] == [None, None, 220.0]
    assert checks[0].ratio is None
    assert checks[1].ratio == 0.82
    assert checks[2].ratio == pytest.approx(145.0 / 220.0)
    assert all(check.evidence is packages[0].evidence for check in checks)
    assert checks[1].evidence["total_required_area"] == 8.25
    assert checks[2].evidence["Vd"] == 145.0
    assert [check.unit for check in checks] == ["mm", "cm²", "kN"]


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
