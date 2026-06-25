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
                root = node.module.split(".", 1)[0]
                assert root not in forbidden_roots, path


def test_write_and_generic_execution_calls_remain_forbidden() -> None:
    forbidden_call_names = {
        "execute_code",
        "SetSection",
        "RunAnalysis",
        "GetObject",
        "CreateObject",
    }

    for path in iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            target = dotted_name(node.func)
            final_name = target.rsplit(".", 1)[-1]
            assert final_name not in forbidden_call_names, (
                f"Forbidden runtime call {target!r} found in {path}"
            )


def test_active_object_and_model_acquisition_are_scoped_to_connection() -> None:
    connection_path = SOURCE_ROOT / "connection.py"

    for path in iter_source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                final_name = dotted_name(node.func).rsplit(".", 1)[-1]
                if final_name == "GetActiveObject":
                    assert path == connection_path, path

            if isinstance(node, ast.Attribute) and node.attr == "SapModel":
                assert path == connection_path, path

        if path not in {connection_path, SOURCE_ROOT / "contracts.py"}:
            assert '"SapModel"' not in path.read_text(encoding="utf-8"), path


def test_platform_dependencies_are_lazy_and_scoped() -> None:
    forbidden_import_roots = {"pythoncom", "win32com", "comtypes"}
    apartment_path = SOURCE_ROOT / "com_apartment.py"
    connection_path = SOURCE_ROOT / "connection.py"

    for path in iter_source_files():
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                assert not roots.intersection(forbidden_import_roots), path
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                assert root not in forbidden_import_roots, path

        if path != apartment_path:
            assert "pythoncom" not in text, path
        if path != connection_path:
            assert "win32com.client" not in text, path

    assert 'import_module("pythoncom")' in apartment_path.read_text(
        encoding="utf-8"
    )
    assert 'import_module("win32com.client")' in connection_path.read_text(
        encoding="utf-8"
    )


def test_source_manifest_declares_read_only_attach_phase() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    manifest = json.loads(
        (repo_root / "provenance" / "SOURCE_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["phase"] == "PHASE_1_3_READ_ONLY_ETABS_ATTACH"
    assert manifest["integration_status"] == "READ_ONLY_ATTACH_IMPLEMENTED"
    assert (
        manifest["runtime_wiring_status"]
        == "ATTACH_ONLY_NOT_LIVE_VERIFIED"
    )
    assert manifest["boundaries"]["integration_performed"] is False
    assert manifest["boundaries"]["production_import_from_vendor_allowed"] is False
    assert manifest["boundaries"]["generic_execute_code_allowed"] is False
