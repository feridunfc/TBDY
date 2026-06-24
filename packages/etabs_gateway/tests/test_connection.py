from pathlib import Path


def test_connection_module_is_explicitly_non_operational_in_p1_0() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "etabs_gateway"
        / "connection.py"
    )
    text = path.read_text(encoding="utf-8")
    assert "contains no COM implementation" in text
