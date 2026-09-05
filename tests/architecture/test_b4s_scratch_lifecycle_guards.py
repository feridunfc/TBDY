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
    scratch_source = _text(SCRATCH_FILE)
    assert "GetModelFilename" not in oapi_source
    assert "GetModelFilename" not in scratch_source
    assert "reread_verified_session_identity" in scratch_source


def test_positive_owned_scratch_issuance_is_private_and_product_unreachable():
    scratch_source = _text(SCRATCH_FILE)
    assert "_OWNED_SCRATCH_ISSUANCE_KEY = object()" in scratch_source
    assert "_issuance_key is not _OWNED_SCRATCH_ISSUANCE_KEY" in scratch_source
    assert "owned=True" not in scratch_source
    assert "verified_scratch" not in scratch_source
    assert "scratch_is_trusted" not in scratch_source

    product_roots = (
        ROOT / "tbdy_engine" / "application",
        ROOT / "tbdy_engine" / "providers",
        ROOT / "tbdy_engine" / "regulatory",
        ROOT / "tbdy_engine" / "design",
        ROOT / "tbdy_engine" / "product_reports",
        ROOT / "tbdy_engine" / "checks",
        ROOT / "tbdy_engine" / "features",
        ROOT / "apps",
        ROOT / "tools",
    )
    violations: list[tuple[str, str]] = []
    for base in product_roots:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            source = _text(path)
            for symbol in B4S_PRIVATE_ISSUANCE:
                if symbol in source:
                    violations.append((path.relative_to(ROOT).as_posix(), symbol))
    assert violations == []


def test_b4s_delta_contains_zero_analysis_design_or_b4b_mutation_calls():
    sources = _text(OAPI_FILE) + "\n" + _text(SCRATCH_FILE)
    for forbidden in FORBIDDEN_B4S_CALLS:
        assert forbidden not in sources


def test_b4s_adds_no_raw_owner_exports():
    oapi_source = _text(OAPI_FILE)
    scratch_source = _text(SCRATCH_FILE)
    for forbidden_export in (
        '"SapModel"',
        '"ETABSObject"',
        '"application"',
        '"model_api"',
        '"_gateway_session"',
    ):
        # Strings may occur in prose/internal code, but never as an __all__ member.
        for tree in (_tree(OAPI_FILE), _tree(SCRATCH_FILE)):
            for node in tree.body:
                if (
                    isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets)
                ):
                    exported = ast.literal_eval(node.value)
                    assert forbidden_export.strip('"') not in exported

    assert "raw SapModel" in oapi_source


def test_gateway_remains_sole_direct_com_sta_and_attach_owner():
    allowed_gateway = GATEWAY.resolve()
    vendor_files: set[str] = set()
    attach_files: set[str] = set()
    sta_owner_files: set[str] = set()
    violations: list[tuple[str, str]] = []

    for path in _runtime_owner_census_python_files():
        tree = _tree(path)
        rel = path.relative_to(ROOT).as_posix()
        in_gateway = path.resolve().is_relative_to(allowed_gateway)
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
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
                if final in {
                    "GetActiveObject",
                    "GetObject",
                    "GetObjectProcess",
                    "CreateObject",
                    "AttachToInstance",
                }:
                    attach_files.add(rel)
                    if not in_gateway:
                        violations.append((rel, f"ATTACH:{final}"))

        source = _text(path)
        if "DedicatedSTAWorker(" in source:
            sta_owner_files.add(rel)
            if not in_gateway:
                violations.append((rel, "STA:DedicatedSTAWorker"))

    assert violations == []
    assert vendor_files
    assert attach_files == {"packages/etabs_gateway/src/etabs_gateway/connection.py"}
    assert sta_owner_files <= {
        "packages/etabs_gateway/src/etabs_gateway/session.py",
        "packages/etabs_gateway/src/etabs_gateway/worker.py",
    }


def test_oapi_package_root_does_not_export_b4s_mutation_capability():
    root_source = _text(ROOT / "tbdy_engine" / "etabs" / "oapi" / "__init__.py")
    assert "file_lifecycle" not in root_source
    assert "open_file_from_session" not in root_source
    for symbol in B4T_PRIVATE:
        assert symbol not in root_source
