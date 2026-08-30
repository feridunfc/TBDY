from __future__ import annotations

import ast
from dataclasses import fields
from functools import lru_cache
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TBDY = ROOT / "tbdy_engine"
GATEWAY = ROOT / "packages/etabs_gateway/src/etabs_gateway"
BASELINE = json.loads(Path(__file__).with_name("g1_legacy_exception_baseline.json").read_text())
SUPPORTED_ROOTS = ("tbdy_engine.application", "tbdy_engine.application.project_execution")
LEGACY_REPORT = frozenset(BASELINE["legacy_reporting_authority_modules"])
FORBIDDEN_LEGACY = frozenset(BASELINE["forbidden_supported_legacy_modules"])
B1_OWNER = "tbdy_engine.integration.etabs_analysis_lineage"
B1_PRIVATE = {
    "_QUALIFICATION_FACTORY_TOKEN",
    "_EXECUTION_PROOF_FACTORY_TOKEN",
    "_VerifiedAnalysisExecutionProof",
    "_build_qualified_analysis_lineage",
}
MUTATION = {"RunAnalysis", "StartDesign", "Save", "SaveAs", "SetPresentUnits", "SetPresentUnits_2"}
RAW_PARAMS = {"sap_model", "database_tables", "design_concrete", "resp_combo"}
RAW_ROOTS = {"DatabaseTables", "Results", "DesignConcrete", "FrameObj", "AreaObj", "PointObj", "PropFrame", "PropArea", "PropMaterial", "RespCombo"}


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def tree(path: Path) -> ast.Module:
    return ast.parse(text(path), filename=str(path))


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = dotted(node.value)
        return f"{head}.{node.attr}" if head else node.attr
    return ""


def module_name(path: Path) -> str:
    if path.is_relative_to(TBDY):
        rel = path.relative_to(ROOT).with_suffix("")
    elif path.is_relative_to(GATEWAY):
        rel = Path("etabs_gateway") / path.relative_to(GATEWAY).with_suffix("")
    else:
        raise AssertionError(path)
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


@lru_cache(maxsize=1)
def production_files() -> tuple[Path, ...]:
    return tuple(sorted((*TBDY.rglob("*.py"), *GATEWAY.rglob("*.py"))))


@lru_cache(maxsize=1)
def module_index() -> dict[str, Path]:
    return {module_name(path): path for path in production_files()}


def resolve_relative(module: str, level: int, imported: str | None) -> str:
    parts = module.split(".")
    path = module_index().get(module)
    if path is None or path.name != "__init__.py":
        parts = parts[:-1]
    if level:
        parts = parts[: max(0, len(parts) - level + 1)]
    if imported:
        parts.extend(imported.split("."))
    return ".".join(parts)


def imports_for(module: str, path: Path, index: dict[str, Path]) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(tree(path)):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = resolve_relative(module, node.level, node.module) if node.level else (node.module or "")
            if base:
                result.add(base)
            for alias in node.names:
                candidate = f"{base}.{alias.name}" if base else alias.name
                if candidate in index:
                    result.add(candidate)
    expanded = set(result)
    for imported in tuple(result):
        parts = imported.split(".")
        for size in range(1, len(parts)):
            parent = ".".join(parts[:size])
            if parent in index:
                expanded.add(parent)
    return expanded


@lru_cache(maxsize=1)
def graph() -> tuple[dict[str, Path], dict[str, set[str]]]:
    index = module_index()
    return index, {name: imports_for(name, path, index) for name, path in index.items()}


@lru_cache(maxsize=8)
def closure_cached(roots: tuple[str, ...]) -> frozenset[str]:
    index, edges = graph()
    seen: set[str] = set()
    pending = list(roots)
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        pending.extend(item for item in edges.get(module, ()) if item in index and item not in seen)
    return frozenset(seen)


def closure(*roots: str) -> set[str]:
    return set(closure_cached(tuple(sorted(roots))))


