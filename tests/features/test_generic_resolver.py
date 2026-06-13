import sys
from pathlib import Path

from tbdy_engine.contracts.loader import ContractConstitutionLoader
from tbdy_engine.features.resolver.generic import GenericFeatureResolver
from tbdy_engine.features.value import FeatureValueStatus
from tbdy_engine.providers.fake_etabs import FakeEtabsProvider
from tbdy_engine.providers.table_registry import TableRegistry

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"


def load_bundle():
    return ContractConstitutionLoader(CATALOG_DIR).load()


def make_table(table_key, rows):
    registry = TableRegistry.from_catalog_dir(CATALOG_DIR)
    actual = registry.preferred_actual_name(table_key)
    provider = FakeEtabsProvider(registry=registry, tables={actual: rows})
    return provider.get_table(table_key)


def test_generic_resolver_resolves_simple_geometry_feature_from_fake_provider_table():
    bundle = load_bundle()
    table = make_table("frame_section_properties", [{"SectionName": "B40x70", "Depth": 700, "Width": 400}])
    resolver = GenericFeatureResolver(bundle, [table])
    value = resolver.resolve_feature("beam_width_mm")
    assert value.status == FeatureValueStatus.RESOLVED
    assert value.value == 400
    assert value.evidence[0].source_column == "Width"
    assert value.evidence[0].source_table == "frame_section_properties"


def test_generic_resolver_returns_missing_for_missing_table():
    bundle = load_bundle()
    provider = FakeEtabsProvider(tables={})
    table = provider.get_table("frame_section_properties")
    resolver = GenericFeatureResolver(bundle, [table])
    value = resolver.resolve_feature("beam_width_mm")
    assert value.status == FeatureValueStatus.MISSING
    assert any(diag.code.value == "TABLE_MISSING" for diag in value.diagnostics)


def test_generic_resolver_returns_partial_for_missing_column():
    bundle = load_bundle()
    table = make_table("frame_section_properties", [{"SectionName": "B40x70", "Depth": 700}])
    resolver = GenericFeatureResolver(bundle, [table])
    value = resolver.resolve_feature("beam_width_mm")
    assert value.status == FeatureValueStatus.PARTIAL
    assert any(diag.code.value == "COLUMN_MISSING" for diag in value.diagnostics)


def test_generic_resolver_does_not_emit_ok_fail_or_import_forbidden_modules():
    bundle = load_bundle()
    table = make_table("frame_section_properties", [{"SectionName": "B40x70", "Depth": 700, "Width": 400}])
    resolver = GenericFeatureResolver(bundle, [table])
    payload = resolver.resolve_feature("beam_width_mm").as_dict()
    text = repr(payload)
    assert "OK" not in text
    assert "FAIL" not in text
    forbidden = ["runner_v2", "archx", "runtime", "CheckEngine"]
    tbdy_modules = [module_name for module_name in sys.modules if module_name.startswith("tbdy_engine")]
    for name in forbidden:
        assert not any(name in module_name for module_name in tbdy_modules), name
