"""Dependency-light product reporting package boundary.

Canonical report models, projections, renderers, and legacy compatibility
modules are imported from their concrete modules.  Package initialization must
not eagerly import legacy C13/P2 report code because supported product modules
share this parent package.

The historical C13 report remains directly importable from
``tbdy_engine.product_reports.c13_1_report``.  It is intentionally not
re-exported from the package root.
"""

__all__: list[str] = []
