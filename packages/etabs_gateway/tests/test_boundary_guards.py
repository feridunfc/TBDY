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


def test_p1_source_contains_no_write_or_generic_execution_surface() -> None:
    forbidden_tokens = (
        "execute_code",
        "SetSection",
        "RunAnalysis",
        "Analyze.RunAnalysis",
    )

    for path in iter_source_files():
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in text, f"{token!r} found in {path}"


def test_p1_1_source_has_no_platform_com_dependency_yet() -> None:
    forbidden_tokens = ("win32com", "pythoncom", "comtypes")

    for path in iter_source_files():
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in text, f"{token!r} found in {path}"


def test_source_manifest_declares_worker_infrastructure_phase() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    manifest = json.loads(
        (repo_root / "provenance" / "SOURCE_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["phase"] == "PHASE_1_1_DEDICATED_STA_WORKER"
    assert manifest["integration_status"] == "INFRASTRUCTURE_ONLY"
    assert manifest["runtime_wiring_status"] == "NONE"
    assert manifest["boundaries"]["integration_performed"] is False
    assert manifest["boundaries"]["production_import_from_vendor_allowed"] is False
    assert manifest["boundaries"]["generic_execute_code_allowed"] is False
