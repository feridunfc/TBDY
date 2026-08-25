from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools" / "run_live_vs5_column_axial.py"
EXECUTION = ROOT / "tbdy_engine" / "engine" / "vs5_column_axial_execution.py"


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def _called_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def test_vs5_runner_imports_only_package_execution_boundary():
    tree = _tree(RUNNER)
    tbdy_imports = {
        module for module in _imported_modules(tree) if module.startswith("tbdy_engine")
    }
    assert tbdy_imports == {
        "tbdy_engine.engine.vs5_column_axial_execution",
        "tbdy_engine.json_safe",
    }
    calls = _called_names(tree)
    assert "build_vs5_column_axial_execution_request" in calls
    assert "execute_live_vs5_column_axial" in calls


def test_vs5_runner_cannot_directly_reach_factual_or_regulatory_authorities():
    modules = _imported_modules(_tree(RUNNER))
    forbidden_prefixes = (
        "tbdy_engine.features",
        "tbdy_engine.checks",
        "tbdy_engine.regulatory",
        "tbdy_engine.etabs",
    )
    assert not any(module.startswith(forbidden_prefixes) for module in modules)


def test_vs5_execution_orchestrates_without_copying_dual_code_rule_logic():
    tree = _tree(EXECUTION)
    modules = _imported_modules(tree)
    assert "tbdy_engine.features.etabs_column_axial_evidence" in modules
    assert "tbdy_engine.regulatory.vs5_column_axial_program" in modules
    assert "tbdy_engine.regulatory.column_axial_dual_code" not in modules
    assert "tbdy_engine.checks.column_axial_selection" in modules

    numbers = {
        float(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }
    strings = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    # Regulatory limits and the TBDY snow coefficient live only in the
    # source-bound selector/formal regulatory modules, never orchestration.
    assert 0.40 not in numbers
    assert 0.90 not in numbers
    assert 0.20 not in numbers
    assert strings.isdisjoint(
        {
            "Ndm <= 0.40 * Ac * fck",
            "Nd <= 0.90 * Ac * fcd; fcd = fck / gamma_mc",
        }
    )


def test_vs5_live_path_declares_no_analysis_design_save_or_property_mutation():
    tree = _tree(EXECUTION)
    called = _called_names(tree)
    forbidden_calls = {
        "RunAnalysis",
        "StartDesign",
        "SetSection",
        "SetMaterial",
        "SetPresentUnits",
        "Save",
        "SaveAs",
    }
    assert called.isdisjoint(forbidden_calls)
