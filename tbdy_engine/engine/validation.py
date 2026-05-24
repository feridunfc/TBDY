# app/engine/validation.py
"""Validation utilities for ModelContext and debug JSON serialization.

This module is intentionally lightweight and dependency-aware: it can inspect
pandas/numpy objects, but it never silently stringifies unknown objects. The
runner should fail fast when a payload is not JSON-contract safe.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from app.engine.design_basis_audit import audit_design_basis


ALLOWED_SEVERITIES = {"ERROR", "WARNING", "INFO"}


@dataclass
class ValidationIssue:
    severity: str
    code: str
    message: str
    path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationReport:
    name: str
    valid: bool
    issues: List[ValidationIssue]

    def to_dict(self) -> Dict[str, Any]:
        counts = {
            "error": sum(1 for i in self.issues if i.severity == "ERROR"),
            "warning": sum(1 for i in self.issues if i.severity == "WARNING"),
            "info": sum(1 for i in self.issues if i.severity == "INFO"),
        }
        return {
            "name": self.name,
            "valid": self.valid,
            "counts": counts,
            "issues": [i.to_dict() for i in self.issues],
        }


def _issue(severity: str, code: str, message: str, path: str = "") -> ValidationIssue:
    severity = str(severity).upper()
    if severity not in ALLOWED_SEVERITIES:
        severity = "ERROR"
    return ValidationIssue(severity=severity, code=code, message=message, path=path)


def _is_df(value: Any) -> bool:
    try:
        import pandas as pd
        return isinstance(value, pd.DataFrame)
    except Exception:
        return False


def _df_rows(value: Any) -> int:
    try:
        return int(len(value))
    except Exception:
        return 0


def _table_rows(ctx: Any, canonical: str) -> Optional[int]:
    tables = getattr(ctx, "tables", {}) or {}
    if canonical not in tables:
        return None
    val = tables.get(canonical)
    if _is_df(val):
        return _df_rows(val)
    return None


def validate_context_contract(ctx: Any) -> ValidationReport:
    """Validate minimum ModelContext contract before checks/reporting."""
    issues: List[ValidationIssue] = []

    for attr in ("tables", "notes", "design_basis", "spectrum", "topology", "geometry"):
        if not hasattr(ctx, attr):
            issues.append(_issue("ERROR", "CTX_MISSING_ATTR", f"ModelContext missing '{attr}'.", attr))

    notes = getattr(ctx, "notes", {}) or {}
    tables = getattr(ctx, "tables", {}) or {}
    if not isinstance(tables, dict):
        issues.append(_issue("ERROR", "CTX_TABLES_NOT_DICT", "ctx.tables must be a dict.", "tables"))
    if not isinstance(notes, dict):
        issues.append(_issue("ERROR", "CTX_NOTES_NOT_DICT", "ctx.notes must be a dict.", "notes"))

    # Hard minimums for a meaningful live ETABS context. Missing/empty tables may
    # still be acceptable for a partial engineering run, so classify as WARNING.
    for canonical in ("story_definitions", "modal_mass", "story_drifts"):
        rows = _table_rows(ctx, canonical)
        if rows is None:
            issues.append(_issue("WARNING", "CTX_CRITICAL_TABLE_MISSING", f"Critical table missing: {canonical}.", f"tables.{canonical}"))
        elif rows <= 0:
            issues.append(_issue("WARNING", "CTX_CRITICAL_TABLE_EMPTY", f"Critical table empty: {canonical}.", f"tables.{canonical}"))

    if not getattr(ctx, "story_order", None):
        issues.append(_issue("WARNING", "CTX_STORY_ORDER_EMPTY", "story_order is empty; story-level checks may be unreliable.", "story_order"))

    design_basis = getattr(ctx, "design_basis", {}) or {}
    for key in ("code", "fck_mpa", "fyk_mpa", "R", "D", "I"):
        # R/D/I may live in spectrum in older context builds.
        if key in {"R", "D", "I"}:
            spectrum = getattr(ctx, "spectrum", {}) or {}
            if key not in design_basis and key not in spectrum:
                issues.append(_issue("WARNING", "DESIGN_BASIS_KEY_MISSING", f"Design basis/spectrum missing '{key}'.", f"design_basis.{key}"))
        elif key not in design_basis:
            issues.append(_issue("WARNING", "DESIGN_BASIS_KEY_MISSING", f"Design basis missing '{key}'.", f"design_basis.{key}"))

    sources = design_basis.get("sources") or design_basis.get("_sources") or {}
    if not sources:
        issues.append(_issue("WARNING", "DESIGN_BASIS_SOURCE_MISSING", "Design basis has no source map; report must treat assumptions as defaults/manual unknown.", "design_basis.sources"))

    db_audit = audit_design_basis(ctx)
    for issue in db_audit.get("issues", []):
        sev = "ERROR" if issue.get("severity") == "CRITICAL" else "WARNING"
        issues.append(_issue(sev, issue.get("code", "DESIGN_BASIS_SOURCE"), issue.get("message", "Design basis source issue."), f"design_basis.{issue.get('parameter','')}"))

    data_gaps = notes.get("data_gaps") or []
    warnings = notes.get("warnings") or []
    if data_gaps:
        issues.append(_issue("INFO", "CTX_DATA_GAPS_PRESENT", f"Context reports {len(data_gaps)} data gaps.", "notes.data_gaps"))
    if warnings:
        issues.append(_issue("INFO", "CTX_WARNINGS_PRESENT", f"Context reports {len(warnings)} warnings.", "notes.warnings"))

    return ValidationReport(
        name="context",
        valid=not any(i.severity == "ERROR" for i in issues),
        issues=issues,
    )


def strict_jsonable(value: Any, path: str = "$") -> Any:
    """Convert known-safe objects to JSON-compatible values, fail on unknowns.

    Unlike json.dumps(default=str), this does not hide contract leaks.
    """
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)

    try:
        import math
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
    except Exception:
        pass

    try:
        import numpy as np
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            v = float(value)
            return None if v != v else v
        if isinstance(value, np.bool_):
            return bool(value)
    except Exception:
        pass

    if _is_df(value):
        raise TypeError(f"DataFrame is not allowed in JSON contract at {path}; export a summary or records explicitly.")

    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if not isinstance(k, (str, int, float, bool)) and k is not None:
                raise TypeError(f"Unsupported dict key type at {path}: {type(k).__name__}")
            key = str(k)
            if key.startswith("_"):
                # Avoid leaking live ETABS COM objects/cache handles.
                continue
            out[key] = strict_jsonable(v, f"{path}.{key}")
        return out

    if isinstance(value, (list, tuple, set)):
        return [strict_jsonable(v, f"{path}[{i}]") for i, v in enumerate(value)]

    raise TypeError(f"Unsupported JSON value at {path}: {type(value).__name__}")


def validation_bundle(*reports: ValidationReport) -> Dict[str, Any]:
    return {
        "valid": all(r.valid for r in reports),
        "reports": {r.name: r.to_dict() for r in reports},
    }
