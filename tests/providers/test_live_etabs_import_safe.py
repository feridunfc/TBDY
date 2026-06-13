import importlib.util
from pathlib import Path


def _load_module():
    path = Path("tools/smoke_etabs_live_provider.py")
    spec = importlib.util.spec_from_file_location("smoke_etabs_live_provider", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manual_live_etabs_smoke_script_is_import_safe_without_etabs():
    module = _load_module()
    assert hasattr(module, "main")


def test_parse_display_array_result_extracts_headers_and_sample_rows_without_status_emission():
    module = _load_module()
    result = (0, ["Frame", "Output Case", "DesignStatus"], 2, ["B1", "CAP_X_1", "OK", "B2", "CAP_X_2", "FAIL"])
    headers, rows, diagnostics = module._parse_display_array_result(result)
    assert headers == ("Frame", "Output Case", "DesignStatus")
    assert rows[0]["Frame"] == "B1"
    assert rows[0]["DesignStatus"] == "[REDACTED_STATUS_VALUE]"
    assert rows[1]["DesignStatus"] == "[REDACTED_STATUS_VALUE]"
    assert diagnostics


class _FakeDatabaseTables:
    def GetTableForDisplayArray(self, *args):
        assert args[0] == "Element Forces - Beams"
        return (0, ["UniqueName", "Output Case", "M3"], 2, ["B1", "CAP_X_1", "12.5", "B2", "CAP_X_2", "13.5"])


def test_get_table_for_display_helper_returns_headers_and_rows_without_model_mutation():
    module = _load_module()
    headers, rows, diagnostics = module._try_get_table_for_display(_FakeDatabaseTables(), "Element Forces - Beams", 3)
    assert headers == ("UniqueName", "Output Case", "M3")
    assert rows[0]["Output Case"] == "CAP_X_1"
    assert diagnostics
