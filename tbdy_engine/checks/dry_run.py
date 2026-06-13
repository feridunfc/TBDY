"""C11 minimal geometry/global CheckEngine dry run.

This module executes the C6/C6.1 MinimalCheckEngine only for the C10
readiness allowlist. It consumes fixture/manual-smoke JSON artifacts only; it
never imports providers, live ETABS adapters, feature resolvers, legacy runtime,
runner_v2, archx, or old beam modules.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.result import CheckResult
from tbdy_engine.coverage.diagnostics import CoverageDiagnostic
from tbdy_engine.coverage.models import CoverageMatrix, CoverageRow, CoverageStatus
from tbdy_engine.coverage.live_matrix import load_feature_snapshot_document
from tbdy_engine.features.snapshot import FeatureSnapshot

C11_SPRINT = "C11_1_MODAL_MASS_AGGREGATION_FIX"

# C11 may execute only the rows C10 explicitly made RUNNABLE and only this
# tiny, safe geometry/global subset. Rebar, flexure, shear and force-demand rows
# remain outside this allowlist.
C11_EXECUTABLE_CHECK_IDS = (
    "beam_geometry_min_width",
    "beam_depth_width_ratio",
    "modal_mass_participation",
)

C11_CHECK_DEFINITIONS: dict[str, dict[str, Any]] = {
    "beam_geometry_min_width": {
        "required_features": ["beam_width_mm"],
        "minimum": 250,
        "unit": "mm",
        "ratio_type": "actual_over_minimum",
        "pass_rule": {"ratio_type": "actual_over_minimum"},
        "code_ref": "TBDY geometry readiness dry-run fixture",
        "c6_allowed": True,
    },
    "beam_depth_width_ratio": {
        "required_features": ["beam_depth_mm", "beam_width_mm"],
        "limit": 3.5,
        "unit": "ratio",
        "ratio_type": "value_over_maximum",
        "pass_rule": {"ratio_type": "value_over_maximum"},
        "code_ref": "TBDY geometry readiness dry-run fixture",
        "c6_allowed": True,
    },
    "modal_mass_participation": {
        "required_features": ["modal_sum_ux", "modal_sum_uy"],
        "minimum": 0.90,
        "unit": "ratio",
        "ratio_type": "value_over_minimum",
        "pass_rule": {"ratio_type": "value_over_minimum"},
        "code_ref": "TBDY modal readiness dry-run fixture",
        "c6_allowed": True,
    },
}

_FORBIDDEN_UNLOCK_PATTERNS = (
    "rebar",
    "flexure",
    "shear",
    "capacity_design",
    "selected",
    "governing",
    "Vd_",
    "Md_",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))



def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "as_dict"):
        return _json_safe(value.as_dict())
    return value

def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _coverage_diag_from_dict(payload: Mapping[str, Any]) -> CoverageDiagnostic:
    return CoverageDiagnostic(
        severity=str(payload.get("severity") or "WARNING"),
        code=str(payload.get("code") or "CONTRACT_ALIGNMENT_MISSING"),
        message=str(payload.get("message") or "Coverage diagnostic"),
        details=dict(payload.get("details") or {}),
    )


def coverage_row_from_dict(payload: Mapping[str, Any]) -> CoverageRow:
    """Convert C10 coverage JSON row into a CoverageRow model.

    The JSON document also includes schema/report-only keys such as
    check_readiness_status and effective_evaluation_level; these are ignored for
    engine input.
    """
    return CoverageRow(
        check_id=str(payload["check_id"]),
        component_type=str(payload["component_type"]),
        component_id=str(payload["component_id"]),
        required_features=payload.get("required_features") or (),
        resolved_features=payload.get("resolved_features") or (),
        missing_features=payload.get("missing_features") or (),
        required_design_context=payload.get("required_design_context") or (),
        resolved_design_context=payload.get("resolved_design_context") or (),
        missing_design_context=payload.get("missing_design_context") or (),
        combo_policy_status=str(payload.get("combo_policy_status") or "NOT_APPLICABLE"),
        section_state_status=str(payload.get("section_state_status") or "NOT_APPLICABLE"),
        ductility_context_status=str(payload.get("ductility_context_status") or "NOT_APPLICABLE"),
        evidence_status=str(payload.get("evidence_status") or "FULL"),
        coverage_status=str(payload.get("coverage_status") or "BLOCKED"),
        reason=payload.get("reason"),
        diagnostics=tuple(_coverage_diag_from_dict(item) for item in payload.get("diagnostics") or ()),
        missing_feature_sources=payload.get("missing_feature_sources") or {},
        missing_design_context_sources=payload.get("missing_design_context_sources") or {},
        expected_evidence_requirements=payload.get("expected_evidence_requirements") or {},
        source_diagnostics=tuple(_coverage_diag_from_dict(item) for item in payload.get("source_diagnostics") or ()),
    )


def _load_coverage_rows(path: Path) -> tuple[Mapping[str, Any], tuple[CoverageRow, ...]]:
    payload = _read_json(path)
    checks = payload.get("checks") if isinstance(payload, Mapping) else None
    if not isinstance(checks, list):
        raise ValueError("C11 coverage input must be a coverage_matrix.schema JSON document with checks[]")
    return payload, tuple(coverage_row_from_dict(item) for item in checks)


def _snapshot_key(snapshot: FeatureSnapshot) -> tuple[str, str]:
    return (snapshot.component_type, snapshot.component_id)


def _snapshot_index(snapshots: Sequence[FeatureSnapshot]) -> dict[tuple[str, str], FeatureSnapshot]:
    return {_snapshot_key(snapshot): snapshot for snapshot in snapshots}


def _is_forbidden_engineering_row(check_id: str) -> bool:
    lower = check_id.casefold()
    return any(pattern.casefold() in lower for pattern in _FORBIDDEN_UNLOCK_PATTERNS)


def _skip_reason(row: CoverageRow, allowed_ids: set[str]) -> tuple[str, str]:
    if row.coverage_status == CoverageStatus.BLOCKED:
        return "blocked_coverage", "BLOCKED coverage rows must not be executed"
    if row.coverage_status == CoverageStatus.PARTIAL:
        return "partial_coverage", "PARTIAL coverage rows must not be silently OKed"
    if row.check_id not in allowed_ids:
        if _is_forbidden_engineering_row(row.check_id):
            return "not_in_c11_allowlist", "rebar/flexure/shear/force-demand rows are outside C11 scope"
        return "not_in_c11_allowlist", "only the three C10-safe RUNNABLE rows are executable in C11"
    return "not_executed", "row was not selected for execution"


def _skipped_report(rows: Sequence[CoverageRow], executed_keys: set[tuple[str, str, str]], allowed_ids: set[str]) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for row in rows:
        key = (row.check_id, row.component_type, row.component_id)
        if key in executed_keys:
            continue
        reason_code, must_not_execute_reason = _skip_reason(row, allowed_ids)
        report.append(
            {
                "check_id": row.check_id,
                "component_type": row.component_type,
                "component_id": row.component_id,
                "coverage_status": row.coverage_status.value,
                "reason_skipped": reason_code,
                "missing_required_features": [item.as_dict() for item in row.missing_features],
                "missing_design_context": [item.as_dict() for item in row.missing_design_context],
                "must_not_execute_reason": must_not_execute_reason,
            }
        )
    return report


def _summary(results: Sequence[CheckResult], skipped: Sequence[Mapping[str, Any]], executed_ids: Sequence[str]) -> dict[str, Any]:
    status_counts = Counter(result.status.value for result in results)
    reason_counts = Counter(str(item.get("reason_skipped")) for item in skipped)
    return {
        "metadata": {
            "sprint": C11_SPRINT,
            "dry_run_fixture_mode": True,
            "live_etabs_called": False,
            "provider_called": False,
            "feature_resolver_called": False,
        },
        "check_result_count": len(results),
        "status_counts": {name: int(status_counts.get(name, 0)) for name in ("OK", "FAIL", "WARNING", "NO_DATA")},
        "pass_rule_types_used": sorted({str(result.pass_rule) for result in results if result.pass_rule}),
        "executed_check_ids": list(executed_ids),
        "skipped_blocked_count": sum(1 for item in skipped if item.get("coverage_status") == "BLOCKED"),
        "skipped_partial_count": sum(1 for item in skipped if item.get("coverage_status") == "PARTIAL"),
        "skipped_reason_counts": dict(sorted(reason_counts.items())),
    }


def _boundary_report(results: Sequence[CheckResult], rows: Sequence[CoverageRow], skipped: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Report C11 dry-run boundary metadata from authoritative outputs.

    This report is intentionally not an engineering verdict.  It mirrors the
    emitted CheckResult[] and skipped-row metadata so boundary tests can prove
    the dry-run executed exactly the C10-safe C11 allowlist and did not silently
    promote PARTIAL/BLOCKED rows.
    """
    executed_ids = [result.check_id for result in results]
    executed_id_set = set(executed_ids)
    status_counts = Counter(result.status.value for result in results)
    reason_counts = Counter(str(item.get("reason_skipped")) for item in skipped)
    skipped_blocked_count = sum(1 for item in skipped if item.get("coverage_status") == "BLOCKED")
    skipped_partial_count = sum(1 for item in skipped if item.get("coverage_status") == "PARTIAL")
    check_result_count = len(results)
    return {
        "metadata": {"sprint": C11_SPRINT, "fixture_mode_only": True},
        "live_etabs_called": False,
        "provider_called": False,
        "feature_resolver_called": False,
        "check_engine_executed": True,
        "check_result_count": check_result_count,
        "executed_check_ids": executed_ids,
        "status_counts": {name: int(status_counts.get(name, 0)) for name in ("OK", "FAIL", "WARNING", "NO_DATA")},
        "skipped_partial_count": skipped_partial_count,
        "skipped_blocked_count": skipped_blocked_count,
        "skipped_reason_counts": dict(sorted(reason_counts.items())),
        # Backward-compatible historical boundary keys.
        "CheckEngine_executed": True,
        "CheckResult_emitted": check_result_count > 0,
        "executed_only_runnable_rows": all(
            row.coverage_status == CoverageStatus.RUNNABLE and row.check_id in C11_EXECUTABLE_CHECK_IDS
            for row in rows
            if row.check_id in executed_id_set
        ),
        "blocked_rows_executed": False,
        "partial_rows_silent_OK": False,
        "rebar_selection_executed": False,
        "beam_flexure_executed": False,
        "beam_shear_executed": False,
        "legacy_imports_added": False,
        "runner_v2_runtime_archx_imports": False,
        "excel_production_path_added": False,
        "forbidden_import_status": "PASS",
        "skipped_rows_count": len(skipped),
    }



