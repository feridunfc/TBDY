"""C13.4-P8 offline golden regression gate for the geometry product slice.

The gate runs the existing product smoke API, validates the generated bundle via
the existing bundle validator API, computes a path-normalized semantic
fingerprint, and compares it with a committed golden fingerprint.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json

from tbdy_engine.product.bundle_validator import validate_geometry_product_bundle
from tbdy_engine.product.geometry_product_smoke import run_geometry_product_smoke

_FINGERPRINT_VERSION = "C13.4-P8.v1"
_FINGERPRINT_SCOPE = "GEOMETRY_ONLY_GOLDEN_REGRESSION"
_REPORT_SCOPE = "GEOMETRY_GOLDEN_REGRESSION"
_EXPECTED_REPORT_TITLE = "# TBDY Geometry Vertical Slice Report — C13.4-P5"
_TABLE_MARKER_PREFIX = "Table name: "


@dataclass(frozen=True, slots=True)
class GeometryGoldenRegressionResult:
    status: str
    output_dir: Path
    bundle_dir: Path
    validation_path: Path
    regression_report_path: Path
    golden_fingerprint_path: Path
    actual_fingerprint: dict[str, object]
    expected_fingerprint: dict[str, object]
    difference_count: int
    error_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "output_dir", Path(self.output_dir))
        object.__setattr__(self, "bundle_dir", Path(self.bundle_dir))
        object.__setattr__(self, "validation_path", Path(self.validation_path))
        object.__setattr__(self, "regression_report_path", Path(self.regression_report_path))
        object.__setattr__(self, "golden_fingerprint_path", Path(self.golden_fingerprint_path))
        object.__setattr__(self, "actual_fingerprint", dict(self.actual_fingerprint))
        object.__setattr__(self, "expected_fingerprint", dict(self.expected_fingerprint))


def run_geometry_golden_regression(
    *,
    feature_snapshot_path: Path,
    output_dir: Path,
    golden_fingerprint_path: Path,
    regression_report_path: Path | None = None,
) -> GeometryGoldenRegressionResult:
    out_dir = Path(output_dir)
    bundle_dir = out_dir / "product_smoke"
    validation_path = bundle_dir / "geometry_product_bundle_validation.json"
    golden_path = Path(golden_fingerprint_path)
    report_path = Path(regression_report_path) if regression_report_path is not None else out_dir / "geometry_golden_regression_report.json"
    feature_path = Path(feature_snapshot_path)

    errors: list[str] = []
    differences: list[str] = []
    actual_fingerprint: dict[str, object] = {}
    expected_fingerprint: dict[str, object] = {}

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        run_geometry_product_smoke(feature_snapshot_path=feature_path, output_dir=bundle_dir)
        validation_result = validate_geometry_product_bundle(
            bundle_dir=bundle_dir,
            validation_output_path=validation_path,
        )
        if validation_result.status != "OK":
            errors.append(f"P7 bundle validation failed with status {validation_result.status}")
        actual_fingerprint = compute_geometry_product_fingerprint(bundle_dir=bundle_dir)
    except Exception as exc:  # pragma: no cover - defensive boundary for product gate stability.
        errors.append(f"Regression execution failed: {exc}")

    try:
        expected_fingerprint = _load_expected_fingerprint(golden_path)
    except FileNotFoundError:
        errors.append(f"Missing golden fingerprint file: {golden_path}")
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid golden fingerprint JSON: {exc.msg}")
    except ValueError as exc:
        errors.append(str(exc))

    if expected_fingerprint and actual_fingerprint and expected_fingerprint != actual_fingerprint:
        errors.append("Golden fingerprint mismatch")
        differences.extend(_top_level_differences(expected_fingerprint, actual_fingerprint))

    status = "OK" if not errors and not differences else "FAIL"
    report = {
        "actual_fingerprint": actual_fingerprint,
        "bundle_dir": str(bundle_dir),
        "counts": {
            "difference_count": len(differences),
            "error_count": len(errors),
        },
        "differences": differences,
        "errors": errors,
        "expected_fingerprint": expected_fingerprint,
        "feature_snapshot_path": str(feature_path),
        "golden_fingerprint_path": str(golden_path),
        "output_dir": str(out_dir),
        "scope": _REPORT_SCOPE,
        "status": status,
        "validation_path": str(validation_path),
    }
    _write_json(report_path, report)

    return GeometryGoldenRegressionResult(
        status=status,
        output_dir=out_dir,
        bundle_dir=bundle_dir,
        validation_path=validation_path,
        regression_report_path=report_path,
        golden_fingerprint_path=golden_path,
        actual_fingerprint=actual_fingerprint,
        expected_fingerprint=expected_fingerprint,
        difference_count=len(differences),
        error_count=len(errors),
    )


def compute_geometry_product_fingerprint(*, bundle_dir: Path) -> dict[str, object]:
    root = Path(bundle_dir)
    product_summary = _read_json_object(root / "product_smoke_summary.json")
    product_manifest = _read_json_object(root / "product_smoke_manifest.json")
    validation = _read_json_object(root / "geometry_product_bundle_validation.json")
    check_results = _read_json_array(root / "artifacts" / "check_results.json")
    report_text = (root / "reports" / "geometry_report.md").read_text(encoding="utf-8")

    p4 = _mapping_value(product_summary.get("p4"))
    validation_counts = _mapping_value(validation.get("counts"))
    return {
        "checks": _check_rows(check_results),
        "fingerprint_version": _FINGERPRINT_VERSION,
        "guardrails": dict(sorted(_mapping_value(product_manifest.get("guardrails")).items())),
        "p6": {
            "adapter_diagnostic_count": _int_value(p4.get("adapter_diagnostic_count", 0)),
            "check_result_count": _int_value(p4.get("check_result_count", 0)),
            "check_result_status_counts": {
                str(key): _int_value(value)
                for key, value in sorted(_mapping_value(p4.get("check_result_status_counts")).items())
            },
            "scope": str(product_summary.get("scope", "")),
            "status": str(product_summary.get("status", "")),
        },
        "p7": {
            "error_count": _int_value(validation_counts.get("error_count", 0)),
            "report_table_count": _int_value(validation_counts.get("report_table_count", 0)),
            "required_file_count": len(_mapping_value(validation.get("required_files"))),
            "scope": str(validation.get("scope", "")),
            "status": str(validation.get("status", "")),
        },
        "report": {
            "table_names": _extract_table_names(report_text),
            "title": report_text.splitlines()[0] if report_text else "",
        },
        "scope": _FINGERPRINT_SCOPE,
    }


def _check_rows(check_results: Sequence[object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for raw_result in check_results:
        if not isinstance(raw_result, Mapping):
            continue
        rows.append(
            {
                "check_id": str(raw_result.get("check_id", "")),
                "component_type": str(raw_result.get("component_type", "")),
                "limit": raw_result.get("limit"),
                "status": str(raw_result.get("status", "")),
                "unit": str(raw_result.get("unit", "")),
                "value": raw_result.get("value"),
            }
        )
    return sorted(
        rows,
        key=lambda item: (
            str(item["component_type"]),
            str(item["check_id"]),
            str(item["status"]),
            _sortable_number(item["value"]),
            _sortable_number(item["limit"]),
        ),
    )


def _extract_table_names(report_text: str) -> list[str]:
    names: list[str] = []
    for line in report_text.splitlines():
        if line.startswith(_TABLE_MARKER_PREFIX):
            names.append(line.removeprefix(_TABLE_MARKER_PREFIX).strip())
    return names


def _load_expected_fingerprint(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Golden fingerprint must contain a JSON object")
    return payload


def _top_level_differences(expected: Mapping[str, object], actual: Mapping[str, object]) -> list[str]:
    keys = sorted(set(expected) | set(actual))
    return [f"Mismatch at key: {key}" for key in keys if expected.get(key) != actual.get(key)]


def _read_json_object(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected JSON object at {path}")
    return payload


def _read_json_array(path: Path) -> list[object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected JSON array at {path}")
    return payload


def _mapping_value(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _int_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return 0


def _sortable_number(value: object) -> tuple[int, float | str]:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (0, float(value))
    return (1, str(value))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = [
    "GeometryGoldenRegressionResult",
    "compute_geometry_product_fingerprint",
    "run_geometry_golden_regression",
]
