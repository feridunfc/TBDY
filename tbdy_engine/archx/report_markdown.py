from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_KEYS = ("artifact_type", "run_id", "summary", "check_results")


def load_archx_run_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_archx_markdown_report(payload: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_archx_markdown_report(payload), encoding="utf-8")
    return path


def render_archx_markdown_report(payload: dict[str, Any]) -> str:
    _validate_payload(payload)
    lines: list[str] = []
    summary = payload.get("summary", {})
    checks = payload.get("check_results", [])

    lines.extend([
        "# ARCH-X Run Report",
        "",
        "This report is generated from an ARCH-X deterministic run artifact. It is not a full building design report.",
        "",
        "## Run Metadata",
        "",
        f"- artifact_type: `{payload.get('artifact_type')}`",
        f"- artifact_version: `{payload.get('artifact_version', '-')}`",
        f"- run_id: `{payload.get('run_id')}`",
        "",
        "## Executive Summary",
        "",
        "| Metric | Count |",
        "|---|---:|",
        f"| Total checks | {_format_count(summary.get('total_check_results'))} |",
        f"| OK | {_status_count(summary, 'OK')} |",
        f"| FAIL | {_status_count(summary, 'FAIL')} |",
        f"| WARNING | {_status_count(summary, 'WARNING')} |",
        f"| NO_DATA | {_status_count(summary, 'NO_DATA')} |",
        f"| ERROR | {_status_count(summary, 'ERROR')} |",
        "",
        "## Status by Check",
        "",
        "| Check ID | Element | Story | Status | Ratio | Message |",
        "|---|---|---|---|---:|---|",
    ])
    for check in checks:
        lines.append(
            "| {check_id} | {element} | {story} | {status} | {ratio} | {message} |".format(
                check_id=_cell(check.get("check_id")),
                element=_cell(check.get("element_label")),
                story=_cell(check.get("story")),
                status=_cell(check.get("status")),
                ratio=_format_number(check.get("ratio")),
                message=_cell(check.get("message")),
            )
        )
    lines.extend(["", "## Failing Checks", ""])
    failing = [check for check in checks if check.get("status") in {"FAIL", "ERROR"}]
    if not failing:
        lines.append("No failing checks.")
    for check in failing:
        lines.extend(_render_failing_check(check))

    lines.extend([
        "",
        "## Formula Trace",
        "",
        "| Check | Step | Expression | LHS | Operator | RHS | Result |",
        "|---|---|---|---:|---|---:|---|",
    ])
    for check in checks:
        for sub in check.get("sub_checks", []):
            trace = sub.get("formula_trace", {})
            lines.append(
                "| {check_id} | {step} | {expr} | {lhs} | {op} | {rhs} | {result} |".format(
                    check_id=_cell(check.get("check_id")),
                    step=_cell(sub.get("step_id")),
                    expr=_cell(trace.get("display_expression")),
                    lhs=_format_number(trace.get("lhs_value")),
                    op=_cell(trace.get("operator")),
                    rhs=_format_number(trace.get("rhs_value")),
                    result=_cell(trace.get("result")),
                )
            )

    lines.extend([
        "",
        "## Evidence Summary",
        "",
        "| Check ID | Evidence Type | Confidence | Unit Conversion | Source Fields | Missing Inputs |",
        "|---|---|---|---|---:|---:|",
    ])
    for check in checks:
        evidence = check.get("evidence", {})
        lines.append(
            "| {check_id} | {etype} | {confidence} | {unit} | {fields} | {missing} |".format(
                check_id=_cell(check.get("check_id")),
                etype=_cell(evidence.get("evidence_type")),
                confidence=_cell(evidence.get("confidence")),
                unit=_cell(evidence.get("unit_conversion_status")),
                fields=len(evidence.get("source_fields", [])),
                missing=len(evidence.get("missing_inputs", [])),
            )
        )

    lines.extend(["", "## Diagnostics", ""])
    diagnostics = payload.get("diagnostics", [])
    if diagnostics:
        for diagnostic in diagnostics:
            lines.append(f"- {_cell(diagnostic)}")
    else:
        lines.append("No diagnostics.")

    lines.extend(["", "## Workbench Index", ""])
    lines.extend(_render_workbench_index(payload.get("workbench_bundle", {})))
    lines.append("")
    return "\n".join(lines)


def _validate_payload(payload: dict[str, Any]) -> None:
    for key in REQUIRED_KEYS:
        if key not in payload:
            raise ValueError(f"Missing required ARCH-X run artifact key: {key}")
    if payload.get("artifact_type") != "ARCH-X_RUN_RESULT":
        raise ValueError("Invalid ARCH-X artifact_type. Expected ARCH-X_RUN_RESULT.")


def _render_failing_check(check: dict[str, Any]) -> list[str]:
    lines = [
        f"### {_cell(check.get('check_id'))} / {_cell(check.get('element_label'))} / {_cell(check.get('story'))}",
        "",
        f"- status: `{_cell(check.get('status'))}`",
        f"- ratio: `{_format_number(check.get('ratio'))}`",
        f"- message: {_cell(check.get('message'))}",
        f"- action: {_cell(check.get('action'))}",
        "",
        "Failed sub-checks:",
    ]
    failed_subs = [sub for sub in check.get("sub_checks", []) if sub.get("status") in {"FAIL", "ERROR"}]
    if not failed_subs:
        lines.append("- None")
    for sub in failed_subs:
        lines.append(f"- `{_cell(sub.get('step_id'))}` {sub.get('status')} ratio={_format_number(sub.get('ratio'))}: {_cell(sub.get('message'))}")
    lines.append("")
    return lines


def _render_workbench_index(bundle: dict[str, Any]) -> list[str]:
    index = bundle.get("index", {})
    if not index:
        return ["No workbench index available."]
    lines: list[str] = []
    for section in ("by_status", "by_check_id", "by_report_section"):
        lines.append(f"### {section}")
        lines.append("")
        values = index.get(section, {})
        if not values:
            lines.append("- None")
        else:
            for key in sorted(values):
                cell_ids = values.get(key, [])
                lines.append(f"- `{key}`: {', '.join(str(item) for item in cell_ids) if cell_ids else '-'}")
        lines.append("")
    return lines


def _status_count(summary: dict[str, Any], status: str) -> str:
    return _format_count(summary.get("by_status", {}).get(status, 0))


def _format_count(value: Any) -> str:
    if value is None:
        return "0"
    return str(value)


def _format_number(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        if float(value).is_integer():
            return str(int(value))
        return f"{float(value):.3f}".rstrip("0").rstrip(".")
    return str(value)


def _cell(value: Any) -> str:
    if value is None:
        return "-"
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")
