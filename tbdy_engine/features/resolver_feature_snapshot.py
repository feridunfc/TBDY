"""Resolver-facing C13.3 FeatureSnapshot API.

This module makes the C13.3-P0 live source-row projection reusable by later
resolver/product/report orchestration without enabling CheckEngine logic.  It
keeps source values explicit, preserves unit metadata/evidence, and permanently
keeps check unlock disabled for this sprint.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from tbdy_engine.features.readiness import assert_no_engineering_verdict_text
from tbdy_engine.features.source_feature_snapshot_builder import (
    BASELINE,
    SOURCE_FAMILIES,
    blocked_check_guardrail_report as _blocked_check_guardrail_report,
    build_c13_3_p0_feature_snapshot,
    readiness_projection_report as _readiness_projection_report,
    summarize_snapshot as _summarize_snapshot,
    unit_normalization_report as _unit_normalization_report,
)

SPRINT = "C13.3-P1"
RESOLVER_NAME = "c13_3_p1_resolver_feature_snapshot"


def _records(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list(snapshot.get("feature_records") or snapshot.get("features") or [])


def _numeric_records(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [record for record in _records(snapshot) if isinstance(record.get("raw_value"), (int, float))]


def _raw_values_preserved(snapshot: Mapping[str, Any]) -> bool:
    return all(record.get("evidence", {}).get("raw_value") == record.get("raw_value") for record in _records(snapshot))


def _source_family_counts(snapshot: Mapping[str, Any]) -> dict[str, int]:
    counts = Counter(str(record.get("source_family")) for record in _records(snapshot) if record.get("source_family"))
    return dict(sorted(counts.items()))


def _decorate_records_for_resolver(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    decorated: list[dict[str, Any]] = []
    for source in records:
        record = deepcopy(dict(source))
        record["check_unlock_allowed"] = False
        record["safe_to_use_for_check"] = False
        guardrails = dict(record.get("semantic_guardrails") or {})
        guardrails.update({
            "check_unlock_allowed": False,
            "safe_to_use_for_check": False,
            "safe_to_implement_checks_now": False,
            "engineering_formulas_implemented": False,
            "resolver_integration_sprint": SPRINT,
        })
        record["semantic_guardrails"] = guardrails
        evidence = dict(record.get("evidence") or {})
        evidence["resolver"] = RESOLVER_NAME
        evidence["resolver_api"] = "build_feature_snapshot_from_source_rows"
        record["evidence"] = evidence
        decorated.append(record)
    return decorated


def _add_root_contract_fields(snapshot: dict[str, Any]) -> dict[str, Any]:
    feature_status_counts = Counter(record["feature_status"] for record in _records(snapshot))
    readiness_status_counts = Counter(record["readiness_status"] for record in _records(snapshot))
    numeric_records = _numeric_records(snapshot)
    unit_report = _unit_normalization_report(snapshot)
    snapshot.update({
        "sprint": SPRINT,
        "source_contract_baseline": BASELINE,
        "feature_status_counts": dict(sorted(feature_status_counts.items())),
        "readiness_status_counts": dict(sorted(readiness_status_counts.items())),
        "source_family_counts": _source_family_counts(snapshot),
        "numeric_feature_count": len(numeric_records),
        "raw_values_preserved": _raw_values_preserved(snapshot),
        "all_numeric_have_units": bool(unit_report["all_numeric_have_units"]),
        "all_numeric_have_quantity_kind": bool(unit_report["all_numeric_have_quantity_kind"]),
        "all_numeric_have_conversion_provenance": bool(unit_report["all_numeric_have_conversion_provenance"]),
        "unit_policy_closed": True,
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
    })
    return snapshot


def build_feature_snapshot_from_source_rows(
    source_rows_by_family: Mapping[str, Iterable[Mapping[str, Any]]] | None,
    *,
    live_etabs_connected: bool,
    model_path: str | None = None,
    etabs_version: str | None = None,
    target_family: str = "all",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the canonical C13.3-P1 resolver-facing FeatureSnapshot dict.

    The function delegates source-row projection to the accepted C13.3-P0
    builder, then hardens the root contract for resolver/product consumption.
    It does not implement checks, formulas, pass/fail verdicts, or CheckResult
    logic.
    """
    base = build_c13_3_p0_feature_snapshot(
        source_rows_by_family,
        live_etabs_connected=live_etabs_connected,
        model_path=model_path,
        etabs_version=etabs_version,
        target_family=target_family,
        generated_at=generated_at or datetime.now(timezone.utc).isoformat(),
    )
    snapshot = deepcopy(base)
    snapshot["feature_records"] = _decorate_records_for_resolver(_records(base))
    snapshot["model_path"] = model_path
    snapshot["etabs_version"] = etabs_version
    snapshot["target_family"] = target_family
    snapshot = _add_root_contract_fields(snapshot)
    assert_no_engineering_verdict_text(snapshot)
    return snapshot


