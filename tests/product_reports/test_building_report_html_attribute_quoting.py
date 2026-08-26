from __future__ import annotations

from html.parser import HTMLParser

from tbdy_engine.product_reports.building_report_html import (
    HtmlRenderOptions,
    render_building_report_html,
)
from tbdy_engine.product_reports.building_report_projection import (
    BuildingReportProjection,
    ReportView,
)


class _FixtureProjection(BuildingReportProjection):
    """Minimal projection-shaped fixture for renderer-only markup regression."""

    def __init__(self, payload: dict[str, object]) -> None:
        object.__setattr__(self, "_fixture_payload", payload)
        object.__setattr__(self, "_fixture_view", ReportView.ENGINEERING)

    @property
    def view(self) -> ReportView:
        return self._fixture_view

    @property
    def report_integrity_status(self) -> str:
        return "RECONCILED"

    def as_dict(self) -> dict[str, object]:
        return self._fixture_payload


class _ClassAttributeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.start_tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.start_tags.append((tag, dict(attrs)))


def _projection() -> BuildingReportProjection:
    contribution_ref = "CHECK|slice:A|beam|B1"
    payload: dict[str, object] = {
        "schema_version": "building_report_projection.ur_1b.v1",
        "artifact_type": "BUILDING_REPORT_PROJECTION",
        "view": "ENGINEERING",
        "report_id": "REPORT:1",
        "project_id": "PROJECT:1",
        "title": "HTML attribute quoting fixture",
        "report_integrity_status": "RECONCILED",
        "project_basis": {"entries": []},
        "coverage_summary": {
            "expected_mandatory_instance_count": 1,
            "accounted_instance_count": 1,
            "executed_result_count": 1,
            "mandatory_closure_complete": True,
            "population_reconciled": True,
            "report_reconciled": True,
        },
        "analysis_basis_summary": {
            "reanalysis_required_count": 0,
            "reanalysis_required_instance_ids": [],
        },
        "analysis_basis_refs": [],
        "status_facets": [{"status": "PASS", "count": 1}],
        "contribution_kind_facets": [
            {"contribution_kind": "CHECK", "count": 1}
        ],
        "component_facets": [
            {
                "component_type": "beam",
                "component_id": "B1",
                "contribution_count": 1,
                "contribution_refs": [contribution_ref],
            }
        ],
        "contributions": [
            {
                "contribution_ref": contribution_ref,
                "report_source_refs": ["RESULT:A"],
                "slice_id": "slice:A",
                "title": "Fixture contribution",
                "contribution_kind": "CHECK",
                "status": "PASS",
                "component_type": "beam",
                "component_id": "B1",
                "summary_fields": [],
                "calculations": [],
                "tables": [
                    {
                        "table_id": "TABLE:A",
                        "title": "Fixture table",
                        "columns": ["case", "value"],
                        "rows": [{"case": "LC1", "value": 1.0}],
                    }
                ],
                "warnings": [],
                "authority_refs": [],
                "evidence_refs": [],
            }
        ],
    }
    return _FixtureProjection(payload)


def test_rendered_html_uses_normal_attribute_quoting() -> None:
    rendered_html = render_building_report_html(
        _projection(),
        options=HtmlRenderOptions(
            include_projection_json=False,
            enable_interactivity=False,
        ),
    )

    assert '\\"' not in rendered_html
    assert '<div class="shell">' in rendered_html
    assert '<div class="table-wrap">' in rendered_html
    assert '<p class="muted">' in rendered_html

    parser = _ClassAttributeParser()
    parser.feed(rendered_html)

    assert any(
        tag == "div" and attrs.get("class") == "shell"
        for tag, attrs in parser.start_tags
    )
    assert any(
        tag == "div" and attrs.get("class") == "table-wrap"
        for tag, attrs in parser.start_tags
    )
    assert any(
        tag == "p" and attrs.get("class") == "muted"
        for tag, attrs in parser.start_tags
    )
