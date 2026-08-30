from __future__ import annotations

import ast
import json
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PACKAGE_ROOT / "src" / "etabs_gateway"


def iter_source_files() -> list[Path]:
    return sorted(SOURCE_ROOT.glob("*.py"))


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def test_production_gateway_does_not_import_vendor_runtime() -> None:
    forbidden_roots = {"etabs_mcp", "vendor"}
    for path in iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                assert not roots.intersection(forbidden_roots), path
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".", 1)[0] not in forbidden_roots, path


def test_write_analysis_table_and_model_mutation_calls_are_forbidden() -> None:
    forbidden = {
        "execute_code", "SetSection", "RunAnalysis", "StartDesign",
        "SetPresentUnits", "SetModelIsLocked", "InitializeNewModel",
        "OpenFile", "Save", "ApplicationStart", "ApplicationExit",
        "GetTableForDisplayArray", "GetAllTables", "GetAvailableTables",
    }
    for path in iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                final_name = dotted_name(node.func).rsplit(".", 1)[-1]
                assert final_name not in forbidden, f"Forbidden {final_name!r} in {path}"


def test_com_discovery_and_sapmodel_acquisition_are_scoped_to_connection() -> None:
    connection_path = SOURCE_ROOT / "connection.py"
    discovery_names = {"GetActiveObject", "GetObject", "GetObjectProcess", "CreateObject"}
    observed_active_object = False
    for path in iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                final_name = dotted_name(node.func).rsplit(".", 1)[-1]
                if final_name in discovery_names:
                    assert path == connection_path, (final_name, path)
                if final_name == "GetActiveObject":
                    observed_active_object = True
            if isinstance(node, ast.Attribute) and node.attr == "SapModel":
                assert path == connection_path, path
    assert observed_active_object is True


def test_metadata_reads_are_scoped_to_context_reader() -> None:
    reader_path = SOURCE_ROOT / "context_reader.py"
    allowed_methods = {"GetVersion", "GetModelFilename", "GetModelIsLocked", "GetPresentUnits"}
    observed: set[str] = set()
    for path in iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            final_name = dotted_name(node.func).rsplit(".", 1)[-1]
            if final_name in allowed_methods:
                assert path == reader_path, (final_name, path)
                observed.add(final_name)
            if final_name == "_invoke":
                assert path == reader_path, path
                assert len(node.args) >= 2
                method_arg = node.args[1]
                assert isinstance(method_arg, ast.Constant) and isinstance(method_arg.value, str)
                if method_arg.value in allowed_methods:
                    observed.add(method_arg.value)
    assert observed == allowed_methods


def test_platform_dependencies_are_lazy_and_scoped() -> None:
    forbidden_import_roots = {"pythoncom", "win32com", "comtypes"}
    apartment_path = SOURCE_ROOT / "com_apartment.py"
    connection_path = SOURCE_ROOT / "connection.py"
    expected = {
        "pythoncom": apartment_path,
        "win32com.client": connection_path,
        "comtypes.client": connection_path,
    }
    observed: set[str] = set()
    for path in iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                assert not roots.intersection(forbidden_import_roots), path
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".", 1)[0] not in forbidden_import_roots, path
            elif isinstance(node, ast.Call) and dotted_name(node.func).rsplit(".", 1)[-1] == "import_module":
                assert node.args and isinstance(node.args[0], ast.Constant)
                module_name = node.args[0].value
                assert isinstance(module_name, str)
                if module_name in expected:
                    observed.add(module_name)
                    assert path == expected[module_name], (module_name, path)
    assert observed == set(expected)


def test_session_layer_contains_no_direct_etabs_com_calls() -> None:
    path = SOURCE_ROOT / "session.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    forbidden = {
        "GetActiveObject", "GetObject", "GetObjectProcess", "CreateObject", "SapModel",
        "GetVersion", "GetModelFilename", "GetModelIsLocked", "GetPresentUnits",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            assert dotted_name(node.func).rsplit(".", 1)[-1] not in forbidden
        if isinstance(node, ast.Attribute):
            assert node.attr not in forbidden


def test_replay_layer_contains_no_com_or_live_etabs_calls() -> None:
    path = SOURCE_ROOT / "replay.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    forbidden = {"GetActiveObject", "SapModel", "RunAnalysis", "GetTableForDisplayArray"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            assert dotted_name(node.func).rsplit(".", 1)[-1] not in forbidden
        if isinstance(node, ast.Attribute):
            assert node.attr not in forbidden
    assert "pythoncom" not in text and "win32com" not in text and "comtypes" not in text


def test_acceptance_layer_does_not_attach_or_mutate_etabs() -> None:
    path = SOURCE_ROOT / "acceptance.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    forbidden_runtime_names = {
        "GetActiveObject",
        "SapModel",
        "GetVersion",
        "GetModelFilename",
        "GetModelIsLocked",
        "GetPresentUnits",
        "RunAnalysis",
        "SetPresentUnits",
        "GetTableForDisplayArray",
    }
    forbidden_import_roots = {
        "pythoncom",
        "win32com",
        "comtypes",
        "etabs_mcp",
        "vendor",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {
                alias.name.split(".", 1)[0]
                for alias in node.names
            }
            assert not roots.intersection(
                forbidden_import_roots
            ), roots

        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            assert root not in forbidden_import_roots, root

        elif isinstance(node, ast.Call):
            final_name = dotted_name(
                node.func
            ).rsplit(".", 1)[-1]

            assert final_name not in forbidden_runtime_names, (
                final_name
            )

            if final_name == "import_module" and node.args:
                module_arg = node.args[0]
                if (
                    isinstance(module_arg, ast.Constant)
                    and isinstance(module_arg.value, str)
                ):
                    root = module_arg.value.split(".", 1)[0]
                    assert root not in forbidden_import_roots, root

        elif isinstance(node, ast.Attribute):
            assert node.attr not in forbidden_runtime_names, (
                node.attr
            )


def test_source_manifest_declares_coverage_orchestration_phase() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    manifest = json.loads((repo_root / "provenance" / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["phase"] == "PHASE_1_11_COVERAGE_BUILDER_ORCHESTRATION"
    assert manifest["integration_status"] == "COVERAGE_BUILDER_ORCHESTRATION_IMPLEMENTED"
    assert manifest["runtime_wiring_status"] == "OFFLINE_AUTHORITATIVE_ORCHESTRATION_VERIFIED"
    assert manifest["boundaries"]["integration_performed"] is True
    assert manifest["boundaries"]["production_import_from_vendor_allowed"] is False
    assert manifest["boundaries"]["generic_execute_code_allowed"] is False
