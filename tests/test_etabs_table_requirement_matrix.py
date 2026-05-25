from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from tbdy_engine.contracts.loader import EngineContractLoader

from tests.fixtures.legacy_check_matrix_reference import (
    LEGACY_CHECK_MATRIX,
    REQUIRED_MATRIX_FIELDS,
)


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PLANNING_FIELDS = (
    "source_table",
    "source_workbook_or_model",
    "source_row",
    "source_columns",
    "evidence_type",
    "confidence",
    "unit_conversion_status",
    "combo_family_status",
)
MANUAL_OR_NON_LITERAL_KEYS = {
    "beam_transverse_rebar_defs",
    "column_transverse_rebar_defs",
    "beam_forces",
    "beam_rebar_defs",
    "beam_geometry",
    "scwb_capacity_inputs",
    "joint_topology",
    "design_basis.materials_verified",
    "design_basis.materials_present",
}
FORBIDDEN_SECOND_CONTRACT_FILES = (
    ROOT / "docs" / "workbook_manifest.yaml",
    ROOT / "docs" / "sheet_contracts.yaml",
    ROOT / "docs" / "unit_contract.yaml",
    ROOT / "docs" / "evidence_contract.yaml",
    ROOT / "tbdy_engine" / "contracts" / "workbook_manifest.yaml",
    ROOT / "tbdy_engine" / "contracts" / "sheet_contracts.yaml",
    ROOT / "tbdy_engine" / "contracts" / "unit_contract.yaml",
    ROOT / "tbdy_engine" / "contracts" / "evidence_contract.yaml",
    ROOT / "tbdy_engine" / "contracts" / "etabs_table_requirements.yaml",
)
FORBIDDEN_IMPORT_PREFIXES = (
    "tbdy_engine.design",
    "tbdy_engine.engine.context_builder",
    "tbdy_engine.runner",
    "tbdy_engine.runner_v2",
    "tbdy_engine.reports",
    "tbdy_engine.adapters",
)

CANDIDATE_ETABS_TABLES: dict[str, list[str]] = {
    "beam_design_summary": [
        "Concrete Beam Design Summary - TS 500-2000(R2018)",
        "Concrete Beam Design Summary",
        "Concrete Beam Flexure Envelope - TS 500-2000(R2018)",
        "Concrete Beam Flexure Envelope -  TS 500-2000(R2018)",
        "Concrete Beam Shear Envelope - TS 500-2000(R2018)",
        "Concrete Beam Shear Envelope -  TS 500-2000(R2018)",
    ],
    "column_design_summary": [
        "Concrete Column Design Summary - TS 500-2000(R2018)",
        "Concrete Column Design Summary",
        "Concrete Column PMM Envelope - TS 500-2000(R2018)",
        "Concrete Column Shear Envelope - TS 500-2000(R2018)",
    ],
    "column_forces": [
        "Element Forces - Columns",
        "Column Forces",
    ],
    "column_rebar_defs": [
        "Column Reinforcement Details",
        "Concrete Column Reinforcing",
    ],
    "scwb_design": [
        "SCWB Ratio Table",
        "Concrete Column Capacity Check",
    ],
    "joint_shear_design": [
        "Joint Shear Design",
        "Concrete Joint Design Summary - TS 500-2000(R2018)",
        "Concrete Joint Design Summary",
        "Concrete Joint Envelope - TS 500-2000(R2018)",
    ],
    "frame_rect_sections": [
        "Frame Section Properties",
        "Frame Sections",
    ],
    "frame_assigns_section": [
        "Frame Assignments - Section Properties",
        "Frame Assignments",
    ],
    "topology": [
        "Objects and Elements - Joints",
        "Connectivity - Frame",
    ],
    "story_drifts": [
        "Story Drifts",
        "Story Max Over Avg Drifts",
    ],
    "story_definitions": [
        "Story Definitions",
    ],
    "modal_mass": [
        "Modal Participating Mass Ratios",
    ],
    "story_forces": [
        "Story Forces",
    ],
}

