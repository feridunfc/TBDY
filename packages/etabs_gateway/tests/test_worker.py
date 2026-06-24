from pathlib import Path


def test_worker_module_is_explicitly_non_operational_in_p1_0() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "etabs_gateway"
        / "worker.py"
    )
    text = path.read_text(encoding="utf-8")
    assert "P1.0 defines contracts" in text
