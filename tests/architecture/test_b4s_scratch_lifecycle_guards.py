from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TBDY = ROOT / "tbdy_engine"
GATEWAY = ROOT / "packages" / "etabs_gateway" / "src" / "etabs_gateway"

OAPI_FILE = ROOT / "tbdy_engine" / "etabs" / "oapi" / "file_lifecycle.py"
B4B_OAPI_FILE = ROOT / "tbdy_engine" / "etabs" / "oapi" / "frame_modifiers.py"
SCRATCH_FILE = ROOT / "tbdy_engine" / "integration" / "etabs_scratch_lifecycle.py"

B4T_MODULE = "etabs_gateway.mutation_transport"
B4T_PRIVATE = {
    "_B4T_MUTATION_TRANSPORT_KEY",
    "_execute_bounded_model_mutation",
    "_execute_mutation_on_worker",
}
B4T_TYPED_OAPI_ALLOWLIST = {
    OAPI_FILE,
    B4B_OAPI_FILE,
}
B4S_PRIVATE_ISSUANCE = {
    "_OWNED_SCRATCH_ISSUANCE_KEY",
    "_issue_owned_scratch_context",
}

FORBIDDEN_B4S_CALLS = {
    "RunAnalysis",
    "StartDesign",
    "SetRunCaseFlag",
    "DeleteResults",
    "SetPresentUnits",
    "MASS_SOURCE",
    "MODAL_CASE_SETUP",
    "SECTION_STIFFNESS_MODIFIERS",
    "ANALYSIS_OPTIONS",
    "DesignConcrete",
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
    roots = (
        ROOT / "tbdy_engine",
        ROOT / "apps",
        ROOT / "tools",
        GATEWAY,
    )
    return tuple(
        sorted(
            path
            for base in roots
            if base.exists()
            for path in base.rglob("*.py")
        )
    )


def _runtime_owner_census_python_files() -> tuple[Path, ...]:
    roots = (
        ROOT / "tbdy_engine",
        GATEWAY,
    )
    return tuple(
        sorted(
            path
            for base in roots
            if base.exists()
            for path in base.rglob("*.py")
        )
    )


def test_private_b4t_transport_is_consumed_only_by_exact_typed_oapi_allowlist():
    violations: list[tuple[str, str]] = []
    for path in _production_python_files():
        source = _text(path)
        rel = path.relative_to(ROOT).as_posix()
        if path in B4T_TYPED_OAPI_ALLOWLIST or path.is_relative_to(GATEWAY):
            continue
        if B4T_MODULE in source:
            violations.append((rel, B4T_MODULE))
        for symbol in B4T_PRIVATE:
            if symbol in source:
                violations.append((rel, symbol))
    assert violations == []

    for typed_oapi in sorted(B4T_TYPED_OAPI_ALLOWLIST):
        source = _text(typed_oapi)
        assert B4T_MODULE in source
        assert "_execute_bounded_model_mutation" in source
        assert "_B4T_MUTATION_TRANSPORT_KEY" in source


def test_integration_scratch_owner_never_bypasses_oapi_into_b4t():
    source = _text(SCRATCH_FILE)
    assert B4T_MODULE not in source
    for symbol in B4T_PRIVATE:
        assert symbol not in source
    assert "tbdy_engine.etabs.oapi.file_lifecycle" in source


def test_b4s_does_not_export_generic_arbitrary_live_model_mutation():
    oapi = _tree(OAPI_FILE)
    scratch = _tree(SCRATCH_FILE)
    for tree in (oapi, scratch):
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                args = {arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)}
                assert "callback" not in args
                assert "function" not in args
                assert "model_api" not in args
                assert "sap_model" not in args

    oapi_source = _text(OAPI_FILE)
    assert "_execute_bounded_model_mutation" not in ast.literal_eval(
        next(
            node.value
            for node in oapi.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
        )
    )
    assert "__all__" in oapi_source


def test_active_model_path_readback_reuses_existing_verified_identity_owner():
    oapi_source = _text(OAPI_FILE)
    assert "reread_verified_session_identity" not in oapi_source


def test_b4s_forbids_execution_and_analysis_state_semantics():
    for path in (OAPI_FILE, SCRATCH_FILE):
        source = _text(path)
        for token in FORBIDDEN_B4S_CALLS:
            assert token not in source


def test_owned_scratch_positive_issuance_is_private_to_scratch_owner():
    violations: list[tuple[str, str]] = []
    for path in _runtime_owner_census_python_files():
        if path == SCRATCH_FILE:
            continue
        source = _text(path)
        rel = path.relative_to(ROOT).as_posix()
        for token in B4S_PRIVATE_ISSUANCE:
            if token in source:
                violations.append((rel, token))
    assert violations == []


def test_scratch_owner_uses_typed_oapi_open_file_not_raw_file_openfile():
    tree = _tree(SCRATCH_FILE)
    calls = {_dotted(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert "open_file_from_session" in calls
    assert all(not dotted.endswith("File.OpenFile") for dotted in calls)
