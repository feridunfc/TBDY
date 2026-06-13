from collections.abc import Mapping
from pathlib import Path

import jsonschema
import pytest

from tbdy_engine.contracts.loader import ContractConstitutionLoader
from tbdy_engine.coverage.builder import CoverageBuilder
from tbdy_engine.coverage.models import CoverageRow, CoverageStatus
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "tbdy_engine" / "catalogs"


def thaw(value):
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value


def load_bundle():
    return ContractConstitutionLoader(CATALOG_DIR).load()


def snapshot(features):
    return FeatureSnapshot(component_type="beam", component_id="B1", identity={"component": "B1"}, features=features)


def evidence(status=FeatureEvidenceStatus.FULL):
    kwargs = dict(
        evidence_status=status,
        source_table="concrete_beam_design_summary",
        actual_table_name="Concrete Beam Design Summary",
        source_column="TopArea",
        source_row={"Frame": "B1"},
        raw_value=1000,
        normalized_value=1000,
        unit="mm2",
        resolver="test",
    )
    if status != FeatureEvidenceStatus.FULL:
        kwargs["reason"] = "evidence incomplete"
        if status == FeatureEvidenceStatus.PARTIAL:
            kwargs["source_column"] = None
    return FeatureEvidence(**kwargs)


def feature(name, *, status=FeatureValueStatus.RESOLVED, ev_status=FeatureEvidenceStatus.FULL):
    return FeatureValue(
        feature_name=name,
        value=1000 if status != FeatureValueStatus.MISSING else None,
        unit="mm2",
        semantic_role="ETABS_REQUIRED_REBAR",
        status=status,
        evidence=[evidence(ev_status)],
    )


def test_blocked_missing_etabs_feature_reports_table_source_details():
    bundle = load_bundle()
    row = CoverageBuilder(bundle).build_row(
        snapshot({}),
        "beam_geometry_min_width",
        design_context={"ductility_class": "HIGH"},
    )
    assert row.coverage_status == CoverageStatus.BLOCKED
    etabs_source = row.missing_feature_sources["beam_width_mm"]
    assert etabs_source.source_kind.value == "etabs_table"
    assert etabs_source.table_key == "frame_section_properties"
    assert etabs_source.table_aliases
    assert "Width" in etabs_source.field_aliases
    assert etabs_source.combo_family == "NONE"
    assert etabs_source.aggregation == "none"


def test_blocked_missing_computed_feature_reports_custom_resolver_inputs():
    bundle = load_bundle()
    row = CoverageBuilder(bundle).build_row(
        snapshot({"beam_width_mm": feature("beam_width_mm")}),
        "beam_flexure_top_selected_ge_governing_required",
        design_context={"ductility_class": "HIGH"},
    )
    source = row.missing_feature_sources["beam_As_top_engine_selected_mm2"]
    assert source.source_kind.value == "computed"
    assert source.custom_resolver == "engine_selected_rebar_resolver"
    assert source.required_inputs == ("beam_As_top_governing_required_mm2",)
    assert source.unit == "mm2"


def test_partial_evidence_reports_expected_evidence_fields():
    bundle = load_bundle()
    snap = snapshot({"beam_width_mm": feature("beam_width_mm", ev_status=FeatureEvidenceStatus.PARTIAL)})
    row = CoverageBuilder(bundle).build_row(snap, "beam_geometry_min_width", design_context={"ductility_class": "HIGH"})
    assert row.coverage_status == CoverageStatus.PARTIAL
    assert "beam_width_mm" in row.expected_evidence_requirements
    assert "source_table" in row.expected_evidence_requirements["beam_width_mm"]
    assert row.source_diagnostics


def test_missing_feature_sources_validate_against_schema():
    bundle = load_bundle()
    row = CoverageBuilder(bundle).build_row(snapshot({}), "beam_geometry_min_width", design_context={"ductility_class": "HIGH"})
    schema = thaw(bundle.schema("coverage_matrix.schema.json"))
    jsonschema.validate({"contract_version": "1.0", "checks": [row.as_schema_check_item()]}, schema)


def test_coverage_row_rejects_ratio_fields_checkresult_and_decision_statuses():
    with pytest.raises((TypeError, ValueError)):
        CoverageRow(check_id="x", component_type="beam", component_id="B1", coverage_status="RUNNABLE", ratio=1.0)
    with pytest.raises(ValueError):
        CoverageRow(check_id="x", component_type="beam", component_id="B1", coverage_status="RUNNABLE", reason="CheckResult")
    with pytest.raises(ValueError):
        CoverageRow(check_id="x", component_type="beam", component_id="B1", coverage_status="RUNNABLE", reason="'FAIL'")
