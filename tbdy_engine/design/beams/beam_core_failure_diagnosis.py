from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


PASS_STATUSES = {"PASS", "OK", "PASSED", "SUCCESS", "TRUE"}
FAIL_STATUSES = {"FAIL", "FAILED", "ERROR", "FALSE"}
WARN_STATUSES = {"WARN", "WARNING"}


CATEGORY_PRIORITY = {
    "capacity_design_shear": 0,
    "shear": 1,
    "flexure": 2,
    "input_contract": 3,
    "geometry": 4,
    "unknown": 5,
}


def diagnose_r7b_batch_summary(*, summary_path: Path, output_dir: Path) -> dict[str, Any]:
    summary_path = Path(summary_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    beams = summary.get("beams", [])

    diagnosed_beams = [
        diagnose_beam_from_summary_entry(beam=beam, summary_path=summary_path)
        for beam in beams
    ]

    result = {
        "status": "OK",
        "source_summary_path": str(summary_path),
        "diagnosis_timestamp": datetime.now(timezone.utc).isoformat(),
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": _git(["rev-parse", "--short", "HEAD"]),
        "selected_story": summary.get("selected_story"),
        "selected_combos": summary.get("selected_combos"),
        "actions_source": summary.get("actions_source"),
        "beam_count_processed": summary.get("beam_count_processed", len(beams)),
        "beam_count_failed": summary.get("beam_count_failed", 0),
        "beam_count": len(diagnosed_beams),
        "note": "BeamCore checks executed; this is not design validation.",
        "beams": diagnosed_beams,
        "forbidden_claims": [
            "ETABS_VALIDATED = TRUE",
            "DESIGN_ENGINE_VALIDATED = TRUE",
            "ETABS_BRIDGE = PROVEN_FOR_ALL_MODELS",
            "PRODUCTION_READY = TRUE",
            "RELEASE_READY = TRUE",
            "CODE_COMPLIANCE_PROVEN = TRUE",
        ],
    }

    json_path = output_dir / "failure_diagnosis_summary.json"
    md_path = output_dir / "failure_diagnosis_summary.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_failure_diagnosis_markdown(result), encoding="utf-8")

    return {
        "status": "OK",
        "json_path": json_path,
        "md_path": md_path,
        "beam_count": len(diagnosed_beams),
        "diagnosis": result,
    }


def diagnose_beam_from_summary_entry(*, beam: Mapping[str, Any], summary_path: Path) -> dict[str, Any]:
    artifact_paths = dict(beam.get("artifact_paths") or {})
    engine_report_path_value = artifact_paths.get("json") or beam.get("engine_report_json") or beam.get("engine_report_path")
    resolved_report_path, artifact_missing = resolve_engine_report_path(
        engine_report_path=engine_report_path_value,
        summary_path=summary_path,
        object_name=beam.get("object_name"),
    )

    engine_report = None
    if not artifact_missing and resolved_report_path is not None:
        engine_report = json.loads(resolved_report_path.read_text(encoding="utf-8"))
        engine_report_path = str(resolved_report_path)
    else:
        engine_report_path = str(resolved_report_path) if resolved_report_path is not None else str(engine_report_path_value or "")

    check_records = extract_check_records(engine_report) if engine_report is not None else []
    normalized_checks = [normalize_check_record(record) for record in check_records]

    passed = [check for check in normalized_checks if check["status"] == "PASS"]
    failed = [check for check in normalized_checks if check["status"] == "FAIL"]
    warnings = [check for check in normalized_checks if check["status"] == "WARN"]

    groups = group_failures_by_category(failed)
    critical = most_critical_checks(failed)

    return {
        "object_name": beam.get("object_name"),
        "label": beam.get("label"),
        "story": beam.get("story"),
        "section": beam.get("section"),
        "BeamCore status": beam.get("beam_core_status"),
        "actions": beam.get("actions", {}),
        "governing": beam.get("governing", {}),
        "check_count": len(normalized_checks),
        "passed_check_count": len(passed),
        "failed_check_count": len(failed),
        "warning_check_count": len(warnings),
        "failed_checks": failed,
        "failure_categories": groups,
        "most_critical_checks": critical,
        "artifact_missing": artifact_missing,
        "artifact_paths": {
            "engine_report.json": engine_report_path,
            "engine_report.xlsx": artifact_paths.get("xlsx"),
        },
    }


def resolve_engine_report_path(
    *,
    engine_report_path: object,
    summary_path: Path,
    object_name: object,
) -> tuple[Path | None, bool]:
    """Resolve R7B per-beam engine report paths without duplicating repo-relative paths.

    Candidate order for relative paths:
    1. path relative to current working directory
    2. summary_path.parent / path
    3. summary_path.parent / object_name / engine_report.json
    """
    candidates: list[Path] = []

    if engine_report_path not in (None, ""):
        raw_path = Path(str(engine_report_path))
        if raw_path.is_absolute():
            candidates.append(raw_path)
        else:
            candidates.append(raw_path)
            candidates.append(summary_path.parent / raw_path)

    if object_name not in (None, ""):
        candidates.append(summary_path.parent / str(object_name) / "engine_report.json")

    for candidate in candidates:
        if candidate.exists():
            return candidate, False

    if candidates:
        return candidates[0], True
    return None, True


def extract_check_records(data: Any) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    _walk_for_checks(data, records)
    return records


def _walk_for_checks(value: Any, records: list[Mapping[str, Any]]) -> None:
    if isinstance(value, Mapping):
        if is_check_like_record(value):
            records.append(value)
        for child in value.values():
            _walk_for_checks(child, records)
    elif isinstance(value, list):
        for item in value:
            _walk_for_checks(item, records)


def is_check_like_record(value: Mapping[str, Any]) -> bool:
    identity_keys = {"check_type", "type", "id", "name"}
    status_keys = {"status", "result", "passed", "ok"}
    metric_keys = {"value", "demand", "capacity", "limit", "utilization", "ratio", "message", "reason"}
    keys = set(value.keys())
    return bool(keys & identity_keys) and bool(keys & (status_keys | metric_keys))


def normalize_check_record(record: Mapping[str, Any]) -> dict[str, Any]:
    check_id = record.get("check_type") or record.get("type") or record.get("id") or record.get("name") or "unknown_check"
    status = normalize_status(record)
    category = infer_check_category(str(check_id), record)
    utilization = numeric_or_none(record.get("utilization"))
    if utilization is None:
        utilization = numeric_or_none(record.get("ratio"))

    return {
        "id": record.get("id"),
        "type": record.get("check_type") or record.get("type"),
        "name": record.get("name") or str(check_id),
        "check_key": str(check_id),
        "status": status,
        "category": category,
        "value": record.get("value"),
        "demand": record.get("demand"),
        "capacity": record.get("capacity"),
        "limit": record.get("limit"),
        "utilization": utilization,
        "message": record.get("message") or record.get("reason"),
        "raw": dict(record),
    }


def normalize_status(record: Mapping[str, Any]) -> str:
    for key in ("status", "result"):
        if key in record:
            status_value = str(record[key]).strip().upper()
            if status_value in PASS_STATUSES:
                return "PASS"
            if status_value in FAIL_STATUSES:
                return "FAIL"
            if status_value in WARN_STATUSES:
                return "WARN"

    for key in ("passed", "ok"):
        if key in record:
            value = record[key]
            if value is True:
                return "PASS"
            if value is False:
                return "FAIL"
            text = str(value).strip().upper()
            if text in PASS_STATUSES:
                return "PASS"
            if text in FAIL_STATUSES:
                return "FAIL"

    return "UNKNOWN"


def infer_check_category(check_key: str, record: Mapping[str, Any] | None = None) -> str:
    text = check_key
    if record:
        text += " " + " ".join(str(record.get(key, "")) for key in ("name", "message", "reason"))
    lowered = text.lower()

    if any(token in lowered for token in ("capacity_design", "ve_le_vr", "ve_le_085_vmax", "plastic", "vmax")):
        return "capacity_design_shear"
    if any(token in lowered for token in ("shear", "vr", "vw", "asw", "stirrup", "v_")):
        return "shear"
    if any(token in lowered for token in ("flexure", "moment", "md", "as_required", "rho", "neutral_axis", "stress_block")):
        return "flexure"
    if any(token in lowered for token in ("geometry", "span", "width", "height", "effective_depth", "cover")):
        return "geometry"
    if any(token in lowered for token in ("missing", "invalid_input", "required_input", "input")):
        return "input_contract"
    return "unknown"


def group_failures_by_category(failed_checks: Iterable[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = {
        "flexure": [],
        "shear": [],
        "capacity_design_shear": [],
        "geometry": [],
        "input_contract": [],
        "unknown": [],
    }
    for check in failed_checks:
        category = str(check.get("category") or "unknown")
        groups.setdefault(category, []).append(check)
    return groups


def most_critical_checks(failed_checks: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if not failed_checks:
        return []
    with_numeric = [check for check in failed_checks if numeric_or_none(check.get("utilization")) is not None]
    if with_numeric:
        return sorted(with_numeric, key=lambda check: numeric_or_none(check.get("utilization")) or 0.0, reverse=True)

    return sorted(
        failed_checks,
        key=lambda check: CATEGORY_PRIORITY.get(str(check.get("category") or "unknown"), 99),
    )


def render_failure_diagnosis_markdown(diagnosis: Mapping[str, Any]) -> str:
    lines = [
        "# BeamCore failure diagnosis",
        "",
        "BeamCore checks executed; this is not design validation.",
        "",
        f"- source R7B summary path: {diagnosis['source_summary_path']}",
        f"- selected story: {diagnosis.get('selected_story')}",
        f"- selected combos: {diagnosis.get('selected_combos')}",
        f"- actions_source: {diagnosis.get('actions_source')}",
        f"- beam_count_processed: {diagnosis.get('beam_count_processed')}",
        f"- beam_count_failed: {diagnosis.get('beam_count_failed')}",
        f"- diagnosis timestamp: {diagnosis.get('diagnosis_timestamp')}",
        "",
    ]

    for beam in diagnosis["beams"]:
        lines.extend(
            [
                f"## Beam {beam.get('object_name')} / {beam.get('label')}",
                "",
                f"- story: {beam.get('story')}",
                f"- section: {beam.get('section')}",
                f"- BeamCore status: {beam.get('BeamCore status')}",
                f"- check_count: {beam.get('check_count')}",
                f"- passed_check_count: {beam.get('passed_check_count')}",
                f"- failed_check_count: {beam.get('failed_check_count')}",
                f"- warning_check_count: {beam.get('warning_check_count')}",
                "",
                "### observed ETABS actions",
                "",
            ]
        )
        actions = beam.get("actions") or {}
        governing = beam.get("governing") or {}
        for key in ("Vd_left_kN", "Ve_left_kN", "Md_left_neg_kNm", "Md_mid_pos_kNm", "Md_right_neg_kNm", "axial_kN"):
            gov = governing.get(key) or {}
            lines.append(f"- {key}: {actions.get(key)} | combo={gov.get('combo')} | station={gov.get('station')}")
        lines.extend(["", "### failed checks", ""])
        if beam.get("artifact_missing"):
            lines.append("- artifact_missing: engine_report.json could not be read")
        elif beam.get("failed_checks"):
            for check in beam["failed_checks"]:
                lines.append(
                    f"- {check.get('check_key') or check.get('name')}: {check.get('status')} "
                    f"category={check.get('category')} utilization={check.get('utilization')} "
                    f"message={check.get('message')}"
                )
        else:
            lines.append("- none")
        lines.extend(["", "### most critical checks", ""])
        if beam.get("most_critical_checks"):
            for check in beam["most_critical_checks"]:
                lines.append(f"- {check.get('check_key') or check.get('name')} ({check.get('category')})")
        else:
            lines.append("- none")
        lines.append("")

    lines.extend(["## Forbidden claims", ""])
    for claim in diagnosis["forbidden_claims"]:
        lines.append(f"- {claim}")
    lines.append("")
    return "\n".join(lines)


def numeric_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _git(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(["git", *args], text=True).strip()
    except Exception:
        return None


__all__ = [
    "diagnose_r7b_batch_summary",
    "diagnose_beam_from_summary_entry",
    "extract_check_records",
    "normalize_check_record",
    "normalize_status",
    "infer_check_category",
    "group_failures_by_category",
    "most_critical_checks",
    "render_failure_diagnosis_markdown",
]
