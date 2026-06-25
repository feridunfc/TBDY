from __future__ import annotations

import ast
import json
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PACKAGE_ROOT / "src" / "etabs_gateway"


def iter_source_files() -> list[Path]:
    return sorted(SOURCE_ROOT.glob("*.py"))


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


def test_p1_source_contains_no_write_attach_or_generic_execution_surface() -> None:
    forbidden_call_names = {
        "execute_code",
        "SetSection",
        "RunAnalysis",
        "GetActiveObject",
        "GetObject",
    }

    def dotted_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parent = dotted_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return ""

    for path in iter_source_files():
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                target = dotted_name(node.func)
                final_name = target.rsplit(".", 1)[-1]

                assert final_name not in forbidden_call_names, (
                    f"Forbidden runtime call {target!r} found in {path}"
                )

            if isinstance(node, ast.Attribute):
                target = dotted_name(node)
                segments = target.split(".")

                assert "SapModel" not in segments, (
                    f"Runtime SapModel access {target!r} found in {path}"
                )

def test_platform_com_dependency_is_lazy_and_scoped_to_adapter() -> None:
    forbidden_import_roots = {"pythoncom", "win32com", "comtypes"}
    adapter_path = SOURCE_ROOT / "com_apartment.py"

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

        if path != adapter_path:
            assert "pythoncom" not in text, path

    adapter_text = adapter_path.read_text(encoding="utf-8")
    assert 'import_module("pythoncom")' in adapter_text


def test_source_manifest_declares_com_apartment_binding_phase() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    manifest = json.loads(
        (repo_root / "provenance" / "SOURCE_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["phase"] == "PHASE_1_2_WINDOWS_COM_APARTMENT_BINDING"
    assert manifest["integration_status"] == "PLATFORM_BINDING_ONLY"
    assert manifest["runtime_wiring_status"] == "NONE"
    assert manifest["boundaries"]["integration_performed"] is False
    assert manifest["boundaries"]["production_import_from_vendor_allowed"] is False
    assert manifest["boundaries"]["generic_execute_code_allowed"] is False
