from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATEWAY = ROOT / "packages" / "etabs_gateway" / "src" / "etabs_gateway"
TBDY = ROOT / "tbdy_engine"

MUTATION_MODULE = "etabs_gateway.mutation_transport"
PRIVATE_MUTATION_SYMBOLS = {
    "_B4T_MUTATION_TRANSPORT_KEY",
    "_execute_bounded_model_mutation",
    "_execute_mutation_on_worker",
}
TRUSTED_FUTURE_CONSUMERS = {
    ROOT / "tbdy_engine" / "etabs" / "safety.py",
}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _tree(path: Path) -> ast.Module:
    return ast.parse(_text(path), filename=str(path))


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _production_python_files() -> tuple[Path, ...]:
    roots = (ROOT / "tbdy_engine", ROOT / "apps", ROOT / "tools")
    return tuple(
        sorted(
            path
            for base in roots
            if base.exists()
            for path in base.rglob("*.py")
        )
    )


def _is_trusted_future_consumer(path: Path) -> bool:
    if path in TRUSTED_FUTURE_CONSUMERS:
        return True
    oapi = ROOT / "tbdy_engine" / "etabs" / "oapi"
    return path.is_relative_to(oapi)


def test_b4t_mutation_transport_is_not_exported_from_gateway_package_root() -> None:
    root_source = _text(GATEWAY / "__init__.py")
    assert MUTATION_MODULE not in root_source
    for symbol in PRIVATE_MUTATION_SYMBOLS:
        assert symbol not in root_source


def test_public_gateway_session_and_connection_remain_read_only_surfaces() -> None:
    session_source = _text(GATEWAY / "session.py")
    connection_source = _text(GATEWAY / "connection.py")
    for symbol in ("execute_bounded_mutation", "execute_model_mutation"):
        assert symbol not in session_source
        assert symbol not in connection_source


def test_private_mutation_capability_has_zero_product_or_engineering_reachability() -> None:
    violations: list[tuple[str, str]] = []
    for path in _production_python_files():
        if _is_trusted_future_consumer(path):
            continue
        source = _text(path)
        if MUTATION_MODULE in source:
            violations.append((path.relative_to(ROOT).as_posix(), MUTATION_MODULE))
        for symbol in PRIVATE_MUTATION_SYMBOLS:
            if symbol in source:
                violations.append((path.relative_to(ROOT).as_posix(), symbol))
    assert violations == []


def test_gateway_transport_adds_no_second_com_or_attach_owner() -> None:
    allowed_gateway = GATEWAY.resolve()
    violations: list[tuple[str, str]] = []
    attach_files: set[str] = set()
    vendor_files: set[str] = set()

    all_production = tuple(sorted((*TBDY.rglob("*.py"), *GATEWAY.rglob("*.py"))))
    for path in all_production:
        tree = _tree(path)
        rel = path.relative_to(ROOT).as_posix()
        in_gateway = path.resolve().is_relative_to(allowed_gateway)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            else:
                names = []
            for name in names:
                if name.split(".", 1)[0] in {"pythoncom", "win32com", "comtypes"}:
                    vendor_files.add(rel)
                    if not in_gateway:
                        violations.append((rel, f"COM:{name}"))
            if isinstance(node, ast.Call):
                final = _dotted(node.func).rsplit(".", 1)[-1]
                if final == "import_module" and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        name = first.value
                        if name.split(".", 1)[0] in {"pythoncom", "win32com", "comtypes"}:
                            vendor_files.add(rel)
                            if not in_gateway:
                                violations.append((rel, f"COM_DYNAMIC:{name}"))
                if final in {"GetActiveObject", "GetObject", "GetObjectProcess", "CreateObject", "AttachToInstance"}:
                    attach_files.add(rel)
                    if not in_gateway:
                        violations.append((rel, f"ATTACH:{final}"))

    assert violations == []
    assert vendor_files
    assert attach_files == {"packages/etabs_gateway/src/etabs_gateway/connection.py"}


def test_b4t_transport_contains_no_analysis_design_or_domain_mutation_ownership() -> None:
    source = _text(GATEWAY / "mutation_transport.py")
    for forbidden in (
        "RunAnalysis",
        "StartDesign",
        "DeleteResults",
        "SetRunCaseFlag",
        "SetPresentUnits",
        "SetModelIsLocked",
        "MASS_SOURCE",
        "MODAL_CASE_SETUP",
        "SECTION_STIFFNESS_MODIFIERS",
        "ANALYSIS_OPTIONS",
        "DesignConcrete",
        "DatabaseTables",
        "Results.Setup",
    ):
        assert forbidden not in source


def test_b4t_transport_exposes_no_raw_owner_reference_in_public_contracts() -> None:
    source = _text(GATEWAY / "mutation_transport.py")
    tree = _tree(GATEWAY / "mutation_transport.py")
    assert "__all__: list[str] = []" in source
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("_execute"):
            assert node.name.startswith("_")
