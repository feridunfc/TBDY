from pathlib import Path

from tbdy_engine.audit.etabs_table_fit import EtabsTableFitAuditor
from tbdy_engine.audit.models import AuditStatus
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.providers.fake_etabs import FakeEtabsProvider
from tbdy_engine.providers.table_registry import TableRegistry


REAL_SMOKE_TABLE_NAMES = {
    "Concrete Beam Design Summary - TS 500-2000(R2018)": [{"Frame": "B1", "Story": "S1", "Station": 0, "TopArea": 10, "BotArea": 12, "VRebar": 1}],
    "Concrete Beam Flexure Envelope - TS 500-2000(R2018)": [{"Frame": "B1", "Story": "S1"}],
    "Concrete Beam Flexure Envelope -  TS 500-2000(R2018)": [{"Frame": "B1", "Story": "S1"}],
    "Concrete Beam Shear Envelope - TS 500-2000(R2018)": [{"Frame": "B1", "Story": "S1"}],
    "Concrete Beam Shear Envelope -  TS 500-2000(R2018)": [{"Frame": "B1", "Story": "S1"}],
    "Concrete Column Design Summary - TS 500-2000(R2018)": [{"Frame": "C1", "Story": "S1"}],
    "Concrete Column PMM Envelope - TS 500-2000(R2018)": [{"Frame": "C1", "Story": "S1"}],
    "Concrete Column Shear Envelope -  TS 500-2000(R2018)": [{"Frame": "C1", "Story": "S1"}],
    "Shear Wall Pier Design Summary - TS 500-2000(R2018)": [{"Pier": "P1", "Story": "S1"}],
    "Pier Section Properties": [{"Pier": "P1", "Story": "S1", "Width Bottom": 3.0, "Thickness Bottom": 0.25}],
    "Pier Forces": [{"Pier": "P1", "Story": "S1", "Output Case": "CAP_X_1", "P": 1, "V2": 2, "M3": 3}],
    "Shear Wall Design Load Combination Data": [{"Combo": "CAP_X_1"}],
    "Shear Wall Design Preferences - TS 500-2000(R2018)": [{"Item": "x"}],
    "Shear Wall Pier Design Overwrites - TS 500-2000(R2018)": [{"Pier": "P1"}],
    "Material Properties - Concrete Data": [{"Material": "C30", "Fc": 30}],
    "Material Properties - Rebar Data": [{"Material": "B420C", "Fy": 420}],
    "Material Properties - Basic Mechanical Properties": [{"Material": "C30"}],
    "Material Properties - General": [{"Material": "C30"}],
    "Concrete Frame Design Load Combination Data": [{"Combo": "DUCTILE_X_1"}],
    "Load Combination Definitions": [{"Combo": "CAP_X_1"}],
    "Load Pattern Definitions": [{"LoadPattern": "G"}],
    "Load Pattern Definitions - Auto Seismic - TSC 2018": [{"LoadPattern": "EX"}],
    "Frame Section Property Definitions - Concrete Rectangular": [{"SectionName": "B40x70", "Depth": 0.7, "Width": 0.4}],
    "Frame Assignments - Summary": [{"Frame": "B1", "UniqueName": "B1", "Label": "B1", "Story": "S1", "Section": "B40x70"}],
}


def _auditor(tables=REAL_SMOKE_TABLE_NAMES):
    return EtabsTableFitAuditor.from_provider(load_contracts(), FakeEtabsProvider(tables=tables))


