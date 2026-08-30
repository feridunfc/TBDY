from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FROZEN_BASE = "74d5b6083afed75e44b832336c31755aee482daa"
BASELINE_DIRECT_RAW_OAPI_PRODUCTION_CALLSITE_COUNT = 29
BASELINE_ATTACH_IMPLEMENTATION_COUNT = 3
TARGET_ATTACH_IMPLEMENTATION_COUNT = 1
BASELINE_DATABASETABLES_RAW_ACCESS_FILE_COUNT = 9
BASELINE_RESULTS_SETUP_RAW_ACCESS_FILE_COUNT = 1
BASELINE_PROVIDER_LOCAL_ABI_OWNER_COUNT = 7

BASELINE_ATTACH_IMPLEMENTATIONS = frozenset(
    {
        "tbdy_engine/features/etabs_com_attach.py",
        "tbdy_engine/etabs/connection.py",
        "packages/etabs_gateway/src/etabs_gateway/connection.py",
    }
)


def _production_python_files() -> list[Path]:
    roots = (
        REPO_ROOT / "tbdy_engine",
        REPO_ROOT / "packages" / "etabs_gateway" / "src" / "etabs_gateway",
    )
    files: list[Path] = []
    for root in roots:
        files.extend(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(files)


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _looks_like_etabs_attach_implementation(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if not (
        "CSI.ETABS.API.ETABSObject" in text
        or "ETABSv1.Helper" in text
        or "ETABSv1.ETABSObject" in text
    ):
        return False

    tree = ast.parse(text, filename=str(path))
    attach_methods = {"GetActiveObject", "GetObject", "GetObjectProcess", "CreateObject"}
    return any(
        isinstance(node, ast.Call)
        and _dotted_name(node.func).rsplit(".", 1)[-1] in attach_methods
        for node in ast.walk(tree)
    )


def _production_call_sites(final_names: set[str]) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in _production_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = _dotted_name(node.func)
            final_name = target.rsplit(".", 1)[-1]
            if final_name in final_names:
                found.append((_relative(path), target))
    return found


def test_corrected_phase0_accounting_is_frozen() -> None:
    assert FROZEN_BASE == "74d5b6083afed75e44b832336c31755aee482daa"
    assert BASELINE_ATTACH_IMPLEMENTATION_COUNT == 3
    assert TARGET_ATTACH_IMPLEMENTATION_COUNT == 1
    assert BASELINE_DIRECT_RAW_OAPI_PRODUCTION_CALLSITE_COUNT == 29
    assert BASELINE_DATABASETABLES_RAW_ACCESS_FILE_COUNT == 9
    assert BASELINE_RESULTS_SETUP_RAW_ACCESS_FILE_COUNT == 1
    assert BASELINE_PROVIDER_LOCAL_ABI_OWNER_COUNT == 7


def test_exact_base_attach_census_names_the_three_corrected_locations() -> None:
    assert BASELINE_ATTACH_IMPLEMENTATIONS == {
        "tbdy_engine/features/etabs_com_attach.py",
        "tbdy_engine/etabs/connection.py",
        "packages/etabs_gateway/src/etabs_gateway/connection.py",
    }


def test_no_production_analysis_or_design_execution_calls_exist() -> None:
    assert _production_call_sites({"RunAnalysis", "StartDesign"}) == []


def test_set_present_units_is_confined_to_legacy_unit_context_helper() -> None:
    observed = _production_call_sites({"SetPresentUnits"})
    assert observed
    assert {path for path, _ in observed} == {"tbdy_engine/engine/unit_context.py"}


def test_gateway_public_session_contract_does_not_name_raw_sap_model() -> None:
    session_path = REPO_ROOT / "packages" / "etabs_gateway" / "src" / "etabs_gateway" / "session.py"
    tree = ast.parse(session_path.read_text(encoding="utf-8"), filename=str(session_path))
    public_attributes = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
    }
    assert "sap_model" not in public_attributes
    assert "model_api" not in public_attributes
    assert "application" not in public_attributes


def test_ts500_promotion_mapping_stays_outside_oapi() -> None:
    mapping_name = "ETABS_PATTERN_TYPE_TO_TS500_ACTION"
    oapi_root = REPO_ROOT / "tbdy_engine" / "etabs" / "oapi"
    assert all(mapping_name not in path.read_text(encoding="utf-8") for path in oapi_root.rglob("*.py"))
    ts500_provider = REPO_ROOT / "tbdy_engine" / "providers" / "etabs_ts500_stability_action_provider.py"
    assert mapping_name in ts500_provider.read_text(encoding="utf-8")
