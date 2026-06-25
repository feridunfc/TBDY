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


def test_write_analysis_table_and_generic_execution_calls_are_forbidden() -> None:
    forbidden_call_names = {
        "execute_code",
        "SetSection",
        "RunAnalysis",
        "SetPresentUnits",
        "SetModelIsLocked",
        "InitializeNewModel",
        "OpenFile",
        "Save",
        "ApplicationStart",
        "ApplicationExit",
        "GetObject",
        "CreateObject",
        "GetTableForDisplayArray",
        "GetAllTables",
        "GetAvailableTables",
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


def test_metadata_reads_are_scoped_to_context_reader() -> None:
    reader_path = SOURCE_ROOT / "context_reader.py"
    allowed_methods = {
        "GetVersion",
        "GetModelFilename",
        "GetModelIsLocked",
        "GetPresentUnits",
    }

    observed: set[str] = set()

    for path in iter_source_files():
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            target = dotted_name(node.func)
            final_name = target.rsplit(".", 1)[-1]

            if final_name in allowed_methods:
                assert path == reader_path, (
                    f"Metadata call {final_name!r} found in {path}"
                )
                observed.add(final_name)

            if final_name == "_invoke":
                assert path == reader_path, (
                    f"_invoke runtime boundary found outside reader: {path}"
                )

                assert len(node.args) >= 2, (
                    "_invoke must receive target and method name."
                )

                method_arg = node.args[1]
                assert isinstance(method_arg, ast.Constant), (
                    "_invoke method name must be a literal string."
                )
                assert isinstance(method_arg.value, str), (
                    "_invoke method name must be a string."
                )

                method_name = method_arg.value
                if method_name in allowed_methods:
                    observed.add(method_name)

    assert observed == allowed_methods


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


def test_session_layer_contains_no_direct_etabs_com_calls() -> None:
    session_path = SOURCE_ROOT / "session.py"
    tree = ast.parse(
        session_path.read_text(encoding="utf-8"),
        filename=str(session_path),
    )
    forbidden = {
        "GetActiveObject",
        "SapModel",
        "GetVersion",
        "GetModelFilename",
        "GetModelIsLocked",
        "GetPresentUnits",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            final_name = dotted_name(node.func).rsplit(".", 1)[-1]
            assert final_name not in forbidden, final_name
        if isinstance(node, ast.Attribute):
            assert node.attr not in forbidden, node.attr


def test_replay_layer_contains_no_com_or_live_etabs_calls() -> None:
    replay_path = SOURCE_ROOT / "replay.py"
    text = replay_path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(replay_path))
    forbidden_names = {
        "GetActiveObject",
        "SapModel",
        "GetVersion",
        "GetModelFilename",
        "GetModelIsLocked",
        "GetPresentUnits",
        "RunAnalysis",
        "GetTableForDisplayArray",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            final_name = dotted_name(node.func).rsplit(".", 1)[-1]
            assert final_name not in forbidden_names, final_name
        if isinstance(node, ast.Attribute):
            assert node.attr not in forbidden_names, node.attr

    assert "pythoncom" not in text
    assert "win32com" not in text
    assert "comtypes" not in text


def test_source_manifest_declares_fixture_replay_phase() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    manifest = json.loads(
        (repo_root / "provenance" / "SOURCE_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["phase"] == "PHASE_1_6_FIXTURE_REPLAY"
    assert manifest["integration_status"] == "FIXTURE_REPLAY_IMPLEMENTED"
    assert (
        manifest["runtime_wiring_status"]
        == "OFFLINE_REPLAY_VERIFIED_NOT_LIVE"
    )
    assert manifest["boundaries"]["integration_performed"] is False
    assert manifest["boundaries"]["production_import_from_vendor_allowed"] is False
    assert manifest["boundaries"]["generic_execute_code_allowed"] is False
