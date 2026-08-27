"""Stable public facade for Unified Engineering Review HTML rendering."""
from tbdy_engine.product_reports.building_report_html_v2 import (
    HtmlRenderIntegrityError,
    HtmlRenderOptions,
    render_building_report_html,
)

__all__ = [
    "HtmlRenderIntegrityError",
    "HtmlRenderOptions",
    "render_building_report_html",
]
