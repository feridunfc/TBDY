from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tools" / "run_live_vs4b_a15.py"
EXECUTION = ROOT / "tbdy_engine" / "engine" / "project_execution.py"


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


def test_vs4b_runner_imports_only_public_package_execution_boundary():
    tree = _tree(RUNNER)
    tbdy_imports = {
        module for module in _imported_modules(tree) if module.startswith("tbdy_engine")
    }
    assert tbdy_imports == {
        "tbdy_engine.engine.project_execution",
        "tbdy_engine.json_safe",
    }
    calls = _called_names(tree)
    assert "build_vs4b_a15_execution_request" in calls
    assert "execute_live_vs4b_a15" in calls


def test_vs4b_runner_cannot_directly_reach_authoritative_internals():
    modules = _imported_modules(_tree(RUNNER))
    forbidden = {
        "tbdy_engine.regulatory.kernel",
        "tbdy_engine.regulatory.rc_a15_wall_share",
        "tbdy_engine.regulatory.vs4b_program",
        "tbdy_engine.features.etabs_mdev_mo_evidence",
        "tbdy_engine.features._etabs_mdev_mo_evidence_core",
        "tbdy_engine.features.etabs_com_attach",
        "tbdy_engine.etabs.safety",
    }
    assert modules.isdisjoint(forbidden)


def test_project_execution_orchestrates_without_copying_regulatory_rule_logic():
    tree = _tree(EXECUTION)
    modules = _imported_modules(tree)
    assert "tbdy_engine.regulatory.vs4b_program" in modules
    assert "tbdy_engine.regulatory.kernel" not in modules
    assert "tbdy_engine.regulatory.rc_a15_wall_share" not in modules

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
    assert 0.40 not in numbers
    assert 0.75 not in numbers
    assert "A13" not in strings
    assert strings.isdisjoint(
        {
            "LOWER",
            "NOMINAL",
            "UPPER",
            "qualification_branch",
            "effective_parameter_basis",
            "effective_r",
            "effective_d",
            "effective_bys_policy",
        }
    )
