"""C14.1-P1 live beam/column minimum-compliance product slice."""
from __future__ import annotations
from collections.abc import Callable, Mapping
from pathlib import Path
from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.input_adapter import build_geometry_check_inputs_from_feature_snapshot
from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.features.etabs_com_attach import EtabsAttachFailure, EtabsAttachResult, attach_to_running_etabs
from tbdy_engine.reports.minimum_compliance_tabular_report import write_minimum_compliance_tabular_report
from tbdy_engine.product._minimum_compliance_source import _load_live_source, _build_inventory, _classify_inventory
from tbdy_engine.product._minimum_compliance_checks import (
    _column_derived_results, _blocked_result, _copy_result, _record,
    _clear_span_candidate, _web_trigger_result, _feature_value, _feature_evidence,
    _evaluate_absolute_beam_depth, _evaluate_depth_vs_slab, _evaluate_web_detailing_trigger,
)
from tbdy_engine.product._minimum_compliance_report_data import _build_report_tables
from tbdy_engine.product._minimum_compliance_summary import _summary, _manifest, _write_failure_bundle, _load_catalog, _filter_snapshots
from tbdy_engine.product._minimum_compliance_util import (
    _rows, _product_diagnostic, _index_rows, _snapshot_key, _adapter_diagnostic_dict,
    _section, _check_key, _diagnostic_key, _prepare_owned_outputs, _write_json,
)
AttachRunner = Callable[[], EtabsAttachResult]
SourceLoader = Callable[[EtabsAttachResult, Path], Mapping[str, object]]
def run_live_beam_column_minimum_compliance(*, output_dir: Path, element_type: str | None = None, story: str | None = None, section: str | None = None, attach_runner: AttachRunner = attach_to_running_etabs, source_loader: SourceLoader | None = None) -> Mapping[str, object]:
    root = Path(output_dir)
    _prepare_owned_outputs(root)
    report_dir, artifact_dir = root / "report", root / "artifacts"
    selectors = {"element_type": element_type, "story": story, "section": section}
    try:
        attach_result = attach_runner()
        if attach_result.status != "ATTACHED" or attach_result.sap_model is None:
            raise EtabsAttachFailure(attach_result)
        source = dict((source_loader or _load_live_source)(attach_result, artifact_dir / "_source"))
    except Exception as exc:
        return _write_failure_bundle(root, report_dir, artifact_dir, selectors, exc)
    component_rows = _rows(source, "component_rows")
    assignment_rows = _rows(source, "assignment_rows")
    section_rows = _rows(source, "section_rows")
    material_rows = _rows(source, "material_rows")
    snapshots = _filter_snapshots(_rows(source, "snapshots"), element_type, story, section)
    source_diagnostics = [dict(item) for item in _rows(source, "source_diagnostics")]
    inventory = _build_inventory(component_rows, assignment_rows, element_type, story, section)
    snapshot_by_component = {str(row.get("component_id")): row for row in snapshots}
    classifications = _classify_inventory(inventory=inventory, section_rows=section_rows, material_rows=material_rows, snapshot_by_component=snapshot_by_component, source_diagnostics=source_diagnostics)
    catalog = _load_catalog()
    engine = MinimalCheckEngine(check_definitions=catalog)
    adapter_diagnostics: list[dict[str, object]] = list(source_diagnostics)
    adapter_diagnostics.extend(_product_diagnostic(str(item["status"]), "INVENTORY_COVERAGE_" + str(item["status"]), str(item["unique_name"]), str(item["element_type"]), item.get("section"), str(item["reason"])) for item in classifications if item["status"] != "SUPPORTED")
    check_records: list[dict[str, object]] = []
    connectivity = _index_rows(_rows(source, "connectivity_rows"), "UniqueName")
    offsets = _index_rows(_rows(source, "offset_rows"), "UniqueName")
    unit_evidence = source.get("unit_evidence")
    for snapshot in sorted(snapshots, key=_snapshot_key):
        built = build_geometry_check_inputs_from_feature_snapshot(snapshot)
        adapter_diagnostics.extend(_adapter_diagnostic_dict(item) for item in built.diagnostics)
        inputs = {item.check_id: item for item in built.check_inputs}
        component_type = str(snapshot.get("component_type", "")).casefold()
        component_id = str(snapshot.get("component_id", ""))
        if component_type == "beam":
            for check_id in ("beam_geometry_min_width", "beam_geometry_min_depth", "beam_depth_width_ratio"):
                if check_id in inputs:
                    result = engine.run_check(check_id, inputs[check_id].snapshot, inputs[check_id].coverage)
                    if check_id == "beam_geometry_min_depth":
                        result = _copy_result(result, "beam_geometry_min_depth_absolute", "TBDY 2018 7.4.1.1(b)")
                    check_records.append(_record(result))
            slab_result = _blocked_result(snapshot, "beam_geometry_depth_ge_three_times_slab_thickness", "BEAM_ADJACENT_SLAB_THICKNESS_NOT_RESOLVED", "Beam-to-adjacent-slab relationship resolver is not implemented; no global or nearby slab fallback is allowed.", code_ref="TBDY 2018 7.4.1.1(b)")
            check_records.append(_record(slab_result))
            adapter_diagnostics.append(_product_diagnostic("BLOCKED", "BEAM_ADJACENT_SLAB_THICKNESS_NOT_RESOLVED", component_id, "beam", _section(snapshot), "Adjacent slab thickness source path is intentionally not implemented."))
            candidate = _clear_span_candidate(component_id, connectivity, offsets, unit_evidence)
            trigger_result, trigger_status = _web_trigger_result(snapshot, candidate, semantics_locked=False)
            check_records.append(_record(trigger_result, result_status=trigger_status, candidate=candidate))
            if trigger_status == "BLOCKED":
                adapter_diagnostics.append(_product_diagnostic("BLOCKED", "BEAM_CLEAR_SPAN_SEMANTICS_NOT_LOCKED", component_id, "beam", _section(snapshot), "Length/Offset candidate exists, but ETABS/TBDY clear-span semantics are not approved."))
            span_result = _blocked_result(snapshot, "beam_span_depth_ratio", "BEAM_SPAN_DEPTH_RULE_NOT_LOCKED", "The governing span-depth rule and clear-span semantics are not locked.", code_ref=None, evidence=(candidate,) if candidate else ())
            material_result = _blocked_result(snapshot, "beam_material_min_concrete_strength", "MATERIAL_MINIMUM_RULE_NOT_LOCKED", "The 25 MPa candidate minimum has no locked TBDY clause in this sprint.", code_ref=None, value=_feature_value(snapshot, "concrete_fck_mpa"), limit=25.0, unit="MPa", evidence=_feature_evidence(snapshot, "concrete_fck_mpa"))
            check_records.extend((_record(span_result), _record(material_result)))
        elif component_type == "column":
            if "column_geometry_min_dimension" in inputs:
                result = engine.run_check("column_geometry_min_dimension", inputs["column_geometry_min_dimension"].snapshot, inputs["column_geometry_min_dimension"].coverage)
                check_records.append(_record(result))
            check_records.extend(_record(result) for result in _column_derived_results(snapshot))
            material_result = _blocked_result(snapshot, "column_material_min_concrete_strength", "MATERIAL_MINIMUM_RULE_NOT_LOCKED", "The 25 MPa candidate minimum has no locked TBDY clause in this sprint.", code_ref=None, value=_feature_value(snapshot, "concrete_fck_mpa"), limit=25.0, unit="MPa", evidence=_feature_evidence(snapshot, "concrete_fck_mpa"))
            check_records.append(_record(material_result))
    for item in classifications:
        if item["status"] != "SUPPORTED":
            result = CheckResult(check_id="minimum_compliance_scope", component=str(item["unique_name"]), component_type=str(item["element_type"]), story=item.get("story"), section=item.get("section"), status=CheckStatus(str(item["status"])), evaluation_level=EvaluationLevel.NO_DATA, evidence=[item], messages=(str(item["reason"]),), code_ref=None)
            check_records.append(_record(result))
    check_records.sort(key=_check_key)
    adapter_diagnostics.sort(key=_diagnostic_key)
    snapshots.sort(key=_snapshot_key)
    tables = _build_report_tables(inventory=inventory, classifications=classifications, snapshots=snapshots, check_records=check_records, diagnostics=adapter_diagnostics, connectivity=connectivity, offsets=offsets, unit_evidence=unit_evidence)
    summary = _summary(tables, inventory, classifications, check_records)
    manifest = _manifest(root, selectors, summary)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    _write_json(artifact_dir / "enriched_feature_snapshots.json", {"snapshots": snapshots})
    _write_json(artifact_dir / "check_results.json", check_records)
    _write_json(artifact_dir / "adapter_diagnostics.json", adapter_diagnostics)
    _write_json(artifact_dir / "product_summary.json", summary)
    _write_json(artifact_dir / "product_manifest.json", manifest)
    report_paths = write_minimum_compliance_tabular_report(output_dir=report_dir, tables=tables)
    return {**summary, "report_paths": dict(report_paths)}
__all__ = ["run_live_beam_column_minimum_compliance", "_evaluate_absolute_beam_depth", "_evaluate_depth_vs_slab", "_evaluate_web_detailing_trigger"]
