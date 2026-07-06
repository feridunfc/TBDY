"""C13.1-like model-level product report assembled from safe source-table evidence.

P2.0 deliberately keeps this layer small and data-oriented.  It consumes the
accepted ``product_report_source_tables.json`` artifact produced by the safe
FeatureResolver/live-smoke evidence path, or the same shape in fixture mode.  It
never calls ETABS, never mutates a model, never runs analysis/design, and never
uses the CheckEngine.

P2.1 keeps the product behavior stable and polishes only deliverables: the full
report remains canonical, the summary is concise, and heavy diagnostics are
moved into a separate evidence file.

P2.2 adds truthful scope/status language and a package manifest. It does not
add engineering checks and it never recasts the product slice as full TBDY
compliance.

P2.3 adds object-scope ledger, concrete material/fck evidence, and a combined
product-scope verdict while keeping full TBDY compliance NOT_EVALUATED.
"""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from tools.render_product_report import TABLE_COLUMNS, TABLE_TITLES, build_product_summary
from tbdy_engine.product_reports.combined_verdict import build_combined_product_scope_verdict
from tbdy_engine.product_reports.material_evidence import build_material_evidence
from tbdy_engine.product_reports.object_scope_ledger import build_object_scope_ledger
from tbdy_engine.product_reports.report_package import write_report_package

SPRINT = "P2.3_SCOPE_MATERIAL_COMBINED_VERDICT"
CANONICAL_PRODUCT_SPRINT = "P2.0_C13_1_LIVE_PRODUCT_REPORT_PARITY"
REPORT_PACKAGE_SPRINT_NAME = "P2.3 - Live Object Scope Ledger + Material Evidence + Combined Product Scope Verdict"
TRUTH_MODEL_VERSION = "P2.3_TRUTH_MODEL_V1"

PRODUCT_REPORT_KEYS: tuple[str, ...] = (
    "executive_summary",
    "concrete_beam_section_geometry_checks",
    "unsupported_beam_sections",
    "concrete_column_section_geometry_checks",
    "unsupported_column_sections",
    "beam_section_detail",
    "column_section_detail",
    "modal_mass_full_table",
    "modal_mass_final_verdict",
    "guardrails",
    "boundary_notes",
)

EXECUTIVE_SUMMARY_FIELDS: tuple[str, ...] = (
    "checked_scope_status",
    "model_scope_status",
    "full_tbdy_compliance_status",
    "unsupported_object_count_total",
    "excluded_frame_object_count_total",
    "frame_assignment_type_counts",
    "source_frame_assignment_row_count",
    "frame_assignment_type_counts_reconciled",
    "object_scope_ledger_row_count",
    "object_scope_reconciled",
    "checked_concrete_beam_object_count",
    "checked_concrete_column_object_count",
    "excluded_brace_object_count",
    "excluded_null_object_count",
    "excluded_other_object_count",
    "malformed_or_missing_evidence_object_count",
    "checked_concrete_section_count",
    "material_evidence_row_count",
    "material_resolved_section_count",
    "material_partial_section_count",
    "material_missing_section_count",
    "material_out_of_scope_section_count",
    "material_evidence_reconciled",
    "material_evidence_status",
    "geometry_product_status",
    "combined_product_scope_status",
    "product_slice_passed",
    "report_product_passed",
    "concrete_beam_section_type_count",
    "concrete_beam_object_count",
    "unsupported_beam_section_type_count",
    "unsupported_beam_object_count",
    "concrete_column_section_type_count",
    "concrete_column_object_count",
    "unsupported_column_section_type_count",
    "unsupported_column_object_count",
    "beam_fail_count",
    "column_fail_count",
    "modal_mass_table_rows",
    "modal_threshold",
    "modal_ux_status",
    "modal_uy_status",
    "total_fail_count",
)

HEAVY_SUMMARY_KEYS: tuple[str, ...] = (
    "beam_section_detail_rows",
    "column_section_detail_rows",
    "beam_section_type_results",
    "column_section_type_results",
    "modal_mass_full_table_rows",
    "source_table_rows",
    "sample_beams",
    "sample_columns",
)

