from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _production_python_files() -> list[Path]:
    roots = (
        REPO_ROOT / "tbdy_engine",
        REPO_ROOT / "packages" / "etabs_gateway" / "src" / "etabs_gateway",
    )
    files: list[Path] = []
    for root in roots:
        if root.exists():
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


def _production_call_sites(final_name: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for path in _production_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = _dotted_name(node.func)
            if target.rsplit(".", 1)[-1] == final_name:
                found.append((_relative(path), target))
    return found


def test_b6_p0_does_not_introduce_start_design_execution() -> None:
    assert _production_call_sites("StartDesign") == []


def test_get_results_available_has_one_factual_oapi_owner() -> None:
    observed: list[tuple[str, str]] = []
    for path in _production_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "GetResultsAvailable"
            ):
                observed.append((_relative(path), "getattr:GetResultsAvailable"))
    assert observed == [
        (
            "tbdy_engine/etabs/oapi/concrete_design.py",
            "getattr:GetResultsAvailable",
        )
    ]


def test_b6_p0_integration_has_no_raw_com_or_second_lineage_system() -> None:
    path = REPO_ROOT / "tbdy_engine" / "integration" / "etabs_design_execution.py"
    text = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(text, filename=str(path))

    forbidden_text = {
        "SapModel",
        "pythoncom",
        "win32com",
        "comtypes",
        "GetActiveObject",
        "CreateObject",
        "StartDesign(",
    }
    assert not {item for item in forbidden_text if item in text}

    class_names = {
        node.name
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    }
    assert "DesignStateIdentity" not in class_names
    assert "DesignResultIdentity" not in class_names


def test_canonical_post_design_provider_remains_factual_and_not_execution_owner() -> None:
    path = (
        REPO_ROOT
        / "tbdy_engine"
        / "providers"
        / "etabs_concrete_column_design_result_provider.py"
    )
    text = path.read_text(encoding="utf-8-sig")
    assert "StartDesign(" not in text
    assert "GetResultsAvailable(" not in text