def test_real_smoke_table_names_map_to_expected_canonical_keys():
    registry = TableRegistry.from_catalog_dir()
    expected = {
        "Concrete Beam Design Summary - TS 500-2000(R2018)": "concrete_beam_design_summary",
        "Concrete Beam Flexure Envelope - TS 500-2000(R2018)": "concrete_beam_flexure_envelope",
        "Concrete Beam Flexure Envelope -  TS 500-2000(R2018)": "concrete_beam_flexure_envelope",
        "Concrete Beam Shear Envelope - TS 500-2000(R2018)": "concrete_beam_shear_envelope",
        "Concrete Column Design Summary - TS 500-2000(R2018)": "concrete_column_design_summary",
        "Concrete Column PMM Envelope - TS 500-2000(R2018)": "concrete_column_pmm_envelope",
        "Concrete Column Shear Envelope -  TS 500-2000(R2018)": "concrete_column_shear_envelope",
        "Shear Wall Pier Design Summary - TS 500-2000(R2018)": "pier_design_summary",
        "Material Properties - Concrete Data": "material_concrete_data",
        "Material Properties - Rebar Data": "material_rebar_data",
        "Load Combination Definitions": "load_combination_definitions",
    }
    for actual, canonical in expected.items():
        assert registry.canonical_key_for_alias(actual) == canonical


def test_duplicate_space_and_case_variants_are_normalized_but_explicit():
    registry = TableRegistry.from_catalog_dir()
    assert registry.canonical_key_for_alias("  concrete beam shear envelope -  TS 500-2000(R2018) ") == "concrete_beam_shear_envelope"
    assert registry.canonical_key_for_alias("Some Unknown ETABS Table") is None


def test_previous_missing_expected_tables_are_matched_when_present_in_inventory():
    reports = {r.table_key: r for r in _auditor().table_contract_fit()}
    for key in [
        "concrete_beam_design_summary",
        "concrete_beam_flexure_envelope",
        "concrete_beam_shear_envelope",
        "concrete_column_design_summary",
        "concrete_column_pmm_envelope",
        "concrete_column_shear_envelope",
        "pier_design_summary",
        "material_concrete_data",
        "material_rebar_data",
        "load_combination_definitions",
    ]:
        assert reports[key].status in {AuditStatus.MATCHED, AuditStatus.PARTIAL}
        assert reports[key].matched_actual_table_name is not None


def test_unmatched_etabs_tables_remain_allowed_inventory_noise():
    auditor = _auditor({"Unmatched Noise Table": [{"A": 1}], **REAL_SMOKE_TABLE_NAMES})
    inventory = {r.actual_table_name: r for r in auditor.table_inventory()}
    assert inventory["Unmatched Noise Table"].matched_by == "none"


def test_column_section_data_is_composite_diagnostic_not_single_missing_table_dependency():
    bundle = load_contracts()
    column_section = bundle.catalog("table_registry.yaml")["tables"]["column_section_data"]
    assert column_section["source_kind"] == "composite"
    assert "frame_section_properties" in column_section["requires_tables"]
    feature_reports = {r.feature_name: r for r in _auditor().feature_source_fit()}
    assert feature_reports["column_width_mm"].table_key == "frame_section_properties"


def test_material_split_tables_are_recognized_by_features():
    reports = {r.feature_name: r for r in _auditor().feature_source_fit()}
    assert reports["concrete_fck_mpa"].table_key == "material_concrete_data"
    assert reports["rebar_fyk_mpa"].table_key == "material_rebar_data"
    assert reports["concrete_fck_mpa"].status == AuditStatus.RESOLVABLE
    assert reports["rebar_fyk_mpa"].status == AuditStatus.RESOLVABLE


def test_beam_column_wall_design_etabs_tables_fit_contract():
    reports = {r.table_key: r for r in _auditor().table_contract_fit()}
    assert reports["concrete_beam_design_summary"].matched_actual_table_name == "Concrete Beam Design Summary - TS 500-2000(R2018)"
    assert reports["concrete_column_design_summary"].matched_actual_table_name == "Concrete Column Design Summary - TS 500-2000(R2018)"
    assert reports["pier_design_summary"].matched_actual_table_name == "Shear Wall Pier Design Summary - TS 500-2000(R2018)"


def test_deep_fit_reports_are_generated(tmp_path: Path):
    auditor = _auditor()
    auditor.write_deep_fit_reports(tmp_path)
    for name in [
        "table_contract_fit_report.json",
        "feature_source_fit_report.json",
        "combo_family_fit_report.json",
        "element_identity_fit_report.json",
        "missing_required_sources.json",
    ]:
        assert (tmp_path / name).exists()
