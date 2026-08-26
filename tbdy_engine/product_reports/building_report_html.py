"""Deterministic standalone HTML renderer for UR-1C.

The renderer consumes only the UR-1B BuildingReportProjection read-model.
It owns presentation, navigation, filtering and print layout only. It does not
execute checks, query ETABS/FCR, recalculate engineering values, reinterpret
statuses, or emit a project/global compliance verdict.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import escape
import json
from typing import Any, Mapping, Sequence

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
    """Raised when deterministic truthful rendering cannot be guaranteed."""


@dataclass(frozen=True, slots=True)
class HtmlRenderOptions:
    """Renderer-only deterministic options; no engineering semantics."""

    include_projection_json: bool = True
    enable_interactivity: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.include_projection_json, bool):
            raise TypeError("include_projection_json must be bool")
        if not isinstance(self.enable_interactivity, bool):
            raise TypeError("enable_interactivity must be bool")


def _esc(value: object) -> str:
    if value is None:
        return ""
    return escape(str(value), quote=True)


def _display(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _json_scalar(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _stable_dom_id(prefix: str, canonical_identity: str) -> str:
    digest = sha256(canonical_identity.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def _safe_json_script(payload: Mapping[str, object]) -> str:
    text = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _checked(value: bool) -> str:
    return " checked" if value else ""


def _section_shell(section_id: str, title: str, content: str, included: bool) -> str:
    if included:
        body = content
        state = "included"
    else:
        body = (
            '<div class="empty-state">Excluded from this deterministic presentation '
            "selection. Canonical assessment/coverage remains unchanged.</div>"
        )
        state = "excluded"
    return (
        f'<section id="{_esc(section_id)}" class="report-section" '
        f'data-presentation-state="{state}">'
        f'<div class="section-heading"><h2>{_esc(title)}</h2>'
        f'<span class="section-state">{state.upper()}</span></div>{body}</section>'
    )


def _render_basis(project_basis: object) -> str:
    if not isinstance(project_basis, dict):
        return '<div class="empty-state">No canonical project basis is available.</div>'
    entries = project_basis.get("entries", [])
    if not isinstance(entries, list) or not entries:
        return '<div class="empty-state">No canonical project basis entries are available.</div>'
    rows: list[str] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        sources = item.get("source_ids", [])
        source_text = ", ".join(str(value) for value in sources) if isinstance(sources, list) else ""
        rows.append(
            "<tr>"
            f'<td class="mono">{_esc(item.get("key"))}</td>'
            f'<td>{_esc(item.get("label"))}</td>'
            f'<td class="value-cell">{_esc(_display(item.get("value")))}</td>'
            f'<td>{_esc(item.get("unit"))}</td>'
            f'<td class="mono wrap">{_esc(source_text)}</td>'
            f'<td>{_esc(item.get("note"))}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr><th>Key</th><th>Basis</th><th>Value</th>'
        "<th>Unit</th><th>Sources</th><th>Note</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _coverage_items(summary: Mapping[str, object]) -> list[tuple[str, object]]:
    preferred = (
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
    used = set(preferred)
    items = [(key, summary[key]) for key in preferred if key in summary]
    items.extend((key, summary[key]) for key in sorted(summary) if key not in used)
    return items


def _render_coverage(summary: object, analysis_summary: object) -> str:
    if not isinstance(summary, dict):
        return '<div class="empty-state">No canonical FCR coverage summary is available.</div>'
    cards = [
        (
            '<div class="metric" '
            f'data-coverage-key="{_esc(key)}" '
            f'data-canonical-value="{_esc(_json_scalar(value))}">'
            f'<div class="metric-label">{_esc(key)}</div>'
            f'<div class="metric-value">{_esc(_display(value))}</div></div>'
        )
        for key, value in _coverage_items(summary)
    ]
    reanalysis = None
    if isinstance(analysis_summary, dict):
        reanalysis = analysis_summary.get("reanalysis_required_count")
    if reanalysis is not None:
        cards.append(
            '<div class="metric emphasis" data-coverage-key="reanalysis_required_count" '
            f'data-canonical-value="{_esc(_json_scalar(reanalysis))}">'
            '<div class="metric-label">reanalysis_required_count</div>'
            f'<div class="metric-value">{_esc(_display(reanalysis))}</div></div>'
        )
    legend = (
        '<div class="accounting-legend">'
        '<span>EXECUTED</span><span>PROVEN_NOT_APPLICABLE</span><span>BLOCKED</span>'
        '<span>NO_DATA</span><span>UNRESOLVED</span><span>REANALYSIS_REQUIRED</span>'
        '</div>'
    )
    return (
        '<p class="section-intro">Canonical accounting from ProjectCoverageReconciliation. '
        'Counts are not recomputed from visible result rows.</p>'
        + '<div class="metric-grid">'
        + "".join(cards)
        + "</div>"
        + legend
    )


def _render_status_facets(facets: object) -> str:
    if not isinstance(facets, list) or not facets:
        return '<div class="empty-state">No canonical status facets are available.</div>'
    blocks: list[str] = []
    for item in facets:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        count = item.get("count")
        blocks.append(
            f'<div class="facet-card"><span class="status-badge" data-status="{_esc(status)}">'
            f'{_esc(status)}</span><strong>{_esc(_display(count))}</strong></div>'
        )
    return '<div class="facet-grid">' + "".join(blocks) + "</div>"


def _render_analysis_warning(analysis_summary: object, warnings: object) -> str:
    count = 0
    ids: Sequence[object] = ()
    if isinstance(analysis_summary, dict):
        raw_count = analysis_summary.get("reanalysis_required_count", 0)
        if isinstance(raw_count, int):
            count = raw_count
        raw_ids = analysis_summary.get("reanalysis_required_instance_ids", [])
        if isinstance(raw_ids, list):
            ids = raw_ids
    if count <= 0:
        return '<div class="integrity-note">No REANALYSIS_REQUIRED instance is reported by the projection.</div>'
    id_list = "".join(f'<li class="mono wrap">{_esc(value)}</li>' for value in ids)
    warning_rows = ""
    if isinstance(warnings, list):
        warning_rows = "".join(
            '<li>'
            f'<span class="mono wrap">{_esc(item.get("instance_id"))}</span> — '
            f'<strong>{_esc(item.get("status"))}</strong> — '
            f'<span class="mono wrap">{_esc(item.get("source_ref"))}</span></li>'
            for item in warnings
            if isinstance(item, dict)
        )
    return (
        '<div class="warning-banner" role="alert">'
        f'<strong>Analysis basis contains {count} REANALYSIS_REQUIRED instance(s).</strong>'
        '<p>This is the exact upstream analysis-basis state; the renderer does not map it to PASS or FAIL.</p>'
        f'<details><summary>Instance identities</summary><ul>{id_list}</ul></details>'
        + (f'<details><summary>Projected analysis-basis refs</summary><ul>{warning_rows}</ul></details>' if warning_rows else "")
        + "</div>"
    )


def _render_fields(fields: object) -> str:
    if not isinstance(fields, list) or not fields:
        return ""
    rows: list[str] = []
    for item in fields:
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr>"
            f'<td class="mono">{_esc(item.get("key"))}</td>'
            f'<td>{_esc(item.get("label"))}</td>'
            f'<td class="value-cell">{_esc(_display(item.get("value")))}</td>'
            f'<td>{_esc(item.get("unit"))}</td>'
            f'<td>{_esc(item.get("role"))}</td>'
            f'<td>{_esc(item.get("note"))}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table class="compact"><thead><tr><th>Key</th><th>Field</th>'
        "<th>Value</th><th>Unit</th><th>Role</th><th>Note</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _render_table(table: Mapping[str, object]) -> str:
    columns = table.get("columns", [])
    rows = table.get("rows", [])
    if not isinstance(columns, list):
        columns = []
    if not isinstance(rows, list):
        rows = []
    header = "".join(f"<th>{_esc(column)}</th>" for column in columns)
    body_rows: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        body_rows.append(
            "<tr>"
            + "".join(
                f'<td class="value-cell">{_esc(_display(row.get(str(column))))}</td>'
                for column in columns
            )
            + "</tr>"
        )
    return (
        '<div class="subpanel"><div class="subpanel-title">'
        f'{_esc(table.get("title"))} <span class="muted mono">{_esc(table.get("table_id"))}</span>'
        f' <span class="chip">{_esc(table.get("purpose"))}</span></div>'
        '<div class="table-wrap"><table><thead><tr>'
        + header
        + "</tr></thead><tbody>"
        + "".join(body_rows)
        + "</tbody></table></div></div>"
    )


def _render_calculation(calculation: Mapping[str, object]) -> str:
    formula = calculation.get("formula")
    governing = calculation.get("governing_ref")
    return (
        '<div class="subpanel calculation">'
        '<div class="subpanel-title">'
        f'{_esc(calculation.get("title"))} '
        f'<span class="muted mono">{_esc(calculation.get("calculation_id"))}</span></div>'
        + (f'<div class="formula"><span>Formula text</span><code>{_esc(formula)}</code></div>' if formula is not None else "")
        + '<h5>Resolved inputs</h5>'
        + _render_fields(calculation.get("inputs"))
        + '<h5>Resolved outputs</h5>'
        + _render_fields(calculation.get("outputs"))
        + (f'<div class="trace-line"><strong>governing_ref:</strong> <span class="mono wrap">{_esc(governing)}</span></div>' if governing is not None else "")
        + _render_ref_list("Calculation authority refs", calculation.get("authority_refs"))
        + _render_ref_list("Calculation evidence refs", calculation.get("evidence_refs"))
        + "</div>"
    )


def _render_ref_list(label: str, refs: object) -> str:
    if not isinstance(refs, list) or not refs:
        return ""
    items = "".join(f'<li class="mono wrap">{_esc(ref)}</li>' for ref in refs)
    return f'<details class="trace-list"><summary>{_esc(label)}</summary><ul>{items}</ul></details>'


def _component_label(component_type: object, component_id: object) -> str:
    if component_id is None:
        return "PROJECT / GLOBAL"
    if component_type is None:
        return str(component_id)
    return f"{component_type} / {component_id}"


def _render_contribution(item: Mapping[str, object]) -> str:
    ref = str(item.get("contribution_ref", ""))
    dom_id = _stable_dom_id("contribution", ref)
    component_type = item.get("component_type")
    component_id = item.get("component_id")
    status = item.get("status")
    kind = item.get("contribution_kind")
    warnings = item.get("warnings", [])
    warning_html = ""
    if isinstance(warnings, list) and warnings:
        warning_html = (
            '<div class="warning-list"><strong>Warnings</strong><ul>'
            + "".join(f"<li>{_esc(value)}</li>" for value in warnings)
            + "</ul></div>"
        )
    calculations = item.get("calculations", [])
    calc_html = ""
    if isinstance(calculations, list) and calculations:
        calc_html = '<h4>Resolved calculations</h4>' + "".join(
            _render_calculation(calc) for calc in calculations if isinstance(calc, dict)
        )
    tables = item.get("tables", [])
    table_html = ""
    if isinstance(tables, list) and tables:
        table_html = '<h4>Resolved tables</h4>' + "".join(
            _render_table(table) for table in tables if isinstance(table, dict)
        )
    return (
        f'<article id="{dom_id}" class="result-card" '
        f'data-contribution-ref="{_esc(ref)}" '
        f'data-status="{_esc(status)}" '
        f'data-kind="{_esc(kind)}" '
        f'data-component-type="{_esc(component_type)}" '
        f'data-component-id="{_esc(component_id)}" '
        f'data-project-level="{"true" if component_id is None else "false"}">'
        '<div class="result-header">'
        '<div><div class="eyebrow">'
        f'{_esc(kind)} · {_esc(item.get("slice_id"))}</div>'
        f'<h3>{_esc(item.get("title"))}</h3>'
        f'<div class="component-label">{_esc(_component_label(component_type, component_id))}</div></div>'
        f'<span class="status-badge" data-status="{_esc(status)}">{_esc(status)}</span></div>'
        '<div class="identity-strip">'
        f'<span><strong>contribution_ref</strong> <code>{_esc(ref)}</code></span>'
        f'<span><strong>component_type</strong> <code>{_esc(component_type)}</code></span>'
        f'<span><strong>component_id</strong> <code>{_esc(_display(component_id))}</code></span>'
        '</div>'
        + warning_html
        + '<details class="result-detail"><summary>Engineering detail / trace</summary>'
        + '<h4>Resolved fields</h4>'
        + _render_fields(item.get("summary_fields"))
        + calc_html
        + table_html
        + _render_ref_list("Report source refs", item.get("report_source_refs"))
        + _render_ref_list("Authority refs", item.get("authority_refs"))
        + _render_ref_list("Evidence refs", item.get("evidence_refs"))
        + "</details></article>"
    )


def _render_results(payload: Mapping[str, object], selected_refs: set[str]) -> str:
    contributions = payload.get("contributions", [])
    if not isinstance(contributions, list):
        contributions = []
    selected = [
        item
        for item in contributions
        if isinstance(item, dict) and str(item.get("contribution_ref")) in selected_refs
    ]
    total = len(contributions)
    if not selected:
        cards = '<div class="empty-state">No contributions are included by the current presentation selection.</div>'
    else:
        cards = "".join(_render_contribution(item) for item in selected)

    status_options = ['<option value="">All statuses</option>']
    for facet in payload.get("status_facets", []):
        if isinstance(facet, dict):
            value = facet.get("status")
            status_options.append(f'<option value="{_esc(value)}">{_esc(value)} ({_esc(facet.get("count"))})</option>')
    kind_options = ['<option value="">All contribution kinds</option>']
    for facet in payload.get("contribution_kind_facets", []):
        if isinstance(facet, dict):
            value = facet.get("contribution_kind")
            kind_options.append(f'<option value="{_esc(value)}">{_esc(value)} ({_esc(facet.get("count"))})</option>')

    toolbar = (
        '<div class="result-toolbar no-print" aria-label="Result navigation filters">'
        '<label>Status<select id="filter-status">' + "".join(status_options) + '</select></label>'
        '<label>Kind<select id="filter-kind">' + "".join(kind_options) + '</select></label>'
        '<label>Component type<input id="filter-component-type" type="text" placeholder="Exact component_type"></label>'
        '<label>Component id<input id="filter-component-id" type="text" placeholder="Exact component_id"></label>'
        '<label class="search-label">Navigation search<input id="result-search" type="search" placeholder="Display-text search only"></label>'
        '</div>'
        '<div id="active-filter-banner" class="filter-banner no-print" hidden>Interactive display filter active. Search/filtering has zero engineering authority.</div>'
        f'<div id="result-count" class="count-line" data-presentation-count="{len(selected)}" data-canonical-total="{total}">'
        f'Visible {len(selected)} / presentation-selected {len(selected)} / canonical total {total}</div>'
    )
    return toolbar + '<div id="result-list">' + cards + "</div>"


def _render_components(payload: Mapping[str, object], selected_refs: set[str]) -> str:
    facets = payload.get("component_facets", [])
    if not isinstance(facets, list) or not facets:
        return '<div class="empty-state">No canonical component facets are available.</div>'
    groups: list[str] = []
    for facet in facets:
        if not isinstance(facet, dict):
            continue
        refs = facet.get("contribution_refs", [])
        if not isinstance(refs, list):
            refs = []
        selected = [str(ref) for ref in refs if str(ref) in selected_refs]
        if not selected:
            continue
        links = "".join(
            f'<li><a href="#{_stable_dom_id("contribution", ref)}"><code>{_esc(ref)}</code></a></li>'
            for ref in selected
        )
        groups.append(
            '<div class="component-card" '
            f'data-component-type="{_esc(facet.get("component_type"))}" '
            f'data-component-id="{_esc(facet.get("component_id"))}">'
            f'<h3>{_esc(_component_label(facet.get("component_type"), facet.get("component_id")))}</h3>'
            f'<p>{len(selected)} presentation-selected contribution(s); canonical facet count '
            f'{_esc(_display(facet.get("contribution_count")))}.</p><ul>{links}</ul></div>'
        )
    if not groups:
        return '<div class="empty-state">No components are included by the current presentation selection.</div>'
    return '<div class="component-grid">' + "".join(groups) + "</div>"


def _render_manifest(manifest: object) -> str:
    if not isinstance(manifest, dict):
        return '<div class="empty-state">No SourceManifest is available in this projection.</div>'
    entries = manifest.get("entries", [])
    if not isinstance(entries, list) or not entries:
        return '<div class="empty-state">SourceManifest contains no entries.</div>'
    rows: list[str] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr>"
            f'<td class="mono wrap">{_esc(item.get("source_id"))}</td>'
            f'<td>{_esc(item.get("source_kind"))}</td>'
            f'<td>{_esc(item.get("title"))}</td>'
            f'<td class="mono wrap">{_esc(item.get("fingerprint"))}</td>'
            f'<td class="mono wrap">{_esc(item.get("locator"))}</td>'
            f'<td class="mono wrap">{_esc(", ".join(str(v) for v in item.get("authority_refs", [])))}</td>'
            f'<td class="mono wrap">{_esc(", ".join(str(v) for v in item.get("evidence_refs", [])))}</td>'
            "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr><th>source_id</th><th>Kind</th><th>Title</th>'
        '<th>Fingerprint</th><th>Locator</th><th>Authority refs</th><th>Evidence refs</th>'
        '</tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>"
    )


def _render_bindings(bindings: object) -> str:
    if not isinstance(bindings, list) or not bindings:
        return '<div class="empty-state">No report bindings are available in this projection.</div>'
    rows = "".join(
        '<tr>'
        f'<td class="mono wrap">{_esc(item.get("source_ref"))}</td>'
        f'<td class="mono wrap">{_esc(item.get("contribution_ref"))}</td>'
        '</tr>'
        for item in bindings
        if isinstance(item, dict)
    )
    return '<div class="table-wrap"><table><thead><tr><th>source_ref</th><th>contribution_ref</th></tr></thead><tbody>' + rows + '</tbody></table></div>'


def _render_audit(payload: Mapping[str, object], view: ReportView) -> str:
    if view is not ReportView.AUDIT:
        return (
            '<div class="empty-state">Full audit provenance is not part of the ENGINEERING projection. '
            'Contribution-level report source, authority and evidence refs remain visible in Results.</div>'
        )
    reconciliation = payload.get("coverage_reconciliation")
    reconciliation_json = ""
    if isinstance(reconciliation, dict):
        reconciliation_json = (
            '<details><summary>Full ProjectCoverageReconciliation</summary><pre class="json-block">'
            + _esc(json.dumps(reconciliation, ensure_ascii=True, sort_keys=True, indent=2))
            + "</pre></details>"
        )
    basis_refs = payload.get("analysis_basis_refs", [])
    basis_html = ""
    if isinstance(basis_refs, list) and basis_refs:
        rows = "".join(
            '<tr>'
            f'<td class="mono wrap">{_esc(item.get("instance_id"))}</td>'
            f'<td>{_esc(item.get("status"))}</td>'
            f'<td class="mono wrap">{_esc(item.get("source_ref"))}</td></tr>'
            for item in basis_refs
            if isinstance(item, dict)
        )
        basis_html = '<h3>Analysis basis refs</h3><div class="table-wrap"><table><thead><tr><th>instance_id</th><th>Status</th><th>source_ref</th></tr></thead><tbody>' + rows + '</tbody></table></div>'
    return (
        '<p class="section-intro">Exact provenance copied from AuditProjection. Missing provenance is shown as absent; none is manufactured.</p>'
        '<h3>Source manifest</h3>' + _render_manifest(payload.get("source_manifest"))
        + '<h3>Report bindings</h3>' + _render_bindings(payload.get("report_bindings"))
        + basis_html + reconciliation_json
    )


def _render_actions(payload: Mapping[str, object]) -> str:
    reconciliation = payload.get("coverage_reconciliation")
    if not isinstance(reconciliation, dict):
        return '<div class="empty-state">No canonical action records are available in this projection.</div>'
    keys = (
        "required_action_finding_ids",
        "missing_action_finding_ids",
        "duplicate_action_finding_ids",
        "orphan_action_binding_finding_ids",
    )
    available = {key: reconciliation.get(key) for key in keys if reconciliation.get(key)}
    if not available:
        return '<div class="empty-state">No canonical action records are available in this projection.</div>'
    sections: list[str] = [
        '<p class="section-intro">These are exact action-reconciliation references only. The renderer does not synthesize remediation actions.</p>'
    ]
    for key in keys:
        values = available.get(key)
        if not isinstance(values, list):
            continue
        sections.append(
            f'<h3>{_esc(key)}</h3><ul>'
            + "".join(f'<li class="mono wrap">{_esc(value)}</li>' for value in values)
            + "</ul>"
        )
    return "".join(sections)


def _render_reports(
    payload: Mapping[str, object],
    selection: ReportPresentationSelection,
    selected_count: int,
    canonical_total: int,
    selection_is_default: bool,
) -> str:
    coverage = payload.get("coverage_summary", {})
    expected = coverage.get("expected_mandatory_instance_count") if isinstance(coverage, dict) else None
    filter_rows: list[str] = []
    if selection.statuses:
        filter_rows.append("Statuses: " + ", ".join(selection.statuses))
    if selection.contribution_kinds:
        filter_rows.append("Contribution kinds: " + ", ".join(selection.contribution_kinds))
    if selection.component_refs:
        filter_rows.append(
            "Components: " + ", ".join(
                _component_label(item.component_type, item.component_id)
                for item in selection.component_refs
            )
        )
    if selection.contribution_refs:
        filter_rows.append("Contribution refs: " + ", ".join(selection.contribution_refs))
    filter_text = "No contribution filter applied." if not filter_rows else " | ".join(filter_rows)
    state = "DEFAULT / COMPLETE PRESENTATION" if selection_is_default else "FILTERED / SELECTED PRESENTATION"
    return (
        '<div class="scope-declaration">'
        '<h3>Assessment scope ≠ presentation scope</h3>'
        '<div class="scope-grid">'
        '<div><strong>Assessment population</strong><p>Canonical ProjectCoverageReconciliation population.</p>'
        f'<p>expected mandatory: <span class="mono">{_esc(_display(expected))}</span></p></div>'
        '<div><strong>Presentation scope</strong>'
        f'<p>{_esc(state)}</p><p>{selected_count} selected contribution(s) / {canonical_total} canonical contribution(s).</p>'
        f'<p class="wrap">{_esc(filter_text)}</p></div></div></div>'
        '<div class="report-selection" aria-label="Deterministic report presentation selection">'
        f'<label><input type="checkbox" disabled{_checked(selection.include_overview)}> Overview</label>'
        f'<label><input type="checkbox" disabled{_checked(selection.include_coverage)}> Coverage</label>'
        f'<label><input type="checkbox" disabled{_checked(selection.include_results)}> Results</label>'
        f'<label><input type="checkbox" disabled{_checked(selection.include_components)}> Components</label>'
        f'<label><input type="checkbox" disabled{_checked(selection.include_evidence)}> Evidence / Audit</label>'
        f'<label><input type="checkbox" disabled{_checked(selection.include_actions)}> Actions</label>'
        '</div>'
        '<p class="muted">Selection is deterministic renderer policy. It changes presentation visibility only; FCR, statuses, closure and report bindings are unchanged.</p>'
    )


def _styles() -> str:
    return r"""
