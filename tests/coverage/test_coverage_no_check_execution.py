import inspect
import sys
from pathlib import Path

from tbdy_engine.contracts.loader import ContractConstitutionLoader
from tbdy_engine.coverage.builder import CoverageBuilder
from tbdy_engine.coverage.models import CoverageStatus
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"


def test_coverage_builder_does_not_import_check_or_legacy_modules():
    forbidden = ["runner_v2", "archx", "runtime", "CheckEngine"]
    tbdy_modules = [module_name for module_name in sys.modules if module_name.startswith("tbdy_engine")]
    for name in forbidden:
        assert not any(name in module_name for module_name in tbdy_modules), name


def test_coverage_builder_does_not_compute_ratio_or_execute_pass_rule():
    source = inspect.getsource(CoverageBuilder)
    forbidden_snippets = ["pass_rule", "ratio", "CheckEngine", "runner_v2", "archx"]
    for snippet in forbidden_snippets:
        assert snippet not in source


def test_coverage_output_contains_no_ok_fail_and_no_check_result():
    bundle = ContractConstitutionLoader(CATALOG_DIR).load()
    ev = FeatureEvidence(
        evidence_status=FeatureEvidenceStatus.FULL,
        source_table="frame_section_properties",
        actual_table_name="Frame Section Properties",
        source_column="Width",
        source_row={"SectionName": "B40x70"},
        raw_value=400,
        normalized_value=400,
        unit="mm",
        resolver="test",
    )
    fv = FeatureValue(feature_name="beam_width_mm", value=400, unit="mm", semantic_role="GEOMETRY", evidence=[ev])
    snap = FeatureSnapshot(component_type="beam", component_id="B1", identity={"component": "B1"}, features={"beam_width_mm": fv})
    row = CoverageBuilder(bundle).build_row(snap, "beam_geometry_min_width", design_context={"ductility_class": "HIGH"})
    assert row.coverage_status == CoverageStatus.RUNNABLE
    text = repr(row.as_dict())
    assert "CheckResult" not in text
    assert "'OK'" not in text
    assert "'FAIL'" not in text
