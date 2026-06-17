"""Diagnostic-only check preflight contract for C13.3-P3.

The report explains why checks remain locked.  It does not import CheckEngine,
execute checks, or compute engineering results.
"""
from __future__ import annotations

from typing import Any, Mapping

from tbdy_engine.features.feature_snapshot_artifact_validator import scan_for_forbidden_engineering_verdicts

SPRINT = "C13.3-P3"
DIAGNOSTIC_CONTRACT_VERSION = "c13.3-p3.check_preflight_diagnostic.v1"

_GROUP_DEFINITIONS = (
    {
        "group_id": "material_compliance",
        "related_source_families": ["material_properties"],
        "required_before_check_unlock": [
            "material rule scope contract",
            "material acceptance fixture set",
            "check result schema binding",
        ],
    },
    {
        "group_id": "story_drift_torsion_force",
        "related_source_families": ["story_definitions"],
        "required_before_check_unlock": [
            "force result semantic promotion",
            "combo envelope governing semantic contract",
            "per-check validation fixture set",
        ],
    },
    {
        "group_id": "pier_wall_force_capacity_detailing",
        "related_source_families": ["pier_section_properties"],
        "required_before_check_unlock": [
            "pier force result semantic promotion",
            "design output rebar semantic review",
            "per-check validation fixture set",
        ],
    },
)


def _ready_sources(report_payload: Mapping[str, Any], families: list[str]) -> dict[str, Any]:
    by_family = {str(item.get("source_family")): item for item in report_payload.get("source_families", [])}
    ready: dict[str, Any] = {}
    for family in families:
        item = by_family.get(family, {})
        ready[family] = {
            "feature_record_count": int(item.get("feature_record_count", 0) or 0),
            "numeric_feature_count": int(item.get("numeric_feature_count", 0) or 0),
            "readiness_status_counts": dict(item.get("readiness_status_counts", {})),
            "source_tables": list(item.get("source_tables", [])),
        }
    return ready


def build_check_preflight_diagnostic_report(report_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a deterministic diagnostic-only preflight report.

    The output describes current source evidence and future blockers only.  It
    never invokes checks and never emits engineering verdicts.
    """
    prospective_groups: list[dict[str, Any]] = []
    for group in _GROUP_DEFINITIONS:
        related_families = list(group["related_source_families"])
        current_ready_sources = _ready_sources(report_payload, related_families)
        has_source_records = any(item["feature_record_count"] > 0 for item in current_ready_sources.values())
        prospective_groups.append({
            "group_id": group["group_id"],
            "current_status": "CHECKS_LOCKED" if has_source_records else "NOT_READY_FOR_CHECK",
            "related_source_families": related_families,
            "current_ready_sources": current_ready_sources,
            "blocked_by": [
                "checks are locked by sprint policy",
                "source evidence is not promoted to check input semantics",
                "CheckEngine invocation is outside C13.3-P3 scope",
            ],
            "required_before_check_unlock": list(group["required_before_check_unlock"]),
            "check_engine_invoked": False,
            "engineering_verdict_emitted": False,
        })
    blockers = [
        "force result semantic promotion",
        "combo envelope governing semantics",
        "design output rebar semantic review",
        "CheckResult schema binding",
        "report harness for check artifacts",
        "per-check engineering validation fixtures",
    ]
    report = {
        "sprint": SPRINT,
        "diagnostic_contract_version": DIAGNOSTIC_CONTRACT_VERSION,
        "diagnostic_only": True,
        "check_engine_invoked": False,
        "checks_locked": True,
        "safe_to_implement_checks_now": False,
        "check_unlock_allowed": False,
        "source_evidence_only": True,
        "prospective_check_groups": prospective_groups,
        "blockers": blockers,
        "required_future_contracts": [
            "force result semantic contract",
            "combo governing contract",
            "design output semantic contract",
            "CheckResult schema binding",
            "check artifact report contract",
            "per-check validation fixture contract",
        ],
        "engineering_verdicts_emitted": False,
        "check_results_emitted": False,
        "excel_production_input_used": False,
    }
    scan = scan_for_forbidden_engineering_verdicts(report)
    if scan["forbidden_terms_found"]:
        raise ValueError(f"Forbidden diagnostic terms emitted: {scan['forbidden_terms_found']}")
    return report


__all__ = [
    "DIAGNOSTIC_CONTRACT_VERSION",
    "SPRINT",
    "build_check_preflight_diagnostic_report",
]
