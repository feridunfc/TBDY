import sys
from pathlib import Path

from tbdy_engine.canonical_tables import CanonicalTable, DiagnosticCode
from tbdy_engine.providers.fake_etabs import FakeEtabsProvider
from tbdy_engine.providers.table_registry import TableRegistry

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"


def make_provider(tables):
    return FakeEtabsProvider(registry=TableRegistry.from_catalog_dir(CATALOG_DIR), tables=tables, units={"Height": "m"})


def test_fake_provider_returns_known_table():
    registry = TableRegistry.from_catalog_dir(CATALOG_DIR)
    actual = registry.preferred_actual_name("frame_assignments")
    provider = make_provider({actual: [{"Frame": "B1", "Story": "S1", "Section": "B40x70"}]})
    table = provider.get_table("frame_assignments")
    assert isinstance(table, CanonicalTable)
    assert table.table_key == "frame_assignments"
    assert table.actual_table_name == actual
    assert table.rows[0]["Frame"] == "B1"
    assert not table.diagnostics


def test_fake_provider_returns_missing_table_diagnostic_without_crash():
    table = make_provider({}).get_table("frame_assignments")
    assert isinstance(table, CanonicalTable)
    assert table.table_key == "frame_assignments"
    assert table.rows == ()
    assert table.columns == ()
    assert table.diagnostics[0].code == DiagnosticCode.TABLE_MISSING


def test_fake_provider_returns_empty_table_diagnostic():
    registry = TableRegistry.from_catalog_dir(CATALOG_DIR)
    actual = registry.preferred_actual_name("frame_assignments")
    table = make_provider({actual: []}).get_table("frame_assignments")
    assert isinstance(table, CanonicalTable)
    assert table.diagnostics[0].code == DiagnosticCode.TABLE_EMPTY


def test_provider_does_not_import_forbidden_architecture_modules_or_emit_check_results():
    forbidden = ["runner_v2", "archx", "runtime", "CheckEngine", "FeatureResolver"]
    tbdy_modules = [module_name for module_name in sys.modules if module_name.startswith("tbdy_engine")]
    for name in forbidden:
        assert not any(name in module_name for module_name in tbdy_modules), name
    table = make_provider({}).get_table("frame_assignments")
    payload = table.as_dict()
    text = repr(payload)
    assert "CheckResult" not in text
    assert "OK" not in text
    assert "FAIL" not in text
