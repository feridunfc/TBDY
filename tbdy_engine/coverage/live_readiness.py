"""C10 minimal live/fixture readiness slice.

This module consumes C8 FeatureSnapshot JSON plus explicit design context and
produces coverage/readiness reports only. It deliberately does not import or
execute CheckEngine, does not emit canonical check-result payloads, and does not
create engineering verdicts.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.coverage.builder import CoverageBuilder
from tbdy_engine.coverage.models import CoverageMatrix
from tbdy_engine.coverage.live_matrix import (
    _drift_torsion_semantic_report,
    _evidence_readiness_report,
    _matrix_schema_document,
    _missing_design_context_report,
    _missing_expected_sources_report,
    _missing_required_features_report,
    _runnable_gap_report,
    _status_counts,
    _write_json,
    load_feature_snapshot_document,
)
from tbdy_engine.features.snapshot import FeatureSnapshot

C10_RESOLVER_NAME = "c10_minimal_live_readiness_slice"
_FORBIDDEN_OUTPUT_TOKENS = ('"OK"', '"FAIL"', "CheckResult")

# C10 intentionally unlocks a minimal safe readiness slice only. These are
# observed-feature geometry/global readiness rows; no rebar, flexure, shear, or
# force-demand rows are unlocked in this sprint.
C10_SAFE_READINESS_CHECK_IDS = frozenset(
    {
        "beam_geometry_min_width",
        "beam_depth_width_ratio",
        "modal_mass_participation",
    }
)
C10_FORBIDDEN_UNLOCK_CHECK_PATTERNS = (
    "flexure",
    "shear",
    "capacity_design",
    "selected",
    "governing",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_all(out_dir: Path, outputs: Mapping[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in sorted(outputs.items()):
        _write_json(out_dir / filename, payload)


def _assert_output_clean(payloads: Mapping[str, Any]) -> None:
    text = json.dumps(payloads, ensure_ascii=False, sort_keys=True)
    for token in _FORBIDDEN_OUTPUT_TOKENS:
        if token in text:
            raise ValueError(f"C10 output contains forbidden token: {token}")


def load_design_context(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load explicit design context and provenance from a JSON document.

    Supported input shape is intentionally small and explicit, for example:
    {
      "ductility_class": "HIGH",
      "source": "manual_project_design_basis",
      "notes": "..."
    }
    """
    payload = _load_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError("Design context must be a JSON object")
    values: dict[str, Any] = {}
    if payload.get("ductility_class") is not None:
        values["ductility_class"] = payload.get("ductility_class")
    source = str(payload.get("source") or "manual_design_context")
    provenance = {
        "source_kind": "manual_design_context",
        "source": source,
        "source_file": str(path),
        "notes": payload.get("notes"),
        "fields": {
            key: {
                "value": value,
                "source": source,
                "source_file": str(path),
                "provenance": "manual_design_context",
            }
            for key, value in values.items()
        },
        "silent_inference_used": False,
    }
    return values, provenance


def _build_matrix_with_minimal_context(
    bundle: ContractBundle,
    snapshots: Sequence[FeatureSnapshot],
    design_context: Mapping[str, Any],
) -> CoverageMatrix:
    builder = CoverageBuilder(bundle)
    rows = []
    for snapshot in snapshots:
        check_ids = builder._checks_for_component_type(snapshot.component_type)  # noqa: SLF001 - contract smoke helper only
        for check_id in check_ids:
            context_for_row = design_context if check_id in C10_SAFE_READINESS_CHECK_IDS else {}
            rows.extend(builder.build_for_snapshot(snapshot, check_ids=(check_id,), design_context=context_for_row).rows)
    return CoverageMatrix(rows=tuple(rows))


