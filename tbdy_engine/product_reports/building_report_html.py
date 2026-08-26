"""Deterministic standalone HTML renderer for UR-1C.

Consumes only the UR-1B BuildingReportProjection read-model. This module owns
presentation only: no ETABS/FCR queries, engineering calculations, status
reinterpretation, or project/global compliance authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import escape
import json
from typing import Mapping

from tbdy_engine.product_reports.building_report_projection import (
    BuildingReportProjection,
    ReportView,
)
from tbdy_engine.product_reports.report_presentation_selection import (
    ReportPresentationSelection,
    default_presentation_selection,
    resolve_presentation_selection,
)


class HtmlRenderIntegrityError(ValueError):
    """Raised when truthful deterministic rendering cannot be guaranteed."""


@dataclass(frozen=True, slots=True)
class HtmlRenderOptions:
    include_projection_json: bool = True
    enable_interactivity: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.include_projection_json, bool):
            raise TypeError("include_projection_json must be bool")
        if not isinstance(self.enable_interactivity, bool):
            raise TypeError("enable_interactivity must be bool")


def _esc(value: object) -> str:
    return escape("" if value is None else str(value), quote=True)


def _show(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _dom_id(canonical_ref: str) -> str:
    return "contribution-" + sha256(canonical_ref.encode("utf-8")).hexdigest()[:20]


def _safe_json(payload: Mapping[str, object]) -> str:
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def _component_label(component_type: object, component_id: object) -> str:
    if component_id is None:
        return "PROJECT / GLOBAL"
    if component_type is None:
        return str(component_id)
    return f"{component_type} / {component_id}"


def _section(section_id: str, title: str, body: str, included: bool) -> str:
    state = "included" if included else "excluded"
    if not included:
        body = (
            '<div class="empty-state">Excluded from this presentation selection. '
            "Canonical assessment and coverage remain unchanged.</div>"
        )
    return (
        f'<section id="{section_id}" class="report-section" data-presentation-state="{state}">'
        f'<div class="section-heading"><h2>{_esc(title)}</h2>'
        f'<span class="section-state">{state.upper()}</span></div>{body}</section>'
    )


def _refs(label: str, values: object) -> str:
    if not isinstance(values, list) or not values:
        return ""
    return (
        f'<details class="trace"><summary>{_esc(label)}</summary><ul>'
        + "".join(f'<li class="mono wrap">{_esc(item)}</li>' for item in values)
        + "</ul></details>"
    )


def _fields(values: object) -> str:
    if not isinstance(values, list) or not values:
        return '<div class="empty-inline">No resolved fields.</div>'
    rows = []
    for item in values:
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr>"
            f'<td class="mono">{_esc(item.get("key"))}</td>'
            f'<td>{_esc(item.get("label"))}</td>'
            f'<td class="numeric">{_esc(_show(item.get("value")))}</td>'
            f'<td>{_esc(item.get("unit"))}</td>'
            f'<td>{_esc(item.get("role"))}</td>'
            f'<td>{_esc(item.get("note"))}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="compact"><thead><tr>'
        "<th>Key</th><th>Field</th><th>Value</th><th>Unit</th><th>Role</th><th>Note</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _projected_table(item: Mapping[str, object]) -> str:
    columns = item.get("columns", [])
    rows = item.get("rows", [])
    if not isinstance(columns, list):
        columns = []
    if not isinstance(rows, list):
        rows = []
    head = "".join(f"<th>{_esc(column)}</th>" for column in columns)
    body = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        body.append(
            "<tr>"
            + "".join(
                f'<td class="numeric">{_esc(_show(row.get(str(column))))}</td>'
                for column in columns
            )
            + "</tr>"
        )
    return (
        '<div class="subpanel"><h4>'
        f'{_esc(item.get("title"))} <span class="muted mono">{_esc(item.get("table_id"))}</span>'
        "</h4><div class=\"table-wrap\"><table><thead><tr>"
        + head
        + "</tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table></div></div>"
    )


def _calculation(item: Mapping[str, object]) -> str:
    formula = item.get("formula")
    governing = item.get("governing_ref")
    html = (
        '<div class="subpanel calculation"><h4>'
        f'{_esc(item.get("title"))} <span class="muted mono">{_esc(item.get("calculation_id"))}</span>'
        "</h4>"
    )
    if formula is not None:
        html += f'<div class="formula"><strong>Formula text</strong><code>{_esc(formula)}</code></div>'
    html += "<h5>Resolved inputs</h5>" + _fields(item.get("inputs"))
    html += "<h5>Resolved outputs</h5>" + _fields(item.get("outputs"))
    if governing is not None:
        html += (
            '<p><strong>governing_ref:</strong> '
            f'<span class="mono wrap">{_esc(governing)}</span></p>'
        )
    html += _refs("Calculation authority refs", item.get("authority_refs"))
    html += _refs("Calculation evidence refs", item.get("evidence_refs"))
    return html + "</div>"


def _contribution(item: Mapping[str, object]) -> str:
    ref = str(item["contribution_ref"])
    status = item.get("status")
    kind = item.get("contribution_kind")
    component_type = item.get("component_type")
    component_id = item.get("component_id")
    warnings = item.get("warnings", [])
    warning_html = ""
    if isinstance(warnings, list) and warnings:
        warning_html = (
            '<div class="warning-list"><strong>Warnings</strong><ul>'
            + "".join(f"<li>{_esc(value)}</li>" for value in warnings)
            + "</ul></div>"
        )
    calculations = item.get("calculations", [])
    calculation_html = ""
    if isinstance(calculations, list) and calculations:
        calculation_html = "<h4>Resolved calculations</h4>" + "".join(
            _calculation(value) for value in calculations if isinstance(value, dict)
        )
    tables = item.get("tables", [])
    table_html = ""
    if isinstance(tables, list) and tables:
        table_html = "<h4>Resolved tables</h4>" + "".join(
            _projected_table(value) for value in tables if isinstance(value, dict)
        )
    return (
        f'<article id="{_dom_id(ref)}" class="result-card" '
        f'data-contribution-ref="{_esc(ref)}" data-status="{_esc(status)}" '
        f'data-kind="{_esc(kind)}" data-component-type="{_esc(component_type)}" '
        f'data-component-id="{_esc(component_id)}" '
        f'data-project-level="{"true" if component_id is None else "false"}">'
        '<div class="result-header"><div>'
        f'<div class="eyebrow">{_esc(kind)} · {_esc(item.get("slice_id"))}</div>'
        f'<h3>{_esc(item.get("title"))}</h3>'
        f'<div class="muted">{_esc(_component_label(component_type, component_id))}</div>'
        "</div>"
        f'<span class="status-badge" data-status="{_esc(status)}">{_esc(status)}</span></div>'
        '<div class="identity-strip">'
        f'<span><strong>contribution_ref</strong> <code>{_esc(ref)}</code></span>'
        f'<span><strong>component_type</strong> <code>{_esc(_show(component_type))}</code></span>'
        f'<span><strong>component_id</strong> <code>{_esc(_show(component_id))}</code></span>'
        "</div>"
        + warning_html
        + '<details class="result-detail"><summary>Engineering detail / trace</summary>'
        + "<h4>Resolved fields</h4>"
        + _fields(item.get("summary_fields"))
        + calculation_html
        + table_html
        + _refs("Report source refs", item.get("report_source_refs"))
        + _refs("Authority refs", item.get("authority_refs"))
        + _refs("Evidence refs", item.get("evidence_refs"))
        + "</details></article>"
    )


def _basis(payload: object) -> str:
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        return '<div class="empty-state">No canonical project basis is available.</div>'
    rows = []
    for item in payload["entries"]:
        if not isinstance(item, dict):
            continue
        source_ids = item.get("source_ids", [])
        source_text = ", ".join(str(v) for v in source_ids) if isinstance(source_ids, list) else ""
        rows.append(
            "<tr>"
            f'<td class="mono">{_esc(item.get("key"))}</td>'
            f'<td>{_esc(item.get("label"))}</td>'
            f'<td class="numeric">{_esc(_show(item.get("value")))}</td>'
            f'<td>{_esc(item.get("unit"))}</td>'
            f'<td class="mono wrap">{_esc(source_text)}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>Key</th><th>Basis</th><th>Value</th><th>Unit</th><th>Sources</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _status_facets(payload: object) -> str:
    if not isinstance(payload, list):
        return ""
    return '<div class="facet-grid">' + "".join(
        f'<div class="facet"><span class="status-badge" data-status="{_esc(item.get("status"))}">'
        f'{_esc(item.get("status"))}</span><strong>{_esc(_show(item.get("count")))}</strong></div>'
        for item in payload if isinstance(item, dict)
    ) + "</div>"


def _analysis_warning(summary: object, refs: object) -> str:
    if not isinstance(summary, dict):
        return ""
    count = summary.get("reanalysis_required_count", 0)
    if not isinstance(count, int) or count <= 0:
        return '<div class="integrity-note">No REANALYSIS_REQUIRED instance is reported by the projection.</div>'
    ids = summary.get("reanalysis_required_instance_ids", [])
    id_html = "".join(
        f'<li class="mono wrap">{_esc(value)}</li>'
        for value in ids if isinstance(ids, list)
    )
    ref_html = ""
    if isinstance(refs, list):
        ref_html = "".join(
            "<li>"
            f'<span class="mono wrap">{_esc(item.get("instance_id"))}</span> — '
            f'<strong>{_esc(item.get("status"))}</strong> — '
            f'<span class="mono wrap">{_esc(item.get("source_ref"))}</span></li>'
            for item in refs if isinstance(item, dict) and item.get("status") == "REANALYSIS_REQUIRED"
        )
    return (
        '<div class="warning-banner" role="alert">'
        f"<strong>Analysis basis contains {count} REANALYSIS_REQUIRED instance(s).</strong>"
        "<p>Exact upstream state; the renderer does not map it to PASS or FAIL.</p>"
        f"<details><summary>Instance identities</summary><ul>{id_html}</ul></details>"
        + (f"<details><summary>Trace refs</summary><ul>{ref_html}</ul></details>" if ref_html else "")
        + "</div>"
    )


_COVERAGE_ORDER = (
    "expected_mandatory_instance_count",
    "accounted_instance_count",
    "executed_result_count",
    "proven_not_applicable_count",
    "blocked_count",
    "no_data_count",
    "unresolved_count",
    "silent_missing_count",
    "duplicate_result_count",
    "missing_report_binding_count",
    "orphan_report_binding_count",
    "mandatory_closure_complete",
    "population_reconciled",
    "report_reconciled",
)


def _coverage(summary: object, analysis: object) -> str:
    if not isinstance(summary, dict):
        return '<div class="empty-state">No canonical FCR coverage summary is available.</div>'
    keys = [key for key in _COVERAGE_ORDER if key in summary]
    keys += [key for key in sorted(summary) if key not in set(keys)]
    cards = [
        '<div class="metric" '
        f'data-coverage-key="{_esc(key)}" '
        f'data-canonical-value="{_esc(json.dumps(summary[key], ensure_ascii=True))}">'
        f'<div class="metric-label">{_esc(key)}</div>'
        f'<div class="metric-value">{_esc(_show(summary[key]))}</div></div>'
        for key in keys
    ]
    if isinstance(analysis, dict) and "reanalysis_required_count" in analysis:
        value = analysis["reanalysis_required_count"]
        cards.append(
            '<div class="metric emphasis" data-coverage-key="reanalysis_required_count" '
            f'data-canonical-value="{_esc(json.dumps(value, ensure_ascii=True))}">'
            '<div class="metric-label">reanalysis_required_count</div>'
            f'<div class="metric-value">{_esc(_show(value))}</div></div>'
        )
    return (
        '<p class="section-intro">Canonical FCR accounting. Counts are not recomputed '
        "from visible result rows.</p>"
        '<div class="metric-grid">' + "".join(cards) + "</div>"
        '<div class="legend"><span>EXECUTED</span><span>PROVEN_NOT_APPLICABLE</span>'
        "<span>BLOCKED</span><span>NO_DATA</span><span>UNRESOLVED</span>"
        "<span>REANALYSIS_REQUIRED</span></div>"
    )


def _results(payload: Mapping[str, object], selected_refs: set[str]) -> str:
    values = payload.get("contributions", [])
    contributions = values if isinstance(values, list) else []
    selected = [
        item for item in contributions
        if isinstance(item, dict) and str(item.get("contribution_ref")) in selected_refs
    ]
    status_options = ['<option value="">All statuses</option>'] + [
        f'<option value="{_esc(item.get("status"))}">{_esc(item.get("status"))} ({_esc(item.get("count"))})</option>'
        for item in payload.get("status_facets", []) if isinstance(item, dict)
    ]
    kind_options = ['<option value="">All contribution kinds</option>'] + [
        f'<option value="{_esc(item.get("contribution_kind"))}">{_esc(item.get("contribution_kind"))} ({_esc(item.get("count"))})</option>'
        for item in payload.get("contribution_kind_facets", []) if isinstance(item, dict)
    ]
    controls = (
        '<div class="result-toolbar no-print">'
        '<label>Status<select id="filter-status">' + "".join(status_options) + "</select></label>"
        '<label>Kind<select id="filter-kind">' + "".join(kind_options) + "</select></label>"
        '<label>Component type<input id="filter-component-type" placeholder="Exact component_type"></label>'
        '<label>Component id<input id="filter-component-id" placeholder="Exact component_id"></label>'
        '<label>Navigation search<input id="result-search" type="search" placeholder="Display-text search only"></label>'
        "</div>"
        '<div id="active-filter-banner" class="filter-banner no-print" hidden>'
        "Interactive display filter active. Search/filtering has zero engineering authority.</div>"
        f'<div id="result-count" class="count-line" data-canonical-total="{len(contributions)}">'
        f"Visible {len(selected)} / presentation-selected {len(selected)} / canonical total {len(contributions)}</div>"
    )
    cards = "".join(_contribution(item) for item in selected)
    if not cards:
        cards = '<div class="empty-state">No contributions are included by this presentation selection.</div>'
    return controls + '<div id="result-list">' + cards + "</div>"


def _components(payload: Mapping[str, object], selected_refs: set[str]) -> str:
    facets = payload.get("component_facets", [])
    if not isinstance(facets, list):
        return '<div class="empty-state">No canonical component facets are available.</div>'
    groups = []
    for facet in facets:
        if not isinstance(facet, dict):
            continue
        refs = facet.get("contribution_refs", [])
        selected = [str(ref) for ref in refs if isinstance(refs, list) and str(ref) in selected_refs]
        if not selected:
            continue
        links = "".join(
            f'<li><a href="#{_dom_id(ref)}"><code>{_esc(ref)}</code></a></li>'
            for ref in selected
        )
        groups.append(
            '<div class="component-card">'
            f'<h3>{_esc(_component_label(facet.get("component_type"), facet.get("component_id")))}</h3>'
            f'<p>{len(selected)} selected contribution(s); canonical facet count '
            f'{_esc(_show(facet.get("contribution_count")))}.</p><ul>{links}</ul></div>'
        )
    return (
        '<div class="component-grid">' + "".join(groups) + "</div>"
        if groups else
        '<div class="empty-state">No components are included by this presentation selection.</div>'
    )


def _manifest(payload: object) -> str:
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        return '<div class="empty-state">No SourceManifest is available in this projection.</div>'
    rows = []
    for item in payload["entries"]:
        if not isinstance(item, dict):
            continue
        authority = item.get("authority_refs", [])
        evidence = item.get("evidence_refs", [])
        rows.append(
            "<tr>"
            f'<td class="mono wrap">{_esc(item.get("source_id"))}</td>'
            f'<td>{_esc(item.get("source_kind"))}</td>'
            f'<td>{_esc(item.get("title"))}</td>'
            f'<td class="mono wrap">{_esc(item.get("fingerprint"))}</td>'
            f'<td class="mono wrap">{_esc(item.get("locator"))}</td>'
            f'<td class="mono wrap">{_esc(", ".join(str(v) for v in authority) if isinstance(authority, list) else "")}</td>'
            f'<td class="mono wrap">{_esc(", ".join(str(v) for v in evidence) if isinstance(evidence, list) else "")}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr><th>source_id</th><th>Kind</th>'
        "<th>Title</th><th>Fingerprint</th><th>Locator</th><th>Authority refs</th>"
        "<th>Evidence refs</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _audit(payload: Mapping[str, object], view: ReportView) -> str:
    if view is not ReportView.AUDIT:
        return (
            '<div class="empty-state">Full audit provenance is not part of the '
            "ENGINEERING projection. Contribution-level source/authority/evidence refs "
            "remain visible in Results.</div>"
        )
    bindings = payload.get("report_bindings", [])
    binding_rows = ""
    if isinstance(bindings, list):
        binding_rows = "".join(
            "<tr>"
            f'<td class="mono wrap">{_esc(item.get("source_ref"))}</td>'
            f'<td class="mono wrap">{_esc(item.get("contribution_ref"))}</td></tr>'
            for item in bindings if isinstance(item, dict)
        )
    reconciliation = payload.get("coverage_reconciliation")
    reconciliation_html = ""
    if isinstance(reconciliation, dict):
        reconciliation_html = (
            '<details><summary>Full ProjectCoverageReconciliation</summary>'
            '<pre class="json-block">'
            + _esc(json.dumps(reconciliation, ensure_ascii=True, sort_keys=True, indent=2))
            + "</pre></details>"
        )
    return (
        '<p class="section-intro">Exact trace copied from AuditProjection; missing '
        "provenance is not manufactured.</p><h3>SourceManifest</h3>"
        + _manifest(payload.get("source_manifest"))
        + '<h3>Report bindings</h3><div class="table-wrap"><table><thead><tr>'
        "<th>source_ref</th><th>contribution_ref</th></tr></thead><tbody>"
        + binding_rows + "</tbody></table></div>"
        + reconciliation_html
    )


def _actions(payload: Mapping[str, object]) -> str:
    reconciliation = payload.get("coverage_reconciliation")
    if not isinstance(reconciliation, dict):
        return '<div class="empty-state">No canonical action records are available in this projection.</div>'
    keys = (
        "required_action_finding_ids",
        "missing_action_finding_ids",
        "duplicate_action_finding_ids",
        "orphan_action_binding_finding_ids",
    )
    blocks = []
    for key in keys:
        values = reconciliation.get(key)
        if isinstance(values, list) and values:
            blocks.append(
                f"<h3>{_esc(key)}</h3><ul>"
                + "".join(f'<li class="mono wrap">{_esc(v)}</li>' for v in values)
                + "</ul>"
            )
    if not blocks:
        return '<div class="empty-state">No canonical action records are available in this projection.</div>'
    return (
        '<p class="section-intro">Exact action-reconciliation references only; '
        "the renderer does not synthesize remediation.</p>" + "".join(blocks)
    )


def _reports(
    payload: Mapping[str, object],
    selection: ReportPresentationSelection,
    selected_count: int,
    total_count: int,
    default: bool,
) -> str:
    coverage = payload.get("coverage_summary")
    expected = coverage.get("expected_mandatory_instance_count") if isinstance(coverage, dict) else None
    state = "DEFAULT / COMPLETE PRESENTATION" if default else "FILTERED / SELECTED PRESENTATION"
    filters = []
    if selection.statuses:
        filters.append("statuses=" + ",".join(selection.statuses))
    if selection.contribution_kinds:
        filters.append("contribution_kinds=" + ",".join(selection.contribution_kinds))
    if selection.component_refs:
        filters.append(
            "components=" + ",".join(
                _component_label(ref.component_type, ref.component_id)
                for ref in selection.component_refs
            )
        )
    if selection.contribution_refs:
        filters.append("contribution_refs=" + ",".join(selection.contribution_refs))
    filter_text = "none" if not filters else " | ".join(filters)
    def checked(value: bool) -> str:
        return " checked" if value else ""
    return (
        '<div class="scope"><h3>Assessment scope ≠ presentation scope</h3>'
        '<div class="scope-grid"><div><strong>Assessment population</strong>'
        "<p>Canonical ProjectCoverageReconciliation population.</p>"
        f'<p>expected mandatory: <span class="mono">{_esc(_show(expected))}</span></p></div>'
        "<div><strong>Presentation scope</strong>"
        f"<p>{_esc(state)}</p><p>{selected_count} selected / {total_count} canonical contributions.</p>"
        f'<p class="wrap">filters: {_esc(filter_text)}</p></div></div></div>'
        '<div class="selection">'
        f'<label><input disabled type="checkbox"{checked(selection.include_overview)}> Overview</label>'
        f'<label><input disabled type="checkbox"{checked(selection.include_coverage)}> Coverage</label>'
        f'<label><input disabled type="checkbox"{checked(selection.include_results)}> Results</label>'
        f'<label><input disabled type="checkbox"{checked(selection.include_components)}> Components</label>'
        f'<label><input disabled type="checkbox"{checked(selection.include_evidence)}> Evidence / Audit</label>'
        f'<label><input disabled type="checkbox"{checked(selection.include_actions)}> Actions</label>'
        "</div><p class=\"muted\">Presentation visibility only; FCR, closure, statuses and bindings are unchanged.</p>"
    )


def _css() -> str:
    return r"""
