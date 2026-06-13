from pathlib import Path

from tbdy_engine.canonical_tables import DiagnosticCode
from tbdy_engine.providers.table_registry import TableRegistry

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"


def test_table_registry_resolves_canonical_key_to_actual_alias():
    registry = TableRegistry.from_catalog_dir(CATALOG_DIR)
    actual = registry.preferred_actual_name("frame_assignments")
    assert actual
    assert "Frame" in actual


def test_table_registry_resolves_actual_alias_to_canonical_key():
    registry = TableRegistry.from_catalog_dir(CATALOG_DIR)
    actual = registry.preferred_actual_name("frame_assignments")
    assert registry.canonical_key_for_alias(actual) == "frame_assignments"


def test_table_registry_unknown_alias_does_not_crash_and_has_diagnostic():
    registry = TableRegistry.from_catalog_dir(CATALOG_DIR)
    assert registry.canonical_key_for_alias("Unknown ETABS Table") is None
    diagnostic = registry.diagnostic_for_unknown_alias("Unknown ETABS Table")
    assert diagnostic.code == DiagnosticCode.ALIAS_NOT_FOUND
