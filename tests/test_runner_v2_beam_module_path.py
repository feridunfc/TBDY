from __future__ import annotations

import importlib
from pathlib import Path

import yaml

from tbdy_engine.design.beams.evaluation_package import BeamDesignModule, BeamEvaluationPackage
from tbdy_engine.runner_v2 import TBDYEngineV2


EXPECTED_MODULE_PATH = "tbdy_engine.design.beams.evaluation_package.BeamDesignModule"


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
            "beam_flexure_grouped": {},
            "beam_shear_grouped": {},
        }
    }


def _beam_design_config() -> dict[str, object]:
    config_path = Path("tbdy_engine/contracts/evaluations.yaml")
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return payload["evaluations"]["BEAM_DESIGN"]


def test_beam_design_config_points_to_active_module_path() -> None:
    config = _beam_design_config()

    assert config["module"] == EXPECTED_MODULE_PATH
    assert config["method"] == "run"


def test_beam_design_config_imports_active_beam_design_module() -> None:
    config = _beam_design_config()
    module_name, class_name = str(config["module"]).rsplit(".", 1)

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)

    assert cls is BeamDesignModule


def test_configured_beam_design_module_run_returns_packages() -> None:
    config = _beam_design_config()
    module_name, class_name = str(config["module"]).rsplit(".", 1)
    cls = getattr(importlib.import_module(module_name), class_name)

    result = getattr(cls(_minimal_context()), str(config["method"]))()

    assert isinstance(result, tuple)
    assert len(result) == 1
    package = result[0]
    assert isinstance(package, BeamEvaluationPackage)
    assert package.component == "B1"
    assert [check.check_type for check in package.checks] == ["beam_geometry", "beam_flexure", "beam_shear"]


def test_runner_make_evaluator_calls_active_beam_design_module() -> None:
    config = _beam_design_config()
    engine = object.__new__(TBDYEngineV2)

    evaluator = engine._make_evaluator("BEAM_DESIGN", config)
    result = evaluator(_minimal_context())

    assert isinstance(result, tuple)
    assert len(result) == 1
    assert isinstance(result[0], BeamEvaluationPackage)
    assert result[0].component == "B1"
    assert [check.check_type for check in result[0].checks] == ["beam_geometry", "beam_flexure", "beam_shear"]
