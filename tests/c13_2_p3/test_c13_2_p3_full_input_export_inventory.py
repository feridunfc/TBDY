from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "inventory_c13_2_p3_full_input_export.py"

REQUIRED_OUTPUTS = {
    "workbook_inventory.json",
    "table_header_inventory.json",
    "table_sample_inventory.json",
    "source_family_fit_report.json",
    "check_engine_source_readiness_inventory.json",
    "wall_pier_story_material_chain_report.json",
    "live_probe_target_recommendations.json",
    "acceptance_policy_recommendations.json",
    "c13_2_p3_full_input_inventory_summary.json",
}


def make_workbook(path: Path) -> None:
    wb = Workbook()
    wb.remove(wb.active)

    def add_sheet(name: str, headers: list[str], rows: list[list[object]], unit_row: list[str] | None = None):
        ws = wb.create_sheet(name)
        ws.append(headers)
        if unit_row:
            ws.append(unit_row)
        for row in rows:
            ws.append(row)

    add_sheet("Story Definitions", ["Story", "Height", "MasterStory"], [["S1", 3.5, "Yes"]], ["", "m", ""])
    add_sheet("Tower and Base Story Definition", ["Tower", "BSElev"], [["Tower1", 0.0]])
    add_sheet("Material Properties - Basic Mechanical Properties", ["Material", "E1", "G12", "U12"], [["C30", 32000, 13000, 0.2]])
    add_sheet("Pier Section Properties", ["Story", "Pier", "Width Bottom", "Thickness Bottom", "Material"], [["S1", "P1", 2.0, 0.25, "C30"]])
    add_sheet("Wall Object Connectivity", ["Story", "Wall", "Point1", "Point2"], [["S1", "W1", "A", "B"]])
    add_sheet("Wall Bays", ["Wall", "Bay", "Story"], [["W1", "B1", "S1"]])
    add_sheet("Area Assigns - Pier Labels", ["Area", "Pier", "Story"], [["A1", "P1", "S1"]])
    add_sheet("Area Assigns - Sect Prop", ["Area", "SectProp", "Story"], [["A1", "W25", "S1"]])
    add_sheet("Wall Property Def - Specified", ["Name", "Material", "Thickness"], [["W25", "C30", 0.25]])
    add_sheet("Frame Assignments - Summary", ["UniqueName", "Label", "Story", "DesignSect"], [["1", "B1", "S1", "B40x70"]])
    add_sheet("Modal Participating Mass Ratios", ["Mode", "Period", "UX", "UY", "SumUX", "SumUY"], [[1, 0.5, .3, .2, .3, .2]])
    add_sheet("Story Drifts", ["Story", "OutputCase", "Direction", "Drift"], [["S1", "EQX", "X", 0.001]])
    add_sheet("Pier Forces", ["Pier", "OutputCase", "P", "V2", "M3"], [["P1", "EQX", 10, 20, 30]])
    wb.save(path)