CURRENT_TO_LEGACY_ALIAS = {
    "beam_shear": "beam_shear",
    "column_shear": "column_shear",
    "column_confinement": "column_confinement",
    "column_axial": "column_axial",
    "beam_flexure": "beam_flexure",
    "column_capacity_hierarchy": "scwb",
    "beam_capacity_hierarchy": "scwb",
    "joint_shear": "joint_shear",
    "global_story_drift": "drift",
    "global_modal_mass": "modal",
    "column_geometry": "joint_dimensions",
    "beam_geometry": "joint_dimensions",
    "column_pmm": "column_axial",
    "column_rebar_minimum": "column_confinement",
    "beam_ductility": "beam_flexure",
}


def _catalog():
    return EngineContractLoader.from_project_root(ROOT).build_runtime_catalog()


def _model_to_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        try:
            return obj.dict()
        except TypeError:
            pass
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return dict(vars(obj))
    return {}


def _split_canonical(value: Any) -> list[str]:
    out: list[str] = []
    if value in (None, ""):
        return out
    values = value if isinstance(value, list) else [value]
    for item in values:
        for token in str(item).split("/"):
            token = token.strip()
            if token:
                out.append(token)
    return out


def _legacy_requirement_keys(spec: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    keys.extend(_split_canonical(spec.get("etabs_canonical")))
    keys.extend(_split_canonical(spec.get("design_table_required", [])))
    deduped: list[str] = []
    for key in keys:
        if key not in deduped:
            deduped.append(key)
    return deduped


def _candidate_tables(keys: list[str]) -> list[str]:
    tables: list[str] = []
    for key in keys:
        for table in CANDIDATE_ETABS_TABLES.get(key, []):
            if table not in tables:
                tables.append(table)
    return tables


def _current_checks() -> dict[str, dict[str, Any]]:
    catalog = _catalog()
    catalog_dict = _model_to_dict(catalog)
    checks = catalog_dict.get("checks", {}) or {}
    return {check_id: _model_to_dict(check) for check_id, check in checks.items()}


def _confidence(check_id: str, check: dict[str, Any], legacy_name: str | None, keys: list[str], tables: list[str]) -> str:
    if not legacy_name or legacy_name not in LEGACY_CHECK_MATRIX:
        return "LOW"
    if check_id == legacy_name and check.get("evaluation") and check.get("evaluation_field") and tables:
        return "HIGH"
    if check.get("evaluation") and check.get("evaluation_field") and tables and keys:
        return "MEDIUM"
    return "LOW"


def _reconciliation_matrix() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for check_id, check in sorted(_current_checks().items()):
        if not bool(check.get("runner_enabled", True)):
            continue
        legacy_name = CURRENT_TO_LEGACY_ALIAS.get(check_id)
        legacy_spec = LEGACY_CHECK_MATRIX.get(legacy_name or "", {})
        keys = _legacy_requirement_keys(legacy_spec) if legacy_spec else []
        tables = _candidate_tables(keys)
        confidence = _confidence(check_id, check, legacy_name, keys, tables)
        entries.append(
            {
                "check_id": check_id,
                "legacy_check": legacy_name,
                "evaluation": check.get("evaluation"),
                "evaluation_field": check.get("evaluation_field"),
                "runner_enabled": bool(check.get("runner_enabled", True)),
                "legacy_canonical_requirements": keys,
                "candidate_etabs_tables": tables,
                "confidence": confidence,
                "source": "legacy_check_matrix_reference + runtime_catalog",
                "notes": (
                    "Audit-only table requirement mapping. Candidate tables are plain strings for future one-at-a-time "
                    "read_etabs_table_on_demand(table_name) use. Evidence planning fields: "
                    + ", ".join(EVIDENCE_PLANNING_FIELDS)
                ),
            }
        )
    return entries


def test_legacy_reference_contains_required_matrix_fields():
    required_checks = {
        "beam_shear",
        "column_shear",
        "column_confinement",
        "column_axial",
        "scwb",
        "beam_flexure",
        "joint_shear",
        "joint_dimensions",
        "drift",
        "modal",
        "second_order",
    }

    assert required_checks.issubset(set(LEGACY_CHECK_MATRIX))
    for name, spec in LEGACY_CHECK_MATRIX.items():
        for field in REQUIRED_MATRIX_FIELDS:
            assert field in spec, (name, field)
            assert spec[field] not in (None, ""), (name, field)
        if spec.get("cross_check") is True:
            assert spec.get("tolerance"), name


def test_candidate_table_mapping_covers_legacy_canonical_keys():
    missing: dict[str, list[str]] = {}
    for name, spec in LEGACY_CHECK_MATRIX.items():
        keys = _legacy_requirement_keys(spec)
        uncovered = [
            key for key in keys
            if key not in CANDIDATE_ETABS_TABLES and key not in MANUAL_OR_NON_LITERAL_KEYS
        ]
        if uncovered:
            missing[name] = uncovered

    assert missing == {}


def test_current_runtime_catalog_checks_reconcile_to_legacy_where_possible():
    matrix = _reconciliation_matrix()
    by_check = {entry["check_id"]: entry for entry in matrix}
    runner_enabled = {
        check_id: check
        for check_id, check in _current_checks().items()
        if bool(check.get("runner_enabled", True))
    }

    assert set(runner_enabled).issubset(set(by_check))
    for check_id, check in runner_enabled.items():
        entry = by_check[check_id]
        assert entry["evaluation"] == check.get("evaluation")
        assert entry["evaluation_field"] == check.get("evaluation_field")
        assert entry["confidence"] in {"HIGH", "MEDIUM", "LOW"}
        if entry["legacy_check"] is not None:
            assert entry["legacy_check"] in LEGACY_CHECK_MATRIX

    assert by_check["column_axial"]["confidence"] == "HIGH"
    assert by_check["beam_flexure"]["confidence"] == "HIGH"
    assert by_check["beam_shear"]["confidence"] == "HIGH"
    assert by_check["column_capacity_hierarchy"]["legacy_check"] == "scwb"


def test_no_live_broad_table_reads_are_added():
    source = Path(__file__).read_text(encoding="utf-8")
    forbidden_raw_com_import = "win32com" + "." + "client"
    forbidden_raw_com_call = "Get" + "Active" + "Object"

    assert forbidden_raw_com_import not in source
    assert forbidden_raw_com_call not in source
    assert "get_table_df(" not in source
    assert "for table_name in CANDIDATE_ETABS_TABLES" not in source
    assert "read_etabs_table_on_demand(" not in source


def test_on_demand_boundary_is_future_reader_contract_without_live_reads():
    from tbdy_engine.etabs.table_access import read_etabs_table_on_demand

    assert callable(read_etabs_table_on_demand)
    for entry in _reconciliation_matrix():
        for table_name in entry["candidate_etabs_tables"]:
            assert isinstance(table_name, str)
            assert table_name.strip() == table_name
            assert table_name


def test_reconciliation_matrix_is_json_serializable():
    payload = _reconciliation_matrix()

    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "candidate_etabs_tables" in encoded
    assert "legacy_canonical_requirements" in encoded


def test_no_second_contract_system_files_exist():
    for path in FORBIDDEN_SECOND_CONTRACT_FILES:
        assert not path.exists(), str(path.relative_to(ROOT))


def test_no_forbidden_production_imports_in_audit_files():
    for relative_path in (
        "tests/test_etabs_table_requirement_matrix.py",
        "tests/fixtures/legacy_check_matrix_reference.py",
    ):
        tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
        imported_modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module)

        forbidden = sorted(
            module_name
            for module_name in imported_modules
            if any(
                module_name == prefix or module_name.startswith(prefix + ".")
                for prefix in FORBIDDEN_IMPORT_PREFIXES
            )
        )
        assert forbidden == []


def test_evidence_planning_fields_are_explicit_in_matrix_entries():
    for entry in _reconciliation_matrix():
        assert entry["notes"]
        for field in EVIDENCE_PLANNING_FIELDS:
            assert field in entry["notes"]
        assert "combo_family_status" in entry["notes"]
        assert "uses_combo" not in entry["notes"]
        assert "message_text" not in entry["notes"]


def test_legacy_design_table_matrix_remains_separate_from_live_proof():
    live_attach = ROOT / "tests" / "test_etabs_live_model_attach.py"
    table_access = ROOT / "tests" / "test_etabs_table_access.py"

    assert live_attach.exists()
    assert table_access.exists()
    assert "TBDY_RUN_ETABS_LIVE_SMOKE" in live_attach.read_text(encoding="utf-8")
    assert "TBDY_RUN_ETABS_LIVE_SMOKE" in table_access.read_text(encoding="utf-8")
    assert "TBDY_RUN_ETABS_LIVE_SMOKE" not in Path(__file__).read_text(encoding="utf-8")