_EVIDENCE_KEYS: tuple[str, ...] = (
    "beam_section_type_results",
    "column_section_type_results",
    "beam_section_detail_rows",
    "column_section_detail_rows",
    "unsupported_sections",
    "unsupported_beam_sections",
    "unsupported_column_sections",
    "modal_mass_summary",
    "modal_mass_full_table_rows",
    "modal_mass_final_verdict_rows",
    "source_tables_path",
)

_REPORT_TABLES: tuple[tuple[str, str, str], ...] = (
    ("1. Executive Summary", "executive_summary", "executive_summary_rows"),
    ("2. Concrete Beam Section Geometry Checks", "concrete_beam_section_geometry_checks", "concrete_beam_section_geometry_checks"),
    ("3. Unsupported / Out-of-Scope Beam Sections", "unsupported_beam_sections", "unsupported_beam_sections"),
    ("4. Concrete Column Section Geometry Checks", "concrete_column_section_geometry_checks", "concrete_column_section_geometry_checks"),
    ("5. Unsupported / Out-of-Scope Column Sections", "unsupported_column_sections", "unsupported_column_sections"),
    ("6. Beam Section Detail", "beam_section_detail", "beam_section_detail_rows"),
    ("7. Column Section Detail", "column_section_detail", "column_section_detail_rows"),
    ("8. Modal Mass Full Table", "modal_mass_full_table", "modal_mass_full_table_rows"),
    ("9. Modal Mass Final Verdict", "modal_mass_final_verdict", "modal_mass_final_verdict_rows"),
    ("10. Guardrails", "guardrails", "guardrail_rows"),
    ("11. Boundary Notes", "boundary_notes", "boundary_note_rows"),
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _rows_to_mapping(rows: Any, key_name: str, value_name: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not isinstance(rows, list):
        return out
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key = row.get(key_name)
        if key in (None, ""):
            continue
        out[str(key)] = row.get(value_name)
    return out


def _copy_if_exists(src: Path, dst: Path) -> None:
    if not src.is_file():
        return
    try:
        if src.resolve() == dst.resolve():
            return
    except FileNotFoundError:
        pass
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _source_tables_payload(input_dir: Path) -> Mapping[str, Any]:
    path = Path(input_dir) / "product_report_source_tables.json"
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    return payload if isinstance(payload, Mapping) else {}


def _source_table_rows(source: Mapping[str, Any], table_key: str) -> list[dict[str, Any]]:
    tables = source.get("tables") if isinstance(source, Mapping) else None
    table = tables.get(table_key) if isinstance(tables, Mapping) else None
    if not isinstance(table, Mapping):
        return []
    rows = table.get("rows") or table.get("parsed_rows") or []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _first_present_value(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    direct = {str(key): key for key in row.keys()}
    folded = {str(key).replace(" ", "").replace("_", "").casefold(): key for key in row.keys()}
    for alias in aliases:
        if alias in direct:
            value = row.get(direct[alias])
            if value not in (None, ""):
                return value
        folded_key = folded.get(alias.replace(" ", "").replace("_", "").casefold())
        if folded_key is not None:
            value = row.get(folded_key)
            if value not in (None, ""):
                return value
    return None


def _frame_type_bucket(row: Mapping[str, Any]) -> str:
    raw = _first_present_value(row, ("Type", "FrameType", "ObjectType"))
    if raw in (None, ""):
        return "Null"
    normalized = str(raw).strip().casefold()
    if normalized == "beam":
        return "Beam"
    if normalized == "column":
        return "Column"
    if normalized == "brace":
        return "Brace"
    if normalized in {"null", "none", "unassigned", ""}:
        return "Null"
    return "Other"


def _frame_assignment_type_counts(source: Mapping[str, Any]) -> tuple[dict[str, int], int, bool]:
    rows = _source_table_rows(source, "frame_assignments")
    counts = {"Beam": 0, "Column": 0, "Brace": 0, "Null": 0, "Other": 0}
    for row in rows:
        counts[_frame_type_bucket(row)] += 1
    row_count = len(rows)
    return counts, row_count, sum(counts.values()) == row_count


def _modal_fail_count(summary: Mapping[str, Any]) -> int:
    count = 0
    for key in ("modal_ux_status", "modal_uy_status"):
        status = summary.get(key)
        if status not in ("OK", None):
            count += 1
    return count


def _truth_status_summary(summary: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any]:
    frame_counts, source_row_count, reconciled = _frame_assignment_type_counts(source)
    unsupported_object_count_total = int(summary.get("unsupported_beam_object_count") or 0) + int(summary.get("unsupported_column_object_count") or 0)
    excluded_frame_object_count_total = (
        unsupported_object_count_total
        + int(frame_counts.get("Brace", 0))
        + int(frame_counts.get("Null", 0))
        + int(frame_counts.get("Other", 0))
    )
    checked_has_data = bool(summary.get("concrete_beam_section_type_count")) and bool(summary.get("concrete_column_section_type_count")) and bool(summary.get("modal_mass_table_rows"))
    checked_fail_count = int(summary.get("beam_fail_count") or 0) + int(summary.get("column_fail_count") or 0) + _modal_fail_count(summary)
    if checked_fail_count:
        checked_scope_status = "FAIL"
    elif not checked_has_data:
        checked_scope_status = "NO_DATA"
    else:
        checked_scope_status = "PASS"

    if checked_scope_status == "FAIL":
        model_scope_status = "FAIL"
    elif checked_scope_status == "NO_DATA":
        model_scope_status = "NO_DATA"
    elif excluded_frame_object_count_total:
        model_scope_status = "PASS_WITH_EXCLUSIONS"
    else:
        model_scope_status = "PASS"

    return {
        "checked_scope_status": checked_scope_status,
        "model_scope_status": model_scope_status,
        "full_tbdy_compliance_status": "NOT_EVALUATED",
        "unsupported_object_count_total": unsupported_object_count_total,
        "excluded_frame_object_count_total": excluded_frame_object_count_total,
        "frame_assignment_type_counts": frame_counts,
        "source_frame_assignment_row_count": source_row_count,
        "frame_assignment_type_counts_reconciled": reconciled,
        "excluded_frame_object_count_basis": (
            "unsupported beam/column section assignments plus Brace, Null, and Other frame assignment types "
            "from product_report_source_tables.json; this is intentionally conservative when source inventory is incomplete"
        ),
    }


def _truth_notice_lines(executive: Mapping[str, Any]) -> list[str]:
    return [
        "This report is NOT full TBDY compliance.",
        f"full_tbdy_compliance_status = {executive.get('full_tbdy_compliance_status', 'NOT_EVALUATED')}",
        f"checked_scope_status = {executive.get('checked_scope_status')}",
        f"model_scope_status = {executive.get('model_scope_status')}",
        "The checked product scope is limited to the implemented live ETABS product slice.",
        "Object scope ledger accounts for every available frame assignment row.",
        "Concrete material/fck values are evidence only; fck adequacy is NOT_EVALUATED.",
        "Unsupported/out-of-scope objects are visible and are not silently ignored.",
        "Legacy booleans product_slice_passed and report_product_passed are product-slice compatibility signals only, not full TBDY compliance.",
    ]


def _stable_source_tables_path(summary: Mapping[str, Any]) -> str | None:
    raw = summary.get("source_tables_path")
    if raw in (None, ""):
        return None
    # Keep product JSON deterministic across output directories while preserving
    # the source artifact identity expected by this product command.
    return "product_report_source_tables.json"


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, list):
        return ", ".join(_fmt(item) for item in value)
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _table_columns(report: Mapping[str, Any], summary: Mapping[str, Any], summary_key: str, report_key: str) -> list[str]:
    if summary_key == "executive_summary_rows":
        return ["metric", "value"]
    if summary_key == "modal_mass_full_table_rows":
        modal_columns = [str(column) for column in (summary.get("modal_mass_summary") or {}).get("columns", [])]
        if modal_columns:
            return modal_columns
        rows = report.get(report_key) or []
        return list(rows[0].keys()) if rows else []
    return list(TABLE_COLUMNS.get(summary_key, []))


def _rows_for_table(report: Mapping[str, Any], summary_key: str, report_key: str) -> list[dict[str, Any]]:
    if summary_key == "executive_summary_rows":
        executive = report.get("executive_summary") if isinstance(report.get("executive_summary"), Mapping) else {}
        return [{"metric": field, "value": executive.get(field)} for field in EXECUTIVE_SUMMARY_FIELDS]
    if report_key == "guardrails":
        guardrails = report.get("guardrails") if isinstance(report.get("guardrails"), Mapping) else {}
        return [{"guardrail": key, "value": guardrails.get(key)} for key in sorted(guardrails)]
    if report_key == "boundary_notes":
        notes = report.get("boundary_notes") if isinstance(report.get("boundary_notes"), Mapping) else {}
        return [{"item": key, "statement": notes.get(key)} for key in sorted(notes)]
    rows = report.get(report_key) or []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _md_table(headers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    if not headers:
        return "_No rows._"
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(_fmt(row.get(header)).replace("\n", " ") for header in headers) + " |")
    return "\n".join(out)


def _mapping_rows(mapping: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{"metric": key, "value": mapping.get(key)} for key in sorted(mapping)]


def _object_scope_summary_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = report.get("object_scope_summary") if isinstance(report.get("object_scope_summary"), Mapping) else {}
    keys = (
        "source_frame_assignment_row_count",
        "object_scope_ledger_row_count",
        "object_scope_reconciled",
        "checked_concrete_beam_object_count",
        "checked_concrete_column_object_count",
        "unsupported_beam_object_count",
        "unsupported_column_object_count",
        "excluded_brace_object_count",
        "excluded_null_object_count",
        "excluded_other_object_count",
        "malformed_or_missing_evidence_object_count",
        "excluded_frame_object_count_total",
    )
    return [{"metric": key, "value": summary.get(key)} for key in keys]


def _unsupported_excluded_sample_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_key, count_key, bucket in (
        ("unsupported_beam_sections", "assigned_beam_count", "UNSUPPORTED_BEAM"),
        ("unsupported_column_sections", "assigned_column_count", "UNSUPPORTED_COLUMN"),
    ):
        for row in report.get(source_key, []) or []:
            if not isinstance(row, Mapping):
                continue
            rows.append({
                "scope_bucket": bucket,
                "section": row.get("section"),
                "object_count": row.get(count_key),
                "stories": row.get("stories"),
                "sample_labels": row.get("sample_labels"),
                "reason": row.get("reason"),
                "product_pass_impact": row.get("product_pass_impact"),
            })
    obj = report.get("object_scope_summary") if isinstance(report.get("object_scope_summary"), Mapping) else {}
    for bucket, key in (
        ("EXCLUDED_BRACE", "excluded_brace_object_count"),
        ("EXCLUDED_NULL_ASSIGNMENT", "excluded_null_object_count"),
        ("EXCLUDED_OTHER", "excluded_other_object_count"),
        ("MALFORMED_OR_MISSING_EVIDENCE", "malformed_or_missing_evidence_object_count"),
    ):
        count = obj.get(key)
        if count:
            rows.append({
                "scope_bucket": bucket,
                "section": "-",
                "object_count": count,
                "stories": "-",
                "sample_labels": "Full samples are in object_scope_ledger.json",
                "reason": "See object_scope_ledger.json for row-level evidence.",
                "product_pass_impact": "Not counted as concrete geometry FAIL",
            })
    return rows


def _combined_verdict_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    verdict = report.get("combined_product_scope_verdict") if isinstance(report.get("combined_product_scope_verdict"), Mapping) else {}
    keys = (
        "geometry_product_status",
        "material_evidence_status",
        "combined_product_scope_status",
        "full_tbdy_compliance_status",
        "unsupported_object_count_total",
        "excluded_frame_object_count_total",
        "combined_product_scope_reason",
    )
    return [{"metric": key, "value": verdict.get(key)} for key in keys]


def _p2_3_markdown_sections(report: Mapping[str, Any]) -> str:
    sections = [
        ("12. Object Scope Ledger Summary", ["metric", "value"], _object_scope_summary_rows(report)),
        ("13. Unsupported and Excluded Object Samples", ["scope_bucket", "section", "object_count", "stories", "sample_labels", "reason", "product_pass_impact"], _unsupported_excluded_sample_rows(report)),
        ("14. Concrete Material Evidence Summary", ["metric", "value"], _mapping_rows(report.get("material_summary") if isinstance(report.get("material_summary"), Mapping) else {})),
        ("15. Combined Product Scope Verdict", ["metric", "value"], _combined_verdict_rows(report)),
    ]
    lines: list[str] = []
    for title, headers, rows in sections:
        lines.extend([f"## {title}", "", _md_table(headers, rows), ""])
    lines.append("Full object_scope_ledger.json is intentionally not rendered in this Markdown report.")
    lines.append("")
    return "\n".join(lines)


def _p2_3_html_sections(report: Mapping[str, Any]) -> str:
    sections = [
        ("12. Object Scope Ledger Summary", ["metric", "value"], _object_scope_summary_rows(report)),
        ("13. Unsupported and Excluded Object Samples", ["scope_bucket", "section", "object_count", "stories", "sample_labels", "reason", "product_pass_impact"], _unsupported_excluded_sample_rows(report)),
        ("14. Concrete Material Evidence Summary", ["metric", "value"], _mapping_rows(report.get("material_summary") if isinstance(report.get("material_summary"), Mapping) else {})),
        ("15. Combined Product Scope Verdict", ["metric", "value"], _combined_verdict_rows(report)),
    ]
    out = []
    for title, headers, rows in sections:
        out.append("<section>" f"<h2>{html.escape(title)}</h2>" f"{_html_table(title, headers, rows)}" "</section>")
    out.append("<p><strong>Full object_scope_ledger.json is intentionally not rendered in this HTML report.</strong></p>")
    return "".join(out)


def render_product_markdown(report: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    executive = report.get("executive_summary") if isinstance(report.get("executive_summary"), Mapping) else {}
    lines = [
        "# TBDY Minimal Live Product Report - C13.1",
        "",
        "Concrete rectangular assigned beam and column geometry screening + unsupported section classification + full modal mass table.",
        "",
        "## Truth and Scope Notice",
        "",
    ]
    lines.extend(f"- {line}" for line in _truth_notice_lines(executive))
    lines.append("")
    for title, report_key, summary_key in _REPORT_TABLES:
        rows = _rows_for_table(report, summary_key, report_key)
        headers = _table_columns(report, summary, summary_key, report_key)
        lines.extend([
            f"## {title}",
            "",
            f"Table name: `{TABLE_TITLES.get(summary_key, report_key)}`",
            "",
            _md_table(headers, rows),
            "",
        ])
    lines.append(_p2_3_markdown_sections(report))
    return "\n".join(lines)


def _html_table(caption: str, headers: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> str:
    if not headers:
        return f"<p><strong>{html.escape(caption)}:</strong> no rows.</p>"
    head = "".join(f"<th>{html.escape(str(header))}</th>" for header in headers)
    body_lines = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(_fmt(row.get(header)))}</td>" for header in headers)
        body_lines.append(f"<tr>{cells}</tr>")
    body = "\n".join(body_lines)
    return f"<table><caption>{html.escape(caption)}</caption><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_product_html(report: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    title = "TBDY Minimal Live Product Report - C13.1"
    executive = report.get("executive_summary") if isinstance(report.get("executive_summary"), Mapping) else {}
    truth_notice = "".join(f"<li>{html.escape(line)}</li>" for line in _truth_notice_lines(executive))
    sections = []
    for title_text, report_key, summary_key in _REPORT_TABLES:
        rows = _rows_for_table(report, summary_key, report_key)
        headers = _table_columns(report, summary, summary_key, report_key)
        table_name = TABLE_TITLES.get(summary_key, report_key)
        sections.append(
            "<section>"
            f"<h2>{html.escape(title_text)}</h2>"
            f"<p><strong>Table name:</strong> <code>{html.escape(table_name)}</code></p>"
            f"{_html_table(table_name, headers, rows)}"
            "</section>"
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; max-width: 1400px; margin: 32px auto; padding: 0 20px; line-height: 1.45; }}
    table {{ border-collapse: collapse; margin: 12px 0 28px; width: 100%; font-size: 13px; }}
    caption {{ text-align: left; font-weight: 700; margin-bottom: 6px; }}
    th, td {{ border: 1px solid #ddd; padding: 6px 8px; vertical-align: top; }}
    th {{ background: #f3f3f3; }}
    code {{ background: #f7f7f7; padding: 2px 4px; border-radius: 4px; }}
    .scope-warning {{ border: 2px solid #555; padding: 12px 16px; background: #fafafa; margin: 18px 0 28px; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <section class="scope-warning"><h2>Truth and Scope Notice</h2><ul>{truth_notice}</ul></section>
  {''.join(sections)}
  {_p2_3_html_sections(report)}
</body>
</html>
"""


def build_c13_1_product_report(input_dir: Path, out_dir: Path) -> dict[str, Any]:
    """Build the C13.1-like product report shape plus P2.3 scope evidence.

    ``input_dir`` must contain ``product_report_source_tables.json`` and may
    contain ``product_slice_manifest.json``. The returned payload is still a
    product report contract, not a CheckResult schema. P2.3 adds object-scope
    accounting and material/fck evidence, but does not add TBDY adequacy checks.
    """
    summary = build_product_summary(Path(input_dir), Path(out_dir))
    source_payload = _source_tables_payload(Path(input_dir))
    truth_summary = _truth_status_summary(summary, source_payload)
    enriched_summary = dict(summary)
    enriched_summary.update(truth_summary)
    guardrails = dict(summary.get("guardrails") or _rows_to_mapping(summary.get("guardrail_rows"), "guardrail", "value"))
    boundary_notes = _rows_to_mapping(summary.get("boundary_note_rows"), "item", "statement")

    report = {
        "metadata": {
            "sprint": CANONICAL_PRODUCT_SPRINT,
            "product_slice_origin_sprint_id": CANONICAL_PRODUCT_SPRINT,
            "deliverable_sprint": SPRINT,
            "report_package_sprint_id": SPRINT,
            "report_package_sprint_name": REPORT_PACKAGE_SPRINT_NAME,
            "truth_model_version": TRUTH_MODEL_VERSION,
            "source_tables_path": _stable_source_tables_path(summary),
            "full_tbdy_compliance_status": "NOT_EVALUATED",
            "report_product_passed_semantics": "Legacy product-slice compatibility boolean only; not full TBDY compliance.",
            "excel_production_path_used": False,
            "streamlit_ui_used": False,
            "legacy_runtime_used": False,
            "check_engine_executed": False,
            "check_result_emitted": False,
            "etabs_model_mutated": False,
            "analysis_run": False,
            "design_run": False,
        },
        "executive_summary": {},
        "concrete_beam_section_geometry_checks": list(summary.get("concrete_beam_section_geometry_checks") or []),
        "unsupported_beam_sections": list(summary.get("unsupported_beam_sections") or []),
        "concrete_column_section_geometry_checks": list(summary.get("concrete_column_section_geometry_checks") or []),
        "unsupported_column_sections": list(summary.get("unsupported_column_sections") or []),
        "beam_section_detail": list(summary.get("beam_section_detail_rows") or []),
        "column_section_detail": list(summary.get("column_section_detail_rows") or []),
        "modal_mass_full_table": list(summary.get("modal_mass_full_table_rows") or []),
        "modal_mass_final_verdict": list(summary.get("modal_mass_final_verdict_rows") or []),
        "guardrails": guardrails,
        "boundary_notes": boundary_notes,
        "compatibility": {
            "p2_0_product_report_shape_preserved": True,
            "report_product_passed_semantics": "Product-slice compatibility boolean; not full-model or full-TBDY compliance.",
            "table_contract_keys": list(PRODUCT_REPORT_KEYS),
        },
    }
    initial_executive = {field: enriched_summary.get(field) for field in EXECUTIVE_SUMMARY_FIELDS}
    report["executive_summary"] = initial_executive

    object_scope_ledger, object_scope_summary = build_object_scope_ledger(source_payload, report)
    material_evidence, material_summary = build_material_evidence(source_payload, report)
    enriched_summary.update(object_scope_summary)
    enriched_summary.update(material_summary)
    # Keep P2.2 field names consistent with the more complete P2.3 ledger.
    enriched_summary["unsupported_object_count_total"] = object_scope_summary.get("unsupported_object_count_total")
    enriched_summary["excluded_frame_object_count_total"] = object_scope_summary.get("excluded_frame_object_count_total")

    refreshed_executive = {field: enriched_summary.get(field) for field in EXECUTIVE_SUMMARY_FIELDS}
    report["executive_summary"] = refreshed_executive
    combined = build_combined_product_scope_verdict(
        report=report,
        executive_summary=refreshed_executive,
        material_summary=material_summary,
        object_scope_summary=object_scope_summary,
    )
    enriched_summary.update(combined)
    executive_summary = {field: enriched_summary.get(field) for field in EXECUTIVE_SUMMARY_FIELDS}
    report["executive_summary"] = executive_summary
    report["scope_manifest"] = {
        **truth_summary,
        **object_scope_summary,
        **material_summary,
        **combined,
    }
    report["object_scope_summary"] = object_scope_summary
    report["material_summary"] = material_summary
    report["combined_product_scope_verdict"] = combined
    report["material_evidence_notice"] = "Concrete material/fck evidence is reported without fck adequacy or full TBDY compliance evaluation."
    return report

def build_product_summary_deliverable(report: Mapping[str, Any], summary: Mapping[str, Any]) -> dict[str, Any]:
    """Return the concise, stable ``product_summary.json`` payload for P2.1."""
    executive = report.get("executive_summary") if isinstance(report.get("executive_summary"), Mapping) else {}
    payload: dict[str, Any] = {field: executive.get(field) for field in EXECUTIVE_SUMMARY_FIELDS}
    payload["metadata"] = {
        "sprint": SPRINT,
        "canonical_report_file": "product_report.json",
        "evidence_file": "product_evidence.json",
        "source_tables_path": _stable_source_tables_path(summary),
    }
    return payload


def build_product_evidence_deliverable(report: Mapping[str, Any], summary: Mapping[str, Any]) -> dict[str, Any]:
    """Return deterministic diagnostics moved out of ``product_summary.json``."""
    evidence = {
        "metadata": {
            "sprint": SPRINT,
            "canonical_report_file": "product_report.json",
            "summary_file": "product_summary.json",
            "source_tables_path": _stable_source_tables_path(summary),
        },
        "beam_section_type_results": list(summary.get("beam_section_type_results") or []),
        "column_section_type_results": list(summary.get("column_section_type_results") or []),
        "beam_section_detail_rows": list(report.get("beam_section_detail") or []),
        "column_section_detail_rows": list(report.get("column_section_detail") or []),
        "unsupported_sections": list(summary.get("unsupported_sections") or []),
        "unsupported_beam_sections": list(report.get("unsupported_beam_sections") or []),
        "unsupported_column_sections": list(report.get("unsupported_column_sections") or []),
        "modal_mass_summary": dict(summary.get("modal_mass_summary") or {}),
        "modal_mass_selected_rows": list((summary.get("modal_mass_summary") or {}).get("selected_rows") or []),
        "modal_mass_final_verdict_rows": list(report.get("modal_mass_final_verdict") or []),
        "source_references": {
            "source_tables_path": _stable_source_tables_path(summary),
            "product_report_source_tables_file": "product_report_source_tables.json",
        },
        "scope_status_summary": dict(report.get("scope_manifest") or {}),
    }
    # Keep a stable marker list so tests can reject accidental summary bloat.
    evidence["moved_from_product_summary"] = list(_EVIDENCE_KEYS)
    return evidence


def build_product_slice_manifest(report: Mapping[str, Any]) -> dict[str, Any]:
    executive = report.get("executive_summary") if isinstance(report.get("executive_summary"), Mapping) else {}
    combined = report.get("combined_product_scope_verdict") if isinstance(report.get("combined_product_scope_verdict"), Mapping) else {}
    return {
        "product_slice_id": "C13.1_MINIMAL_LIVE_PRODUCT_REPORT",
        "product_slice_origin_sprint_id": CANONICAL_PRODUCT_SPRINT,
        "report_package_sprint_id": SPRINT,
        "report_package_sprint_name": REPORT_PACKAGE_SPRINT_NAME,
        "truth_model_version": TRUTH_MODEL_VERSION,
        "full_tbdy_compliance_status": "NOT_EVALUATED",
        "checked_scope_status": executive.get("checked_scope_status"),
        "model_scope_status": executive.get("model_scope_status"),
        "combined_product_scope_status": combined.get("combined_product_scope_status"),
        "material_evidence_status": combined.get("material_evidence_status"),
        "legacy_product_slice_passed": executive.get("product_slice_passed"),
        "legacy_report_product_passed": executive.get("report_product_passed"),
        "legacy_boolean_semantics": "Legacy booleans are product-slice compatibility signals only, not full TBDY compliance.",
        "guardrails": {
            "excel_production_path_used": False,
            "streamlit_ui_used": False,
            "legacy_runtime_used": False,
            "rebar_flexure_shear_capacity_unlocked": False,
            "check_engine_executed": False,
            "etabs_model_mutated": False,
            "analysis_run": False,
            "design_run": False,
        },
    }


def write_c13_1_product_report(input_dir: Path, out_dir: Path) -> dict[str, Any]:
    """Write stable P2.3 deliverables without changing P2.0 geometry behavior."""
    input_dir = Path(input_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _copy_if_exists(input_dir / "product_report_source_tables.json", out_dir / "product_report_source_tables.json")

    summary = build_product_summary(input_dir, out_dir)
    report = build_c13_1_product_report(input_dir, out_dir)
    source_payload = _source_tables_payload(input_dir)
    object_scope_ledger, object_scope_summary = build_object_scope_ledger(source_payload, report)
    material_evidence_rows, material_summary = build_material_evidence(source_payload, report)
    summary_deliverable = build_product_summary_deliverable(report, summary)
    evidence_deliverable = build_product_evidence_deliverable(report, summary)
    evidence_deliverable["object_scope_summary"] = dict(object_scope_summary)
    evidence_deliverable["material_summary"] = dict(material_summary)
    evidence_deliverable["combined_product_scope_verdict"] = dict(report.get("combined_product_scope_verdict") or {})

    _write_json(out_dir / "product_report.json", report)
    _write_json(out_dir / "product_summary.json", summary_deliverable)
    _write_json(out_dir / "product_evidence.json", evidence_deliverable)
    _write_json(out_dir / "object_scope_ledger.json", object_scope_ledger)
    _write_json(out_dir / "object_scope_summary.json", object_scope_summary)
    _write_json(out_dir / "material_evidence.json", material_evidence_rows)
    _write_json(out_dir / "material_summary.json", material_summary)
    _write_json(out_dir / "product_slice_manifest.json", build_product_slice_manifest(report))
    (out_dir / "product_report.md").write_text(render_product_markdown(report, summary), encoding="utf-8")
    (out_dir / "product_report.html").write_text(render_product_html(report, summary), encoding="utf-8")
    write_report_package(out_dir, report, summary_deliverable)
    return report
