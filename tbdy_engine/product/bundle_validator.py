"""C13.4-P7 offline validator for geometry product smoke bundles.

The validator inspects an already-created C13.4-P6 output bundle. It does not
run product smoke generation, render reports, resolve features, or execute
engineering checks.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
import json

_SCOPE = "GEOMETRY_PRODUCT_BUNDLE_VALIDATION"
_REQUIRED_FILES = (
    "artifacts/check_results.json",
    "artifacts/adapter_diagnostics.json",
    "artifacts/run_summary.json",
    "artifacts/run_manifest.json",
    "reports/geometry_report.md",
    "product_smoke_summary.json",
    "product_smoke_manifest.json",
)
_REQUIRED_JSON_FILES = (
    "artifacts/check_results.json",
    "artifacts/adapter_diagnostics.json",
    "artifacts/run_summary.json",
    "artifacts/run_manifest.json",
    "product_smoke_summary.json",
    "product_smoke_manifest.json",
)
_ALLOWED_EXTRA_FILES = frozenset({"geometry_product_bundle_validation.json"})
_EXPECTED_TABLE_NAMES = (
    "executive_summary",
    "geometry_check_summary",
    "adapter_diagnostics",
    "beam_geometry_detail",
    "column_geometry_detail",
    "evidence_trace_detail",
    "artifact_manifest",
    "guardrails",
    "boundary_notes",
)
_EXPECTED_REPORT_TITLE = "# TBDY Geometry Vertical Slice Report — C13.4-P5"
_EXPECTED_SOURCE_STEPS = (
    "C13.4-P4 Geometry Vertical Slice Runner",
    "C13.4-P5 Geometry Markdown Report Renderer",
)
_EXPECTED_GUARDRAILS = {
    "geometry_only": True,
    "orchestration_only": True,
    "new_engineering_checks_added": False,
    "etabs_live_fetching_used": False,
    "excel_production_path_used": False,
    "streamlit_ui_used": False,
    "legacy_runtime_used": False,
    "rebar_flexure_shear_capacity_unlocked": False,
    "modal_mass_unlocked": False,
    "final_building_compliance_verdict_emitted": False,
}
_CANONICAL_CHECK_RESULT_STATUSES = frozenset({"OK", "FAIL", "NO_DATA", "BLOCKED", "OUT_OF_SCOPE", "WARNING"})
_FORBIDDEN_SUMMARY_TERMS = (
    "final_building_compliance",
    "beam_flexure",
    "beam_shear",
    "rebar_adequacy",
    "capacity_design",
    "governing_combo_selection",
    "force_envelope_selection",
    "SCWB",
    "PMM",
    "drift",
    "modal_mass",
    "ETABS_live_fetching",
    "Excel_production_path",
    "legacy_runtime_execution",
)
_CHECK_NAMES = (
    "json_parse",
    "summary_contract",
    "manifest_contract",
    "p4_artifact_consistency",
    "p5_report_contract",
    "guardrail_contract",
    "forbidden_scope_contract",
)


@dataclass(frozen=True, slots=True)
class GeometryProductBundleValidationResult:
    bundle_dir: Path
    validation_path: Path | None
    status: str
    error_count: int
    warning_count: int
    required_file_count: int
    checked_table_count: int
    check_result_count: int
    adapter_diagnostic_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "bundle_dir", Path(self.bundle_dir))
        if self.validation_path is not None:
            object.__setattr__(self, "validation_path", Path(self.validation_path))


def validate_geometry_product_bundle(
    *,
    bundle_dir: Path,
    validation_output_path: Path | None = None,
) -> GeometryProductBundleValidationResult:
    root = Path(bundle_dir)
    validation_path = Path(validation_output_path) if validation_output_path is not None else None
    errors: list[str] = []
    warnings: list[str] = []
    required_file_status = _validate_required_files(root, errors)
    parsed_json = _load_json_artifacts(root, required_file_status, errors)
    report_text = _load_report_text(root, required_file_status, errors)

    check_states = {name: "OK" for name in _CHECK_NAMES}
    if any(message.startswith("Invalid JSON") for message in errors):
        check_states["json_parse"] = "FAIL"

    _validate_summary_contract(parsed_json.get("product_smoke_summary.json"), errors, check_states)
    _validate_manifest_contract(parsed_json.get("product_smoke_manifest.json"), errors, check_states)
    _validate_p4_consistency(parsed_json, errors, check_states)
    checked_table_count = _validate_report_contract(report_text, errors, check_states)
    _validate_guardrails(parsed_json.get("product_smoke_manifest.json"), errors, check_states)
    _validate_forbidden_scope(root, required_file_status, errors, check_states)
    _validate_extra_files(root, warnings)

    check_results = parsed_json.get("artifacts/check_results.json")
    adapter_diagnostics = parsed_json.get("artifacts/adapter_diagnostics.json")
    check_result_count = len(check_results) if isinstance(check_results, list) else 0
    adapter_diagnostic_count = len(adapter_diagnostics) if isinstance(adapter_diagnostics, list) else 0
    status = "OK" if not errors else "FAIL"

    payload = {
        "bundle_dir": str(root),
        "checks": check_states,
        "counts": {
            "adapter_diagnostic_count": adapter_diagnostic_count,
            "check_result_count": check_result_count,
            "error_count": len(errors),
            "report_section_count": checked_table_count,
            "report_table_count": checked_table_count,
            "warning_count": len(warnings),
        },
        "errors": errors,
        "required_files": required_file_status,
        "scope": _SCOPE,
        "status": status,
        "warnings": warnings,
    }

    if validation_path is not None:
        _write_json(validation_path, payload)

    return GeometryProductBundleValidationResult(
        bundle_dir=root,
        validation_path=validation_path,
        status=status,
        error_count=len(errors),
        warning_count=len(warnings),
        required_file_count=len(_REQUIRED_FILES),
        checked_table_count=checked_table_count,
        check_result_count=check_result_count,
        adapter_diagnostic_count=adapter_diagnostic_count,
    )


def _validate_required_files(root: Path, errors: list[str]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for rel_path in _REQUIRED_FILES:
        path = root / rel_path
        if path.is_file():
            statuses[rel_path] = "OK"
        else:
            statuses[rel_path] = "MISSING"
            errors.append(f"Missing required file: {rel_path}")
    return statuses


def _load_json_artifacts(root: Path, required_file_status: Mapping[str, str], errors: list[str]) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for rel_path in _REQUIRED_JSON_FILES:
        if required_file_status.get(rel_path) != "OK":
            continue
        path = root / rel_path
        try:
            parsed[rel_path] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"Invalid JSON in {rel_path}: {exc.msg}")
        except OSError as exc:
            errors.append(f"Unreadable JSON file {rel_path}: {exc}")
    return parsed


def _load_report_text(root: Path, required_file_status: Mapping[str, str], errors: list[str]) -> str | None:
    rel_path = "reports/geometry_report.md"
    if required_file_status.get(rel_path) != "OK":
        return None
    try:
        return (root / rel_path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        errors.append(f"Report is not UTF-8 readable: {exc}")
    except OSError as exc:
        errors.append(f"Unreadable report file {rel_path}: {exc}")
    return None


def _validate_summary_contract(summary: object, errors: list[str], check_states: dict[str, str]) -> None:
    if not isinstance(summary, Mapping):
        errors.append("product_smoke_summary.json must contain a JSON object")
        check_states["summary_contract"] = "FAIL"
        return
    _expect(summary.get("status") == "OK", "product_smoke_summary.status must be OK", errors, check_states, "summary_contract")
    _expect(
        summary.get("scope") == "GEOMETRY_ONLY_PRODUCT_SMOKE",
        "product_smoke_summary.scope must be GEOMETRY_ONLY_PRODUCT_SMOKE",
        errors,
        check_states,
        "summary_contract",
    )
    p4 = summary.get("p4")
    p5 = summary.get("p5")
    if not isinstance(p4, Mapping):
        errors.append("product_smoke_summary.p4 must be a JSON object")
        check_states["summary_contract"] = "FAIL"
    else:
        for key in ("check_result_count", "adapter_diagnostic_count"):
            if not isinstance(p4.get(key), int):
                errors.append(f"product_smoke_summary.p4.{key} must be an integer")
                check_states["summary_contract"] = "FAIL"
        if not isinstance(p4.get("check_result_status_counts"), Mapping):
            errors.append("product_smoke_summary.p4.check_result_status_counts must be a mapping")
            check_states["summary_contract"] = "FAIL"
    if not isinstance(p5, Mapping):
        errors.append("product_smoke_summary.p5 must be a JSON object")
        check_states["summary_contract"] = "FAIL"
        return
    _expect(p5.get("section_count") == 9, "product_smoke_summary.p5.section_count must be 9", errors, check_states, "summary_contract")
    _expect(p5.get("table_count") == 9, "product_smoke_summary.p5.table_count must be 9", errors, check_states, "summary_contract")
    _expect(
        tuple(p5.get("table_names", ())) == _EXPECTED_TABLE_NAMES,
        "product_smoke_summary.p5.table_names must match the required C13.4-P5 table order",
        errors,
        check_states,
        "summary_contract",
    )


def _validate_manifest_contract(manifest: object, errors: list[str], check_states: dict[str, str]) -> None:
    if not isinstance(manifest, Mapping):
        errors.append("product_smoke_manifest.json must contain a JSON object")
        check_states["manifest_contract"] = "FAIL"
        return
    _expect(
        manifest.get("runner") == "C13.4-P6 Geometry Product Smoke",
        "product_smoke_manifest.runner must be C13.4-P6 Geometry Product Smoke",
        errors,
        check_states,
        "manifest_contract",
    )
    _expect(
        manifest.get("scope") == "GEOMETRY_ONLY_PRODUCT_SMOKE",
        "product_smoke_manifest.scope must be GEOMETRY_ONLY_PRODUCT_SMOKE",
        errors,
        check_states,
        "manifest_contract",
    )
    _expect(
        tuple(manifest.get("source_steps", ())) == _EXPECTED_SOURCE_STEPS,
        "product_smoke_manifest.source_steps must list the P4 runner then the P5 renderer",
        errors,
        check_states,
        "manifest_contract",
    )


def _validate_p4_consistency(parsed_json: Mapping[str, object], errors: list[str], check_states: dict[str, str]) -> None:
    check_results = parsed_json.get("artifacts/check_results.json")
    adapter_diagnostics = parsed_json.get("artifacts/adapter_diagnostics.json")
    run_summary = parsed_json.get("artifacts/run_summary.json")
    run_manifest = parsed_json.get("artifacts/run_manifest.json")
    summary = parsed_json.get("product_smoke_summary.json")

    _expect(isinstance(check_results, list), "artifacts/check_results.json must contain a JSON array", errors, check_states, "p4_artifact_consistency")
    _expect(isinstance(adapter_diagnostics, list), "artifacts/adapter_diagnostics.json must contain a JSON array", errors, check_states, "p4_artifact_consistency")
    _expect(isinstance(run_summary, Mapping), "artifacts/run_summary.json must contain a JSON object", errors, check_states, "p4_artifact_consistency")
    _expect(isinstance(run_manifest, Mapping), "artifacts/run_manifest.json must contain a JSON object", errors, check_states, "p4_artifact_consistency")

    if isinstance(check_results, list):
        for index, item in enumerate(check_results):
            if not isinstance(item, Mapping):
                errors.append(f"CheckResult entry at index {index} must be a JSON object")
                check_states["p4_artifact_consistency"] = "FAIL"
                continue
            status = item.get("status")
            if status not in _CANONICAL_CHECK_RESULT_STATUSES:
                errors.append(f"Non-canonical CheckResult status at index {index}: {status!r}")
                check_states["p4_artifact_consistency"] = "FAIL"
    if isinstance(adapter_diagnostics, list):
        for index, item in enumerate(adapter_diagnostics):
            if not isinstance(item, Mapping):
                errors.append(f"Adapter diagnostic entry at index {index} must be a JSON object")
                check_states["p4_artifact_consistency"] = "FAIL"
                continue
            status = item.get("status")
            if status in {"OK", "FAIL"}:
                errors.append(f"Adapter diagnostic status must not be {status} at index {index}")
                check_states["p4_artifact_consistency"] = "FAIL"

    if isinstance(run_summary, Mapping) and isinstance(check_results, list):
        _expect(
            run_summary.get("check_result_count") == len(check_results),
            "run_summary.check_result_count must equal len(check_results.json)",
            errors,
            check_states,
            "p4_artifact_consistency",
        )
    if isinstance(run_summary, Mapping) and isinstance(adapter_diagnostics, list):
        _expect(
            run_summary.get("adapter_diagnostic_count") == len(adapter_diagnostics),
            "run_summary.adapter_diagnostic_count must equal len(adapter_diagnostics.json)",
            errors,
            check_states,
            "p4_artifact_consistency",
        )
    if isinstance(run_summary, Mapping) and isinstance(summary, Mapping):
        p4 = summary.get("p4")
        if isinstance(p4, Mapping):
            _expect(
                p4.get("check_result_count") == run_summary.get("check_result_count"),
                "product_smoke_summary.p4.check_result_count must equal run_summary.check_result_count",
                errors,
                check_states,
                "p4_artifact_consistency",
            )
            _expect(
                p4.get("adapter_diagnostic_count") == run_summary.get("adapter_diagnostic_count"),
                "product_smoke_summary.p4.adapter_diagnostic_count must equal run_summary.adapter_diagnostic_count",
                errors,
                check_states,
                "p4_artifact_consistency",
            )
            _expect(
                p4.get("check_result_status_counts") == run_summary.get("check_result_status_counts"),
                "product_smoke_summary.p4.check_result_status_counts must equal run_summary.check_result_status_counts",
                errors,
                check_states,
                "p4_artifact_consistency",
            )
        else:
            errors.append("product_smoke_summary.p4 must be present for P4 consistency validation")
            check_states["p4_artifact_consistency"] = "FAIL"
    if isinstance(run_summary, Mapping) and isinstance(check_results, list):
        actual_counts = dict(sorted(Counter(str(item.get("status")) for item in check_results if isinstance(item, Mapping)).items()))
        expected_counts = run_summary.get("check_result_status_counts")
        if isinstance(expected_counts, Mapping):
            _expect(
                {str(key): value for key, value in expected_counts.items()} == actual_counts,
                "run_summary.check_result_status_counts must match CheckResult statuses",
                errors,
                check_states,
                "p4_artifact_consistency",
            )


def _validate_report_contract(report_text: str | None, errors: list[str], check_states: dict[str, str]) -> int:
    if report_text is None:
        check_states["p5_report_contract"] = "FAIL"
        return 0
    if not report_text.startswith(_EXPECTED_REPORT_TITLE):
        errors.append("reports/geometry_report.md must start with the C13.4-P5 report title")
        check_states["p5_report_contract"] = "FAIL"
    markers = [f"Table name: {table_name}" for table_name in _EXPECTED_TABLE_NAMES]
    positions: list[int] = []
    for marker in markers:
        position = report_text.find(marker)
        if position == -1:
            errors.append(f"Missing report table marker: {marker}")
            check_states["p5_report_contract"] = "FAIL"
        positions.append(position)
    present_positions = [position for position in positions if position >= 0]
    if present_positions != sorted(present_positions):
        errors.append("Report table markers must appear in the required order")
        check_states["p5_report_contract"] = "FAIL"
    return len(present_positions)


def _validate_guardrails(manifest: object, errors: list[str], check_states: dict[str, str]) -> None:
    if not isinstance(manifest, Mapping):
        check_states["guardrail_contract"] = "FAIL"
        return
    guardrails = manifest.get("guardrails")
    if not isinstance(guardrails, Mapping):
        errors.append("product_smoke_manifest.guardrails must be a JSON object")
        check_states["guardrail_contract"] = "FAIL"
        return
    for key, expected_value in _EXPECTED_GUARDRAILS.items():
        actual_value = guardrails.get(key)
        if actual_value is not expected_value:
            errors.append(f"Guardrail {key} must be {expected_value}")
            check_states["guardrail_contract"] = "FAIL"


def _validate_forbidden_scope(root: Path, required_file_status: Mapping[str, str], errors: list[str], check_states: dict[str, str]) -> None:
    rel_path = "product_smoke_summary.json"
    if required_file_status.get(rel_path) != "OK":
        check_states["forbidden_scope_contract"] = "FAIL"
        return
    try:
        summary_text = (root / rel_path).read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"Unreadable product_smoke_summary.json for forbidden scope validation: {exc}")
        check_states["forbidden_scope_contract"] = "FAIL"
        return
    for term in _FORBIDDEN_SUMMARY_TERMS:
        if term in summary_text:
            errors.append(f"Forbidden scope term found in product_smoke_summary.json: {term}")
            check_states["forbidden_scope_contract"] = "FAIL"


def _validate_extra_files(root: Path, warnings: list[str]) -> None:
    if not root.exists():
        return
    required = set(_REQUIRED_FILES)
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        rel = path.relative_to(root).as_posix()
        if rel in required or path.name in _ALLOWED_EXTRA_FILES:
            continue
        warnings.append(f"Extra non-contract file in bundle: {rel}")


def _expect(condition: bool, message: str, errors: list[str], check_states: dict[str, str], check_name: str) -> None:
    if not condition:
        errors.append(message)
        check_states[check_name] = "FAIL"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


__all__ = ["GeometryProductBundleValidationResult", "validate_geometry_product_bundle"]
