from pathlib import Path
from tbdy_engine.runner_v2 import TBDYEngineV2

def test_runner_v2_imports():
    assert TBDYEngineV2 is not None

def test_runner_v2_enabled_evaluations_are_column_and_beam_for_alpha():
    root = Path(__file__).resolve().parents[1]

    class DummyCtx:
        pass

    engine = TBDYEngineV2(
        DummyCtx(),
        contracts_dir=root / "tbdy_engine" / "contracts",
        report_dir=root / "reports_out_test",
        include_legacy=True,
    )
    enabled = engine.enabled_evaluation_ids()

    assert "COLUMN_DESIGN" in enabled
    assert "BEAM_DESIGN" in enabled
    assert "GLOBAL_CHECKS" not in enabled
    assert "JOINT_DESIGN" not in enabled