@pytest.fixture(scope="session")
def inventory_out(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("inventory")
    xlsx = tmp / "input.xlsx"
    out = tmp / "out"
    make_workbook(xlsx)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--xlsx", str(xlsx), "--out", str(out), "--max-sample-rows", "2"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    return out


def load(out: Path, name: str):
    return json.loads((out / name).read_text(encoding="utf-8"))


def families(out: Path):
    return load(out, "source_family_fit_report.json")["families"]


def test_01_script_compiles():
    compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec")


def test_02_missing_xlsx_exits_nonzero(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--xlsx", str(tmp_path / "missing.xlsx"), "--out", str(tmp_path / "out")],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert result.returncode != 0
    assert "Workbook not found" in result.stderr


def test_03_minimal_workbook_writes_all_required_output_files(inventory_out):
    assert REQUIRED_OUTPUTS <= {p.name for p in inventory_out.iterdir()}


def test_04_header_detection_works_with_first_row_headers(inventory_out):
    story = next(row for row in load(inventory_out, "table_header_inventory.json")["tables"] if row["sheet_name"] == "Story Definitions")
    assert story["detected_header_row"] == 1
    assert "story" in story["normalized_columns"]


def test_05_header_detection_tolerates_unit_row_under_headers(inventory_out):
    story_sample = next(row for row in load(inventory_out, "table_sample_inventory.json")["tables"] if row["sheet_name"] == "Story Definitions")
    assert story_sample["sample_rows"][0]["Story"] == "S1"


def test_06_story_definitions_recognized(inventory_out):
    assert families(inventory_out)["story_definitions"]["confidence"] in {"HIGH", "MEDIUM"}


def test_07_bselev_supports_derived_elevation(inventory_out):
    chain = load(inventory_out, "wall_pier_story_material_chain_report.json")
    assert chain["story_elevation_chain"]["derived_elevation_supported"] is True
    assert families(inventory_out)["tower_and_base_story_definition"]["confidence"] in {"HIGH", "MEDIUM"}


def test_08_material_basic_mechanical_with_e1_g12_u12_is_recognized(inventory_out):
    row = families(inventory_out)["material_properties_basic_mechanical"]
    assert row["confidence"] == "HIGH"
    found = " ".join(row["required_columns_found"])
    assert "E1" in found and "G12" in found and "U12" in found


def test_09_pier_section_with_direct_geometry_is_high_confidence(inventory_out):
    assert families(inventory_out)["pier_section_properties"]["confidence"] == "HIGH"


def test_10_pier_section_does_not_require_literal_section_column(inventory_out):
    row = families(inventory_out)["pier_section_properties"]
    assert "Section" not in " ".join(row["required_columns_missing"])


def test_11_wall_object_connectivity_is_supporting_evidence(inventory_out):
    assert families(inventory_out)["wall_object_connectivity"]["matching_sheets"]


def test_12_wall_bays_is_topology_context(inventory_out):
    assert families(inventory_out)["wall_bays"]["matching_sheets"]


def test_13_area_assigns_pier_labels_is_mapping(inventory_out):
    assert families(inventory_out)["area_assigns_pier_labels"]["matching_sheets"]


def test_14_area_assigns_sect_prop_is_mapping(inventory_out):
    assert families(inventory_out)["area_assigns_sect_prop"]["matching_sheets"]


def test_15_wall_property_def_specified_is_material_thickness_definition(inventory_out):
    assert families(inventory_out)["wall_property_def_specified"]["matching_sheets"]


def test_16_frame_assignments_summary_is_identity_evidence(inventory_out):
    assert families(inventory_out)["frame_assignments_summary"]["matching_sheets"]


def test_17_modal_participating_mass_is_modal_global_evidence(inventory_out):
    assert families(inventory_out)["modal_participating_mass"]["matching_sheets"]


def test_18_story_drifts_are_inventory_but_not_check_ready(inventory_out):
    row = families(inventory_out)["story_drifts"]
    assert row["matching_sheets"]
    assert row["check_unlock_allowed"] is False


def test_19_design_outputs_are_semantic_review_required(inventory_out):
    assert families(inventory_out)["pier_forces"]["readiness_hint"] == "SEMANTIC_REVIEW_REQUIRED"


def test_20_check_engine_source_readiness_exists_and_blocks_checks(inventory_out):
    readiness = load(inventory_out, "check_engine_source_readiness_inventory.json")
    assert readiness["check_areas"]
    assert all(row["check_implementation_allowed_now"] is False for row in readiness["check_areas"].values())


def test_21_acceptance_policy_requires_live_before_merge(inventory_out):
    assert load(inventory_out, "acceptance_policy_recommendations.json")["live_required_before_merge"] is True


def test_22_acceptance_policy_promote_now_false(inventory_out):
    assert load(inventory_out, "acceptance_policy_recommendations.json")["promote_now"] is False


def test_23_acceptance_policy_says_excel_is_not_live_proof(inventory_out):
    assert load(inventory_out, "acceptance_policy_recommendations.json")["excel_evidence_is_not_live_proof"] is True


def test_24_every_output_keeps_safe_to_implement_false(inventory_out):
    assert load(inventory_out, "workbook_inventory.json")["safe_to_implement_checks_now"] is False
    assert load(inventory_out, "c13_2_p3_full_input_inventory_summary.json")["safe_to_implement_checks_now"] is False
    assert load(inventory_out, "source_family_fit_report.json")["safe_to_implement_checks_now"] is False
    assert load(inventory_out, "live_probe_target_recommendations.json")["safe_to_implement_checks_now"] is False


def test_25_every_family_and_recommendation_keeps_check_unlock_false(inventory_out):
    for row in families(inventory_out).values():
        assert row["check_unlock_allowed"] is False
    for row in load(inventory_out, "live_probe_target_recommendations.json")["recommendations"]:
        assert row["check_unlock_allowed"] is False


def test_26_no_etabs_com_win32_import_is_used():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    joined = "\n".join(imports).lower()
    assert "comtypes" not in joined
    assert "win32com" not in joined
    assert "etabs.connection" not in joined
