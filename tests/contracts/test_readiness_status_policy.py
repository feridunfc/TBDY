from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
STATUSES = yaml.safe_load((ROOT / "tbdy_engine/catalogs/readiness_status_policy.yaml").read_text(encoding="utf-8"))["statuses"]


def test_readiness_status_policy_contains_required_statuses():
    assert set(STATUSES) >= {
        "VERIFIED_LIVE",
        "NEEDS_LIVE_PROBE",
        "SEMANTIC_REVIEW",
        "EXCEL_INVENTORY_ONLY",
        "PLANNED",
        "OUT_OF_SCOPE",
        "UNSUPPORTED_SECTION_TYPE",
    }


def test_verified_live_does_not_unlock_engineering_checks():
    assert STATUSES["VERIFIED_LIVE"]["may_unlock_engineering_check"] is False
