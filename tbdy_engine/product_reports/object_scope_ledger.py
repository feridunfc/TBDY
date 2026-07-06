"""Object-level product-scope ledger for the C13.1/P2.x report slice.

This module is deliberately data-only. It consumes already captured ETABS
source-table rows plus the product report's checked/unsupported section tables.
It does not call ETABS, does not run analysis/design, and does not execute a
CheckEngine.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

SCOPE_BUCKETS: tuple[str, ...] = (
    "CHECKED_CONCRETE_BEAM",
    "CHECKED_CONCRETE_COLUMN",
    "UNSUPPORTED_BEAM",
    "UNSUPPORTED_COLUMN",
    "EXCLUDED_BRACE",
    "EXCLUDED_NULL_ASSIGNMENT",
    "EXCLUDED_OTHER",
    "MALFORMED_OR_MISSING_EVIDENCE",
)


def _first_present(row: Mapping[str, Any] | None, aliases: Sequence[str]) -> Any:
    if not row:
        return None
    direct = {str(k): k for k in row.keys()}
    folded = {str(k).replace(" ", "").replace("_", "").casefold(): k for k in row.keys()}
    for alias in aliases:
        if alias in direct:
            value = row.get(direct[alias])
            if value not in (None, ""):
                return value
        key = folded.get(alias.replace(" ", "").replace("_", "").casefold())
        if key is not None:
            value = row.get(key)
            if value not in (None, ""):
                return value
    return None


def _rows(source: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    tables = source.get("tables") if isinstance(source, Mapping) else None
    item = tables.get(key) if isinstance(tables, Mapping) else None
    if not isinstance(item, Mapping):
        return []
    rows = item.get("rows") or item.get("parsed_rows") or []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _actual_table_name(source: Mapping[str, Any], key: str, fallback: str) -> str:
    tables = source.get("tables") if isinstance(source, Mapping) else None
    item = tables.get(key) if isinstance(tables, Mapping) else None
    if isinstance(item, Mapping):
        return str(item.get("actual_table_name") or fallback)
    return fallback


def _frame_type(row: Mapping[str, Any]) -> str:
    raw = _first_present(row, ("Type", "FrameType", "ObjectType"))
    if raw in (None, ""):
        return "Null"
    text = str(raw).strip()
    folded = text.casefold()
    if folded == "beam":
        return "Beam"
    if folded == "column":
        return "Column"
    if folded == "brace":
        return "Brace"
    if folded in {"null", "none", "unassigned", "-"}:
        return "Null"
    return "Other"


def _section(row: Mapping[str, Any]) -> str | None:
    value = _first_present(row, ("DesignSect", "Design Section", "DesignSection", "AnalysisSect", "Analysis Section", "AnalysisSection", "SectProp", "Section"))
    if value in (None, ""):
        return None
    return str(value).strip()


def _stable_source_reference(*, row_index: int, object_id: Any, label: Any, story: Any, section: Any) -> str:
    parts = [f"source_table=Frame Assignments", f"row={row_index}"]
    if object_id not in (None, ""):
        parts.append(f"object_id={object_id}")
    else:
        parts.extend([
            f"label={label if label not in (None, '') else '-'}",
            f"story={story if story not in (None, '') else '-'}",
            f"section={section if section not in (None, '') else '-'}",
        ])
    return ":".join(str(part) for part in parts)


def _unsupported_reasons(rows: Sequence[Mapping[str, Any]], count_key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        section = row.get("section")
        if section in (None, ""):
            continue
        out[str(section)] = {
            "reason": row.get("reason") or "Section is unsupported by this product slice",
            "product_pass_impact": row.get("product_pass_impact") or "Not counted as FAIL",
            "assigned_count": row.get(count_key),
        }
    return out


def build_object_scope_ledger(source: Mapping[str, Any], report: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return one scope-ledger row for every frame assignment source row."""
    frame_rows = _rows(source, "frame_assignments")
    source_table_name = _actual_table_name(source, "frame_assignments", "Frame Assignments")
    checked_beams = {str(row.get("section")) for row in report.get("concrete_beam_section_geometry_checks", []) if isinstance(row, Mapping) and row.get("section") not in (None, "")}
    checked_columns = {str(row.get("section")) for row in report.get("concrete_column_section_geometry_checks", []) if isinstance(row, Mapping) and row.get("section") not in (None, "")}
    unsupported_beam_reasons = _unsupported_reasons(report.get("unsupported_beam_sections", []), "assigned_beam_count")
    unsupported_column_reasons = _unsupported_reasons(report.get("unsupported_column_sections", []), "assigned_column_count")

    ledger: list[dict[str, Any]] = []
    for row_index, row in enumerate(frame_rows):
        object_id = _first_present(row, ("UniqueName", "Unique Name", "ObjectID", "ObjectId", "Name"))
        label = _first_present(row, ("Label", "ObjectLabel"))
        story = _first_present(row, ("Story", "StoryName"))
        section = _section(row)
        frame_type = _frame_type(row)
        stable = _stable_source_reference(row_index=row_index, object_id=object_id, label=label, story=story, section=section)
        malformed = object_id in (None, "") and (label in (None, "") or story in (None, "") or section in (None, ""))

        bucket: str
        status: str
        checked = False
        impact = "Not counted as FAIL"
        reason = ""
        if malformed:
            bucket = "MALFORMED_OR_MISSING_EVIDENCE"
            status = "MALFORMED"
            reason = "Frame assignment row lacks stable object identity and/or section context"
        elif frame_type == "Beam" and section in checked_beams:
            bucket = "CHECKED_CONCRETE_BEAM"
            status = "CHECKED"
            checked = True
            impact = "Checked by product slice"
            reason = "Concrete rectangular beam section checked by product slice"
        elif frame_type == "Column" and section in checked_columns:
            bucket = "CHECKED_CONCRETE_COLUMN"
            status = "CHECKED"
            checked = True
            impact = "Checked by product slice"
            reason = "Concrete rectangular column section checked by product slice"
        elif frame_type == "Beam":
            bucket = "UNSUPPORTED_BEAM"
            status = "OUT_OF_SCOPE"
            info = unsupported_beam_reasons.get(str(section), {})
            reason = str(info.get("reason") or "Beam section is not checked by this product slice")
            impact = str(info.get("product_pass_impact") or "Not counted as FAIL")
        elif frame_type == "Column":
            bucket = "UNSUPPORTED_COLUMN"
            status = "OUT_OF_SCOPE"
            info = unsupported_column_reasons.get(str(section), {})
            reason = str(info.get("reason") or "Column section is not checked by this product slice")
            impact = str(info.get("product_pass_impact") or "Not counted as FAIL")
        elif frame_type == "Brace":
            bucket = "EXCLUDED_BRACE"
            status = "EXCLUDED"
            reason = "Brace frame assignment is outside the current checked concrete beam/column geometry scope"
        elif frame_type == "Null":
            bucket = "EXCLUDED_NULL_ASSIGNMENT"
            status = "EXCLUDED"
            reason = "Null/unclassified frame assignment is outside the current checked product scope"
        else:
            bucket = "EXCLUDED_OTHER"
            status = "EXCLUDED"
            reason = "Frame assignment type is outside the current checked product scope"

        ledger.append({
            "object_id": None if object_id in (None, "") else str(object_id),
            "object_label": None if label in (None, "") else str(label),
            "story": None if story in (None, "") else str(story),
            "source_row_index": row_index,
            "stable_source_reference": stable,
            "source_table": source_table_name,
            "frame_assignment_type": frame_type,
            "section": section,
            "scope_bucket": bucket,
            "scope_status": status,
            "reason": reason,
            "checked_by_product_slice": checked,
            "product_pass_impact": impact,
        })

    bucket_counts = Counter(str(row["scope_bucket"]) for row in ledger)
    summary = {
        "source_frame_assignment_row_count": len(frame_rows),
        "object_scope_ledger_row_count": len(ledger),
        "object_scope_reconciled": len(frame_rows) == len(ledger),
        "checked_concrete_beam_object_count": bucket_counts.get("CHECKED_CONCRETE_BEAM", 0),
        "checked_concrete_column_object_count": bucket_counts.get("CHECKED_CONCRETE_COLUMN", 0),
        "unsupported_beam_object_count": bucket_counts.get("UNSUPPORTED_BEAM", 0),
        "unsupported_column_object_count": bucket_counts.get("UNSUPPORTED_COLUMN", 0),
        "excluded_brace_object_count": bucket_counts.get("EXCLUDED_BRACE", 0),
        "excluded_null_object_count": bucket_counts.get("EXCLUDED_NULL_ASSIGNMENT", 0),
        "excluded_other_object_count": bucket_counts.get("EXCLUDED_OTHER", 0),
        "malformed_or_missing_evidence_object_count": bucket_counts.get("MALFORMED_OR_MISSING_EVIDENCE", 0),
        "scope_bucket_counts": {bucket: bucket_counts.get(bucket, 0) for bucket in SCOPE_BUCKETS},
        "object_scope_bucket_total": sum(bucket_counts.get(bucket, 0) for bucket in SCOPE_BUCKETS),
        "object_scope_bucket_counts_reconciled": len(frame_rows) == sum(bucket_counts.get(bucket, 0) for bucket in SCOPE_BUCKETS),
        "unsupported_object_count_total": bucket_counts.get("UNSUPPORTED_BEAM", 0) + bucket_counts.get("UNSUPPORTED_COLUMN", 0),
        "excluded_frame_object_count_total": (
            bucket_counts.get("UNSUPPORTED_BEAM", 0)
            + bucket_counts.get("UNSUPPORTED_COLUMN", 0)
            + bucket_counts.get("EXCLUDED_BRACE", 0)
            + bucket_counts.get("EXCLUDED_NULL_ASSIGNMENT", 0)
            + bucket_counts.get("EXCLUDED_OTHER", 0)
            + bucket_counts.get("MALFORMED_OR_MISSING_EVIDENCE", 0)
        ),
        "object_scope_status": "RECONCILED" if len(frame_rows) == len(ledger) and len(frame_rows) == sum(bucket_counts.get(bucket, 0) for bucket in SCOPE_BUCKETS) else "UNRECONCILED",
        "object_scope_notes": "Every frame assignment row is assigned exactly one product-scope bucket; unsupported/excluded objects are not counted as concrete geometry failures.",
    }
    return ledger, summary
