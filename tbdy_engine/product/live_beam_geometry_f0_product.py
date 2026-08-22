"""Deterministic pure product artifact for the VS-1 live beam F0 cutover."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from tbdy_engine.features.etabs_com_attach import (
    EtabsAttachFailure,
    EtabsAttachResult,
    attach_to_running_etabs,
)
from tbdy_engine.features.live_etabs_geometry_probe import (
    create_live_etabs_geometry_provider,
    probe_geometry_feature_snapshots,
)
from tbdy_engine.findings import Finding
from tbdy_engine.integration.live_beam_geometry_f0 import (
    LiveBeamSliceRun,
    VS1LiveBeamIntegrationError,
    build_live_capture_epoch,
    load_live_beam_capture_artifact,
    read_observed_etabs_model_path,
    run_live_beam_f0_slice,
)
from tbdy_engine.json_safe import to_jsonable

PRODUCT_CONTRACT = "VS1_LIVE_BEAM_GEOMETRY_F0_PRODUCT_V1"
PRODUCT_FILENAME = "live_beam_geometry_f0_product.json"
CAPTURE_DIRNAME = "live_beam_geometry_capture"


@dataclass(frozen=True, slots=True)
class LiveBeamGeometryF0ProductResult:
    output_path: Path
    payload: dict[str, Any]
    beam_count: int
    finding_count: int


def _finding_payload(finding: Finding) -> dict[str, object]:
    return {
        "finding_id": finding.finding_id,
        "source_kind": finding.source_kind.value,
        "source_ref": finding.source_ref,
        "source_status": finding.source_status.value,
        "scope_ref": finding.scope_ref,
        "direction": finding.direction,
        "rule_instance_ref": (
            None if finding.rule_instance_ref is None else finding.rule_instance_ref.value
        ),
        "code_refs": list(finding.code_refs),
        "regulatory_quantity_keys": [
            item.value for item in finding.regulatory_quantity_keys
        ],
        "evidence_refs": list(finding.evidence_refs),
        "diagnostic_refs": list(finding.diagnostic_refs),
        "messages": list(finding.messages),
        "provenance_refs": list(finding.provenance_refs),
    }


def _beam_payload(run: LiveBeamSliceRun) -> dict[str, object]:
    result_by_instance = {
        record.instance_id: record.result for record in run.store.formal_results
    }
    closure_by_instance = {
        outcome.compiled_record_ref: outcome
        for outcome in run.assessment.closure_outcomes
    }
    instances = tuple(
        sorted(run.program.plan.compiled_rule_instances, key=lambda item: item.value)
    )

    closure_inventory = [
        {
            "rule_id": instance.rule_id.value,
            "rule_instance_id": instance.value,
            "closure_status": closure_by_instance[instance].execution_status.value,
        }
        for instance in instances
    ]
    check_results = [
        result_by_instance[instance].as_dict()
        for instance in instances
        if instance in result_by_instance
    ]
    findings = [_finding_payload(item) for item in run.findings]

    provenance_refs = tuple(
        sorted(
            {
                ref
                for authority in run.authorities
                for ref in authority.provenance_refs
            }
        )
    )
    evidence_refs = tuple(
        ref for ref in provenance_refs if ref.startswith("evidence:")
    )
    assessment = run.assessment
    return {
        "component_type": run.snapshot.component_type,
        "component_id": run.snapshot.component_id,
        "story": run.snapshot.identity.get("story"),
        "section": run.snapshot.identity.get("section"),
        "epoch_ref": f"epoch:{run.epoch.epoch_id}",
        "plan_identity": run.program.plan.plan_identity,
        "rule_instance_count": len(instances),
        "check_result_count": len(check_results),
        "closure_inventory": closure_inventory,
        "check_results": check_results,
        "evidence_refs": list(evidence_refs),
        "provenance_refs": list(provenance_refs),
        "assessment": {
            "structural_status": assessment.structural_status.value,
            "full_tbdy_compliance_status": assessment.full_tbdy_compliance_status,
            "incomplete_mandatory_instances": [
                item.value for item in assessment.incomplete_mandatory_instances
            ],
            "diagnostics": list(assessment.diagnostics),
        },
        "finding_count": len(findings),
        "findings": findings,
    }


def _product_payload(*, epoch, runs: tuple[LiveBeamSliceRun, ...]) -> dict[str, Any]:
    beam_payloads = tuple(
        _beam_payload(run)
        for run in sorted(runs, key=lambda item: item.snapshot.component_id)
    )
    if any(
        run.assessment.full_tbdy_compliance_status != "NOT_EVALUATED"
        for run in runs
    ):
        raise VS1LiveBeamIntegrationError(
            "VS-1 may not emit a full-TBDY compliance verdict"
        )
    all_findings = tuple(
        sorted(
            (finding for run in runs for finding in run.findings),
            key=lambda item: item.finding_id,
        )
    )
    return {
        "contract": PRODUCT_CONTRACT,
        "origin": epoch.origin.value,
        "epoch_id": epoch.epoch_id,
        "epoch_ref": f"epoch:{epoch.epoch_id}",
        "model_fingerprint": epoch.model_fingerprint,
        "source_fingerprint": epoch.source_fingerprint,
        "regulatory_authority": "F0_ONLY",
        "legacy_minimal_check_engine_executed": False,
        "legacy_yaml_authority_executed": False,
        "full_tbdy_compliance_status": "NOT_EVALUATED",
        "beam_count": len(beam_payloads),
        "selected_rule_instance_count": sum(
            int(item["rule_instance_count"]) for item in beam_payloads
        ),
        "check_result_count": sum(
            int(item["check_result_count"]) for item in beam_payloads
        ),
        "finding_count": len(all_findings),
        "beams": list(beam_payloads),
        "findings": [_finding_payload(item) for item in all_findings],
    }


def _write_product(path: Path, payload: dict[str, Any]) -> None:
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


def build_live_beam_geometry_f0_product_from_capture(
    *,
    model_path: object,
    feature_snapshot_path: Path,
    output_path: Path,
) -> LiveBeamGeometryF0ProductResult:
    """Consume exact capture bytes and build the deterministic F0-only product."""
    capture = load_live_beam_capture_artifact(feature_snapshot_path)
    if not capture.beam_snapshots:
        raise VS1LiveBeamIntegrationError(
            "No beam FeatureSnapshot is available for the VS-1 selected capture"
        )
    epoch = build_live_capture_epoch(
        model_path=model_path,
        source_bytes=capture.raw_bytes,
    )
    runs = tuple(
        run_live_beam_f0_slice(epoch=epoch, snapshot=snapshot)
        for snapshot in capture.beam_snapshots
    )
    payload = _product_payload(epoch=epoch, runs=runs)
    path = Path(output_path)
    _write_product(path, payload)
    return LiveBeamGeometryF0ProductResult(
        output_path=path,
        payload=payload,
        beam_count=len(runs),
        finding_count=int(payload["finding_count"]),
    )


def run_live_beam_geometry_f0_product(
    *,
    output_dir: Path,
    target_story: str | None = None,
    target_label: str | None = None,
    target_component: str | None = None,
    max_rows: int = 20,
    attach_result: EtabsAttachResult | None = None,
) -> LiveBeamGeometryF0ProductResult:
    """Run accepted live geometry capture once, then feed its exact artifact to F0."""
    resolved_attach = attach_result or attach_to_running_etabs()
    if resolved_attach.status != "ATTACHED":
        raise EtabsAttachFailure(resolved_attach)
    model_path = read_observed_etabs_model_path(resolved_attach.sap_model)

    out_dir = Path(output_dir)
    capture_dir = out_dir / CAPTURE_DIRNAME
    provider = create_live_etabs_geometry_provider(attach_result=resolved_attach)
    probe = probe_geometry_feature_snapshots(
        provider=provider,
        output_dir=capture_dir,
        target_story=target_story,
        target_label=target_label,
        target_component=target_component,
        max_rows=max_rows,
    )
    if not probe.feature_snapshot_path.exists():
        raise VS1LiveBeamIntegrationError(
            "Live geometry probe did not produce the canonical FeatureSnapshot artifact"
        )
    return build_live_beam_geometry_f0_product_from_capture(
        model_path=model_path,
        feature_snapshot_path=probe.feature_snapshot_path,
        output_path=out_dir / PRODUCT_FILENAME,
    )


__all__ = [
    "PRODUCT_CONTRACT",
    "PRODUCT_FILENAME",
    "CAPTURE_DIRNAME",
    "LiveBeamGeometryF0ProductResult",
    "build_live_beam_geometry_f0_product_from_capture",
    "run_live_beam_geometry_f0_product",
]