def build_c13_3_p1_feature_snapshot(
    source_rows_by_family: Mapping[str, Iterable[Mapping[str, Any]]] | None,
    *,
    live_etabs_connected: bool,
    model_path: str | None = None,
    etabs_version: str | None = None,
    target_family: str = "all",
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Backward-friendly named alias for the C13.3-P1 API."""
    return build_feature_snapshot_from_source_rows(
        source_rows_by_family,
        live_etabs_connected=live_etabs_connected,
        model_path=model_path,
        etabs_version=etabs_version,
        target_family=target_family,
        generated_at=generated_at,
    )


def summarize_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    summary = _summarize_snapshot(snapshot)
    summary.update({
        "sprint": snapshot.get("sprint", SPRINT),
        "target_family": snapshot.get("target_family"),
        "source_family_counts": dict(snapshot.get("source_family_counts") or _source_family_counts(snapshot)),
        "numeric_feature_count": int(snapshot.get("numeric_feature_count") or len(_numeric_records(snapshot))),
        "raw_values_preserved": bool(snapshot.get("raw_values_preserved", _raw_values_preserved(snapshot))),
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "unit_policy_closed": True,
    })
    return dict(sorted(summary.items()))


def unit_normalization_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    report = _unit_normalization_report(snapshot)
    report.update({
        "sprint": snapshot.get("sprint", SPRINT),
        "numeric_feature_count": int(snapshot.get("numeric_feature_count") or report["numeric_feature_count"]),
        "raw_values_preserved": bool(snapshot.get("raw_values_preserved", report["raw_values_preserved"])),
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
    })
    return dict(sorted(report.items()))


def readiness_projection_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    report = _readiness_projection_report(snapshot)
    report.update({
        "sprint": snapshot.get("sprint", SPRINT),
        "source_family_counts": dict(snapshot.get("source_family_counts") or _source_family_counts(snapshot)),
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
    })
    return dict(sorted(report.items()))


def blocked_check_guardrail_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    report = _blocked_check_guardrail_report(snapshot)
    report.update({
        "sprint": snapshot.get("sprint", SPRINT),
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "engineering_verdicts_emitted": False,
    })
    return report


def source_family_projection_report(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    records = _records(snapshot)
    families = sorted({str(record.get("source_family")) for record in records if record.get("source_family")})
    by_family: dict[str, dict[str, Any]] = {}
    for family in families:
        family_records = [record for record in records if record.get("source_family") == family]
        status_counts = Counter(str(record.get("feature_status")) for record in family_records)
        readiness_counts = Counter(str(record.get("readiness_status")) for record in family_records)
        by_family[family] = {
            "feature_record_count": len(family_records),
            "feature_status_counts": dict(sorted(status_counts.items())),
            "readiness_status_counts": dict(sorted(readiness_counts.items())),
            "source_tables": sorted({table for record in family_records for table in record.get("source_tables", [])}),
            "numeric_feature_count": len([record for record in family_records if isinstance(record.get("raw_value"), (int, float))]),
        }
    return {
        "sprint": snapshot.get("sprint", SPRINT),
        "projected_families": families,
        "source_family_counts": dict(snapshot.get("source_family_counts") or _source_family_counts(snapshot)),
        "families": by_family,
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
    }


__all__ = [
    "SOURCE_FAMILIES",
    "SPRINT",
    "blocked_check_guardrail_report",
    "build_c13_3_p1_feature_snapshot",
    "build_feature_snapshot_from_source_rows",
    "readiness_projection_report",
    "source_family_projection_report",
    "summarize_snapshot",
    "unit_normalization_report",
]