:root{--ink:#17202a;--muted:#68727d;--line:#d8dee5;--panel:#f7f9fb;--accent:#203b57;--warn:#7c3f00;--warn-bg:#fff4df;--ok-bg:#edf7ef;--bad-bg:#fff0f0;--blocked-bg:#fff5e8;--nodata-bg:#f1f3f5;--scope-bg:#eef4fb;font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:var(--ink);background:#eef1f4}
*{box-sizing:border-box}body{margin:0;line-height:1.45}.app-shell{max-width:1500px;margin:0 auto;background:white;min-height:100vh;box-shadow:0 0 32px rgba(0,0,0,.08)}
header{padding:28px 34px 20px;border-bottom:1px solid var(--line);background:#fff}.eyebrow{text-transform:uppercase;letter-spacing:.08em;font-size:11px;color:var(--muted);font-weight:700}h1{margin:6px 0 8px;font-size:28px;line-height:1.15}h2{margin:0;font-size:21px}h3{margin:12px 0 8px;font-size:16px}h4{margin:18px 0 8px;font-size:14px}h5{margin:14px 0 6px;font-size:12px;text-transform:uppercase;color:var(--muted)}
.identity-line{display:flex;flex-wrap:wrap;gap:8px 20px;font-size:13px}.identity-line code,.mono,code{font-family:"SFMono-Regular",Consolas,"Liberation Mono",monospace}.wrap,.identity-line code,code{overflow-wrap:anywhere;word-break:break-word}
.integrity-banner{margin-top:16px;padding:10px 12px;border:1px solid #9fb3c8;background:#f2f7fb;display:flex;gap:10px;align-items:center}.integrity-banner strong{font-size:13px}.view-pill,.chip,.section-state{display:inline-flex;align-items:center;padding:3px 8px;border:1px solid var(--line);border-radius:999px;font-size:11px;font-weight:700;letter-spacing:.03em}
nav{position:sticky;top:0;z-index:10;display:flex;gap:2px;overflow:auto;padding:8px 20px;border-bottom:1px solid var(--line);background:rgba(255,255,255,.97);backdrop-filter:blur(8px)}nav a{white-space:nowrap;color:var(--accent);text-decoration:none;padding:8px 11px;border-radius:5px;font-size:13px;font-weight:600}nav a:hover{background:#eef3f7}
main{padding:0 34px 60px}.report-section{padding:30px 0;border-bottom:1px solid var(--line);scroll-margin-top:58px}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px}.section-state{color:var(--muted)}.section-intro{max-width:920px;color:var(--muted);font-size:13px}.muted{color:var(--muted)}
.metric-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}.metric{border:1px solid var(--line);background:var(--panel);padding:12px;min-height:76px}.metric-label{font-size:11px;color:var(--muted);overflow-wrap:anywhere}.metric-value{font-size:23px;font-weight:750;margin-top:4px}.metric.emphasis{border-color:#d6a35b;background:var(--warn-bg)}
.accounting-legend{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}.accounting-legend span{border:1px solid var(--line);padding:4px 7px;font-family:monospace;font-size:11px;background:white}.facet-grid{display:flex;flex-wrap:wrap;gap:8px}.facet-card{display:flex;gap:10px;align-items:center;border:1px solid var(--line);padding:8px 10px}.status-badge{display:inline-flex;align-items:center;padding:4px 8px;border:1px solid currentColor;border-radius:3px;font-family:monospace;font-size:11px;font-weight:800;white-space:nowrap}.status-badge[data-status="PASS"],.status-badge[data-status="PROVEN"]{background:var(--ok-bg)}.status-badge[data-status="FAIL"]{background:var(--bad-bg)}.status-badge[data-status="BLOCKED"]{background:var(--blocked-bg)}.status-badge[data-status="NO_DATA"],.status-badge[data-status="NOT_EVALUATED"]{background:var(--nodata-bg)}.status-badge[data-status="REANALYSIS_REQUIRED"]{background:var(--warn-bg)}
.warning-banner{border-left:5px solid #b76500;background:var(--warn-bg);padding:14px 16px;margin:14px 0}.warning-banner p{margin:5px 0}.integrity-note,.empty-state{border:1px dashed #b8c0c8;background:#fafbfc;padding:14px;color:var(--muted)}
.result-toolbar{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:8px;margin:0 0 10px}.result-toolbar label{font-size:11px;color:var(--muted);font-weight:700}.result-toolbar input,.result-toolbar select{width:100%;margin-top:3px;padding:7px 8px;border:1px solid #bfc8d1;background:white;color:var(--ink)}.search-label{grid-column:span 1}.filter-banner{padding:9px 10px;background:#fff7dd;border:1px solid #dec273;font-size:12px}.count-line{font-size:12px;color:var(--muted);margin:8px 0 14px}
.result-card{border:1px solid #cbd3db;margin:0 0 12px;background:white;break-inside:avoid}.result-header{display:flex;align-items:flex-start;justify-content:space-between;gap:14px;padding:14px 16px;background:#fbfcfd;border-bottom:1px solid var(--line)}.result-header h3{margin:2px 0 3px}.component-label{font-size:12px;color:var(--muted)}.identity-strip{display:flex;flex-wrap:wrap;gap:8px 18px;padding:9px 16px;background:#f6f8fa;border-bottom:1px solid var(--line);font-size:11px}.identity-strip code{font-size:10.5px}.warning-list{padding:10px 16px;background:#fffaf1;border-bottom:1px solid var(--line)}.warning-list ul{margin:5px 0}.result-detail{padding:12px 16px}.result-detail>summary{cursor:pointer;font-weight:700;color:var(--accent)}
.table-wrap{overflow-x:auto;max-width:100%}table{border-collapse:collapse;width:100%;font-size:12px;margin:6px 0 12px}th,td{text-align:left;vertical-align:top;border:1px solid var(--line);padding:6px 7px;overflow-wrap:anywhere;word-break:break-word}th{background:#f0f3f6;font-weight:700}.compact{font-size:11px}.value-cell{font-variant-numeric:tabular-nums}.subpanel{border:1px solid var(--line);padding:10px 12px;margin:8px 0;background:#fcfdfe;break-inside:avoid}.subpanel-title{font-weight:700}.formula{margin:8px 0;display:flex;gap:10px;align-items:flex-start}.formula span{font-size:11px;color:var(--muted);min-width:80px}.formula code{white-space:pre-wrap}.trace-line{font-size:12px;margin:7px 0}.trace-list{font-size:12px;margin:7px 0}.trace-list summary{cursor:pointer}.trace-list ul{margin:5px 0}
.component-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px}.component-card{border:1px solid var(--line);padding:12px;background:#fbfcfd;break-inside:avoid}.component-card ul{padding-left:20px}.component-card a{color:var(--accent)}
.json-block{max-height:520px;overflow:auto;background:#111820;color:#e9eef3;padding:12px;font-size:10px;white-space:pre-wrap;overflow-wrap:anywhere}.scope-declaration{border:1px solid #b7c9dc;background:var(--scope-bg);padding:14px}.scope-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.scope-grid>div{background:white;border:1px solid #cfdae5;padding:10px}.report-selection{display:flex;flex-wrap:wrap;gap:8px 18px;margin:12px 0;padding:10px;border:1px solid var(--line)}.report-selection label{font-size:12px}.report-selection input{vertical-align:middle}
footer{padding:18px 34px;border-top:1px solid var(--line);font-size:11px;color:var(--muted)}
@media(max-width:900px){main,header{padding-left:18px;padding-right:18px}.result-toolbar{grid-template-columns:1fr 1fr}.scope-grid{grid-template-columns:1fr}.result-header{flex-direction:column}.metric-grid{grid-template-columns:1fr 1fr}}
@page{size:A4;margin:13mm 11mm}
@media print{body{background:white;font-size:9.5pt}.app-shell{max-width:none;box-shadow:none}.no-print,nav{display:none!important}header,main,footer{padding-left:0;padding-right:0}.report-section{padding:12mm 0 5mm;border-bottom:0}.section-heading{break-after:avoid}.result-card,.component-card,.subpanel,.metric{break-inside:avoid}.result-detail{display:block}.result-detail[open]{}details>summary{font-weight:700}details:not([open])>*:not(summary){display:block!important}.table-wrap{overflow:visible}table{font-size:8pt;table-layout:auto}th,td{padding:3px 4px}.status-badge{background:white!important;border:1px solid #555}.json-block{max-height:none;color:#111;background:#f6f6f6;border:1px solid #aaa}.wrap,code,.mono{overflow-wrap:anywhere;word-break:break-word}.report-section[data-presentation-state="excluded"]{display:none}.scope-grid{grid-template-columns:1fr 1fr}}
"""


def _script() -> str:
    return r"""
(function(){
  'use strict';
  const cards = Array.from(document.querySelectorAll('.result-card'));
  const status = document.getElementById('filter-status');
  const kind = document.getElementById('filter-kind');
  const ctype = document.getElementById('filter-component-type');
  const cid = document.getElementById('filter-component-id');
  const search = document.getElementById('result-search');
  const count = document.getElementById('result-count');
  const banner = document.getElementById('active-filter-banner');
  if(!status || !kind || !ctype || !cid || !search || !count || !banner){return;}
  const selectedTotal = cards.length;
  const canonicalTotal = Number(count.dataset.canonicalTotal || selectedTotal);
  function apply(){
    const exactStatus = status.value;
    const exactKind = kind.value;
    const exactType = ctype.value;
    const exactId = cid.value;
    const text = search.value.toLocaleLowerCase();
    let visible = 0;
    cards.forEach(function(card){
      const matchStatus = !exactStatus || card.dataset.status === exactStatus;
      const matchKind = !exactKind || card.dataset.kind === exactKind;
      const matchType = !exactType || card.dataset.componentType === exactType;
      const matchId = !exactId || card.dataset.componentId === exactId;
      const matchText = !text || card.textContent.toLocaleLowerCase().includes(text);
      const show = matchStatus && matchKind && matchType && matchId && matchText;
      card.hidden = !show;
      if(show){visible += 1;}
    });
    const active = Boolean(exactStatus || exactKind || exactType || exactId || text);
    banner.hidden = !active;
    count.textContent = 'Visible ' + visible + ' / presentation-selected ' + selectedTotal + ' / canonical total ' + canonicalTotal;
  }
  [status, kind, ctype, cid, search].forEach(function(control){control.addEventListener('input', apply);});
  document.querySelectorAll('a[href^="#"]').forEach(function(link){
    link.addEventListener('click', function(){
      const target = document.querySelector(link.getAttribute('href'));
      if(target){target.scrollIntoView({behavior:'smooth', block:'start'});}
    });
  });
  apply();
})();
"""


def render_building_report_html(
    projection: BuildingReportProjection,
    *,
    options: HtmlRenderOptions | None = None,
    selection: ReportPresentationSelection | None = None,
) -> str:
    """Render one canonical Engineering/Audit projection as standalone HTML."""

    if not isinstance(projection, BuildingReportProjection):
        raise TypeError("projection must be BuildingReportProjection")
    if projection.view not in (ReportView.ENGINEERING, ReportView.AUDIT):
        raise HtmlRenderIntegrityError("UR-1C supports only ENGINEERING and AUDIT projections")
    if projection.report_integrity_status != "RECONCILED":
        raise HtmlRenderIntegrityError(
            "report_integrity_status must be canonical RECONCILED before rendering"
        )
    if options is None:
        options = HtmlRenderOptions()
    if not isinstance(options, HtmlRenderOptions):
        raise TypeError("options must be HtmlRenderOptions or None")

    resolved_selection = resolve_presentation_selection(projection, selection)
    default_selection = default_presentation_selection(projection)
    selection_is_default = resolved_selection.as_dict() == default_selection.as_dict()
    payload = projection.as_dict()

    contributions = payload.get("contributions", [])
    if not isinstance(contributions, list):
        raise HtmlRenderIntegrityError("projection contributions must be a list")
    canonical_refs = tuple(
        str(item["contribution_ref"])
        for item in contributions
        if isinstance(item, dict) and "contribution_ref" in item
    )
    if len(canonical_refs) != len(contributions) or len(set(canonical_refs)) != len(canonical_refs):
        raise HtmlRenderIntegrityError("projection contribution_ref identity must be exact and unique")
    selected_refs = set(resolved_selection.selected_contribution_refs(projection))

    analysis_summary = payload.get("analysis_basis_summary", {})
    analysis_warnings = payload.get("analysis_basis_warnings", payload.get("analysis_basis_refs", []))
    reanalysis_count = 0
    if isinstance(analysis_summary, dict) and isinstance(analysis_summary.get("reanalysis_required_count"), int):
        reanalysis_count = int(analysis_summary["reanalysis_required_count"])

    presentation_banner = ""
    if not selection_is_default:
        presentation_banner = (
            '<div class="warning-banner presentation-filter-banner">'
            '<strong>Presentation selection/filter applied.</strong> '
            'Assessment population and canonical coverage are unchanged. '</n            f'<span>{len(selected_refs)} of {len(canonical_refs)} contributions are selected for presentation.</span></div>'
        )

    overview = (
        presentation_banner
        + _render_analysis_warning(analysis_summary, analysis_warnings)
        + '<div class="overview-grid"><h3>Project / design basis</h3>'
        + _render_basis(payload.get("project_basis"))
        + '<h3>Canonical status facets</h3>'
        + _render_status_facets(payload.get("status_facets"))
        + '</div>'
    )
    coverage = _render_coverage(payload.get("coverage_summary"), analysis_summary)
    results = _render_results(payload, selected_refs)
    components = _render_components(payload, selected_refs)
    evidence = _render_audit(payload, projection.view)
    actions = _render_actions(payload)
    reports = _render_reports(
        payload,
        resolved_selection,
        len(selected_refs),
        len(canonical_refs),
        selection_is_default,
    )

    sections = "".join(
        (
            _section_shell("overview", "Overview", overview, resolved_selection.include_overview),
            _section_shell("coverage", "Coverage", coverage, resolved_selection.include_coverage),
            _section_shell("results", "Results", results, resolved_selection.include_results),
            _section_shell("components", "Components", components, resolved_selection.include_components),
            _section_shell("evidence-audit", "Evidence / Audit", evidence, resolved_selection.include_evidence),
            _section_shell("actions", "Actions", actions, resolved_selection.include_actions),
            _section_shell("reports", "Reports", reports, True),
        )
    )

    nav = "".join(
        f'<a href="#{section_id}">{label}</a>'
        for section_id, label in (
            ("overview", "Overview"),
            ("coverage", "Coverage"),
            ("results", "Results"),
            ("components", "Components"),
            ("evidence-audit", "Evidence / Audit"),
            ("actions", "Actions"),
            ("reports", "Reports"),
        )
    )

    projection_json = ""
    if options.include_projection_json:
        projection_json = (
            '<script id="canonical-projection-json" type="application/json">'
            + _safe_json_script(payload)
            + "</script>"
        )
    interactivity = f"<script>{_script()}</script>" if options.enable_interactivity else ""
    reanalysis_marker = (
        f'<span class="view-pill">REANALYSIS_REQUIRED: {reanalysis_count}</span>'
        if reanalysis_count > 0
        else ""
    )

    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{_esc(payload.get("title"))} · Unified Engineering Review</title>'
        f'<style>{_styles()}</style></head><body><div class="app-shell">'
        '<header><div class="eyebrow">Unified Engineering Review</div>'
        f'<h1>{_esc(payload.get("title"))}</h1>'
        '<div class="identity-line">'
        f'<span><strong>project</strong> <code>{_esc(payload.get("project_id"))}</code></span>'
        f'<span><strong>report</strong> <code>{_esc(payload.get("report_id"))}</code></span>'
        f'<span><strong>view</strong> <code>{_esc(payload.get("view"))}</code></span>'
        '</div>'
        '<div class="integrity-banner">'
        f'<strong>report_integrity_status: {_esc(payload.get("report_integrity_status"))}</strong>'
        f'<span class="view-pill">{_esc(payload.get("view"))}</span>{reanalysis_marker}'
        '</div></header>'
        f'<nav class="no-print" aria-label="Primary review navigation">{nav}</nav>'
        f'<main>{sections}</main>'
        '<footer>Renderer authority: presentation only. Projection is the read-model; BuildingReportModel, FCR and the canonical engine remain truth.</footer>'
        f'{projection_json}{interactivity}</div></body></html>\n'
    )


__all__ = [
    "HtmlRenderIntegrityError",
    "HtmlRenderOptions",
    "render_building_report_html",
]
