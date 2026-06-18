"""Deterministic modular catalog loader for C13.4-P2.

The loader only builds validated catalog dictionaries. It does not execute checks,
read ETABS, read Excel, or import legacy design/runtime code.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

GEOMETRY_CHECK_IDS = {
    "column_geometry_min_dimension",
    "beam_geometry_min_width",
    "beam_geometry_min_depth",
    "beam_depth_width_ratio",
}

CHECK_REQUIRED_FIELDS = {
    "title",
    "element_type",
    "category",
    "readiness",
    "required_features",
    "optional_features",
    "pass_rule",
    "output",
    "evidence_policy",
    "code_ref",
}

FEATURE_REQUIRED_FIELDS = {
    "element_type",
    "type",
    "unit",
    "semantic_role",
    "availability",
    "source",
    "unit_policy",
    "fallback",
    "semantics",
    "evidence_fields",
}

ENGINEERING_SENSITIVE_CHECK_FIELDS = {
    "element_type",
    "required_features",
    "pass_rule",
    "output",
    "code_ref",
}

ENGINEERING_SENSITIVE_FEATURE_FIELDS = {
    "element_type",
    "unit",
    "semantic_role",
    "source",
    "unit_policy",
}

_ALLOWED_TOP_LEVEL = {"metadata", "checks", "features", "policies"}


@dataclass(frozen=True, slots=True)
class CatalogDiagnostic:
    file_path: str
    catalog_section: str
    item_id: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "catalog_section": self.catalog_section,
            "id": self.item_id,
            "reason": self.reason,
        }


class CatalogLoadError(ValueError):
    def __init__(self, diagnostics: list[CatalogDiagnostic]):
        self.diagnostics = diagnostics
        message = "; ".join(
            f"{d.file_path}:{d.catalog_section}:{d.item_id or '-'}: {d.reason}"
            for d in diagnostics[:8]
        )
        super().__init__(message or "catalog loading failed")


def _diagnostic(path: Path | str, section: str, item_id: str | None, reason: str) -> CatalogDiagnostic:
    return CatalogDiagnostic(str(path), section, item_id, reason)


def _plain_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        raise CatalogLoadError([_diagnostic(path, "yaml", None, f"invalid yaml: {exc}")]) from exc
    if not isinstance(data, dict):
        raise CatalogLoadError([_diagnostic(path, "root", None, "fragment must be a YAML object")])
    return data


def load_single_file_catalog(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    data = _plain_yaml(path)
    section = None
    if "checks" in data:
        section = "checks"
    elif "features" in data:
        section = "features"
    else:
        raise CatalogLoadError([_diagnostic(path, "root", None, "single catalog must contain checks or features")])
    master = {"metadata": data.get("metadata", {}), "checks": {}, "features": {}, "policies": {}}
    master[section] = dict(data.get(section) or {})
    validate_master_catalog(master)
    return master


def load_single_file_master(catalog_dir: Path | str) -> dict[str, Any]:
    catalog_dir = Path(catalog_dir)
    check_catalog = _plain_yaml(catalog_dir / "check_catalog.yaml")
    feature_catalog = _plain_yaml(catalog_dir / "feature_catalog.yaml")
    master = {
        "metadata": {"source": "single_file", "catalog_dir": str(catalog_dir)},
        "checks": dict(check_catalog.get("checks") or {}),
        "features": dict(feature_catalog.get("features") or {}),
        "policies": {},
    }
    validate_master_catalog(master)
    return master


def _merge_mapping(master: dict[str, Any], section: str, entries: Mapping[str, Any], path: Path, diagnostics: list[CatalogDiagnostic]) -> None:
    if not isinstance(entries, Mapping):
        diagnostics.append(_diagnostic(path, section, None, f"{section} must be a mapping"))
        return
    for item_id, payload in entries.items():
        if not isinstance(item_id, str) or not item_id:
            diagnostics.append(_diagnostic(path, section, str(item_id), "id must be a non-empty string"))
            continue
        if item_id in master[section]:
            diagnostics.append(_diagnostic(path, section, item_id, "duplicate id"))
            continue
        if not isinstance(payload, Mapping):
            diagnostics.append(_diagnostic(path, section, item_id, "entry must be a mapping"))
            continue
        row = dict(payload)
        row.setdefault("_source_file", str(path))
        master[section][item_id] = row


def load_modular_catalog(root: Path | str) -> dict[str, Any]:
    root = Path(root)
    if not root.exists():
        raise CatalogLoadError([_diagnostic(root, "root", None, "modular catalog directory does not exist")])
    files = sorted(path for path in root.rglob("*.yaml") if path.is_file())
    master: dict[str, Any] = {"metadata": {"source": "modular", "root": str(root)}, "checks": {}, "features": {}, "policies": {}}
    diagnostics: list[CatalogDiagnostic] = []
    for path in files:
        try:
            fragment = _plain_yaml(path)
        except CatalogLoadError as exc:
            diagnostics.extend(exc.diagnostics)
            continue
        unknown = sorted(set(fragment) - _ALLOWED_TOP_LEVEL)
        if unknown:
            diagnostics.append(_diagnostic(path, "root", None, "unknown top-level key(s): " + ", ".join(unknown)))
            continue
        for section in ("checks", "features", "policies"):
            if section not in fragment:
                continue
            if section == "policies":
                _merge_mapping(master, section, fragment[section] or {}, path, diagnostics)
            else:
                _merge_mapping(master, section, fragment[section] or {}, path, diagnostics)
    if diagnostics:
        raise CatalogLoadError(diagnostics)
    validate_master_catalog(master)
    return master


def _require_flat_string_list(value: Any, *, path: Path | str, section: str, item_id: str, field: str) -> list[CatalogDiagnostic]:
    if not isinstance(value, list):
        return [_diagnostic(path, section, item_id, f"{field} must be a list")]
    diagnostics: list[CatalogDiagnostic] = []
    for index, item in enumerate(value):
        if isinstance(item, list):
            diagnostics.append(_diagnostic(path, section, item_id, f"{field}[{index}] is a nested list; YAML aliases must expand to a flat list"))
        elif not isinstance(item, str) or not item:
            diagnostics.append(_diagnostic(path, section, item_id, f"{field}[{index}] must be a non-empty string"))
    return diagnostics


def validate_master_catalog(master: Mapping[str, Any]) -> None:
    diagnostics: list[CatalogDiagnostic] = []
    checks = master.get("checks")
    features = master.get("features")
    if not isinstance(checks, Mapping):
        diagnostics.append(_diagnostic("<master>", "checks", None, "checks must be a mapping"))
        checks = {}
    if not isinstance(features, Mapping):
        diagnostics.append(_diagnostic("<master>", "features", None, "features must be a mapping"))
        features = {}

    for check_id, check in checks.items():
        path = Path(str(check.get("_source_file", "<master>"))) if isinstance(check, Mapping) else Path("<master>")
        if not isinstance(check, Mapping):
            diagnostics.append(_diagnostic(path, "checks", str(check_id), "check entry must be a mapping"))
            continue
        missing = sorted(CHECK_REQUIRED_FIELDS - set(check))
        if missing:
            diagnostics.append(_diagnostic(path, "checks", str(check_id), "missing required field(s): " + ", ".join(missing)))
        sensitive_missing = sorted(field for field in ENGINEERING_SENSITIVE_CHECK_FIELDS if check.get(field) in (None, "", [], {}))
        if sensitive_missing:
            diagnostics.append(_diagnostic(path, "checks", str(check_id), "engineering-sensitive field(s) missing: " + ", ".join(sensitive_missing)))
        diagnostics.extend(_require_flat_string_list(check.get("required_features"), path=path, section="checks", item_id=str(check_id), field="required_features"))
        for feature_id in check.get("required_features", []) or []:
            if isinstance(feature_id, str) and feature_id not in features:
                diagnostics.append(_diagnostic(path, "checks", str(check_id), f"required feature not found: {feature_id}"))

    for feature_id, feature in features.items():
        path = Path(str(feature.get("_source_file", "<master>"))) if isinstance(feature, Mapping) else Path("<master>")
        if not isinstance(feature, Mapping):
            diagnostics.append(_diagnostic(path, "features", str(feature_id), "feature entry must be a mapping"))
            continue
        missing = sorted(FEATURE_REQUIRED_FIELDS - set(feature))
        if missing:
            diagnostics.append(_diagnostic(path, "features", str(feature_id), "missing required field(s): " + ", ".join(missing)))
        sensitive_missing = sorted(field for field in ENGINEERING_SENSITIVE_FEATURE_FIELDS if feature.get(field) in (None, "", [], {}))
        if sensitive_missing:
            diagnostics.append(_diagnostic(path, "features", str(feature_id), "engineering-sensitive field(s) missing: " + ", ".join(sensitive_missing)))

    missing_geometry = sorted(GEOMETRY_CHECK_IDS - set(checks))
    if missing_geometry:
        diagnostics.append(_diagnostic("<master>", "checks", None, "missing C13.4-P1 geometry checks: " + ", ".join(missing_geometry)))
    if diagnostics:
        raise CatalogLoadError(diagnostics)


def summarize_master_catalog(master: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "checks": len(master.get("checks", {}) or {}),
        "features": len(master.get("features", {}) or {}),
        "duplicate_ids": 0,
        "missing_feature_references": 0,
    }


__all__ = [
    "CatalogDiagnostic",
    "CatalogLoadError",
    "GEOMETRY_CHECK_IDS",
    "load_modular_catalog",
    "load_single_file_catalog",
    "load_single_file_master",
    "summarize_master_catalog",
    "validate_master_catalog",
]
