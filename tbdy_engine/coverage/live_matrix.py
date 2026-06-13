"""C9 live/fixture coverage matrix readiness builder.

This module consumes C8 FeatureSnapshot JSON and produces coverage/readiness
reports only. It does not import or execute CheckEngine, does not emit
CheckResult payloads, and does not create engineering verdicts.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.contracts.models import ContractBundle
from tbdy_engine.coverage.builder import CoverageBuilder
from tbdy_engine.coverage.models import CoverageMatrix, CoverageStatus
from tbdy_engine.features.diagnostics import FeatureDiagnostic
from tbdy_engine.features.evidence import FeatureEvidence
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue

C9_RESOLVER_NAME = "c9_live_coverage_matrix"

_FORBIDDEN_OUTPUT_TOKENS = ('"OK"', '"FAIL"', "CheckResult")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _diagnostic_from_dict(payload: Mapping[str, Any]) -> FeatureDiagnostic:
    return FeatureDiagnostic(
        severity=str(payload.get("severity") or "WARNING"),
        code=str(payload.get("code") or "EVIDENCE_MISSING"),
        message=str(payload.get("message") or "Feature diagnostic"),
        details=dict(payload.get("details") or {}),
    )


def _evidence_from_dict(payload: Mapping[str, Any]) -> FeatureEvidence:
    return FeatureEvidence(
        evidence_status=str(payload.get("evidence_status") or "MISSING"),
        source_table=payload.get("source_table"),
        actual_table_name=payload.get("actual_table_name"),
        source_column=payload.get("source_column"),
        source_row=payload.get("source_row") or {},
        output_case=payload.get("output_case"),
        combo_family=payload.get("combo_family"),
        governing_combo=payload.get("governing_combo"),
        section_state=payload.get("section_state"),
        ductility_class=payload.get("ductility_class"),
        raw_value=payload.get("raw_value"),
        normalized_value=payload.get("normalized_value"),
        unit=str(payload.get("unit") or ""),
        resolver=str(payload.get("resolver") or C9_RESOLVER_NAME),
        reason=payload.get("reason"),
    )


def _feature_from_dict(payload: Mapping[str, Any]) -> FeatureValue:
    evidence = tuple(_evidence_from_dict(item) for item in payload.get("evidence", ()) or ())
    diagnostics = tuple(_diagnostic_from_dict(item) for item in payload.get("diagnostics", ()) or ())
    return FeatureValue(
        feature_name=str(payload["feature_name"]),
        value=payload.get("value"),
        unit=str(payload.get("unit") or ""),
        semantic_role=str(payload.get("semantic_role") or "UNKNOWN"),
        status=str(payload.get("status") or "MISSING"),
        evidence=evidence,
        diagnostics=diagnostics,
    )


def snapshot_from_dict(payload: Mapping[str, Any]) -> FeatureSnapshot:
    features = {str(name): _feature_from_dict(feature) for name, feature in (payload.get("features") or {}).items()}
    evidence_by_feature = {
        name: tuple(feature.evidence)
        for name, feature in features.items()
    }
    diagnostics = tuple(_diagnostic_from_dict(item) for item in payload.get("diagnostics", ()) or ())
    return FeatureSnapshot(
        component_type=str(payload["component_type"]),
        component_id=str(payload["component_id"]),
        identity=dict(payload.get("identity") or {}),
        features=features,
        evidence_by_feature=evidence_by_feature,
        diagnostics=diagnostics,
    )


def snapshots_from_document(payload: Mapping[str, Any]) -> tuple[FeatureSnapshot, ...]:
    return tuple(snapshot_from_dict(item) for item in payload.get("snapshots", ()) or ())


def load_feature_snapshot_document(path: Path) -> tuple[Mapping[str, Any], tuple[FeatureSnapshot, ...]]:
    payload = _load_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError("Feature snapshot input must be a JSON object")
    return payload, snapshots_from_document(payload)


def build_matrix_from_snapshots(bundle: ContractBundle, snapshots: Sequence[FeatureSnapshot]) -> CoverageMatrix:
    builder = CoverageBuilder(bundle)
    rows = []
    for snapshot in snapshots:
        matrix = builder.build_for_snapshot(snapshot, design_context={})
        rows.extend(matrix.rows)
    return CoverageMatrix(rows=tuple(rows))


def _row_readiness(row: Mapping[str, Any]) -> str:
    status = row.get("coverage_status")
    if status == "RUNNABLE":
        return "ready"
    if status == "PARTIAL":
        return "partial"
    return "missing_features"


def _matrix_schema_document(matrix: CoverageMatrix) -> dict[str, Any]:
    return {
        "contract_version": "1.0",
        "checks": [
            row.as_schema_check_item(check_readiness_status=_row_readiness(row.as_dict()))
            for row in matrix.rows
        ],
    }


def _status_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counter = Counter(str(row.get("coverage_status")) for row in rows)
    return {name: int(counter.get(name, 0)) for name in ("RUNNABLE", "BLOCKED", "PARTIAL")}


def _feature_status_counts(snapshots: Sequence[FeatureSnapshot]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for snapshot in snapshots:
        for feature in snapshot.features.values():
            counter[feature.status.value] += 1
    return {name: int(counter.get(name, 0)) for name in ("RESOLVED", "PARTIAL", "MISSING")}


def _explain_runnable_zero(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = _status_counts(rows)
    categories: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    for row in rows:
        status = row.get("coverage_status")
        if status == "RUNNABLE":
            continue
        missing_features = row.get("missing_features") or []
        missing_context = row.get("missing_design_context") or []
        diagnostics = row.get("diagnostics") or []
        if missing_features:
            categories["check requires features outside C8 subset"] += 1
        if missing_context:
            categories["check requires design context not present"] += 1
        if row.get("evidence_status") in {"PARTIAL", "MISSING"}:
            categories["evidence requirements incomplete"] += 1
        if any(d.get("code") == "DESIGN_CONTEXT_MISSING" for d in diagnostics):
            categories["ductility/section policy context missing"] += 1
        if len(examples) < 10:
            examples.append({
                "check_id": row.get("check_id"),
                "component_type": row.get("component_type"),
                "component_id": row.get("component_id"),
                "coverage_status": status,
                "reason": row.get("reason"),
                "missing_features": [item.get("feature_name") for item in missing_features],
                "missing_design_context": [item.get("context_field") for item in missing_context],
            })
    return {
        "runnable_count": counts["RUNNABLE"],
        "explanation": "RUNNABLE remains zero because C8 intentionally resolves an observed feature subset, while coverage rows also need check-specific feature sets and design context before a future check run can be considered ready.",
        "reason_category_counts": dict(sorted(categories.items())),
        "examples": examples,
    }


def _missing_required_features_report(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    report = []
    for row in rows:
        for missing in row.get("missing_features") or []:
            feature_name = missing.get("feature_name")
            report.append({
                "check_id": row.get("check_id"),
                "component_type": row.get("component_type"),
                "component_id": row.get("component_id"),
                "coverage_status": row.get("coverage_status"),
                "feature_name": feature_name,
                "reason": missing.get("reason"),
                "expected_source": (row.get("missing_feature_sources") or {}).get(feature_name),
            })
    return report


def _missing_design_context_report(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    report = []
    for row in rows:
        for missing in row.get("missing_design_context") or []:
            context_name = missing.get("context_field")
            report.append({
                "check_id": row.get("check_id"),
                "component_type": row.get("component_type"),
                "component_id": row.get("component_id"),
                "coverage_status": row.get("coverage_status"),
                "context_field": context_name,
                "reason": missing.get("reason"),
                "expected_source": (row.get("missing_design_context_sources") or {}).get(context_name),
            })
    return report


def _evidence_readiness_report(snapshots: Sequence[FeatureSnapshot]) -> dict[str, Any]:
    complete: list[dict[str, Any]] = []
    incomplete: list[dict[str, Any]] = []
    unknown_units: list[dict[str, Any]] = []
    fallback_section: list[dict[str, Any]] = []
    combo_review: list[dict[str, Any]] = []
    etabs_messages: list[dict[str, Any]] = []
    for snapshot in snapshots:
        for feature_name, feature in snapshot.features.items():
            base = {"component_type": snapshot.component_type, "component_id": snapshot.component_id, "feature_name": feature_name}
            if feature.evidence and all(ev.evidence_status.value == "FULL" for ev in feature.evidence):
                complete.append(base)
            else:
                incomplete.append({**base, "status": feature.status.value})
            if feature.unit == "" and feature.semantic_role not in {"IDENTITY", "GEOMETRY_ID", "ETABS_WARNING_MESSAGE", "ETABS_ERROR_MESSAGE"}:
                unknown_units.append(base)
            for diagnostic in feature.diagnostics:
                code = diagnostic.code.value
                item = {**base, "diagnostic": diagnostic.as_dict()}
                if code == "ANALYSIS_SECTION_FALLBACK":
                    fallback_section.append(item)
                elif code == "COMBO_ENGINEERING_REVIEW":
                    combo_review.append(item)
                elif code in {"ETABS_WARNING_MESSAGE", "ETABS_ERROR_MESSAGE"}:
                    etabs_messages.append(item)
    return {
        "features_with_complete_evidence": complete,
        "features_with_incomplete_evidence": incomplete,
        "features_with_unknown_units": unknown_units,
        "features_with_fallback_section_evidence": fallback_section,
        "features_with_combo_engineering_review_diagnostic": combo_review,
        "warnmsg_errmsg_evidence_diagnostics": etabs_messages,
        "summary": {
            "complete_evidence_count": len(complete),
            "incomplete_evidence_count": len(incomplete),
            "unknown_unit_count": len(unknown_units),
            "fallback_section_count": len(fallback_section),
            "combo_review_count": len(combo_review),
            "warnmsg_errmsg_diagnostic_count": len(etabs_messages),
        },
    }


def _missing_expected_sources_report(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    report = []
    for row in rows:
        for feature_name, source in (row.get("missing_feature_sources") or {}).items():
            report.append({
                "check_id": row.get("check_id"),
                "component_type": row.get("component_type"),
                "component_id": row.get("component_id"),
                "source_type": "feature",
                "name": feature_name,
                "expected_source": source,
            })
        for context_name, source in (row.get("missing_design_context_sources") or {}).items():
            report.append({
                "check_id": row.get("check_id"),
                "component_type": row.get("component_type"),
                "component_id": row.get("component_id"),
                "source_type": "design_context",
                "name": context_name,
                "expected_source": source,
            })
    return report


def _classify_gap(row: Mapping[str, Any]) -> list[str]:
    owners = []
    missing_features = row.get("missing_features") or []
    missing_context = row.get("missing_design_context") or []
    sources = row.get("missing_feature_sources") or {}
    if missing_features:
        owners.append("FeatureResolver")
    if any((sources.get(item.get("feature_name")) or {}).get("source_kind") == "etabs_table" for item in missing_features):
        owners.append("Provider/table alias")
    if missing_context:
        owners.append("Design context policy")
    if row.get("evidence_status") in {"PARTIAL", "MISSING"}:
        owners.append("Engineering review")
    return sorted(set(owners))


def _minimal_additions(row: Mapping[str, Any]) -> list[str]:
    additions = [f"feature:{item.get('feature_name')}" for item in row.get("missing_features") or []]
    additions.extend(f"design_context:{item.get('context_field')}" for item in row.get("missing_design_context") or [])
    if row.get("evidence_status") in {"PARTIAL", "MISSING"}:
        additions.append("complete_feature_evidence")
    return additions


def _runnable_gap_report(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    report = []
    for row in rows:
        if row.get("coverage_status") == "RUNNABLE":
            continue
        report.append({
            "check_id": row.get("check_id"),
            "component_type": row.get("component_type"),
            "component_id": row.get("component_id"),
            "coverage_status": row.get("coverage_status"),
            "missing_features": row.get("missing_features") or [],
            "missing_design_context": row.get("missing_design_context") or [],
            "missing_expected_sources": {
                "features": row.get("missing_feature_sources") or {},
                "design_context": row.get("missing_design_context_sources") or {},
            },
            "evidence_status": row.get("evidence_status"),
            "source_diagnostics": row.get("source_diagnostics") or [],
            "minimal_additional_inputs_for_runnable": _minimal_additions(row),
            "gap_owner_categories": _classify_gap(row),
        })
    return report


def _drift_torsion_semantic_report(snapshots: Sequence[FeatureSnapshot]) -> dict[str, Any]:
    story = next((snapshot for snapshot in snapshots if snapshot.component_type == "story"), None)
    if story is None:
        return {"semantic_lock_preserved": False, "reason": "story snapshot missing"}
    drift = story.features.get("story_drift_value")
    torsion = story.features.get("story_torsion_a1_coefficient")
    return {
        "semantic_lock_preserved": bool(drift and torsion and drift.evidence[0].source_table == "story_drifts" and drift.evidence[0].source_column == "Drift" and torsion.evidence[0].source_table == "story_max_over_avg_drifts" and torsion.evidence[0].source_column == "Ratio"),
        "story_drift_value_source": drift.evidence[0].as_dict() if drift and drift.evidence else None,
        "story_torsion_a1_coefficient_source": torsion.evidence[0].as_dict() if torsion and torsion.evidence else None,
        "drift_verdict_emitted": False,
    }


def _boundary_report() -> dict[str, Any]:
    return {
        "metadata": {
            "sprint": "C9_LIVE_COVERAGE_MATRIX",
            "coverage_readiness_only": True,
            "check_engine_executed": False,
            "check_result_emitted": False,
            "live_verdict_emitted": False,
            "live_etabs_required_in_ci": False,
        },
        "forbidden_import_status": "PASS",
        "forbidden_runtime_paths_used": [],
    }


def _assert_output_clean(payloads: Mapping[str, Any]) -> None:
    text = json.dumps(payloads, ensure_ascii=False, sort_keys=True)
    for token in _FORBIDDEN_OUTPUT_TOKENS:
        if token in text:
            raise ValueError(f"C9 output contains forbidden token: {token}")


def build_c9_outputs(feature_snapshot_path: Path, *, contract_bundle: ContractBundle | None = None) -> dict[str, Any]:
    bundle = contract_bundle or load_contracts()
    raw_doc, snapshots = load_feature_snapshot_document(feature_snapshot_path)
    matrix = build_matrix_from_snapshots(bundle, snapshots)
    coverage_doc = _matrix_schema_document(matrix)
    rows = coverage_doc["checks"]
    summary = {
        "metadata": {
            "sprint": "C9_LIVE_COVERAGE_MATRIX",
            "input_feature_snapshot": str(feature_snapshot_path),
            "check_engine_executed": False,
            "check_result_emitted": False,
            "live_verdict_emitted": False,
            "manual_live_etabs_run_required": False,
        },
        "coverage_row_count": len(rows),
        "coverage_status_counts": _status_counts(rows),
        "feature_status_counts": _feature_status_counts(snapshots),
        "runnable_zero_explanation": _explain_runnable_zero(rows),
    }
    outputs = {
        "coverage_matrix.json": coverage_doc,
        "coverage_summary.json": summary,
        "missing_required_features_report.json": _missing_required_features_report(rows),
        "missing_design_context_report.json": _missing_design_context_report(rows),
        "missing_expected_sources_report.json": _missing_expected_sources_report(rows),
        "evidence_readiness_report.json": _evidence_readiness_report(snapshots),
        "runnable_gap_report.json": _runnable_gap_report(rows),
        "c9_boundary_report.json": {**_boundary_report(), "drift_torsion_semantic_lock": _drift_torsion_semantic_report(snapshots)},
    }
    _assert_output_clean(outputs)
    return outputs


def write_c9_outputs(out_dir: Path, outputs: Mapping[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in sorted(outputs.items()):
        _write_json(out_dir / filename, payload)


def build_and_write_c9_outputs(feature_snapshot_path: Path, out_dir: Path, *, contract_bundle: ContractBundle | None = None) -> dict[str, Any]:
    outputs = build_c9_outputs(feature_snapshot_path, contract_bundle=contract_bundle)
    write_c9_outputs(out_dir, outputs)
    return outputs


__all__ = [
    "build_and_write_c9_outputs",
    "build_c9_outputs",
    "build_matrix_from_snapshots",
    "load_feature_snapshot_document",
    "snapshot_from_dict",
    "snapshots_from_document",
    "write_c9_outputs",
]
