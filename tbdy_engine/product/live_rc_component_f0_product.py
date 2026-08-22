"""Deterministic product projection and live composition for VS-2."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from tbdy_engine.etabs.safety import (
    EtabsCapabilityError,
    EtabsVerifiedSession,
    read_capability_snapshot,
    read_session_identity,
)
from tbdy_engine.features.etabs_com_attach import (
    EtabsAttachFailure,
    EtabsAttachResult,
    attach_to_running_etabs,
)
from tbdy_engine.features.live_etabs_geometry_probe import (
    create_live_etabs_geometry_provider,
    probe_geometry_feature_snapshots,
)
from tbdy_engine.features.used_rc_material_population import (
    MaterialPopulationReadiness,
    MaterialSourceContractResolutionError,
    UsedRcMaterialPopulation,
    build_used_rc_material_population_from_same_verified_session,
    canonical_material_population_json,
)
from tbdy_engine.findings import Finding
from tbdy_engine.integration.live_beam_geometry_f0 import (
    build_live_capture_epoch,
    model_fingerprint_from_path,
    read_observed_etabs_model_path,
    validate_tbdy_7411_applies,
)
from tbdy_engine.integration.live_rc_component_f0 import (
    MATERIAL_DOMAIN_BLOCK_REASON,
    WALL_NOT_EVALUATED_REASON,
    LiveRcComponentPackRun,
    MissingLiveMaterialEvidenceError,
    RealComponentPackConflictError,
    VS2RcComponentIntegrationError,
    build_material_live_capture_epoch,
    load_rc_geometry_capture,
    run_live_rc_component_f0_pack,
)
from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.regulatory.contracts import Grain

PRODUCT_CONTRACT = "VS2_LIVE_RC_COMPONENT_COMPLIANCE_PRODUCT_V1"
PRODUCT_FILENAME = "live_rc_component_compliance_product.json"
GEOMETRY_CAPTURE_DIRNAME = "live_rc_component_geometry_capture"
MATERIAL_CAPTURE_FILENAME = "used_rc_material_population.json"
APPLICABILITY_SOURCE_KIND = "EXPLICIT_CALLER_INPUT"


@dataclass(frozen=True, slots=True)
class LiveRcComponentF0ProductResult:
    output_path: Path
    payload: dict[str, Any]
    beam_count: int
    column_count: int
    used_concrete_material_count: int
    finding_count: int


@dataclass(frozen=True, slots=True)
class _CachedGeometryProvider:
    rows: tuple[dict[str, object], ...]
    diagnostics: tuple[object, ...]
    summary: dict[str, object]
    population_audit: object

    def live_geometry_probe_data(self):
        return self.rows, self.diagnostics, self.summary, self.population_audit


def _canonical_geometry_rows(rows) -> tuple[dict[str, object], ...]:
    """Stabilize factual provider ordering before the existing probe serializes it."""
    return tuple(
        sorted(
            (dict(item) for item in rows),
            key=lambda row: json.dumps(
                to_jsonable(row),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    )


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
        "regulatory_quantity_keys": [item.value for item in finding.regulatory_quantity_keys],
        "evidence_refs": list(finding.evidence_refs),
        "diagnostic_refs": list(finding.diagnostic_refs),
        "messages": list(finding.messages),
        "provenance_refs": list(finding.provenance_refs),
    }


def _domain_for_instance(instance) -> str:
    if instance.grain is Grain.MATERIAL_DEFINITION:
        return "concrete_material"
    rule = instance.rule_id.value
    if rule.startswith("beam_"):
        return "beam_geometry"
    if rule.startswith("column_"):
        return "column_geometry"
    raise VS2RcComponentIntegrationError(f"unsupported VS-2 rule instance domain: {rule}")


def _result_inventory(run: LiveRcComponentPackRun) -> list[dict[str, object]]:
    result_by_instance = {item.instance_id: item.result for item in run.store.formal_results}
    closure_by_instance = {
        item.compiled_record_ref: item for item in run.assessment.closure_outcomes
    }
    compiled_by_instance = {
        item.instance_id: item for item in run.program.plan.compiled_closure_inventory
    }
    inventory: list[dict[str, object]] = []
    for instance in sorted(run.program.plan.compiled_rule_instances, key=lambda item: item.value):
        item: dict[str, object] = {
            "domain": _domain_for_instance(instance),
            "rule_id": instance.rule_id.value,
            "rule_instance_id": instance.value,
            "grain": instance.grain.value,
            "scope_ref": instance.scope_ref,
            "direction": instance.direction,
            "applicability": compiled_by_instance[instance].applicability.value,
            "closure_status": closure_by_instance[instance].execution_status.value,
            "check_result": None,
        }
        if instance in result_by_instance:
            item["check_result"] = result_by_instance[instance].as_dict()
        inventory.append(item)
    return inventory


def _domain_counts(results: list[dict[str, object]], domain: str) -> tuple[int, int]:
    rows = [item for item in results if item["domain"] == domain]
    return len(rows), sum(item["check_result"] is not None for item in rows)


def build_product_payload(
    *,
    run: LiveRcComponentPackRun,
    geometry_truncation_applied: bool,
) -> dict[str, Any]:
    if type(geometry_truncation_applied) is not bool:
        raise TypeError("geometry_truncation_applied must be bool")
    results = _result_inventory(run)
    findings = [_finding_payload(item) for item in run.findings]
    beam_instances, beam_results = _domain_counts(results, "beam_geometry")
    column_instances, column_results = _domain_counts(results, "column_geometry")
    material_instances, material_results = _domain_counts(results, "concrete_material")
    factual_material_count = len(run.material_population.used_concrete_material_definitions)

    provenance_refs = sorted(
        {
            ref
            for authority in run.authorities
            for ref in authority.provenance_refs
        }
        | {
            run.geometry_epoch.epoch_id,
            run.geometry_epoch.model_fingerprint,
            run.geometry_epoch.source_fingerprint or "",
            run.material_epoch.epoch_id,
            run.material_epoch.source_fingerprint or "",
        }
        - {""}
    )

    material_domain: dict[str, object] = {
        "support_status": "SUPPORTED" if run.material_domain_supported else "BLOCKED",
        "population_readiness": run.material_population.readiness.value,
        "rule_instance_count": material_instances,
        "check_result_count": material_results,
    }
    if not run.material_domain_supported:
        material_domain["reason"] = MATERIAL_DOMAIN_BLOCK_REASON

    return {
        "contract": PRODUCT_CONTRACT,
        "model_fingerprint": run.geometry_epoch.model_fingerprint,
        "capture_epochs": {
            "geometry": {
                "epoch_id": run.geometry_epoch.epoch_id,
                "origin": run.geometry_epoch.origin.value,
                "model_fingerprint": run.geometry_epoch.model_fingerprint,
                "source_fingerprint": run.geometry_epoch.source_fingerprint,
            },
            "material": {
                "epoch_id": run.material_epoch.epoch_id,
                "origin": run.material_epoch.origin.value,
                "model_fingerprint": run.material_epoch.model_fingerprint,
                "source_fingerprint": run.material_epoch.source_fingerprint,
            },
        },
        "applicability_input": {
            "tbdy_7411_applies": run.tbdy_7411_applies,
            "source_kind": APPLICABILITY_SOURCE_KIND,
        },
        "regulatory_authority": "F0_ONLY",
        "registry_version": run.registry.registry_version,
        "plan_identity": run.program.plan.plan_identity,
        "structural_assessment_status": run.structural_assessment_status,
        "full_tbdy_compliance_status": "NOT_EVALUATED",
        "rule_instance_count": len(run.program.plan.compiled_rule_instances),
        "check_result_count": len(run.store.formal_results),
        "finding_count": len(findings),
        "population": {
            "beam_count": run.beam_count,
            "column_count": run.column_count,
            "used_concrete_material_count": factual_material_count,
            "geometry_truncation_applied": geometry_truncation_applied,
        },
        "domains": {
            "beam_geometry": {
                "support_status": "SUPPORTED",
                "rule_instance_count": beam_instances,
                "check_result_count": beam_results,
            },
            "column_geometry": {
                "support_status": "SUPPORTED",
                "rule_instance_count": column_instances,
                "check_result_count": column_results,
            },
            "concrete_material": material_domain,
            "wall_geometry": {
                "support_status": "NOT_EVALUATED",
                "reason": WALL_NOT_EVALUATED_REASON,
                "rule_instance_count": 0,
                "check_result_count": 0,
                "finding_count": 0,
            },
        },
        "results": results,
        "findings": findings,
        "provenance_refs": provenance_refs,
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


def build_live_rc_component_f0_product(
    *,
    geometry_epoch,
    snapshots,
    material_epoch,
    material_population: UsedRcMaterialPopulation,
    tbdy_7411_applies: bool | None,
    geometry_truncation_applied: bool,
    output_path: Path,
) -> LiveRcComponentF0ProductResult:
    run = run_live_rc_component_f0_pack(
        geometry_epoch=geometry_epoch,
        snapshots=snapshots,
        material_epoch=material_epoch,
        material_population=material_population,
        tbdy_7411_applies=tbdy_7411_applies,
    )
    payload = build_product_payload(
        run=run,
        geometry_truncation_applied=geometry_truncation_applied,
    )
    path = Path(output_path)
    _write_product(path, payload)
    return LiveRcComponentF0ProductResult(
        output_path=path,
        payload=payload,
        beam_count=run.beam_count,
        column_count=run.column_count,
        used_concrete_material_count=len(material_population.used_concrete_material_definitions),
        finding_count=len(run.findings),
    )


def _verified_same_session(attach_result: EtabsAttachResult, model_path: str) -> EtabsVerifiedSession:
    identity = read_session_identity(
        attach_result.etabs_object,
        attach_result.sap_model,
        attach_strategy=attach_result.strategy,
    )
    if model_fingerprint_from_path(identity.model_full_path) != model_fingerprint_from_path(model_path):
        raise RealComponentPackConflictError("verified session model path differs from geometry model identity")
    return EtabsVerifiedSession(
        attach_result=attach_result,
        identity=identity,
        capabilities=read_capability_snapshot(
            attach_result.sap_model,
            attach_result=attach_result,
        ),
        diagnostics=(),
    )


def _capture_full_geometry(*, attach_result: EtabsAttachResult, output_dir: Path):
    provider = create_live_etabs_geometry_provider(attach_result=attach_result)
    bundle_reader = getattr(provider, "live_geometry_probe_data", None)
    if not callable(bundle_reader):
        raise RealComponentPackConflictError("existing live geometry provider has no full-population bundle")
    rows, diagnostics, summary, population_audit = bundle_reader()
    rows = _canonical_geometry_rows(rows)
    if not rows:
        raise RealComponentPackConflictError("live geometry provider returned no in-scope beam/column rows")
    cached = _CachedGeometryProvider(
        rows=rows,
        diagnostics=tuple(diagnostics),
        summary=dict(summary),
        population_audit=population_audit,
    )
    probe = probe_geometry_feature_snapshots(
        provider=cached,
        output_dir=output_dir,
        max_rows=len(rows),
    )
    summary_payload = json.loads(probe.summary_path.read_text(encoding="utf-8"))
    if summary_payload.get("truncation_applied") is not False:
        raise RealComponentPackConflictError("complete geometry capture was truncated")
    if summary_payload.get("candidate_row_count") != len(rows):
        raise RealComponentPackConflictError("geometry candidate population accounting mismatch")
    if summary_payload.get("selected_row_count") != len(rows):
        raise RealComponentPackConflictError("geometry selection did not preserve full candidate population")
    if summary_payload.get("population_blocked_row_count", 0) != 0 or probe.status != "OK":
        raise RealComponentPackConflictError("live geometry population contains unresolved/blocking factual rows")
    return probe, summary_payload


def run_live_rc_component_f0_product(
    *,
    output_dir: Path,
    tbdy_7411_applies: bool | None,
    attach_result: EtabsAttachResult | None = None,
) -> LiveRcComponentF0ProductResult:
    tbdy_7411_applies = validate_tbdy_7411_applies(tbdy_7411_applies)
    resolved_attach = attach_result or attach_to_running_etabs()
    if resolved_attach.status != "ATTACHED":
        raise EtabsAttachFailure(resolved_attach)
    if resolved_attach.sap_model is None:
        raise RealComponentPackConflictError("ETABS attach succeeded without SapModel")

    model_path = read_observed_etabs_model_path(resolved_attach.sap_model)
    model_fingerprint = model_fingerprint_from_path(model_path)
    try:
        verified_session = _verified_same_session(resolved_attach, model_path)
    except EtabsCapabilityError as exc:
        raise MissingLiveMaterialEvidenceError(
            "verified ETABS session lacks required factual material/unit evidence"
        ) from exc

    out_dir = Path(output_dir)
    probe, geometry_summary = _capture_full_geometry(
        attach_result=resolved_attach,
        output_dir=out_dir / GEOMETRY_CAPTURE_DIRNAME,
    )
    geometry_capture = load_rc_geometry_capture(probe.feature_snapshot_path)
    if not geometry_capture.beam_snapshots or not geometry_capture.column_snapshots:
        raise RealComponentPackConflictError("VS-2 live acceptance requires beam and column populations")
    geometry_epoch = build_live_capture_epoch(
        model_path=model_path,
        source_bytes=geometry_capture.raw_bytes,
    )

    try:
        material_population = build_used_rc_material_population_from_same_verified_session(
            session=verified_session,
            inventory_identity_namespace=model_fingerprint,
        )
    except MaterialSourceContractResolutionError as exc:
        raise MissingLiveMaterialEvidenceError(
            "authoritative same-session used-RC material factual seam is unresolved"
        ) from exc

    material_text = canonical_material_population_json(material_population)
    material_path = out_dir / MATERIAL_CAPTURE_FILENAME
    material_path.parent.mkdir(parents=True, exist_ok=True)
    material_path.write_text(material_text, encoding="utf-8")
    material_bytes = material_path.read_bytes()
    material_epoch = build_material_live_capture_epoch(
        model_fingerprint=model_fingerprint,
        source_bytes=material_bytes,
    )

    if material_population.model_fingerprint != model_fingerprint:
        raise RealComponentPackConflictError("authoritative M0 population belongs to another model")
    if geometry_epoch.model_fingerprint != material_epoch.model_fingerprint:
        raise RealComponentPackConflictError("geometry/material captures do not share model identity")
    if material_population.readiness is not MaterialPopulationReadiness.COMPLETE:
        raise MissingLiveMaterialEvidenceError(
            "authoritative used-RC material population is not COMPLETE"
        )
    if not material_population.used_concrete_material_definitions:
        raise MissingLiveMaterialEvidenceError(
            "authoritative COMPLETE material population contains no used concrete definition"
        )

    return build_live_rc_component_f0_product(
        geometry_epoch=geometry_epoch,
        snapshots=geometry_capture.snapshots,
        material_epoch=material_epoch,
        material_population=material_population,
        tbdy_7411_applies=tbdy_7411_applies,
        geometry_truncation_applied=bool(geometry_summary["truncation_applied"]),
        output_path=out_dir / PRODUCT_FILENAME,
    )


__all__ = [
    "PRODUCT_CONTRACT",
    "PRODUCT_FILENAME",
    "GEOMETRY_CAPTURE_DIRNAME",
    "MATERIAL_CAPTURE_FILENAME",
    "APPLICABILITY_SOURCE_KIND",
    "LiveRcComponentF0ProductResult",
    "build_product_payload",
    "build_live_rc_component_f0_product",
    "run_live_rc_component_f0_product",
]
