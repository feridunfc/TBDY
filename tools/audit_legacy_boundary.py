#!/usr/bin/env python
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "local_out" / "c13_4_p1_boundary_guard" / "legacy_boundary_audit_report.json"

PRODUCTION_GLOBS = (
    "tbdy_engine/checks/*.py",
    "tbdy_engine/check_inputs/*.py",
    "tbdy_engine/features/*.py",
    "tbdy_engine/reports/*.py",
    "tbdy_engine/product/*.py",
    "tools/smoke_c13_4_p1_geometry_checkresult_slice.py",
)

# These files are known legacy/reference-only files in the current repository.
# C13.4-P1 does not refactor or execute them. They are explicitly excluded from
# the active new-pipeline boundary scan and reported in the JSON output.
LEGACY_REFERENCE_ONLY_FILES = {
    "tbdy_engine/checks/beam_checks_patch.py",
    "tbdy_engine/checks/registry.py",
}

FORBIDDEN_IMPORT_PREFIXES = (
    "tbdy_engine.design",
    "tbdy_engine.adapters.check_adapter",
    "tbdy_engine.engine.topology",
    "tbdy_engine.contracts.runtime_catalog",
    "tbdy_engine.contracts.generated",
    "tbdy_engine.contracts.legacy",
    "tbdy_engine.archx",
    "tbdy_engine.runtime",
    "tbdy_engine.runner_v2",
)

FORBIDDEN_SYMBOLS = {
    "BeamDesignModule",
    "BeamCheckResult",
    "run_beam_design",
    "ColumnDesignModule",
    "CheckAdapter",
    "EvaluationPackage",
    "CoreCheck",
}

FORBIDDEN_ATTRIBUTE_NAMES = FORBIDDEN_SYMBOLS | {"check_type"}


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _scan_files() -> list[Path]:
    files: set[Path] = set()
    for pattern in PRODUCTION_GLOBS:
        files.update(path for path in ROOT.glob(pattern) if path.is_file())
    return sorted(path for path in files if _rel(path) not in LEGACY_REFERENCE_ONLY_FILES)


def _excluded_files() -> list[str]:
    return sorted(
        rel
        for rel in LEGACY_REFERENCE_ONLY_FILES
        if (ROOT / rel).is_file()
    )


def _import_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]

    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        names = [module] if module else []
        for alias in node.names:
            if module:
                names.append(f"{module}.{alias.name}")
            else:
                names.append(alias.name)
        return names

    return []


def _matches_prefix(name: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in prefixes:
        if name == prefix or name.startswith(prefix + "."):
            return prefix
    return None


def _scan_file(path: Path) -> list[dict[str, Any]]:
    rel = _rel(path)
    text = path.read_text(encoding="utf-8-sig")

    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError as exc:
        return [
            {
                "file": rel,
                "line": exc.lineno,
                "kind": "syntax_error",
                "name": "SyntaxError",
                "message": exc.msg,
            }
        ]

    blockers: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for name in _import_names(node):
                prefix = _matches_prefix(name, FORBIDDEN_IMPORT_PREFIXES)
                if prefix:
                    blockers.append(
                        {
                            "file": rel,
                            "line": getattr(node, "lineno", None),
                            "kind": "forbidden_import",
                            "name": name,
                            "matched": prefix,
                        }
                    )

        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_SYMBOLS:
                blockers.append(
                    {
                        "file": rel,
                        "line": getattr(node, "lineno", None),
                        "kind": "forbidden_symbol",
                        "name": node.id,
                    }
                )

        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_ATTRIBUTE_NAMES:
                blockers.append(
                    {
                        "file": rel,
                        "line": getattr(node, "lineno", None),
                        "kind": "forbidden_attribute",
                        "name": node.attr,
                    }
                )

    return blockers


def build_report() -> dict[str, Any]:
    files = _scan_files()
    blockers: list[dict[str, Any]] = []

    for path in files:
        blockers.extend(_scan_file(path))

    excluded = _excluded_files()

    return {
        "sprint": "C13.4-P1",
        "status": "BLOCKED" if blockers else "OK",
        "checked_files": [_rel(path) for path in files],
        "excluded_legacy_reference_files": excluded,
        "forbidden_import_prefixes": list(FORBIDDEN_IMPORT_PREFIXES),
        "forbidden_symbols": sorted(FORBIDDEN_SYMBOLS),
        "blocker_count": len(blockers),
        "blockers": blockers,
        "legacy_code_policy": (
            "Known legacy files may remain in repository as reference-only during C13.4-P1. "
            "They are excluded from active new-pipeline scanning only when explicitly listed "
            "in LEGACY_REFERENCE_ONLY_FILES."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit C13.4-P1 legacy boundary for the new check pipeline")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)

    report = build_report()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
