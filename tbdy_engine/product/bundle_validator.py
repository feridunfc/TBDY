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
    "artifacts/coverage_rows.json",
    "artifacts/coverage_execution_trace.json",
    "artifacts/check_results.json",
    "artifacts/adapter_diagnostics.json",
    "artifacts/run_summary.json",
    "artifacts/run_manifest.json",
    "reports/geometry_report.md",
    "product_smoke_summary.json",
    "product_smoke_manifest.json",
)
_REQUIRED_JSON_FILES = (
    "artifacts/coverage_rows.json",
    "artifacts/coverage_execution_trace.json",
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
_FORBIDDEN_COVERAGE_FIELD_NAMES = frozenset({
    "check_result",
    "result_status",
    "ratio",
    "value",
    "limit",
    "formula",
    "pass_rule",
    "utilization",
    "governing_combo",
    "engineering_verdict",
})
_COVERAGE_IDENTITY_FIELDS = ("check_id", "component_type", "component_id", "coverage_status")
_TRACE_REQUIRED_FIELDS = (
    "component_type",
    "component_id",
    "check_id",
    "coverage_status",
    "check_input_emitted",
    "adapter_status",
    "adapter_reason",
    "adapter_diagnostic_index",
    "check_result_emitted",
    "check_result_index",
    "check_result_status",
)
_TRACE_ALLOWED_ADAPTER_STATUSES = frozenset({"READY", "BLOCKED", "NO_DATA", "OUT_OF_SCOPE"})
_TRACE_FORBIDDEN_FIELD_NAMES = frozenset({
    "value",
    "limit",
    "ratio",
    "demand",
    "capacity",
    "formula",
    "pass_rule",
    "utilization",
    "governing_combo",
    "engineering_verdict",
})
_TRACE_SUMMARY_INTEGER_FIELDS = (
    "coverage_execution_trace_count",
    "check_input_emitted_count",
    "check_input_not_emitted_count",
    "check_result_emitted_count",
    "check_result_not_emitted_count",
)
_TRACE_SUMMARY_MAPPING_FIELDS = (
    "trace_adapter_status_counts",
    "trace_result_status_counts",
)
_CHECK_NAMES = (
    "json_parse",
    "summary_contract",
    "manifest_contract",
    "p4_artifact_consistency",
    "coverage_artifact_contract",
    "execution_trace_contract",
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
    _validate_coverage_artifact(parsed_json, errors, check_states)
    _validate_execution_trace_artifact(parsed_json, errors, check_states)
    checked_table_count = _validate_report_contract(report_text, errors, check_states)
    _validate_guardrails(parsed_json.get("product_smoke_manifest.json"), errors, check_states)
    _validate_forbidden_scope(root, required_file_status, errors, check_states)
    _validate_extra_files(root, warnings)

    coverage_rows = parsed_json.get("artifacts/coverage_rows.json")
    execution_trace = parsed_json.get("artifacts/coverage_execution_trace.json")
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
            "coverage_row_count": len(coverage_rows) if isinstance(coverage_rows, list) else 0,
            "coverage_execution_trace_count": len(parsed_json.get("artifacts/coverage_execution_trace.json", ()))
            if isinstance(parsed_json.get("artifacts/coverage_execution_trace.json"), list)
            else 0,
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
        for key in (
            "check_result_count",
            "adapter_diagnostic_count",
            "coverage_row_count",
            *_TRACE_SUMMARY_INTEGER_FIELDS,
        ):
            if not isinstance(p4.get(key), int):
                errors.append(f"product_smoke_summary.p4.{key} must be an integer")
                check_states["summary_contract"] = "FAIL"
        if not isinstance(p4.get("check_result_status_counts"), Mapping):
            errors.append("product_smoke_summary.p4.check_result_status_counts must be a mapping")
            check_states["summary_contract"] = "FAIL"
        if not isinstance(p4.get("coverage_status_counts"), Mapping):
            errors.append("product_smoke_summary.p4.coverage_status_counts must be a mapping")
            check_states["summary_contract"] = "FAIL"
        for key in _TRACE_SUMMARY_MAPPING_FIELDS:
            if not isinstance(p4.get(key), Mapping):
                errors.append(f"product_smoke_summary.p4.{key} must be a mapping")
                check_states["summary_contract"] = "FAIL"
        outputs = summary.get("outputs")
        if not isinstance(outputs, Mapping) or not isinstance(
            outputs.get("coverage_execution_trace_json"), str
        ):
            errors.append(
                "product_smoke_summary.outputs.coverage_execution_trace_json must be a string"
            )
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
    artifact_files = manifest.get("artifact_files")
    _expect(
        isinstance(artifact_files, list) and "artifacts/coverage_rows.json" in artifact_files,
        "product_smoke_manifest.artifact_files must include artifacts/coverage_rows.json",
        errors,
        check_states,
        "manifest_contract",
    )
    _expect(
        isinstance(artifact_files, list)
        and "artifacts/coverage_execution_trace.json" in artifact_files,
        "product_smoke_manifest.artifact_files must include artifacts/coverage_execution_trace.json",
        errors,
        check_states,
        "manifest_contract",
    )


def _validate_p4_consistency(parsed_json: Mapping[str, object], errors: list[str], check_states: dict[str, str]) -> None:
    coverage_rows = parsed_json.get("artifacts/coverage_rows.json")
    execution_trace = parsed_json.get("artifacts/coverage_execution_trace.json")
    check_results = parsed_json.get("artifacts/check_results.json")
    adapter_diagnostics = parsed_json.get("artifacts/adapter_diagnostics.json")
    run_summary = parsed_json.get("artifacts/run_summary.json")
    run_manifest = parsed_json.get("artifacts/run_manifest.json")
    summary = parsed_json.get("product_smoke_summary.json")

    _expect(isinstance(coverage_rows, list), "artifacts/coverage_rows.json must contain a JSON array", errors, check_states, "p4_artifact_consistency")
    _expect(isinstance(execution_trace, list), "artifacts/coverage_execution_trace.json must contain a JSON array", errors, check_states, "p4_artifact_consistency")
    _expect(isinstance(check_results, list), "artifacts/check_results.json must contain a JSON array", errors, check_states, "p4_artifact_consistency")
    _expect(isinstance(adapter_diagnostics, list), "artifacts/adapter_diagnostics.json must contain a JSON array", errors, check_states, "p4_artifact_consistency")
    _expect(isinstance(run_summary, Mapping), "artifacts/run_summary.json must contain a JSON object", errors, check_states, "p4_artifact_consistency")
    _expect(isinstance(run_manifest, Mapping), "artifacts/run_manifest.json must contain a JSON object", errors, check_states, "p4_artifact_consistency")

    if isinstance(run_manifest, Mapping):
        _expect(
            run_manifest.get("coverage_authority") == "CoverageBuilder",
            "run_manifest.coverage_authority must be CoverageBuilder",
            errors,
            check_states,
            "p4_artifact_consistency",
        )
        _expect(
            run_manifest.get("coverage_artifact_source") == "authoritative_runtime_objects",
            "run_manifest.coverage_artifact_source must be authoritative_runtime_objects",
            errors,
            check_states,
            "p4_artifact_consistency",
        )
        _expect(
            run_manifest.get("coverage_reconstructed_from_check_results") is False,
            "run_manifest.coverage_reconstructed_from_check_results must be false",
            errors,
            check_states,
            "p4_artifact_consistency",
        )
        _expect(
            run_manifest.get("synthetic_coverage_path_used") is False,
            "run_manifest.synthetic_coverage_path_used must be false",
            errors,
            check_states,
            "p4_artifact_consistency",
        )
        _expect(
            "coverage_rows.json" in tuple(run_manifest.get("artifact_files", ())),
            "run_manifest.artifact_files must include coverage_rows.json",
            errors,
            check_states,
            "p4_artifact_consistency",
        )
        _expect(
            "coverage_execution_trace.json" in tuple(run_manifest.get("artifact_files", ())),
            "run_manifest.artifact_files must include coverage_execution_trace.json",
            errors,
            check_states,
            "p4_artifact_consistency",
        )
        expected_trace_manifest = {
            "execution_trace_authority": "runtime_coverage_adapter_engine_chain",
            "execution_trace_artifact_source": "authoritative_runtime_objects",
            "execution_trace_reconstructed_from_serialized_artifacts": False,
            "execution_trace_covers_every_coverage_row": True,
            "check_input_coverage_object_identity_required": True,
        }
        for field_name, expected_value in expected_trace_manifest.items():
            _expect(
                run_manifest.get(field_name) == expected_value,
                f"run_manifest.{field_name} must equal {expected_value!r}",
                errors,
                check_states,
                "p4_artifact_consistency",
            )

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
            _expect(
                p4.get("coverage_row_count") == run_summary.get("coverage_row_count"),
                "product_smoke_summary.p4.coverage_row_count must equal run_summary.coverage_row_count",
                errors,
                check_states,
                "p4_artifact_consistency",
            )
            _expect(
                p4.get("coverage_status_counts") == run_summary.get("coverage_status_counts"),
                "product_smoke_summary.p4.coverage_status_counts must equal run_summary.coverage_status_counts",
                errors,
                check_states,
                "p4_artifact_consistency",
            )
            for field_name in (*_TRACE_SUMMARY_INTEGER_FIELDS, *_TRACE_SUMMARY_MAPPING_FIELDS):
                _expect(
                    p4.get(field_name) == run_summary.get(field_name),
                    f"product_smoke_summary.p4.{field_name} must equal run_summary.{field_name}",
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


def _validate_coverage_artifact(
    parsed_json: Mapping[str, object],
    errors: list[str],
    check_states: dict[str, str],
) -> None:
    rows = parsed_json.get("artifacts/coverage_rows.json")
    run_summary = parsed_json.get("artifacts/run_summary.json")
    check_name = "coverage_artifact_contract"
    if not isinstance(rows, list):
        errors.append("artifacts/coverage_rows.json must contain a JSON array")
        check_states[check_name] = "FAIL"
        return

    canonical_keys: list[tuple[str, str, str]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    status_counts: Counter[str] = Counter()
    for index, item in enumerate(rows):
        if not isinstance(item, Mapping):
            errors.append(f"CoverageRow entry at index {index} must be a JSON object")
            check_states[check_name] = "FAIL"
            continue
        missing_fields = [field for field in _COVERAGE_IDENTITY_FIELDS if field not in item]
        if missing_fields:
            errors.append(
                f"CoverageRow entry at index {index} missing required identity fields: "
                + ", ".join(missing_fields)
            )
            check_states[check_name] = "FAIL"
            continue
        identity_values = {field: item.get(field) for field in _COVERAGE_IDENTITY_FIELDS}
        invalid_fields = [
            field
            for field, value in identity_values.items()
            if not isinstance(value, str) or not value
        ]
        if invalid_fields:
            errors.append(
                f"CoverageRow entry at index {index} has invalid identity fields: "
                + ", ".join(invalid_fields)
            )
            check_states[check_name] = "FAIL"
            continue

        key = (
            str(item["component_type"]),
            str(item["component_id"]),
            str(item["check_id"]),
        )
        canonical_keys.append(key)
        if key in seen_keys:
            errors.append(f"Duplicate CoverageRow canonical key at index {index}: {key!r}")
            check_states[check_name] = "FAIL"
        seen_keys.add(key)
        status_counts[str(item["coverage_status"])] += 1

        for field_path in _forbidden_coverage_field_paths(item):
            errors.append(
                f"Forbidden engineering-result field in coverage artifact at index {index}: {field_path}"
            )
            check_states[check_name] = "FAIL"

    if canonical_keys != sorted(canonical_keys):
        errors.append("CoverageRow entries must be in canonical component_type/component_id/check_id order")
        check_states[check_name] = "FAIL"

    if not isinstance(run_summary, Mapping):
        errors.append("run_summary.json must be available for coverage artifact validation")
        check_states[check_name] = "FAIL"
        return
    _expect(
        run_summary.get("coverage_row_count") == len(rows),
        "run_summary.coverage_row_count must equal len(coverage_rows.json)",
        errors,
        check_states,
        check_name,
    )
    expected_status_counts = run_summary.get("coverage_status_counts")
    actual_status_counts = {key: int(status_counts[key]) for key in sorted(status_counts)}
    _expect(
        isinstance(expected_status_counts, Mapping)
        and {str(key): value for key, value in expected_status_counts.items()} == actual_status_counts,
        "run_summary.coverage_status_counts must match authoritative CoverageRow statuses",
        errors,
        check_states,
        check_name,
    )


def _forbidden_coverage_field_paths(value: object, *, path: str = "$") -> tuple[str, ...]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text.casefold() in _FORBIDDEN_COVERAGE_FIELD_NAMES:
                found.append(child_path)
            found.extend(_forbidden_coverage_field_paths(nested, path=child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            found.extend(_forbidden_coverage_field_paths(nested, path=f"{path}[{index}]"))
    return tuple(found)



def _validate_execution_trace_artifact(
    parsed_json: Mapping[str, object],
    errors: list[str],
    check_states: dict[str, str],
) -> None:
    trace = parsed_json.get("artifacts/coverage_execution_trace.json")
    coverage_rows = parsed_json.get("artifacts/coverage_rows.json")
    check_results = parsed_json.get("artifacts/check_results.json")
    adapter_diagnostics = parsed_json.get("artifacts/adapter_diagnostics.json")
    run_summary = parsed_json.get("artifacts/run_summary.json")
    product_summary = parsed_json.get("product_smoke_summary.json")
    check_name = "execution_trace_contract"

    if not isinstance(trace, list):
        errors.append("artifacts/coverage_execution_trace.json must contain a JSON array")
        check_states[check_name] = "FAIL"
        return
    if not isinstance(coverage_rows, list):
        errors.append("coverage_rows.json must be available for execution trace validation")
        check_states[check_name] = "FAIL"
        return
    if not isinstance(check_results, list):
        errors.append("check_results.json must be available for execution trace validation")
        check_states[check_name] = "FAIL"
        return
    if not isinstance(adapter_diagnostics, list):
        errors.append("adapter_diagnostics.json must be available for execution trace validation")
        check_states[check_name] = "FAIL"
        return

    coverage_by_key: dict[tuple[str, str, str], Mapping[str, object]] = {}
    for item in coverage_rows:
        if not isinstance(item, Mapping):
            continue
        key = _mapping_identity_key(item)
        if key is not None:
            coverage_by_key[key] = item

    trace_keys: list[tuple[str, str, str]] = []
    seen_keys: set[tuple[str, str, str]] = set()
    referenced_results: set[int] = set()
    referenced_diagnostics: set[int] = set()
    adapter_status_counts: Counter[str] = Counter()
    result_status_counts: Counter[str] = Counter()
    check_input_emitted_count = 0
    check_result_emitted_count = 0

    for index, item in enumerate(trace):
        if not isinstance(item, Mapping):
            errors.append(f"Execution trace entry at index {index} must be a JSON object")
            check_states[check_name] = "FAIL"
            continue
        missing_fields = [field for field in _TRACE_REQUIRED_FIELDS if field not in item]
        if missing_fields:
            errors.append(
                f"Execution trace entry at index {index} missing required fields: "
                + ", ".join(missing_fields)
            )
            check_states[check_name] = "FAIL"
            continue

        key = _mapping_identity_key(item)
        coverage_status = item.get("coverage_status")
        check_input_emitted = item.get("check_input_emitted")
        adapter_status = item.get("adapter_status")
        adapter_reason = item.get("adapter_reason")
        adapter_diagnostic_index = item.get("adapter_diagnostic_index")
        check_result_emitted = item.get("check_result_emitted")
        check_result_index = item.get("check_result_index")
        check_result_status = item.get("check_result_status")

        if key is None:
            errors.append(f"Execution trace entry at index {index} has invalid identity fields")
            check_states[check_name] = "FAIL"
        else:
            trace_keys.append(key)
            if key in seen_keys:
                errors.append(f"Duplicate execution trace canonical key at index {index}: {key!r}")
                check_states[check_name] = "FAIL"
            seen_keys.add(key)
            coverage_item = coverage_by_key.get(key)
            if coverage_item is None:
                errors.append(f"Execution trace key has no matching CoverageRow at index {index}: {key!r}")
                check_states[check_name] = "FAIL"
            elif coverage_status != coverage_item.get("coverage_status"):
                errors.append(f"Execution trace coverage_status mismatch at index {index}")
                check_states[check_name] = "FAIL"

        if not isinstance(coverage_status, str) or not coverage_status:
            errors.append(f"Execution trace coverage_status must be a non-empty string at index {index}")
            check_states[check_name] = "FAIL"
        if not isinstance(check_input_emitted, bool):
            errors.append(f"Execution trace check_input_emitted must be boolean at index {index}")
            check_states[check_name] = "FAIL"
        if adapter_status not in _TRACE_ALLOWED_ADAPTER_STATUSES:
            errors.append(f"Execution trace adapter_status is invalid at index {index}: {adapter_status!r}")
            check_states[check_name] = "FAIL"
        if adapter_reason is not None and not isinstance(adapter_reason, str):
            errors.append(f"Execution trace adapter_reason must be string or null at index {index}")
            check_states[check_name] = "FAIL"
        if not _is_optional_non_negative_int(adapter_diagnostic_index):
            errors.append(f"Execution trace adapter_diagnostic_index is invalid at index {index}")
            check_states[check_name] = "FAIL"
        if not isinstance(check_result_emitted, bool):
            errors.append(f"Execution trace check_result_emitted must be boolean at index {index}")
            check_states[check_name] = "FAIL"
        if not _is_optional_non_negative_int(check_result_index):
            errors.append(f"Execution trace check_result_index is invalid at index {index}")
            check_states[check_name] = "FAIL"
        if check_result_status is not None and not isinstance(check_result_status, str):
            errors.append(f"Execution trace check_result_status must be string or null at index {index}")
            check_states[check_name] = "FAIL"

        terminal_valid = True
        if check_input_emitted is True:
            terminal_valid = (
                adapter_status == "READY"
                and adapter_reason is None
                and adapter_diagnostic_index is None
                and check_result_emitted is True
                and _is_non_negative_int(check_result_index)
                and isinstance(check_result_status, str)
                and bool(check_result_status)
            )
        elif check_input_emitted is False:
            terminal_valid = (
                adapter_status in {"BLOCKED", "NO_DATA", "OUT_OF_SCOPE"}
                and isinstance(adapter_reason, str)
                and bool(adapter_reason.strip())
                and _is_non_negative_int(adapter_diagnostic_index)
                and check_result_emitted is False
                and check_result_index is None
                and check_result_status is None
            )
        if not terminal_valid:
            errors.append(f"Execution trace terminal invariant violation at index {index}")
            check_states[check_name] = "FAIL"

        if isinstance(adapter_status, str):
            adapter_status_counts[adapter_status] += 1
        if check_input_emitted is True:
            check_input_emitted_count += 1
        if check_result_emitted is True:
            check_result_emitted_count += 1
        if isinstance(check_result_status, str):
            result_status_counts[check_result_status] += 1

        if _is_non_negative_int(check_result_index):
            result_index = int(check_result_index)
            if result_index >= len(check_results):
                errors.append(f"Execution trace check_result_index out of range at index {index}: {result_index}")
                check_states[check_name] = "FAIL"
            else:
                if result_index in referenced_results:
                    errors.append(f"CheckResult index linked more than once: {result_index}")
                    check_states[check_name] = "FAIL"
                referenced_results.add(result_index)
                result_item = check_results[result_index]
                if not isinstance(result_item, Mapping):
                    errors.append(f"Referenced CheckResult at index {result_index} must be an object")
                    check_states[check_name] = "FAIL"
                elif key is not None and (
                    result_item.get("component_type") != key[0]
                    or result_item.get("component") != key[1]
                    or result_item.get("check_id") != key[2]
                    or result_item.get("status") != check_result_status
                ):
                    errors.append(f"Execution trace CheckResult identity/status mismatch at index {index}")
                    check_states[check_name] = "FAIL"

        if _is_non_negative_int(adapter_diagnostic_index):
            diagnostic_index = int(adapter_diagnostic_index)
            if diagnostic_index >= len(adapter_diagnostics):
                errors.append(
                    f"Execution trace adapter_diagnostic_index out of range at index {index}: {diagnostic_index}"
                )
                check_states[check_name] = "FAIL"
            else:
                if diagnostic_index in referenced_diagnostics:
                    errors.append(f"Adapter diagnostic index linked more than once: {diagnostic_index}")
                    check_states[check_name] = "FAIL"
                referenced_diagnostics.add(diagnostic_index)
                diagnostic_item = adapter_diagnostics[diagnostic_index]
                if not isinstance(diagnostic_item, Mapping):
                    errors.append(f"Referenced adapter diagnostic at index {diagnostic_index} must be an object")
                    check_states[check_name] = "FAIL"
                elif key is not None and (
                    diagnostic_item.get("component_type") != key[0]
                    or diagnostic_item.get("component_id") != key[1]
                    or diagnostic_item.get("check_id") != key[2]
                    or diagnostic_item.get("status") != adapter_status
                    or diagnostic_item.get("reason") != adapter_reason
                ):
                    errors.append(f"Execution trace adapter diagnostic identity/status/reason mismatch at index {index}")
                    check_states[check_name] = "FAIL"

        for field_path in _forbidden_trace_field_paths(item):
            errors.append(f"Forbidden engineering payload field in execution trace at index {index}: {field_path}")
            check_states[check_name] = "FAIL"

    if trace_keys != sorted(trace_keys):
        errors.append("Execution trace entries must be in canonical component_type/component_id/check_id order")
        check_states[check_name] = "FAIL"
    if set(trace_keys) != set(coverage_by_key):
        errors.append("Execution trace keys must exactly equal coverage_rows.json keys")
        check_states[check_name] = "FAIL"
    if referenced_results != set(range(len(check_results))):
        errors.append("Every CheckResult index must be referenced exactly once by the execution trace")
        check_states[check_name] = "FAIL"
    coverage_specific_diagnostics = {
        index
        for index, item in enumerate(adapter_diagnostics)
        if isinstance(item, Mapping) and item.get("check_id") != "geometry_check_input_adapter"
    }
    if referenced_diagnostics != coverage_specific_diagnostics:
        errors.append(
            "Every coverage-specific adapter diagnostic must be referenced exactly once by the execution trace"
        )
        check_states[check_name] = "FAIL"

    if not isinstance(run_summary, Mapping):
        errors.append("run_summary.json must be available for execution trace summary validation")
        check_states[check_name] = "FAIL"
        return

    actual_summary = {
        "coverage_execution_trace_count": len(trace),
        "check_input_emitted_count": check_input_emitted_count,
        "check_input_not_emitted_count": len(trace) - check_input_emitted_count,
        "check_result_emitted_count": check_result_emitted_count,
        "check_result_not_emitted_count": len(trace) - check_result_emitted_count,
        "trace_adapter_status_counts": {
            key: int(adapter_status_counts[key]) for key in sorted(adapter_status_counts)
        },
        "trace_result_status_counts": {
            key: int(result_status_counts[key]) for key in sorted(result_status_counts)
        },
    }
    for field_name, actual_value in actual_summary.items():
        _expect(
            run_summary.get(field_name) == actual_value,
            f"run_summary.{field_name} must match coverage execution trace rows",
            errors,
            check_states,
            check_name,
        )
    _expect(
        run_summary.get("coverage_execution_trace_count") == run_summary.get("coverage_row_count"),
        "coverage_execution_trace_count must equal coverage_row_count",
        errors,
        check_states,
        check_name,
    )
    _expect(
        check_input_emitted_count + (len(trace) - check_input_emitted_count) == len(trace),
        "CheckInput emitted/non-emitted counts must reconcile to coverage_row_count",
        errors,
        check_states,
        check_name,
    )
    _expect(
        check_result_emitted_count == len(check_results) == run_summary.get("check_result_count"),
        "check_result_emitted_count must equal check_result_count",
        errors,
        check_states,
        check_name,
    )

    if isinstance(product_summary, Mapping):
        p4 = product_summary.get("p4")
        if isinstance(p4, Mapping):
            for field_name, actual_value in actual_summary.items():
                _expect(
                    p4.get(field_name) == actual_value,
                    f"product_smoke_summary.p4.{field_name} must match execution trace rows",
                    errors,
                    check_states,
                    check_name,
                )
        else:
            errors.append("product_smoke_summary.p4 must be available for execution trace validation")
            check_states[check_name] = "FAIL"


def _mapping_identity_key(item: Mapping[str, object]) -> tuple[str, str, str] | None:
    component_type = item.get("component_type")
    component_id = item.get("component_id")
    check_id = item.get("check_id")
    if not all(isinstance(value, str) and value for value in (component_type, component_id, check_id)):
        return None
    return (str(component_type), str(component_id), str(check_id))


def _is_non_negative_int(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def _is_optional_non_negative_int(value: object) -> bool:
    return value is None or _is_non_negative_int(value)


def _forbidden_trace_field_paths(value: object, *, path: str = "$") -> tuple[str, ...]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, nested in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text.casefold() in _TRACE_FORBIDDEN_FIELD_NAMES:
                found.append(child_path)
            found.extend(_forbidden_trace_field_paths(nested, path=child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            found.extend(_forbidden_trace_field_paths(nested, path=f"{path}[{index}]"))
    return tuple(found)

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
