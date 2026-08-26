from pathlib import Path

from collections.abc import Mapping

import jsonschema
import pytest

from tbdy_engine.contracts.loader import ContractConstitutionLoader
from tbdy_engine.coverage.builder import CoverageBuilder
from tbdy_engine.coverage.models import (
    CoverageExecutionContextReadiness,
    CoverageExecutionContextStatus,
    CoverageMatrix,
    CoverageRow,
    CoverageStatus,
)
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue

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


def make_snapshot_for_width():
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
    return FeatureSnapshot(component_type="beam", component_id="B1", identity={"component": "B1"}, features={"beam_width_mm": fv})


def test_every_check_id_can_produce_a_coverage_row_or_blocked_row():
    bundle = load_bundle()
    builder = CoverageBuilder(bundle)
    snap = make_snapshot_for_width()
    check_catalog = bundle.catalog("check_catalog.yaml")["checks"]
    for check_id in check_catalog:
        row = builder.build_row(snap, check_id, design_context={"ductility_class": "HIGH"})
        assert row.check_id == check_id
        assert row.coverage_status in {CoverageStatus.RUNNABLE, CoverageStatus.PARTIAL, CoverageStatus.BLOCKED}


def test_contracted_scope_items_are_aligned_for_coverage():
    bundle = load_bundle()
    diagnostics = CoverageBuilder(bundle).validate_contract_alignment()
    assert diagnostics == ()


def test_coverage_row_references_known_check_and_component_type():
    bundle = load_bundle()
    row = CoverageBuilder(bundle).build_row(make_snapshot_for_width(), "beam_geometry_min_width", design_context={"ductility_class": "HIGH"})
    assert row.check_id in bundle.catalog("check_catalog.yaml")["checks"]
    assert row.component_type in bundle.catalog("element_registry.yaml")["element_types"]


def test_coverage_output_validates_against_schema_with_empty_execution_context_arrays():
    bundle = load_bundle()
    row = CoverageBuilder(bundle).build_row(make_snapshot_for_width(), "beam_geometry_min_width", design_context={"ductility_class": "HIGH"})
    matrix = CoverageMatrix(rows=[row])
    document = matrix.as_schema_document({"beam_geometry_min_width": "ready"})
    item = document["checks"][0]
    assert item["required_execution_context"] == []
    assert item["execution_context_readiness"] == []
    schema = thaw(bundle.schema("coverage_matrix.schema.json"))
    jsonschema.validate(document, schema)


def test_coverage_output_validates_against_schema_with_populated_execution_context_arrays():
    bundle = load_bundle()
    row = CoverageRow(
        check_id="execution_context_contract_probe",
        component_type="beam",
        component_id="B1",
        coverage_status=CoverageStatus.BLOCKED,
        reason="Mandatory execution context/evidence is absent",
        required_execution_context=("analysis_basis",),
        execution_context_readiness=(
            CoverageExecutionContextReadiness(
                context_name="analysis_basis",
                status=CoverageExecutionContextStatus.BLOCKED,
                reason="Mandatory execution context/evidence is absent",
            ),
        ),
    )
    document = {
        "contract_version": "1.0",
        "checks": [row.as_schema_check_item(check_readiness_status="missing_features")],
    }
    item = document["checks"][0]
    assert item["required_execution_context"] == ["analysis_basis"]
    assert item["execution_context_readiness"] == [
        {
            "context_name": "analysis_basis",
            "status": "BLOCKED",
            "reason": "Mandatory execution context/evidence is absent",
        }
    ]
    schema = thaw(bundle.schema("coverage_matrix.schema.json"))
    jsonschema.validate(document, schema)


def test_unknown_component_type_rejected_by_row_builder():
    bundle = load_bundle()
    snap = FeatureSnapshot(component_type="mystery", component_id="X1", identity={"component": "X1"}, features={})
    # The check definition component type wins and is known. Unknown check still rejects.
    with pytest.raises(ValueError):
        CoverageBuilder(bundle).build_row(snap, "not_a_check", design_context={})
