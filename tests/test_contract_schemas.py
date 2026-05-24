from __future__ import annotations
from pathlib import Path
from tbdy_engine.contracts.export_schema import export_all_schemas
from tbdy_engine.contracts.loader import EngineContractLoader
from tbdy_engine.contracts.validator import EngineContractValidator
ROOT = Path(__file__).resolve().parents[1]

def test_contracts_load_with_pydantic():
    b = EngineContractLoader.from_project_root(ROOT).load(include_legacy=True)
    assert b.datasets.datasets and b.evaluations.evaluations and b.checks.checks and b.combos.combo_families and b.reports.reports

def test_runtime_catalog_builds():
    c = EngineContractLoader.from_project_root(ROOT).build_runtime_catalog(include_legacy=True)
    assert "column_geometry" in c.checks
    assert "beam_flexure" in c.checks
    assert "wall_shear" in c.checks

def test_all_checks_have_valid_evaluation():
    loader = EngineContractLoader.from_project_root(ROOT)
    b = loader.load(include_legacy=True)
    c = loader.build_runtime_catalog(include_legacy=True)
    errors = EngineContractValidator(b, c).validate()
    assert not [e for e in errors if "references missing evaluation" in e]

def test_all_combo_families_exist():
    loader = EngineContractLoader.from_project_root(ROOT)
    b = loader.load(include_legacy=True)
    c = loader.build_runtime_catalog(include_legacy=True)
    errors = EngineContractValidator(b, c).validate()
    assert not [e for e in errors if "uses combo family" in e]

def test_schema_export_works(tmp_path):
    names = {p.name for p in export_all_schemas(tmp_path)}
    assert "datasets.schema.json" in names
    assert "runtime_catalog.schema.json" in names

def test_existing_14_check_ids_preserved():
    c = EngineContractLoader.from_project_root(ROOT).build_runtime_catalog(include_legacy=True)
    expected = {
        "column_geometry","column_axial","column_pmm","column_shear","column_confinement",
        "column_capacity_hierarchy","column_rebar_minimum","column_design_full",
        "beam_geometry","beam_flexure","beam_shear","beam_ductility","beam_capacity_hierarchy","beam_design_full",
    }
    assert expected.issubset(set(c.checks))

def test_wall_checks_are_experimental_or_disabled():
    c = EngineContractLoader.from_project_root(ROOT).build_runtime_catalog(include_legacy=True)
    walls = [x for x in c.checks.values() if x.evaluation == "WALL_DESIGN"]
    assert walls
    assert all(x.experimental for x in walls)
