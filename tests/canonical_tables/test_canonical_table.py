import pytest

from tbdy_engine.canonical_tables import CanonicalTable, DiagnosticCode, DiagnosticSeverity, ProviderDiagnostic


def test_canonical_table_validates_required_fields_and_freezes_rows():
    table = CanonicalTable(
        table_key="story_data",
        actual_table_name="Story Data",
        columns=["Story", "Height"],
        rows=[{"Story": "S1", "Height": 3.0}],
        units={"Height": "m"},
        source="FAKE_PROVIDER",
    )
    assert table.table_key == "story_data"
    assert table.columns == ("Story", "Height")
    with pytest.raises(TypeError):
        table.rows[0]["Height"] = 4.0
    with pytest.raises(Exception):
        table.table_key = "x"


def test_canonical_table_diagnostics_work():
    diagnostic = ProviderDiagnostic(
        severity=DiagnosticSeverity.ERROR,
        code=DiagnosticCode.TABLE_MISSING,
        message="missing",
        details={"table_key": "x"},
    )
    table = CanonicalTable(
        table_key="x",
        actual_table_name=None,
        columns=[],
        rows=[],
        units={},
        source="FAKE_PROVIDER",
        diagnostics=[diagnostic],
    )
    assert table.is_missing is True
    assert table.diagnostics[0].as_dict()["code"] == "TABLE_MISSING"


def test_canonical_table_rejects_check_result_and_ok_fail_payloads():
    with pytest.raises(ValueError):
        CanonicalTable(table_key="check_result", columns=[], rows=[], units={}, source="FAKE_PROVIDER")
    with pytest.raises(ValueError):
        CanonicalTable(table_key="frame_assignments", columns=["status"], rows=[{"status": "OK"}], units={}, source="FAKE_PROVIDER")
    with pytest.raises(ValueError):
        CanonicalTable(table_key="frame_assignments", columns=["formula"], rows=[{"formula": "x"}], units={}, source="FAKE_PROVIDER")