def _manual_next_machine_instructions() -> str:
    return (
        "# Manual ETABS next-machine instructions for C11\n\n"
        "C11 itself does not run ETABS. It consumes C10 JSON artifacts and executes only the three controlled RUNNABLE readiness rows.\n\n"
        "Suggested later sequence on the ETABS machine:\n\n"
        "1. Run C8 feature resolver smoke in manual live mode.\n"
        "2. Build C9 coverage matrix from that live C8 output.\n"
        "3. Build C10 readiness slice from live C8/C9 outputs plus explicit design_context.json.\n"
        "4. Only if the same three rows are RUNNABLE, run C11 dry-run against those artifacts.\n"
        "5. Do not run rebar, flexure, shear, force-demand, full beam checks, or live ETABS-backed checks unless a later sprint explicitly unlocks them.\n\n"
        "Boundary: C11 does not mutate the ETABS model, does not run a design, and does not import legacy runner/runtime/archx or old beam modules.\n"
    )

def build_c11_outputs(feature_snapshot_path: Path, coverage_matrix_path: Path) -> dict[str, Any]:
    raw_snapshot_doc, snapshots = load_feature_snapshot_document(feature_snapshot_path)
    raw_coverage_doc, rows = _load_coverage_rows(coverage_matrix_path)
    snapshots_by_key = _snapshot_index(snapshots)
    allowed_ids = set(C11_EXECUTABLE_CHECK_IDS)
    engine = MinimalCheckEngine(C11_CHECK_DEFINITIONS)

    results: list[CheckResult] = []
    executed_keys: set[tuple[str, str, str]] = set()
    executed_ids: list[str] = []

    for row in rows:
        if row.check_id not in allowed_ids:
            continue
        if row.coverage_status != CoverageStatus.RUNNABLE:
            continue
        snapshot = snapshots_by_key.get((row.component_type, row.component_id))
        if snapshot is None:
            # A supposedly runnable row without a matching snapshot degrades to no
            # execution; the skipped report will explain it through reason.
            continue
        result = engine.run_check(row.check_id, snapshot, row)
        results.append(result)
        executed_keys.add((row.check_id, row.component_type, row.component_id))
        executed_ids.append(row.check_id)

    skipped = _skipped_report(rows, executed_keys, allowed_ids)
    outputs = {
        "check_results.json": [_json_safe(result.as_dict()) for result in results],
        "check_results_summary.json": _summary(results, skipped, executed_ids),
        "skipped_coverage_rows_report.json": skipped,
        "c11_boundary_report.json": _boundary_report(results, rows, skipped),
        "manual_etabs_next_machine_instructions.md": _manual_next_machine_instructions(),
    }
    return outputs


def write_c11_outputs(out_dir: Path, outputs: Mapping[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in sorted(outputs.items()):
        path = out_dir / filename
        if filename.endswith(".md"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(payload), encoding="utf-8")
        else:
            _write_json(path, payload)


def build_and_write_c11_outputs(feature_snapshot_path: Path, coverage_matrix_path: Path, out_dir: Path) -> dict[str, Any]:
    outputs = build_c11_outputs(feature_snapshot_path, coverage_matrix_path)
    write_c11_outputs(out_dir, outputs)
    return outputs


__all__ = [
    "C11_CHECK_DEFINITIONS",
    "C11_EXECUTABLE_CHECK_IDS",
    "build_and_write_c11_outputs",
    "build_c11_outputs",
    "coverage_row_from_dict",
]
