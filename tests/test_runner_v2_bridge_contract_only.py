from pathlib import Path
from inspect import signature

from tbdy_engine.runner_v2 import TBDYEngineV2, run_engine_v2

def test_runner_v2_imports():
    assert TBDYEngineV2 is not None

def test_runner_v2_enabled_evaluations_are_column_and_beam_for_alpha():
    root = Path(__file__).resolve().parents[1]

    engine = TBDYEngineV2(
        object(),
        contracts_dir=root / "tbdy_engine" / "contracts",
        report_dir=root / "reports_out_test",
        include_legacy=True,
    )
    enabled = engine.enabled_evaluation_ids()

    assert "COLUMN_DESIGN" in enabled
    assert "BEAM_DESIGN" in enabled
    assert "GLOBAL_CHECKS" not in enabled
    assert "JOINT_DESIGN" not in enabled


def test_runner_v2_default_does_not_load_legacy_contracts():
    root = Path(__file__).resolve().parents[1]

    engine = TBDYEngineV2(
        object(),
        contracts_dir=root / "tbdy_engine" / "contracts",
        report_dir=root / "reports_out_test",
    )

    assert engine.include_legacy is False
    assert engine.bundle.legacy_raw == {}


def test_runner_v2_legacy_loading_requires_explicit_opt_in():
    root = Path(__file__).resolve().parents[1]

    engine = TBDYEngineV2(
        object(),
        contracts_dir=root / "tbdy_engine" / "contracts",
        report_dir=root / "reports_out_test",
        include_legacy=True,
    )

    assert engine.include_legacy is True
    assert engine.bundle.legacy_raw


def test_run_engine_v2_helper_default_is_contract_first():
    assert signature(run_engine_v2).parameters["include_legacy"].default is False
