"""Professional Unified Engineering Review v2 HTML renderer.

UR-2 presentation layer. The renderer consumes only BuildingReportProjection
and delegates the accepted UR-1C detailed rendering to a frozen compatibility
implementation. The v2 layer adds information architecture and styling only.
It performs no engineering calculation, threshold evaluation, applicability,
governing selection, PASS/FAIL decision, remediation synthesis, ETABS query,
or project compliance verdict.
"""
from __future__ import annotations

from html import escape
import json
from typing import Mapping

from tbdy_engine.product_reports import building_report_html_ur1c as _ur1c
from tbdy_engine.product_reports.building_report_projection import BuildingReportProjection
from tbdy_engine.product_reports.report_presentation_selection import ReportPresentationSelection, resolve_presentation_selection

HtmlRenderIntegrityError = _ur1c.HtmlRenderIntegrityError
HtmlRenderOptions = _ur1c.HtmlRenderOptions


def _esc(value: object) -> str:
    return escape("" if value is None else str(value), quote=True)


def _show(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _list_of_dicts(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _basis_rows(payload: Mapping[str, object]) -> str:
    basis = payload.get("project_basis")
    if not isinstance(basis, dict):
        return '<div class="ur2-empty">No canonical project basis available.</div>'
    entries = _list_of_dicts(basis.get("entries"))
    if not entries:
        return '<div class="ur2-empty">No canonical project basis available.</div>'
    return (
        '<div class="table-wrap"><table class="ur2-table"><thead><tr>'
        '<th>Basis</th><th>Value</th><th>Unit</th><th>Source</th><th>Note</th>'
        '</tr></thead><tbody>'
        + ''.join(
            '<tr>'
            f'<td><strong>{_esc(item.get("label"))}</strong><div class="ur2-internal">{_esc(item.get("key"))}</div></td>'
            f'<td>{_esc(_show(item.get("value")))}</td>'
            f'<td>{_esc(_show(item.get("unit")))}</td>'
            f'<td class="ur2-internal">{_esc(", ".join(str(v) for v in item.get("source_ids", [])) if isinstance(item.get("source_ids"), list) else "")}</td>'
            f'<td>{_esc(_show(item.get("note")))}</td>'
            '</tr>' for item in entries
        )
        + '</tbody></table></div>'
    )


def _status_cards(payload: Mapping[str, object]) -> str:
    facets = _list_of_dicts(payload.get("status_facets"))
    if not facets:
        return '<div class="ur2-empty">No canonical contribution status facets.</div>'
    return '<div class="ur2-kpis">' + ''.join(
        '<div class="ur2-kpi">'
        f'<div class="ur2-kpi-label">{_esc(item.get("status"))}</div>'
        f'<div class="ur2-kpi-value">{_esc(_show(item.get("count")))}</div>'
        '<div class="ur2-kpi-note">Canonical contribution count</div></div>'
        for item in facets
    ) + '</div>'


def _coverage_cards(payload: Mapping[str, object]) -> str:
    values = _list_of_dicts(payload.get("coverage_display"))
    if not values:
        return '<div class="ur2-empty">No canonical FCR coverage summary.</div>'
    return '<div class="ur2-coverage">' + ''.join(
        '<div class="ur2-coverage-card" '
        f'data-canonical-key="{_esc(item.get("canonical_key"))}" '
        f'data-canonical-value="{_esc(json.dumps(item.get("value"), ensure_ascii=True))}">'
        f'<div class="ur2-coverage-label">{_esc(item.get("label"))}</div>'
        f'<div class="ur2-coverage-value">{_esc(_show(item.get("value")))}</div>'
        f'<div class="ur2-internal">{_esc(item.get("canonical_key"))}</div></div>'
        for item in values
    ) + '</div>'


def _attention_table(payload: Mapping[str, object], selected_refs: set[str]) -> str:
    values = [item for item in _list_of_dicts(payload.get("attention_items")) if str(item.get("contribution_ref")) in selected_refs]
    if not values:
        return '<div class="ur2-clear"><strong>No attention-state contribution is present in this presentation selection.</strong><span>This is not a project compliance verdict.</span></div>'
    rows = []
    for item in values:
        warnings = item.get("warnings")
        warning_text = ' | '.join(str(v) for v in warnings) if isinstance(warnings, list) else ''
        component = item.get("component_id") if item.get("component_id") is not None else 'PROJECT / GLOBAL'
        rows.append(
            '<tr>'
            f'<td><span class="ur2-status" data-status="{_esc(item.get("status"))}">{_esc(item.get("status"))}</span></td>'
            f'<td><strong>{_esc(item.get("title"))}</strong></td>'
            f'<td>{_esc(_show(item.get("component_type")))}</td>'
            f'<td>{_esc(component)}</td>'
            f'<td>{_esc(warning_text or "-")}</td></tr>'
        )
    return '<div class="table-wrap"><table class="ur2-table"><thead><tr><th>Status</th><th>Check / contribution</th><th>Component type</th><th>Component</th><th>Canonical warning / note</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'


def _analysis_basis(payload: Mapping[str, object]) -> str:
    summary = payload.get("analysis_basis_summary")
    if not isinstance(summary, dict):
        return '<div class="ur2-empty">No canonical analysis-basis summary.</div>'
    count = summary.get("reanalysis_required_count")
    ids = summary.get("reanalysis_required_instance_ids")
    id_html = ''
    if isinstance(ids, list) and ids:
        id_html = '<details class="ur2-details"><summary>Exact instance identities</summary><ul>' + ''.join(f'<li class="ur2-internal">{_esc(v)}</li>' for v in ids) + '</ul></details>'
    return '<div class="ur2-analysis-card"><div><span class="ur2-label">Reanalysis required</span>' + f'<strong>{_esc(_show(count))}</strong></div><p>Copied from canonical AnalysisBasisStatus accounting. The renderer preserves this upstream state without reinterpretation.</p>' + id_html + '</div>'


def _domain_cards(payload: Mapping[str, object], selected_refs: set[str]) -> str:
    cards = []
    for domain in _list_of_dicts(payload.get("presentation_domains")):
        refs = domain.get("contribution_refs") if isinstance(domain.get("contribution_refs"), list) else []
        visible_count = sum(1 for ref in refs if str(ref) in selected_refs)
        cards.append(
            '<div class="ur2-domain">'
            f'<div class="ur2-domain-title">{_esc(domain.get("label"))}</div>'
            f'<div class="ur2-domain-count">{visible_count}</div>'
            '<div class="ur2-domain-note">Visible canonical contributions</div>'
            f'<div class="ur2-domain-desc">{_esc(domain.get("description"))}</div></div>'
        )
    return '<div class="ur2-domain-grid">' + ''.join(cards) + '</div>'


def _action_register(payload: Mapping[str, object]) -> str:
    register = payload.get("action_register") if isinstance(payload.get("action_register"), dict) else {}
    required = register.get("required_action_finding_ids") if isinstance(register, dict) else None
    required_values = required if isinstance(required, list) else []
    if not required_values:
        return '<div class="ur2-gap-callout"><strong>REPORT_INPUT_GAP - structured remediation records are not available here.</strong><p>The renderer will not generate actions from result status alone. Only canonical action/remediation records may populate this section.</p></div>'
    return '<div class="ur2-action-list"><div class="ur2-label">Canonical action finding identities</div><ul>' + ''.join(f'<li class="ur2-internal">{_esc(value)}</li>' for value in required_values) + '</ul><p class="ur2-muted">Action text is not synthesized by the renderer.</p></div>'


def _gap_register(payload: Mapping[str, object]) -> str:
    gaps = _list_of_dicts(payload.get("report_input_gaps"))
    if not gaps:
        return '<div class="ur2-empty">No report-input gap metadata.</div>'
    return '<div class="table-wrap"><table class="ur2-table ur2-gap-table"><thead><tr><th>Gap</th><th>Status</th><th>Needed for</th><th>Canonical read-model limitation</th></tr></thead><tbody>' + ''.join(
        '<tr>'
        f'<td class="ur2-internal">{_esc(item.get("gap_id"))}</td>'
        f'<td><span class="ur2-gap-badge">{_esc(item.get("status"))}</span></td>'
        f'<td>{_esc(item.get("needed_for"))}</td>'
        f'<td>{_esc(item.get("detail"))}</td></tr>'
        for item in gaps
    ) + '</tbody></table></div>'


def _demo_banner(payload: Mapping[str, object]) -> str:
    context = payload.get("report_context")
    classification = context.get("data_classification") if isinstance(context, dict) else None
    phase = context.get("report_phase") if isinstance(context, dict) else None
    if classification != "DEMO DATA":
        return ''
    return '<div class="ur2-demo-ribbon" role="note"><strong>DEMO DATA - ILLUSTRATIVE PRODUCT PACKAGE - NOT LIVE ENGINEERING TRUTH</strong>' + f'<span>Report phase: {_esc(_show(phase))}. Values and statuses belong only to the deterministic demo fixture.</span></div>'


def _professional_overview(payload: Mapping[str, object], selected_refs: set[str]) -> str:
    context = payload.get("report_context")
    classification = context.get("data_classification") if isinstance(context, dict) else None
    phase = context.get("report_phase") if isinstance(context, dict) else None
    return (
        '<div class="ur2-professional">' + _demo_banner(payload)
        + '<header class="ur2-cover"><div class="ur2-cover-kicker">TBDY ENGINE - UNIFIED ENGINEERING REVIEW V2</div>'
        + f'<h1>{_esc(payload.get("title"))}</h1>'
        + '<p class="ur2-cover-lead">Professional structural-engineering review presentation of the canonical BuildingReportModel. Presentation does not create engineering truth.</p>'
        + '<div class="ur2-cover-grid">'
        + f'<div><span>Project</span><strong>{_esc(payload.get("project_id"))}</strong></div>'
        + f'<div><span>Report</span><strong>{_esc(payload.get("report_id"))}</strong></div>'
        + f'<div><span>View</span><strong>{_esc(payload.get("view"))}</strong></div>'
        + f'<div><span>Report integrity</span><strong>{_esc(payload.get("report_integrity_status"))}</strong></div>'
        + f'<div><span>Data classification</span><strong>{_esc(_show(classification))}</strong></div>'
        + f'<div><span>Phase</span><strong>{_esc(_show(phase))}</strong></div></div></header>'
        + '<nav class="ur2-toc"><strong>Review path</strong><a href="#ur2-summary">Executive summary</a><a href="#ur2-findings">Critical findings / blockers</a><a href="#ur2-basis">Project / design basis</a><a href="#ur2-analysis">Model / analysis basis</a><a href="#ur2-coverage">Coverage</a><a href="#ur2-domains">Engineering domains</a><a href="#ur2-actions">Required actions</a><a href="#ur2-gaps">Report input gaps</a><a href="#overview">Detailed canonical review</a></nav>'
        + '<section id="ur2-summary" class="ur2-section"><div class="ur2-section-head"><div><span>01</span><h2>Engineering executive summary</h2></div><p>Status populations below are copied exactly from the projection; no project-level score is calculated.</p></div>' + _status_cards(payload) + '</section>'
        + '<section id="ur2-findings" class="ur2-section"><div class="ur2-section-head"><div><span>02</span><h2>Critical findings / blockers / reanalysis</h2></div><p>Attention-state rows are presentation filters over exact canonical statuses. No severity or remediation is invented.</p></div>' + _attention_table(payload, selected_refs) + _analysis_basis(payload) + '</section>'
        + '<section id="ur2-basis" class="ur2-section"><div class="ur2-section-head"><div><span>03</span><h2>Project and seismic design basis</h2></div><p>Canonical ProjectBasisLedger values and sources.</p></div>' + _basis_rows(payload) + '</section>'
        + '<section id="ur2-analysis" class="ur2-section"><div class="ur2-section-head"><div><span>04</span><h2>Model / analysis basis</h2></div><p>Canonical analysis-basis accounting. Model epoch is shown only when upstream supplies it.</p></div>' + _analysis_basis(payload) + '</section>'
        + '<section id="ur2-coverage" class="ur2-section"><div class="ur2-section-head"><div><span>05</span><h2>Coverage by engineering domain</h2></div><p>Human-readable labels are paired with the exact canonical FCR value and key.</p></div>' + _coverage_cards(payload) + '</section>'
        + '<section id="ur2-domains" class="ur2-section"><div class="ur2-section-head"><div><span>06</span><h2>Engineering domain navigation</h2></div><p>Only exact component_type presentation tokens are grouped. Unknown tokens remain in appendices.</p></div>' + _domain_cards(payload, selected_refs) + '</section>'
        + '<section id="ur2-actions" class="ur2-section"><div class="ur2-section-head"><div><span>07</span><h2>Required actions / remediation register</h2></div><p>Canonical action records only. A result status alone never becomes a renderer-authored action.</p></div>' + _action_register(payload) + '</section>'
        + '<section id="ur2-gaps" class="ur2-section"><div class="ur2-section-head"><div><span>08</span><h2>REPORT_INPUT_GAP register</h2></div><p>Professional-report information not yet carried by the canonical upstream read-model.</p></div>' + _gap_register(payload) + '</section>'
        + '<div class="ur2-detail-intro"><strong>Detailed canonical review and complete drill-down continue below.</strong><span>Internal contribution/source identifiers are intentionally deferred to detailed trace.</span></div></div>'
    )


_UR2_CSS = r"""
.ur2-professional{margin:0 0 28px;color:#172033}.ur2-demo-ribbon{padding:14px 18px;background:#fff3cd;border:2px solid #d39e00;color:#674d00;display:flex;gap:10px;flex-direction:column;font-size:13px}.ur2-demo-ribbon strong{font-size:15px;letter-spacing:.035em}.ur2-cover{padding:36px 42px 30px;background:linear-gradient(145deg,#102a43,#1d4f78);color:#fff;border-radius:8px 8px 0 0}.ur2-cover-kicker{font-size:10px;letter-spacing:.17em;font-weight:800;color:#bad3e7}.ur2-cover h1{font-size:31px;line-height:1.12;margin:10px 0 8px;color:#fff}.ur2-cover-lead{max-width:900px;color:#dce8f2;font-size:13px}.ur2-cover-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:20px}.ur2-cover-grid div{border:1px solid #ffffff35;background:#ffffff0d;padding:9px 10px}.ur2-cover-grid span{display:block;font-size:9px;letter-spacing:.08em;color:#c6d9e8;text-transform:uppercase}.ur2-cover-grid strong{display:block;margin-top:3px;font-size:12px;overflow-wrap:anywhere}.ur2-toc{display:flex;flex-wrap:wrap;gap:6px;padding:12px;background:#f3f6f9;border:1px solid #d7e0e8}.ur2-toc strong{margin-right:8px;color:#17324d}.ur2-toc a{font-size:11px;padding:4px 7px;background:#fff;border:1px solid #d7e0e8;border-radius:4px;text-decoration:none;color:#234b70}.ur2-section{padding:24px 0 8px;border-bottom:1px solid #d8e0e7}.ur2-section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;margin-bottom:12px}.ur2-section-head>div{display:flex;align-items:baseline;gap:9px}.ur2-section-head span{font-size:10px;font-weight:800;color:#6b7d90}.ur2-section-head h2{margin:0;color:#17324d;font-size:20px}.ur2-section-head p{max-width:620px;margin:0;color:#64748b;font-size:11px;text-align:right}.ur2-kpis,.ur2-coverage,.ur2-domain-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.ur2-kpi,.ur2-coverage-card,.ur2-domain{border:1px solid #d7e0e8;background:#fff;padding:11px;border-radius:5px}.ur2-kpi-label,.ur2-coverage-label,.ur2-label{font-size:10px;color:#64748b;font-weight:700;text-transform:uppercase;letter-spacing:.04em}.ur2-kpi-value,.ur2-coverage-value,.ur2-domain-count{font-size:23px;font-weight:800;color:#17324d;margin-top:2px}.ur2-kpi-note,.ur2-domain-note,.ur2-domain-desc{font-size:10px;color:#77879a;margin-top:3px}.ur2-domain-title{font-size:12px;font-weight:750;color:#243b53}.ur2-table{width:100%;border-collapse:collapse;font-size:10.5px}.ur2-table th,.ur2-table td{border:1px solid #d7e0e8;padding:6px 7px;text-align:left;vertical-align:top}.ur2-table th{background:#eef3f7;color:#31465b}.ur2-internal{font-family:Consolas,Menlo,monospace;font-size:9px;color:#718096;overflow-wrap:anywhere}.ur2-status,.ur2-gap-badge{display:inline-block;padding:2px 6px;border-radius:10px;font-size:9px;font-weight:800;border:1px solid #cbd5e1;background:#f8fafc}.ur2-status[data-status="FAIL"]{color:#991b1b;background:#fee2e2;border-color:#fecaca}.ur2-status[data-status="BLOCKED"],.ur2-status[data-status="NO_DATA"],.ur2-status[data-status="REANALYSIS_REQUIRED"]{color:#92400e;background:#fef3c7;border-color:#fde68a}.ur2-clear,.ur2-analysis-card,.ur2-gap-callout,.ur2-detail-intro{border-left:4px solid #4c7396;background:#f5f8fb;padding:10px 13px;margin:8px 0}.ur2-clear{border-left-color:#2f855a;background:#f0fff4;display:flex;gap:5px;flex-direction:column}.ur2-gap-callout{border-left-color:#c07a00;background:#fff8e6}.ur2-analysis-card>div{display:flex;justify-content:space-between;align-items:center}.ur2-analysis-card strong{font-size:22px;color:#17324d}.ur2-analysis-card p,.ur2-muted{font-size:10.5px;color:#64748b}.ur2-details summary{cursor:pointer;color:#315d7d;font-weight:700}.ur2-gap-badge{color:#7c2d12;background:#ffedd5;border-color:#fed7aa}.ur2-detail-intro{margin-top:24px;border-left-color:#17324d;display:flex;gap:4px;flex-direction:column}.ur2-empty{padding:10px;background:#f8fafc;border:1px dashed #cbd5e1;color:#64748b;font-size:11px}@media(max-width:900px){.ur2-cover-grid,.ur2-kpis,.ur2-coverage,.ur2-domain-grid{grid-template-columns:1fr 1fr}.ur2-section-head{display:block}.ur2-section-head p{text-align:left;margin-top:5px}}@media print{.ur2-cover{break-inside:avoid}.ur2-demo-ribbon{break-inside:avoid}.ur2-kpi,.ur2-coverage-card,.ur2-domain,.ur2-table tr{break-inside:avoid}.ur2-toc a{text-decoration:none}}
"""


def render_building_report_html(projection: BuildingReportProjection, *, options: HtmlRenderOptions | None = None, selection: ReportPresentationSelection | None = None) -> str:
    if not isinstance(projection, BuildingReportProjection):
        raise TypeError("projection must be BuildingReportProjection")
    resolved = resolve_presentation_selection(projection, selection)
    selected_refs = set(resolved.selected_contribution_refs(projection))
    payload = projection.as_dict()
    html = _ur1c.render_building_report_html(projection, options=options, selection=resolved)
    if not html.startswith("<!doctype html><html") or not html.endswith("</html>\n"):
        raise HtmlRenderIntegrityError("accepted detailed renderer returned invalid standalone HTML")
    overview = _professional_overview(payload, selected_refs)
    if '<div class="shell">' not in html:
        raise HtmlRenderIntegrityError("accepted HTML shell anchor is missing")
    html = html.replace('<div class="shell">', '<div class="shell">' + overview, 1)
    if '</style>' not in html:
        raise HtmlRenderIntegrityError("accepted HTML style anchor is missing")
    html = html.replace('</style>', _UR2_CSS + '</style>', 1)
    return html


__all__ = ["HtmlRenderIntegrityError", "HtmlRenderOptions", "render_building_report_html"]
