"""Product-level report builders.

Package initialization intentionally stays dependency-light. Canonical report
models that depend on coverage/reconciliation are imported from their concrete
modules (for example ``tbdy_engine.product_reports.unified_building_report``)
rather than eagerly re-exported here. This keeps the reporting package from
creating a coverage <-> product_reports import cycle.
"""

from .c13_1_report import build_c13_1_product_report, write_c13_1_product_report

__all__ = ["build_c13_1_product_report", "write_c13_1_product_report"]