def static_imports(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree(path)):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def dynamic_imports(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree(path)):
        if not isinstance(node, ast.Call) or dotted(node.func).rsplit(".", 1)[-1] not in {"import_module", "__import__"}:
            continue
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            found.append(node.args[0].value)
    return found


def call_names(path: Path) -> list[str]:
    return [dotted(node.func) for node in ast.walk(tree(path)) if isinstance(node, ast.Call)]


def fresh_import(module: str) -> dict[str, object]:
    watched = tuple(sorted(LEGACY_REPORT))
    code = "\n".join((
        "import json, sys",
        f"import {module}",
        f"watched={watched!r}",
        "print(json.dumps({'watched':{n:n in sys.modules for n in watched},'tools':sorted(n for n in sys.modules if n=='tools' or n.startswith('tools.'))},sort_keys=True))",
    ))
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "packages/etabs_gateway/src")))
    run = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, check=True, capture_output=True, text=True)
    return json.loads(run.stdout)


def legacy_debt() -> set[str]:
    facts: set[str] = set()
    for path in sorted(TBDY.rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        module = module_name(path)
        boundary_internal = module in {"tbdy_engine.etabs.safety", "tbdy_engine.etabs._safety_legacy"} or module.startswith("tbdy_engine.etabs.oapi")
        for node in ast.walk(tree(path)):
            if isinstance(node, ast.ImportFrom) and node.module == "tbdy_engine.features.etabs_com_attach":
                facts.add(f"LEGACY_IMPORT|{rel}|tbdy_engine.features.etabs_com_attach")
            elif isinstance(node, ast.Import) and any(a.name == "tbdy_engine.features.etabs_com_attach" for a in node.names):
                facts.add(f"LEGACY_IMPORT|{rel}|tbdy_engine.features.etabs_com_attach")
            elif isinstance(node, ast.Call):
                final = dotted(node.func).rsplit(".", 1)[-1]
                if final in MUTATION:
                    facts.add(f"MUTATION_CALL|{rel}|{final}")
            elif isinstance(node, ast.Attribute) and not boundary_internal:
                name = dotted(node)
                if name.startswith("sap_model.") and name.split(".", 2)[1] in RAW_ROOTS:
                    facts.add(f"RAW_CAP_ATTR|{rel}|{'.'.join(name.split('.')[:2])}")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not boundary_internal:
                    for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
                        if arg.arg in RAW_PARAMS:
                            facts.add(f"RAW_PARAM|{rel}|{node.name}|{arg.arg}")
                if rel == "tbdy_engine/etabs/connection.py" and node.name == "get_sap":
                    facts.add(f"RAW_ESCAPE_COMPAT|{rel}|get_sap")
    return facts


def compatibility_callers() -> set[str]:
    targets = {"tbdy_engine.etabs.connection", "tbdy_engine.features.etabs_com_attach"}
    found: set[str] = set()
    for base in (ROOT / "tbdy_engine", ROOT / "tools", ROOT / "tests", ROOT / "apps"):
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if path.resolve() == Path(__file__).resolve():
                continue
            rel = path.relative_to(ROOT).as_posix()
            for imported in (*static_imports(path), *dynamic_imports(path)):
                if imported in targets:
                    found.add(f"{rel}|{imported}")
    return found


def test_g1_p0_regression() -> None:
    expected = {name: False for name in LEGACY_REPORT}
    for module in ("tbdy_engine.product_reports.unified_building_report", "tbdy_engine.application.project_execution"):
        observed = fresh_import(module)
        assert observed["watched"] == expected
        assert observed["tools"] == []


def test_supported_graph_has_zero_forbidden_legacy_tools_or_report_authority() -> None:
    supported = closure(*SUPPORTED_ROOTS)
    assert not supported.intersection(FORBIDDEN_LEGACY)
    assert not supported.intersection(LEGACY_REPORT)
    assert not {m for m in supported if m == "tools" or m.startswith("tools.")}


def test_gateway_is_sole_com_and_attach_owner() -> None:
    violations: list[str] = []
    attach: list[str] = []
    vendor: list[str] = []
    for path in production_files():
        rel = path.relative_to(ROOT).as_posix()
        gateway = path.is_relative_to(GATEWAY)
        for imported in (*static_imports(path), *dynamic_imports(path)):
            if imported.split(".", 1)[0] in {"pythoncom", "win32com", "comtypes"}:
                vendor.append(rel)
                if not gateway:
                    violations.append(f"COM|{rel}|{imported}")
        for name in call_names(path):
            if name.rsplit(".", 1)[-1] in {"GetActiveObject", "GetObject", "GetObjectProcess", "CreateObject", "AttachToInstance"}:
                attach.append(rel)
                if not gateway:
                    violations.append(f"ATTACH|{rel}|{name}")
    assert violations == []
    assert vendor
    assert set(attach) == {"packages/etabs_gateway/src/etabs_gateway/connection.py"}


def test_no_public_raw_sapmodel_escape() -> None:
    supported = closure(*SUPPORTED_ROOTS)
    index, _ = graph()
    violations: list[str] = []
    for module in supported:
        path = index.get(module)
        if not path:
            continue
        for name in call_names(path):
            if name.rsplit(".", 1)[-1] in {"get_sap", "attach_to_running_etabs"}:
                violations.append(f"{module}|{name}")
        if any(item in FORBIDDEN_LEGACY for item in dynamic_imports(path)):
            violations.append(f"{module}|dynamic-legacy")
    assert violations == []
    from tbdy_engine.etabs.safety import EtabsVerifiedSession
    from tbdy_engine.integration.live_etabs_acquisition_context import TrustedLiveAcquisitionContext
    forbidden = {"sap_model", "get_sap", "database_tables", "design_concrete"}
    for cls in (EtabsVerifiedSession, TrustedLiveAcquisitionContext):
        assert not {f.name for f in fields(cls) if not f.name.startswith("_")}.intersection(forbidden)
        assert not {n for n in dir(cls) if not n.startswith("_")}.intersection(forbidden)


def test_supported_product_has_zero_uncontrolled_mutation_calls() -> None:
    index, _ = graph()
    violations: list[str] = []
    for module in closure(*SUPPORTED_ROOTS):
        path = index.get(module)
        if path:
            violations.extend(f"{module}|{name}" for name in call_names(path) if name.rsplit(".", 1)[-1] in MUTATION)
    assert violations == []


def test_application_requests_cannot_inject_runtime_truth() -> None:
    from tbdy_engine.application.contracts import ColumnExecutionRequest, ProjectExecutionRequest
    names = {f.name.lower() for cls in (ColumnExecutionRequest, ProjectExecutionRequest) for f in fields(cls)}
    forbidden = {"model_fingerprint", "evidence_epoch", "evidence_epoch_id", "analysis_state_identity", "analysis_result_identity", "design_state_identity", "design_result_identity", "qualified_lineage", "analysis_lineage_qualification", "factual_result_population", "factual_design_results", "regulatory_compile_inputs"}
    assert not names.intersection(forbidden)
    source = text(ROOT / "tbdy_engine/application/contracts.py") + text(ROOT / "tbdy_engine/application/__init__.py")
    assert not any(name in source for name in {"AnalysisStateIdentity", "AnalysisResultIdentity", "DesignStateIdentity", "DesignResultIdentity", "AnalysisLineageQualification", "RegulatoryCompileInputs", "FactualColumnDesignResultPopulation"})


def test_b1_private_positive_issuer_has_zero_external_production_refs() -> None:
    owner = module_index()[B1_OWNER]
    refs = [(p.relative_to(ROOT).as_posix(), symbol) for p in TBDY.rglob("*.py") if p != owner for symbol in B1_PRIVATE if symbol in text(p)]
    assert refs == []


def test_reporting_is_projection_only_and_cannot_reach_etabs_or_engineering() -> None:
    _, edges = graph()
    reporting = {m for m in closure(*SUPPORTED_ROOTS) if m.startswith("tbdy_engine.product_reports")}
    assert reporting and not reporting.intersection(LEGACY_REPORT)
    forbidden = ("etabs_gateway", "tbdy_engine.etabs", "tbdy_engine.providers", "tbdy_engine.integration.live_", "tbdy_engine.features.live_etabs", "tbdy_engine.design", "tbdy_engine.regulatory")
    assert [(m, i) for m in reporting for i in edges.get(m, ()) if i.startswith(forbidden)] == []


def test_provider_and_oapi_dependency_direction() -> None:
    _, edges = graph()
    provider_forbidden = ("tbdy_engine.application", "tbdy_engine.product_reports", "tbdy_engine.regulatory")
    oapi_forbidden = ("tbdy_engine.regulatory", "tbdy_engine.design", "tbdy_engine.application", "tbdy_engine.product_reports")
    assert [(m, i) for m, imports in edges.items() if m.startswith("tbdy_engine.providers") for i in imports if i.startswith(provider_forbidden)] == []
    assert [(m, i) for m, imports in edges.items() if m.startswith("etabs_gateway") or m.startswith("tbdy_engine.etabs.oapi") for i in imports if i.startswith(oapi_forbidden)] == []


def test_production_never_imports_archive_or_places_it_on_sys_path() -> None:
    violations: list[str] = []
    for path in production_files():
        rel = path.relative_to(ROOT).as_posix()
        for imported in (*static_imports(path), *dynamic_imports(path)):
            if imported == "_archive" or imported.startswith("_archive."):
                violations.append(f"{rel}|{imported}")
        for node in ast.walk(tree(path)):
            if isinstance(node, ast.Call) and dotted(node.func).endswith(("sys.path.append", "sys.path.insert")) and "_archive" in ast.unparse(node):
                violations.append(f"{rel}|sys.path")
    assert violations == []


def test_legacy_exception_baseline_is_shrink_only() -> None:
    observed = legacy_debt()
    allowed = set(BASELINE["legacy_exception_keys"])
    assert observed - allowed == set(), "new legacy exceptions:\n" + "\n".join(sorted(observed - allowed))


def test_compatibility_facades_and_callers_are_shrink_only() -> None:
    modules: set[str] = set()
    for path in TBDY.rglob("*.py"):
        for node in tree(path).body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and node.value.value is True and any(isinstance(t, ast.Name) and t.id == "LEGACY_COMPATIBILITY_ONLY" for t in node.targets):
                modules.add(module_name(path))
    allowed = {m for m, d in BASELINE["compatibility_modules"].items() if d == "KEEP_SHRINK_ONLY"}
    assert modules - allowed == set()
    callers = compatibility_callers()
    frozen = set(BASELINE["compatibility_caller_baseline"])
    assert callers - frozen == set(), "new compatibility callers:\n" + "\n".join(sorted(callers - frozen))


def test_archive_and_oapi_debt_dispositions_are_frozen() -> None:
    assert BASELINE["archived_etabs_files"] == []
    assert {x["capability"] for x in BASELINE["oapi_migration_required"]} == {"DATABASE_TABLE_ENUMERATION", "CONCRETE_MATERIAL_FACTS"}
    assert (ROOT / "tbdy_engine/features/live_etabs_table_discovery.py").is_file()
    assert (ROOT / "tbdy_engine/features/used_rc_material_population.py").is_file()
    assert BASELINE["compatibility_modules"] == {
        "tbdy_engine.engine.unit_context": "KEEP_SHRINK_ONLY",
        "tbdy_engine.etabs._safety_legacy": "ACTIVE_CANONICAL_SUPPORT",
        "tbdy_engine.etabs.connection": "KEEP_SHRINK_ONLY",
        "tbdy_engine.features.etabs_com_attach": "KEEP_SHRINK_ONLY",
    }
