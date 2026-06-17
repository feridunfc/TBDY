"""C13.3-P3 no-live FeatureSnapshot artifact contract validator.

This module validates P2/P3 FeatureSnapshot artifacts without ETABS.  It is a
feature-layer validator only and intentionally does not import or invoke
CheckEngine code.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

SPRINT = "C13.3-P3"
VALIDATION_CONTRACT_VERSION = "c13.3-p3.artifact_validation.v1"

REQUIRED_SOURCE_FAMILIES = ("material_properties", "story_definitions", "pier_section_properties")
REQUIRED_GUARDRAILS = (
    "material_compliance_locked",
    "story_drift_torsion_force_locked",
    "pier_wall_force_capacity_detailing_locked",
)
REQUIRED_ARTIFACT_FILES = (
    "connection_report.json",
    "feature_snapshot.json",
    "feature_snapshot_summary.json",
    "unit_normalization_report.json",
    "readiness_projection_report.json",
    "blocked_check_guardrail_report.json",
    "source_family_projection_report.json",
    "feature_snapshot_report_payload.json",
    "feature_snapshot_artifact_manifest.json",
    "feature_snapshot_evidence_report.md",
    "feature_snapshot_evidence_report.html",
    "check_preflight_diagnostic_report.json",
    "artifact_contract_validation_report.json",
)
SCAN_SUFFIXES = (".json", ".md", ".html")
FORBIDDEN_ENGINEERING_VERDICT_TERMS = (
    "PASS",
    "FAIL",
    "CHECK_OK",
    "CHECK_FAIL",
    "adequate",
    "inadequate",
    "complies",
    "non-compliant",
    "TBDY compliant",
    "TS500 compliant",
    "utilization ratio",
    "capacity ratio",
)


def _json_safe_load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_text(obj_or_text: Any) -> str:
    if isinstance(obj_or_text, str):
        return obj_or_text
    return json.dumps(obj_or_text, sort_keys=True, ensure_ascii=False)


def _status(errors: Sequence[Any]) -> str:
    return "INVALID" if errors else "VALID"


def scan_for_forbidden_engineering_verdicts(obj_or_text: Any) -> dict[str, Any]:
    """Scan text/JSON-like content for C13.3-P3 forbidden verdict terms."""
    text = _as_text(obj_or_text)
    lowered = text.casefold()
    found: list[dict[str, Any]] = []
    for term in FORBIDDEN_ENGINEERING_VERDICT_TERMS:
        count = lowered.count(term.casefold())
        if count:
            found.append({"term": term, "count": count})
    return {
        "validation_status": _status(found),
        "forbidden_terms_found": found,
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "engineering_verdicts_emitted": bool(found),
        "check_results_emitted": False,
        "excel_production_input_used": False,
    }


def _missing_fields(payload: Mapping[str, Any], required: Sequence[str]) -> list[str]:
    return [field for field in required if field not in payload]


def _false_guardrail_errors(payload: Mapping[str, Any], *, context: str) -> list[str]:
    errors: list[str] = []
    must_be_false = (
        "safe_to_implement_checks_now",
        "check_unlock_allowed",
        "engineering_verdicts_emitted",
        "check_results_emitted",
        "excel_production_input_used",
    )
    for key in must_be_false:
        if payload.get(key) is True:
            errors.append(f"{context}.{key} must be false")
    return errors


def validate_feature_snapshot_report_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    required_fields = (
        "sprint",
        "feature_record_count",
        "numeric_feature_count",
        "source_family_counts",
        "source_families",
        "blocked_guardrails",
        "safe_to_implement_checks_now",
        "check_unlock_allowed",
    )
    missing = _missing_fields(payload, required_fields)
    guardrail_errors = _false_guardrail_errors(payload, context="report_payload")
    if payload.get("safe_to_implement_checks_now") is not False:
        guardrail_errors.append("report_payload.safe_to_implement_checks_now must be false")
    if payload.get("check_unlock_allowed") is not False:
        guardrail_errors.append("report_payload.check_unlock_allowed must be false")
    source_counts = payload.get("source_family_counts") or {}
    for family in REQUIRED_SOURCE_FAMILIES:
        if family not in source_counts:
            guardrail_errors.append(f"report_payload.source_family_counts missing {family}")
    guardrail_ids = {str(item.get("feature_id")) for item in payload.get("blocked_guardrails", []) if isinstance(item, Mapping)}
    for feature_id in REQUIRED_GUARDRAILS:
        if feature_id not in guardrail_ids:
            guardrail_errors.append(f"report_payload.blocked_guardrails missing {feature_id}")
    scan = scan_for_forbidden_engineering_verdicts(payload)
    errors = missing + guardrail_errors + [item["term"] for item in scan["forbidden_terms_found"]]
    return {
        "validation_status": _status(errors),
        "missing_required_fields": missing,
        "missing_required_files": [],
        "forbidden_terms_found": scan["forbidden_terms_found"],
        "guardrail_errors": guardrail_errors,
        "checked_files": [],
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "engineering_verdicts_emitted": bool(scan["forbidden_terms_found"]),
        "check_results_emitted": False,
        "excel_production_input_used": False,
    }


def validate_feature_snapshot_artifact_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    required_fields = (
        "artifact_contract_version",
        "output_files",
        "artifact_roles",
        "engineering_verdicts_emitted",
        "check_results_emitted",
        "excel_production_input_used",
        "safe_to_implement_checks_now",
        "check_unlock_allowed",
    )
    missing = _missing_fields(manifest, required_fields)
    guardrail_errors = _false_guardrail_errors(manifest, context="artifact_manifest")
    if manifest.get("engineering_verdicts_emitted") is not False:
        guardrail_errors.append("artifact_manifest.engineering_verdicts_emitted must be false")
    if manifest.get("check_results_emitted") is not False:
        guardrail_errors.append("artifact_manifest.check_results_emitted must be false")
    if manifest.get("excel_production_input_used") is not False:
        guardrail_errors.append("artifact_manifest.excel_production_input_used must be false")
    scan = scan_for_forbidden_engineering_verdicts(manifest)
    errors = missing + guardrail_errors + [item["term"] for item in scan["forbidden_terms_found"]]
    return {
        "validation_status": _status(errors),
        "missing_required_fields": missing,
        "missing_required_files": [],
        "forbidden_terms_found": scan["forbidden_terms_found"],
        "guardrail_errors": guardrail_errors,
        "checked_files": [],
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "engineering_verdicts_emitted": bool(scan["forbidden_terms_found"]),
        "check_results_emitted": False,
        "excel_production_input_used": False,
    }


def validate_check_preflight_diagnostic_report(report: Mapping[str, Any]) -> dict[str, Any]:
    required_fields = (
        "diagnostic_contract_version",
        "diagnostic_only",
        "check_engine_invoked",
        "checks_locked",
        "safe_to_implement_checks_now",
        "check_unlock_allowed",
        "prospective_check_groups",
        "blockers",
    )
    missing = _missing_fields(report, required_fields)
    guardrail_errors = _false_guardrail_errors(report, context="check_preflight_diagnostic")
    if report.get("diagnostic_only") is not True:
        guardrail_errors.append("check_preflight_diagnostic.diagnostic_only must be true")
    if report.get("check_engine_invoked") is not False:
        guardrail_errors.append("check_preflight_diagnostic.check_engine_invoked must be false")
    if report.get("checks_locked") is not True:
        guardrail_errors.append("check_preflight_diagnostic.checks_locked must be true")
    scan = scan_for_forbidden_engineering_verdicts(report)
    errors = missing + guardrail_errors + [item["term"] for item in scan["forbidden_terms_found"]]
    return {
        "validation_status": _status(errors),
        "missing_required_fields": missing,
        "missing_required_files": [],
        "forbidden_terms_found": scan["forbidden_terms_found"],
        "guardrail_errors": guardrail_errors,
        "checked_files": [],
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "engineering_verdicts_emitted": bool(scan["forbidden_terms_found"]),
        "check_results_emitted": False,
        "excel_production_input_used": False,
    }


def _merge_validation_results(results: Sequence[Mapping[str, Any]], *, missing_files: Sequence[str], checked_files: Sequence[str]) -> dict[str, Any]:
    missing_required_fields: dict[str, list[str]] = {}
    forbidden_terms_found: list[dict[str, Any]] = []
    guardrail_errors: list[str] = []
    engineering_verdicts_emitted = False
    check_results_emitted = False
    excel_production_input_used = False
    for index, result in enumerate(results):
        fields = result.get("missing_required_fields", [])
        if fields:
            missing_required_fields[f"result_{index}"] = list(fields)
        forbidden_terms_found.extend(result.get("forbidden_terms_found", []))
        guardrail_errors.extend(result.get("guardrail_errors", []))
        engineering_verdicts_emitted = engineering_verdicts_emitted or bool(result.get("engineering_verdicts_emitted"))
        check_results_emitted = check_results_emitted or bool(result.get("check_results_emitted"))
        excel_production_input_used = excel_production_input_used or bool(result.get("excel_production_input_used"))
    hard_errors = list(missing_files) + guardrail_errors + forbidden_terms_found + list(missing_required_fields)
    return {
        "sprint": SPRINT,
        "validation_contract_version": VALIDATION_CONTRACT_VERSION,
        "validation_status": _status(hard_errors),
        "missing_required_fields": missing_required_fields,
        "missing_required_files": list(missing_files),
        "forbidden_terms_found": forbidden_terms_found,
        "guardrail_errors": guardrail_errors,
        "checked_files": list(checked_files),
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "engineering_verdicts_emitted": engineering_verdicts_emitted,
        "check_results_emitted": check_results_emitted,
        "excel_production_input_used": excel_production_input_used,
    }


def validate_artifact_file_set(output_dir: Path) -> dict[str, Any]:
    """Validate the C13.3-P3 no-live artifact directory."""
    output_dir = Path(output_dir)
    missing_files = [file_name for file_name in REQUIRED_ARTIFACT_FILES if not (output_dir / file_name).exists()]
    checked_files = sorted(path.name for path in output_dir.iterdir() if path.is_file() and path.suffix in SCAN_SUFFIXES)
    results: list[Mapping[str, Any]] = []
    if (output_dir / "feature_snapshot_report_payload.json").exists():
        results.append(validate_feature_snapshot_report_payload(_json_safe_load(output_dir / "feature_snapshot_report_payload.json")))
    if (output_dir / "feature_snapshot_artifact_manifest.json").exists():
        results.append(validate_feature_snapshot_artifact_manifest(_json_safe_load(output_dir / "feature_snapshot_artifact_manifest.json")))
    if (output_dir / "check_preflight_diagnostic_report.json").exists():
        results.append(validate_check_preflight_diagnostic_report(_json_safe_load(output_dir / "check_preflight_diagnostic_report.json")))
    for file_name in checked_files:
        path = output_dir / file_name
        if file_name == "artifact_contract_validation_report.json":
            continue
        if path.suffix == ".json":
            try:
                content = _json_safe_load(path)
            except json.JSONDecodeError as exc:
                results.append({
                    "validation_status": "INVALID",
                    "missing_required_fields": [],
                    "missing_required_files": [],
                    "forbidden_terms_found": [],
                    "guardrail_errors": [f"{file_name} is not valid JSON: {exc}"],
                    "checked_files": [file_name],
                    "safe_to_implement_checks_now": False,
                    "check_unlock_allowed": False,
                    "engineering_verdicts_emitted": False,
                    "check_results_emitted": False,
                    "excel_production_input_used": False,
                })
                continue
        else:
            content = path.read_text(encoding="utf-8")
        scan = scan_for_forbidden_engineering_verdicts(content)
        if scan["forbidden_terms_found"]:
            results.append({**scan, "missing_required_fields": [], "missing_required_files": [], "guardrail_errors": [], "checked_files": [file_name]})
    return _merge_validation_results(results, missing_files=missing_files, checked_files=checked_files)


__all__ = [
    "FORBIDDEN_ENGINEERING_VERDICT_TERMS",
    "REQUIRED_ARTIFACT_FILES",
    "REQUIRED_GUARDRAILS",
    "REQUIRED_SOURCE_FAMILIES",
    "VALIDATION_CONTRACT_VERSION",
    "scan_for_forbidden_engineering_verdicts",
    "validate_artifact_file_set",
    "validate_check_preflight_diagnostic_report",
    "validate_feature_snapshot_artifact_manifest",
    "validate_feature_snapshot_report_payload",
]
