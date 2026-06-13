"""C11.1.8 legacy import/dependency audit.

Scans active repository source/test/tool files for imports that are outside the
accepted contract-first runtime boundary. This is an audit/report tool only: it
does not execute engine code and does not mutate the repository.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any, Iterable

FORBIDDEN_MODULE_PREFIXES = (
    "tbdy_engine.archx",
    "tbdy_engine.runtime",
    "tbdy_engine.runner_v2",
    "tbdy_engine.reports",
    "streamlit",
)
FORBIDDEN_ROOT_FILES = (
    "tbdy_engine/runner_v2.py",
)
FORBIDDEN_ROOT_DIRS = (
    "tbdy_engine/archx",
    "tbdy_engine/runtime",
    "tbdy_engine/reports",
)
CHECK_ENGINE_FORBIDDEN_PREFIXES = (
    "tbdy_engine.providers",
    "tbdy_engine.features.resolver",
    "tbdy_engine.canonical_tables",
    "tbdy_engine.etabs",
    "tbdy_engine.archx",
    "tbdy_engine.runtime",
    "tbdy_engine.runner_v2",
    "tbdy_engine.reports",
)
CHECK_ENGINE_FORBIDDEN_NAMES = (
    "table_registry",
    "load_combo_policy",
    "design_combo_matrix",
    "section_state_policy",
)

SCAN_ROOTS = ("tbdy_engine", "tests", "tools", "app")


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def _iter_py_files(root: Path) -> Iterable[Path]:
    for name in SCAN_ROOTS:
        base = root / name
        if base.exists():
            yield from sorted(base.rglob("*.py"))


def _imports(path: Path) -> tuple[list[str], str | None]:
    text = _read(path)
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [], f"{type(exc).__name__}: {exc}"
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names, None


def _matches_any(name: str, prefixes: tuple[str, ...]) -> bool:
    return any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes)


def _scan_forbidden_imports(root: Path) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]]]:
    violations: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    scanned = 0
    for path in _iter_py_files(root):
        scanned += 1
        imports, error = _imports(path)
        if error:
            parse_errors.append({"file": _rel(path, root), "error": error})
            continue
        for imported in imports:
            if _matches_any(imported, FORBIDDEN_MODULE_PREFIXES):
                violations.append({
                    "file": _rel(path, root),
                    "import": imported,
                    "violation_type": "forbidden_legacy_import",
                })
    return violations, scanned, parse_errors


def _scan_check_engine_boundary(root: Path) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for rel in ("tbdy_engine/checks/engine.py", "tbdy_engine/checks/dry_run.py", "tbdy_engine/checks/__init__.py"):
        path = root / rel
        if not path.exists():
            continue
        imports, error = _imports(path)
        if error:
            violations.append({"file": rel, "error": error, "violation_type": "parse_error"})
            continue
        for imported in imports:
            if _matches_any(imported, CHECK_ENGINE_FORBIDDEN_PREFIXES):
                violations.append({"file": rel, "import": imported, "violation_type": "check_engine_forbidden_import"})
        text = _read(path)
        for token in CHECK_ENGINE_FORBIDDEN_NAMES:
            if token in text:
                violations.append({"file": rel, "token": token, "violation_type": "check_engine_forbidden_token"})
    return violations


def _scan_excel_production(root: Path) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    for path in _iter_py_files(root):
        rel = _rel(path, root)
        if rel == "tools/audit_legacy_imports.py":
            continue
        imports, error = _imports(path)
        for imported in imports:
            if imported in {"openpyxl", "pandas"} or imported.startswith("openpyxl.") or imported.startswith("pandas."):
                violations.append({"file": rel, "import": imported, "violation_type": "excel_production_dependency"})
        if error:
            continue
        try:
            tree = ast.parse(_read(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute) and fn.attr == "read_excel":
                    violations.append({"file": rel, "call": "read_excel", "violation_type": "excel_production_call"})
                elif isinstance(fn, ast.Name) and fn.id == "read_excel":
                    violations.append({"file": rel, "call": "read_excel", "violation_type": "excel_production_call"})
    return violations

def _legacy_candidates(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rel in FORBIDDEN_ROOT_DIRS:
        p = root / rel
        out.append({"path": rel, "exists": p.exists(), "candidate_type": "directory"})
    for rel in FORBIDDEN_ROOT_FILES:
        p = root / rel
        out.append({"path": rel, "exists": p.exists(), "candidate_type": "file"})
    return out


def build_report(root: Path) -> dict[str, Any]:
    forbidden, scanned, parse_errors = _scan_forbidden_imports(root)
    active = _scan_check_engine_boundary(root)
    excel = _scan_excel_production(root)
    legacy_candidates = _legacy_candidates(root)
    blockers = []
    if forbidden:
        blockers.append("forbidden legacy imports remain")
    if active:
        blockers.append("active CheckEngine/runtime boundary violations remain")
    if excel:
        blockers.append("Excel production input path indicators remain")
    safe_to_remove = not blockers and all(not item["exists"] for item in legacy_candidates)
    return {
        "c11_sprint": "C11.1.8_LEGACY_CLEANUP",
        "scanned_files_count": scanned,
        "forbidden_imports_found": bool(forbidden),
        "forbidden_imports": forbidden,
        "active_runtime_violations": active,
        "excel_production_path_violations": excel,
        "legacy_files_candidates": legacy_candidates,
        "safe_to_remove": safe_to_remove,
        "blockers": blockers,
        "parse_errors": parse_errors,
        "summary": {
            "legacy_import_audit_clean": not forbidden and not active and not excel,
            "archx_runtime_runner_v2_removed_or_quarantined": all(not item["exists"] for item in legacy_candidates),
            "old_report_app_not_used": not any(v.get("import", "").startswith("tbdy_engine.reports") for v in forbidden),
            "streamlit_ui_not_in_engine_runtime": not any("streamlit" in str(v) for v in forbidden + active),
            "excel_production_path_absent": not excel,
            "check_engine_reads_only_snapshot_coverage_catalog": not active,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="local_out/c11_1_8_legacy_cleanup")
    args = parser.parse_args()
    root = Path.cwd()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = build_report(root)
    (out_dir / "legacy_import_audit_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "scanned_files_count": report["scanned_files_count"],
        "forbidden_imports_found": report["forbidden_imports_found"],
        "active_runtime_violations": len(report["active_runtime_violations"]),
        "excel_production_path_violations": len(report["excel_production_path_violations"]),
        "safe_to_remove": report["safe_to_remove"],
        "blockers": report["blockers"],
    }, indent=2, ensure_ascii=False))
    return 0 if not report["blockers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