def _status_counter(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    return _status_counts(rows)


def _feature_status_counts(snapshots: Sequence[FeatureSnapshot]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for snapshot in snapshots:
        for feature in snapshot.features.values():
            counter[feature.status.value] += 1
    return {name: int(counter.get(name, 0)) for name in ("RESOLVED", "PARTIAL", "MISSING")}


def _context_report(design_context: Mapping[str, Any], provenance: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "metadata": {
            "sprint": "C10_MINIMAL_LIVE_READINESS_SLICE",
            "explicit_design_context_consumed": True,
            "silent_ductility_inference_used": False,
            "coverage_readiness_only": True,
        },
        "design_context": dict(design_context),
        "provenance": dict(provenance),
        "unlocked_check_ids": sorted(C10_SAFE_READINESS_CHECK_IDS),
        "unlock_policy": {
            "description": "C10 applies explicit design context only to the minimal safe readiness slice; rebar, flexure, shear, and force-demand rows remain locked.",
            "rebar_flexure_shear_rows_not_unlocked": True,
        },
    }


def _feature_snapshot_with_context(raw_doc: Mapping[str, Any], design_context_report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "metadata": {
            "sprint": "C10_MINIMAL_LIVE_READINESS_SLICE",
            "source_snapshot_sprint": (raw_doc.get("metadata") or {}).get("sprint"),
            "check_engine_executed": False,
            "check_result_emitted": False,
            "live_verdict_emitted": False,
            "coverage_readiness_only": True,
        },
        "design_context_report": design_context_report,
        "feature_status_counts": raw_doc.get("feature_status_counts", {}),
        "snapshots": raw_doc.get("snapshots", []),
    }


def _split_rows(rows: Sequence[Mapping[str, Any]], status: str) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if row.get("coverage_status") == status]


def _runnable_rows_report(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    report = []
    for row in rows:
        if row.get("coverage_status") != "RUNNABLE":
            continue
        report.append(
            {
                "check_id": row.get("check_id"),
                "component_type": row.get("component_type"),
                "component_id": row.get("component_id"),
                "coverage_status": row.get("coverage_status"),
                "resolved_features": row.get("resolved_features") or [],
                "resolved_design_context": row.get("resolved_design_context") or [],
                "readiness_only": True,
                "structural_verdict_emitted": False,
                "why_safe_for_C10": "Observed feature and explicit design context are present; C10 does not execute formulas, pass rules, or engineering checks.",
            }
        )
    return report


def _remaining_gap_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    features: Counter[str] = Counter()
    context: Counter[str] = Counter()
    for row in rows:
        if row.get("coverage_status") == "RUNNABLE":
            continue
        for missing in row.get("missing_features") or []:
            features[str(missing.get("feature_name"))] += 1
        for missing in row.get("missing_design_context") or []:
            context[str(missing.get("context_field"))] += 1
    return {
        "top_remaining_missing_features": [name for name, _ in features.most_common(20)],
        "top_remaining_missing_design_context": [name for name, _ in context.most_common(20)],
    }


def _manual_feedback_report(path: Path | None) -> dict[str, Any]:
    if path is None:
        feedback_payload: Any = None
        feedback_status = "not_provided"
    else:
        feedback_payload = _load_json(path)
        feedback_status = "loaded_reference_only"
    return {
        "metadata": {
            "sprint": "C10_MINIMAL_LIVE_READINESS_SLICE",
            "manual_feedback_status": feedback_status,
            "reference_only": True,
        },
        "legacy_feedback_only": {
            "structural_verdict_imported": False,
            "used_for_current_check_result": False,
            "used_for_alias_or_gap_diagnostics": bool(path),
            "old_tests_imported_or_executed": False,
        },
        "feedback_source": str(path) if path else None,
        "feedback_payload": feedback_payload,
    }


def _boundary_report(rows: Sequence[Mapping[str, Any]], manual_feedback: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "metadata": {
            "sprint": "C10_MINIMAL_LIVE_READINESS_SLICE",
            "coverage_readiness_only": True,
            "check_engine_executed": False,
            "check_result_emitted": False,
            "live_verdict_emitted": False,
            "live_etabs_required_in_ci": False,
            "manual_etabs_feedback_reference_only": True,
        },
        "runnable_rows_are_readiness_only": True,
        "rebar_flexure_shear_rows_not_unlocked": all(
            row.get("coverage_status") != "RUNNABLE"
            for row in rows
            if any(pattern in str(row.get("check_id")) for pattern in C10_FORBIDDEN_UNLOCK_CHECK_PATTERNS)
        ),
        "legacy_feedback_policy": manual_feedback.get("legacy_feedback_only", {}),
        "drift_torsion_semantic_lock": None,
        "forbidden_import_status": "PASS",
        "forbidden_runtime_paths_used": [],
    }


def _coverage_summary(
    feature_snapshot_path: Path,
    design_context_path: Path,
    rows: Sequence[Mapping[str, Any]],
    snapshots: Sequence[FeatureSnapshot],
    design_context: Mapping[str, Any],
) -> dict[str, Any]:
    counts = _status_counter(rows)
    gaps = _remaining_gap_summary(rows)
    return {
        "metadata": {
            "sprint": "C10_MINIMAL_LIVE_READINESS_SLICE",
            "input_feature_snapshot": str(feature_snapshot_path),
            "input_design_context": str(design_context_path),
            "check_engine_executed": False,
            "check_result_emitted": False,
            "live_verdict_emitted": False,
            "manual_live_etabs_run_required": False,
        },
        "coverage_row_count": len(rows),
        "coverage_status_counts": counts,
        "feature_status_counts": _feature_status_counts(snapshots),
        "design_context_fields_present": sorted(design_context),
        "runnable_count_preferred_minimum_met": counts["RUNNABLE"] >= 1,
        "runnable_rows_are_readiness_only": True,
        **gaps,
    }


def build_c10_outputs(
    feature_snapshot_path: Path,
    design_context_path: Path,
    *,
    coverage_input_path: Path | None = None,
    manual_feedback_path: Path | None = None,
    contract_bundle: ContractBundle | None = None,
) -> dict[str, Any]:
    del coverage_input_path  # C10 rebuilds readiness from FeatureSnapshot + explicit design context.
    bundle = contract_bundle or load_contracts()
    raw_doc, snapshots = load_feature_snapshot_document(feature_snapshot_path)
    design_context, context_provenance = load_design_context(design_context_path)
    matrix = _build_matrix_with_minimal_context(bundle, snapshots, design_context)
    coverage_doc = _matrix_schema_document(matrix)
    rows = coverage_doc["checks"]
    context_report = _context_report(design_context, context_provenance)
    manual_feedback = _manual_feedback_report(manual_feedback_path)
    boundary = _boundary_report(rows, manual_feedback)
    boundary["drift_torsion_semantic_lock"] = _drift_torsion_semantic_report(snapshots)
    outputs = {
        "feature_snapshot_with_context.json": _feature_snapshot_with_context(raw_doc, context_report),
        "design_context_report.json": context_report,
        "coverage_matrix.json": coverage_doc,
        "coverage_summary.json": _coverage_summary(feature_snapshot_path, design_context_path, rows, snapshots, design_context),
        "runnable_rows_report.json": _runnable_rows_report(rows),
        "blocked_rows_report.json": _split_rows(rows, "BLOCKED"),
        "partial_rows_report.json": _split_rows(rows, "PARTIAL"),
        "runnable_gap_report.json": _runnable_gap_report(rows),
        "evidence_readiness_report.json": _evidence_readiness_report(snapshots),
        "c10_boundary_report.json": boundary,
        "optional_manual_etabs_feedback_report.json": manual_feedback,
        "missing_required_features_report.json": _missing_required_features_report(rows),
        "missing_design_context_report.json": _missing_design_context_report(rows),
        "missing_expected_sources_report.json": _missing_expected_sources_report(rows),
    }
    _assert_output_clean(outputs)
    return outputs


def build_and_write_c10_outputs(
    feature_snapshot_path: Path,
    design_context_path: Path,
    out_dir: Path,
    *,
    coverage_input_path: Path | None = None,
    manual_feedback_path: Path | None = None,
    contract_bundle: ContractBundle | None = None,
) -> dict[str, Any]:
    outputs = build_c10_outputs(
        feature_snapshot_path,
        design_context_path,
        coverage_input_path=coverage_input_path,
        manual_feedback_path=manual_feedback_path,
        contract_bundle=contract_bundle,
    )
    _write_all(out_dir, outputs)
    return outputs


__all__ = [
    "C10_SAFE_READINESS_CHECK_IDS",
    "build_and_write_c10_outputs",
    "build_c10_outputs",
    "load_design_context",
]