:root{--ink:#18222c;--muted:#64717d;--line:#d7dee5;--panel:#f7f9fb;--blue:#254866;--warn:#fff1d6;--pass:#edf7ef;--fail:#fff0f0;--blocked:#fff6e9;--nodata:#f1f3f5;font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:#eef1f4}
*{box-sizing:border-box}body{margin:0;line-height:1.45}.shell{max-width:1480px;margin:auto;background:#fff;min-height:100vh;box-shadow:0 0 30px rgba(0,0,0,.08)}header{padding:26px 32px 20px;border-bottom:1px solid var(--line)}h1{margin:5px 0 8px;font-size:28px}h2{margin:0;font-size:21px}h3{font-size:16px}h4{font-size:14px}h5{font-size:11px;text-transform:uppercase;color:var(--muted)}.eyebrow{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:700}.mono,code{font-family:"SFMono-Regular",Consolas,monospace}.wrap,code{overflow-wrap:anywhere;word-break:break-word}.muted{color:var(--muted)}.identity{display:flex;flex-wrap:wrap;gap:8px 20px;font-size:13px}.integrity{margin-top:14px;padding:9px 11px;background:#f1f7fb;border:1px solid #a9c0d4;display:flex;flex-wrap:wrap;gap:10px}.pill,.section-state{border:1px solid var(--line);padding:3px 7px;border-radius:999px;font-size:11px;font-weight:700}
nav{position:sticky;top:0;z-index:5;display:flex;overflow:auto;gap:2px;padding:8px 18px;background:rgba(255,255,255,.97);border-bottom:1px solid var(--line)}nav a{color:var(--blue);text-decoration:none;font-weight:650;font-size:13px;padding:7px 10px;white-space:nowrap}nav a:hover{background:#eef3f7}main{padding:0 32px 55px}.report-section{padding:28px 0;border-bottom:1px solid var(--line);scroll-margin-top:55px}.section-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}.section-intro{color:var(--muted);font-size:13px;max-width:900px}.empty-state,.empty-inline,.integrity-note{padding:12px;border:1px dashed #b9c2ca;background:#fafbfc;color:var(--muted)}
.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:9px}.metric{border:1px solid var(--line);background:var(--panel);padding:11px;min-height:72px}.metric-label{font-size:11px;color:var(--muted);overflow-wrap:anywhere}.metric-value{font-size:22px;font-weight:750}.metric.emphasis{background:var(--warn)}.legend{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}.legend span{border:1px solid var(--line);padding:3px 6px;font:11px monospace}.facet-grid{display:flex;flex-wrap:wrap;gap:8px}.facet{border:1px solid var(--line);padding:7px 9px;display:flex;gap:10px;align-items:center}
.status-badge{padding:3px 7px;border:1px solid currentColor;border-radius:3px;font:700 11px monospace}.status-badge[data-status="PASS"],.status-badge[data-status="PROVEN"]{background:var(--pass)}.status-badge[data-status="FAIL"]{background:var(--fail)}.status-badge[data-status="BLOCKED"]{background:var(--blocked)}.status-badge[data-status="NO_DATA"],.status-badge[data-status="NOT_EVALUATED"]{background:var(--nodata)}.status-badge[data-status="REANALYSIS_REQUIRED"]{background:var(--warn)}.warning-banner{border-left:5px solid #b76500;background:var(--warn);padding:13px 15px;margin:12px 0}
.result-toolbar{display:grid;grid-template-columns:repeat(5,minmax(145px,1fr));gap:8px}.result-toolbar label{font-size:11px;color:var(--muted);font-weight:700}.result-toolbar input,.result-toolbar select{display:block;width:100%;margin-top:3px;padding:7px;border:1px solid #bac4ce;background:#fff}.filter-banner{padding:8px 10px;background:#fff7dd;border:1px solid #dec273;font-size:12px;margin-top:8px}.count-line{font-size:12px;color:var(--muted);margin:8px 0 13px}
.result-card{border:1px solid #c9d2da;margin:0 0 12px;break-inside:avoid}.result-header{padding:13px 15px;background:#fbfcfd;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:12px}.result-header h3{margin:2px 0}.identity-strip{display:flex;flex-wrap:wrap;gap:8px 17px;padding:8px 15px;background:#f5f7f9;border-bottom:1px solid var(--line);font-size:11px}.warning-list{padding:9px 15px;background:#fffaf1}.result-detail{padding:11px 15px}.result-detail>summary{cursor:pointer;font-weight:700;color:var(--blue)}
.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:12px;margin:6px 0 12px}th,td{text-align:left;vertical-align:top;border:1px solid var(--line);padding:6px;overflow-wrap:anywhere;word-break:break-word}th{background:#f0f3f6}.compact{font-size:11px}.numeric{font-variant-numeric:tabular-nums}.subpanel{border:1px solid var(--line);padding:9px 11px;margin:8px 0;background:#fcfdfe;break-inside:avoid}.formula{display:flex;gap:10px;align-items:flex-start}.formula code{white-space:pre-wrap}.trace{font-size:12px}
.component-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:9px}.component-card{border:1px solid var(--line);padding:11px;background:#fbfcfd;break-inside:avoid}.component-card a{color:var(--blue)}.json-block{max-height:520px;overflow:auto;background:#111820;color:#edf2f6;padding:11px;font-size:10px;white-space:pre-wrap;overflow-wrap:anywhere}.scope{background:#eef4fb;border:1px solid #b9cbe0;padding:13px}.scope-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.scope-grid>div{background:#fff;border:1px solid #cfdae5;padding:9px}.selection{display:flex;flex-wrap:wrap;gap:8px 18px;border:1px solid var(--line);padding:9px;margin-top:10px;font-size:12px}footer{padding:17px 32px;border-top:1px solid var(--line);font-size:11px;color:var(--muted)}
@media(max-width:900px){header,main{padding-left:18px;padding-right:18px}.result-toolbar{grid-template-columns:1fr 1fr}.scope-grid{grid-template-columns:1fr}.result-header{flex-direction:column}}
@page{size:A4;margin:13mm 11mm}
@media print{body{background:#fff;font-size:9pt}.shell{max-width:none;box-shadow:none}.no-print,nav{display:none!important}header,main,footer{padding-left:0;padding-right:0}.report-section{padding:10mm 0 4mm;border-bottom:0}.result-card,.component-card,.subpanel,.metric{break-inside:avoid}.table-wrap{overflow:visible}table{font-size:8pt}th,td{padding:3px 4px}.status-badge{background:#fff!important}.json-block{max-height:none;background:#f7f7f7;color:#111;border:1px solid #aaa}details:not([open])>*:not(summary){display:block!important}.report-section[data-presentation-state="excluded"]{display:none}.wrap,code,.mono{overflow-wrap:anywhere;word-break:break-word}}
"""


def _js() -> str:
    return r"""
(function(){
'use strict';
const cards=[...document.querySelectorAll('.result-card')];
const s=document.getElementById('filter-status'),k=document.getElementById('filter-kind');
const ct=document.getElementById('filter-component-type'),ci=document.getElementById('filter-component-id');
const q=document.getElementById('result-search'),n=document.getElementById('result-count');
const b=document.getElementById('active-filter-banner');
if(!s||!k||!ct||!ci||!q||!n||!b){return;}
const selected=cards.length, canonical=Number(n.dataset.canonicalTotal||selected);
function apply(){
 const text=q.value.toLocaleLowerCase(); let visible=0;
 cards.forEach(function(card){
  const show=(!s.value||card.dataset.status===s.value)&&(!k.value||card.dataset.kind===k.value)&&
   (!ct.value||card.dataset.componentType===ct.value)&&(!ci.value||card.dataset.componentId===ci.value)&&
   (!text||card.textContent.toLocaleLowerCase().includes(text));
  card.hidden=!show;if(show){visible++;}
 });
 b.hidden=!(s.value||k.value||ct.value||ci.value||text);
 n.textContent='Visible '+visible+' / presentation-selected '+selected+' / canonical total '+canonical;
}
[s,k,ct,ci,q].forEach(function(x){x.addEventListener('input',apply);});apply();
})();
"""


def render_building_report_html(
    projection: BuildingReportProjection,
    *,
    options: HtmlRenderOptions | None = None,
    selection: ReportPresentationSelection | None = None,
) -> str:
    """Render an ENGINEERING or AUDIT projection as one standalone HTML document."""

    if not isinstance(projection, BuildingReportProjection):
        raise TypeError("projection must be BuildingReportProjection")
    if projection.view not in (ReportView.ENGINEERING, ReportView.AUDIT):
        raise HtmlRenderIntegrityError("UR-1C supports only ENGINEERING and AUDIT")
    if projection.report_integrity_status != "RECONCILED":
        raise HtmlRenderIntegrityError(
            "report_integrity_status must be canonical RECONCILED before rendering"
        )
    if options is None:
        options = HtmlRenderOptions()
    if not isinstance(options, HtmlRenderOptions):
        raise TypeError("options must be HtmlRenderOptions or None")

    chosen = resolve_presentation_selection(projection, selection)
    default = default_presentation_selection(projection)
    selection_is_default = chosen.as_dict() == default.as_dict()
    payload = projection.as_dict()

    values = payload.get("contributions", [])
    if not isinstance(values, list):
        raise HtmlRenderIntegrityError("projection contributions must be a list")
    refs = tuple(
        str(item["contribution_ref"])
        for item in values
        if isinstance(item, dict) and "contribution_ref" in item
    )
    if len(refs) != len(values) or len(set(refs)) != len(refs):
        raise HtmlRenderIntegrityError("projection contribution_ref identities must be exact and unique")
    selected_refs = set(chosen.selected_contribution_refs(projection))

    analysis = payload.get("analysis_basis_summary", {})
    analysis_refs = payload.get(
        "analysis_basis_warnings",
        payload.get("analysis_basis_refs", []),
    )
    banner = ""
    if not selection_is_default:
        banner = (
            '<div class="warning-banner"><strong>Presentation selection/filter applied.</strong> '
            "Assessment population and canonical coverage are unchanged. "
            f"{len(selected_refs)} of {len(refs)} contributions are selected.</div>"
        )

    overview = (
        banner
        + _analysis_warning(analysis, analysis_refs)
        + "<h3>Project / design basis</h3>"
        + _basis(payload.get("project_basis"))
        + "<h3>Canonical status facets</h3>"
        + _status_facets(payload.get("status_facets"))
    )
    sections = "".join(
        (
            _section("overview", "Overview", overview, chosen.include_overview),
            _section("coverage", "Coverage", _coverage(payload.get("coverage_summary"), analysis), chosen.include_coverage),
            _section("results", "Results", _results(payload, selected_refs), chosen.include_results),
            _section("components", "Components", _components(payload, selected_refs), chosen.include_components),
            _section("evidence-audit", "Evidence / Audit", _audit(payload, projection.view), chosen.include_evidence),
            _section("actions", "Actions", _actions(payload), chosen.include_actions),
            _section("reports", "Reports", _reports(payload, chosen, len(selected_refs), len(refs), selection_is_default), True),
        )
    )
    nav = "".join(
        f'<a href="#{sid}">{label}</a>'
        for sid, label in (
            ("overview", "Overview"),
            ("coverage", "Coverage"),
            ("results", "Results"),
            ("components", "Components"),
            ("evidence-audit", "Evidence / Audit"),
            ("actions", "Actions"),
            ("reports", "Reports"),
        )
    )
    projection_json = (
        '<script id="canonical-projection-json" type="application/json">'
        + _safe_json(payload)
        + "</script>"
        if options.include_projection_json else ""
    )
    script = f"<script>{_js()}</script>" if options.enable_interactivity else ""
    reanalysis = 0
    if isinstance(analysis, dict) and isinstance(analysis.get("reanalysis_required_count"), int):
        reanalysis = analysis["reanalysis_required_count"]
    reanalysis_pill = (
        f'<span class="pill">REANALYSIS_REQUIRED: {reanalysis}</span>'
        if reanalysis else ""
    )

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{_esc(payload.get("title"))} · Unified Engineering Review</title>'
        f"<style>{_css()}</style></head><body><div class=\"shell\">"
        '<header><div class="eyebrow">Unified Engineering Review</div>'
        f'<h1>{_esc(payload.get("title"))}</h1><div class="identity">'
        f'<span><strong>project</strong> <code>{_esc(payload.get("project_id"))}</code></span>'
        f'<span><strong>report</strong> <code>{_esc(payload.get("report_id"))}</code></span>'
        f'<span><strong>view</strong> <code>{_esc(payload.get("view"))}</code></span></div>'
        '<div class="integrity">'
        f'<strong>report_integrity_status: {_esc(payload.get("report_integrity_status"))}</strong>'
        f'<span class="pill">{_esc(payload.get("view"))}</span>{reanalysis_pill}</div></header>'
        f'<nav class="no-print" aria-label="Primary review navigation">{nav}</nav>'
        f"<main>{sections}</main>"
        '<footer>Renderer authority: presentation only. Projection is the read-model; '
        "BuildingReportModel, FCR and the canonical engine remain truth.</footer>"
        f"{projection_json}{script}</div></body></html>\n"
    )


__all__ = [
    "HtmlRenderIntegrityError",
    "HtmlRenderOptions",
    "render_building_report_html",
]
