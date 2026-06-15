from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TABLES = yaml.safe_load((ROOT / "tbdy_engine/catalogs/table_registry.yaml").read_text(encoding="utf-8"))["tables"]
REPORTS = yaml.safe_load((ROOT / "tbdy_engine/catalogs/product_report_table_contract.yaml").read_text(encoding="utf-8"))["report_tables"]


def test_report_contract_sources_exist_and_checks_remain_locked():
    for report_id, report in REPORTS.items():
        assert report["check_unlock_allowed"] is False, report_id
        for field in ("verified_sources", "blocked_sources", "semantic_review_sources"):
            for source in report.get(field) or []:
                assert source in TABLES, (report_id, field, source)
