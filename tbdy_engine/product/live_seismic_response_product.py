"""Pure VS-3 seismic product projection plus bounded live ETABS composition."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from tbdy_engine.etabs.safety import EtabsSafetyError, read_session_identity
from tbdy_engine.features.etabs_com_attach import EtabsAttachFailure, EtabsAttachResult, attach_to_running_etabs
from tbdy_engine.findings import Finding
from tbdy_engine.integration.live_beam_geometry_f0 import read_observed_etabs_model_path
from tbdy_engine.integration.live_seismic_response_f0 import (
    LiveSeismicEvidenceConflictError,
    LiveSeismicPackRun,
    SeismicCaptureArtifact,
    capture_seismic_response,
    run_live_seismic_response_f0_pack,
    write_seismic_capture,
)
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.regulatory.seismic_response import A1_RULE_ID, MODAL_RULE_ID

PRODUCT_CONTRACT = "VS3_LIVE_SEISMIC_RESPONSE_PRODUCT_V1"
PRODUCT_FILENAME = "live_seismic_response_product.json"
CAPTURE_FILENAME = "seismic_response_capture.json"
STORY_DRIFT_NOT_EVALUATED_REASON = "TBDY_4_9_1_ANALYSIS_BASIS_CONTEXT_NOT_CLOSED"
BASE_REACTIONS_NOT_EVALUATED_REASON = "TBDY_4_8_4_SCALING_DEPENDENCIES_NOT_CLOSED"


@dataclass(frozen=True, slots=True)
class LiveSeismicResponseProductResult:
    output_path: Path
    capture_path: Path
    payload: Mapping[str, Any]
    modal_factual_row_count: int
    story_drift_factual_row_count: int
    story_max_over_avg_factual_row_count: int
    base_reaction_factual_row_count: int
    a1_story_direction_count: int
    rule_instance_count: int
    check_result_count: int
    finding_count: int


def _finding_payload(finding: Finding) -> dict[str, object]:
    return {
        "finding_id": finding.finding_id,
        "source_kind": finding.source_kind.value,
        "source_ref": finding.source_ref,
        "source_status": finding.source_status.value,
        "scope_ref": finding.scope_ref,
        "direction": finding.direction,
        "rule_instance_ref": None if finding.rule_instance_ref is None else finding.rule_instance_ref.value,
        "code_refs": list(finding.code_refs),
        "regulatory_quantity_keys": [item.value for item in finding.regulatory_quantity_keys],
        "evidence_refs": list(finding.evidence_refs),
        "diagnostic_refs": list(finding.diagnostic_refs),
        "messages": list(finding.messages),
        "provenance_refs": list(finding.provenance_refs),
    }


def _result_inventory(run: LiveSeismicPackRun) -> list[dict[str, object]]:
    results = {item.instance_id: item.result for item in run.store.formal_results}
    closures = {item.compiled_record_ref: item for item in run.assessment.closure_outcomes}
    compiled = {item.instance_id: item for item in run.program.plan.compiled_closure_inventory}
    rows: list[dict[str, object]] = []
    for instance in sorted(run.program.plan.compiled_rule_instances, key=lambda item: item.value):
        domain = (
            "modal_effective_mass"
            if instance.rule_id == MODAL_RULE_ID
            else "torsional_irregularity_a1"
            if instance.rule_id == A1_RULE_ID
            else "UNKNOWN"
        )
        rows.append(
            {
                "domain": domain,
                "rule_id": instance.rule_id.value,
                "rule_instance_id": instance.value,
                "grain": instance.grain.value,
                "scope_ref": instance.scope_ref,
                "direction": instance.direction,
                "applicability": compiled[instance].applicability.value,
                "closure_status": closures[instance].execution_status.value,
                "check_result": None if instance not in results else results[instance].as_dict(),
            }
        )
    return rows


def _a1_capture_rows(capture: SeismicCaptureArtifact) -> list[dict[str, object]]:
    a1 = capture.payload.get("a1")
    by_direction = a1.get("by_direction") if isinstance(a1, Mapping) else None
    rows: list[dict[str, object]] = []
    if isinstance(by_direction, Mapping):
        for direction in ("X", "Y"):
            item = by_direction.get(direction)
            if isinstance(item, Mapping):
                rows.extend(dict(row) for row in item.get("rows") or () if isinstance(row, Mapping))
    return rows


def _capture_rows(capture: SeismicCaptureArtifact, domain: str) -> list[dict[str, object]]:
    item = capture.payload.get(domain)
    if not isinstance(item, Mapping):
        return []
    return [dict(row) for row in item.get("rows") or () if isinstance(row, Mapping)]


def build_seismic_product_payload(*, run: LiveSeismicPackRun) -> dict[str, Any]:
    capture = run.capture
    modal_rows = _capture_rows(capture, "modal")
    drift_rows = _capture_rows(capture, "story_drift")
    a1_rows = _a1_capture_rows(capture)
    base_rows = _capture_rows(capture, "base_reactions")
    results = _result_inventory(run)
    findings = [_finding_payload(item) for item in run.findings]
    modal_instances = [item for item in results if item["domain"] == "modal_effective_mass"]
    a1_instances = [item for item in results if item["domain"] == "torsional_irregularity_a1"]
    provenance_refs = sorted(
        {
            capture.epoch.epoch_id,
            capture.epoch.model_fingerprint,
            capture.epoch.source_fingerprint or "",
            *(ref for authority in run.authorities for ref in authority.provenance_refs),
        }
        - {""}
    )
    return {
        "contract": PRODUCT_CONTRACT,
        "model_fingerprint": capture.epoch.model_fingerprint,
        "capture_epoch": {
            "epoch_id": capture.epoch.epoch_id,
            "origin": capture.epoch.origin.value,
            "model_fingerprint": capture.epoch.model_fingerprint,
            "source_fingerprint": capture.epoch.source_fingerprint,
        },
        "regulatory_context": {
            "modal_4812_applies": run.modal_4812_applies,
            "modal_case_basis_verified": run.modal_case_basis_verified,
            "a1_eccentricity_basis": run.a1_eccentricity_basis,
            "source_kind": "EXPLICIT_REVIEWED_CALLER_INPUT",
        },
        "regulatory_authority": "F0_ONLY",
        "registry_version": run.program.plan.registry_version,
        "plan_identity": run.program.plan.plan_identity,
        "structural_assessment_status": run.assessment.structural_status.value,
        "full_tbdy_compliance_status": "NOT_EVALUATED",
        "rule_instance_count": len(run.program.plan.compiled_rule_instances),
        "check_result_count": len(run.store.formal_results),
        "finding_count": len(findings),
        "capture": {
            "selectors": to_jsonable(capture.payload.get("capture_selectors") or {}),
            "source_tables": to_jsonable(capture.payload.get("source_tables") or []),
            "truncation_applied": capture.payload.get("truncation_applied"),
            "unit_provenance": to_jsonable(capture.payload.get("unit_provenance") or {}),
            "diagnostics": to_jsonable(capture.payload.get("capture_diagnostics") or []),
        },
        "domains": {
            "modal_effective_mass": {
                "factual_support_status": "SUPPORTED" if modal_rows else "NO_DATA",
                "regulatory_support_status": "SUPPORTED",
                "formal_scope": "95_PERCENT_EFFECTIVE_MASS_SUBCONDITION_ONLY",
                "gt_3_percent_mode_inclusion": "NOT_EVALUATED",
                "factual_row_count": len(modal_rows),
                "rule_instance_count": len(modal_instances),
                "check_result_count": sum(item["check_result"] is not None for item in modal_instances),
                "factual_rows": modal_rows,
            },
            "torsional_irregularity_a1": {
                "factual_support_status": "SUPPORTED" if a1_rows else "NO_DATA",
                "regulatory_support_status": "SUPPORTED",
                "factual_row_count": len(a1_rows),
                "rule_instance_count": len(a1_instances),
                "check_result_count": sum(item["check_result"] is not None for item in a1_instances),
                "factual_rows": a1_rows,
            },
            "story_drift": {
                "factual_support_status": "SUPPORTED" if drift_rows else "NO_DATA",
                "regulatory_support_status": "NOT_EVALUATED",
                "reason": STORY_DRIFT_NOT_EVALUATED_REASON,
                "check_result_count": 0,
                "factual_row_count": len(drift_rows),
                "factual_rows": drift_rows,
            },
            "base_reactions": {
                "factual_support_status": "SUPPORTED" if base_rows else "NO_DATA",
                "regulatory_support_status": "NOT_EVALUATED",
                "reason": BASE_REACTIONS_NOT_EVALUATED_REASON,
                "check_result_count": 0,
                "factual_row_count": len(base_rows),
                "factual_rows": base_rows,
            },
        },
        "results": results,
        "findings": findings,
        "provenance_refs": provenance_refs,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            to_jsonable(payload),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def build_live_seismic_response_product(
    *,
    capture: SeismicCaptureArtifact,
    modal_4812_applies: bool | None,
    modal_case_basis_verified: str,
    a1_eccentricity_basis: str,
    output_path: Path,
    capture_path: Path | None = None,
) -> LiveSeismicResponseProductResult:
    run = run_live_seismic_response_f0_pack(
        capture=capture,
        modal_4812_applies=modal_4812_applies,
        modal_case_basis_verified=modal_case_basis_verified,
        a1_eccentricity_basis=a1_eccentricity_basis,
    )
    payload = build_seismic_product_payload(run=run)
    output_path = Path(output_path)
    resolved_capture_path = Path(capture_path) if capture_path is not None else output_path.parent / CAPTURE_FILENAME
    write_seismic_capture(resolved_capture_path, capture)
    _write_json(output_path, payload)
    return LiveSeismicResponseProductResult(
        output_path=output_path,
        capture_path=resolved_capture_path,
        payload=payload,
        modal_factual_row_count=len(_capture_rows(capture, "modal")),
        story_drift_factual_row_count=len(_capture_rows(capture, "story_drift")),
        story_max_over_avg_factual_row_count=len(_a1_capture_rows(capture)),
        base_reaction_factual_row_count=len(_capture_rows(capture, "base_reactions")),
        a1_story_direction_count=sum(
            1 for item in run.program.plan.compiled_rule_instances if item.rule_id == A1_RULE_ID
        ),
        rule_instance_count=len(run.program.plan.compiled_rule_instances),
        check_result_count=len(run.store.formal_results),
        finding_count=len(run.findings),
    )


def run_live_seismic_response_product(
    *,
    output_dir: Path,
    modal_case: str,
    modal_4812_applies: bool | None,
    modal_case_basis_verified: str,
    a1_x_cases: Sequence[str],
    a1_y_cases: Sequence[str],
    a1_eccentricity_basis: str,
    attach_result: EtabsAttachResult | None = None,
) -> LiveSeismicResponseProductResult:
    resolved_attach = attach_result or attach_to_running_etabs()
    if resolved_attach.status != "ATTACHED":
        raise EtabsAttachFailure(resolved_attach)
    if resolved_attach.sap_model is None:
        raise LiveSeismicEvidenceConflictError("ETABS attach succeeded without SapModel")
    database_tables = getattr(resolved_attach.sap_model, "DatabaseTables", None)
    if database_tables is None:
        raise LiveSeismicEvidenceConflictError("attached SapModel has no DatabaseTables factual seam")

    model_path = read_observed_etabs_model_path(resolved_attach.sap_model)
    try:
        identity = read_session_identity(
            resolved_attach.etabs_object,
            resolved_attach.sap_model,
            attach_strategy=resolved_attach.strategy,
        )
    except EtabsSafetyError as exc:
        raise LiveSeismicEvidenceConflictError("ETABS session identity/unit provenance is unavailable") from exc

    capture = capture_seismic_response(
        database_tables=database_tables,
        model_path=model_path,
        modal_case=modal_case,
        a1_x_cases=a1_x_cases,
        a1_y_cases=a1_y_cases,
        unit_provenance=identity.units.as_dict(),
    )
    out_dir = Path(output_dir)
    return build_live_seismic_response_product(
        capture=capture,
        modal_4812_applies=modal_4812_applies,
        modal_case_basis_verified=modal_case_basis_verified,
        a1_eccentricity_basis=a1_eccentricity_basis,
        output_path=out_dir / PRODUCT_FILENAME,
        capture_path=out_dir / CAPTURE_FILENAME,
    )


__all__ = [
    "PRODUCT_CONTRACT",
    "PRODUCT_FILENAME",
    "CAPTURE_FILENAME",
    "STORY_DRIFT_NOT_EVALUATED_REASON",
    "BASE_REACTIONS_NOT_EVALUATED_REASON",
    "LiveSeismicResponseProductResult",
    "build_seismic_product_payload",
    "build_live_seismic_response_product",
    "run_live_seismic_response_product",
]
