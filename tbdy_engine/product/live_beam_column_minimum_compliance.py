"""C14.1-P1 live beam/column minimum-compliance product slice."""
from __future__ import annotations
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
import json
import math
import re
import shutil
import yaml
from tbdy_engine.checks.engine import MinimalCheckEngine
from tbdy_engine.checks.input_adapter import build_geometry_check_inputs_from_feature_snapshot
from tbdy_engine.checks.result import CheckResult, CheckStatus, EvaluationLevel
from tbdy_engine.features.etabs_com_attach import EtabsAttachFailure, EtabsAttachResult, attach_to_running_etabs
from tbdy_engine.features.live_etabs_concrete_material_probe import (
    ConcreteMaterialProbeInput,
    FixtureConcreteMaterialProbeProvider,
    create_live_etabs_concrete_material_provider,
    probe_concrete_material_feature_snapshots,
)
from tbdy_engine.features.live_etabs_geometry_probe import (
    LENGTH_TO_MM_FACTOR,
    LiveEtabsLengthUnitEvidence,
    read_live_etabs_table_for_geometry,
)
from tbdy_engine.reports.minimum_compliance_tabular_report import write_minimum_compliance_tabular_report
_SCOPE = "C14_1_P1_LIVE_BEAM_COLUMN_MINIMUM_COMPLIANCE"
_COMPONENT_TABLE = "Frame Assignments - Summary"
_ASSIGNMENT_TABLE = "Frame Assignments - Section Properties"
_SECTION_TABLE = "Frame Section Property Definitions - Concrete Rectangular"
_MATERIAL_TABLE = "Material Properties - Concrete Data"
_CONNECTIVITY_TABLE = "Beam Object Connectivity"
_OFFSET_TABLE = "Frame Assignments - End Length Offsets"
_CATALOG = Path(__file__).resolve().parents[1] / "catalogs" / "check_catalog_c14_1_p1_minimum_compliance.yaml"
_REPORT_FILES = (
    "minimum_compliance_report.md", "executive_summary.csv", "beam_section_checks.csv",
    "unsupported_beam_sections.csv", "column_section_checks.csv", "unsupported_column_sections.csv",
    "check_detail.csv", "diagnostic_summary.csv", "guardrails.csv", "boundary_notes.csv",
)
_ARTIFACT_FILES = (
    "enriched_feature_snapshots.json", "check_results.json", "adapter_diagnostics.json",
    "product_summary.json", "product_manifest.json",
)
_STATUS_PRIORITY = {"FAIL": 5, "BLOCKED": 4, "NO_DATA": 3, "OUT_OF_SCOPE": 2, "OK": 1}
_NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
AttachRunner = Callable[[], EtabsAttachResult]
SourceLoader = Callable[[EtabsAttachResult, Path], Mapping[str, object]]
def run_live_beam_column_minimum_compliance(
    *,
    output_dir: Path,
    element_type: str | None = None,
    story: str | None = None,
    section: str | None = None,
    attach_runner: AttachRunner = attach_to_running_etabs,
    source_loader: SourceLoader | None = None,
) -> Mapping[str, object]:
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
    classifications = _classify_inventory(
        inventory=inventory,
        section_rows=section_rows,
        material_rows=material_rows,
        snapshot_by_component=snapshot_by_component,
        source_diagnostics=source_diagnostics,
    )
    catalog = _load_catalog()
    engine = MinimalCheckEngine(check_definitions=catalog)
    adapter_diagnostics: list[dict[str, object]] = list(source_diagnostics)
    adapter_diagnostics.extend(
        _product_diagnostic(str(item["status"]), "INVENTORY_COVERAGE_" + str(item["status"]), str(item["unique_name"]), str(item["element_type"]), item.get("section"), str(item["reason"]))
        for item in classifications if item["status"] != "SUPPORTED"
    )
    check_records: list[dict[str, object]] = []
    result_objects: list[CheckResult] = []
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
                    result_objects.append(result)
                    check_records.append(_record(result))
            slab_result = _blocked_result(
                snapshot, "beam_geometry_depth_ge_three_times_slab_thickness",
                "BEAM_ADJACENT_SLAB_THICKNESS_NOT_RESOLVED",
                "Beam-to-adjacent-slab relationship resolver is not implemented; no global or nearby slab fallback is allowed.",
                code_ref="TBDY 2018 7.4.1.1(b)",
            )
            result_objects.append(slab_result)
            check_records.append(_record(slab_result))
            adapter_diagnostics.append(_product_diagnostic(
                "BLOCKED", "BEAM_ADJACENT_SLAB_THICKNESS_NOT_RESOLVED", component_id, "beam",
                _section(snapshot), "Adjacent slab thickness source path is intentionally not implemented.",
            ))
            candidate = _clear_span_candidate(component_id, connectivity, offsets, unit_evidence)
            trigger_result, trigger_status = _web_trigger_result(snapshot, candidate, semantics_locked=False)
            result_objects.append(trigger_result)
            check_records.append(_record(trigger_result, result_status=trigger_status, candidate=candidate))
            if trigger_status == "BLOCKED":
                adapter_diagnostics.append(_product_diagnostic(
                    "BLOCKED", "BEAM_CLEAR_SPAN_SEMANTICS_NOT_LOCKED", component_id, "beam",
                    _section(snapshot), "Length/Offset candidate exists, but ETABS/TBDY clear-span semantics are not approved.",
                ))
            span_result = _blocked_result(
                snapshot, "beam_span_depth_ratio", "BEAM_SPAN_DEPTH_RULE_N²È="25•Ð ‰É…Ñ¥¼ˆ¤°€‰É…Ñ¥½}ÑåÁ”ˆèÉ•ÍÕ±Ð¹•Ð ‰É…Ñ¥½}ÑåÁ”ˆ¤°(€€€€€€€€‰•Ù…±Õ…Ñ¥½¹}±•Ù•°ˆèÉ•ÍÕ±Ð¹•Ð ‰•Ù…±Õ…Ñ¥½¹}±•Ù•°ˆ¤°€‰Ñ‰‘å}É•˜ˆèÉ•ÍÕ±Ð¹•Ð ‰½‘•}É•˜ˆ¤°(€€€€€€€€‰•Ù¥‘•¹•}Ñ…‰±”ˆèÍ½ÉÑ•¡}•Ù¥‘•¹•}Ñ…‰±•Ì¡mÉ•ÍÕ±Ñt¤¤°(€€€€€€€€‰•Ù¥‘•¹•}½±Õµ¹ÌˆèÍ½ÉÑ•¡}•Ù¥‘•¹•}½±Õµ¹Ì¡•Ù¥‘•¹”¤¤°(€€€€€€€€‰É…Ý}Ù…±Õ•Ìˆè}•Ù¥‘•¹•}Ù…±Õ•Ì¡•Ù¥‘•¹”°€‰É…Ý}Ù…±Õ”ˆ¤°(€€€€€€€€‰¹½Éµ…±¥é•‘}Ù…±Õ•Ìˆè}•Ù¥‘•¹•}Ù…±Õ•Ì¡•Ù¥‘•¹”°€‰¹½Éµ…±¥é•‘}Ù…±Õ”ˆ¤°(€€€ô)‘•˜}‘¥…¹½ÍÑ¥}ÍÕµµ…Éä¡‘¥…¹½ÍÑ¥ÌèM•ÅÕ•¹•m5…ÁÁ¥¹mÍÑÈ°½‰©•Ñut¤€´ø±¥ÍÑm‘¥ÑmÍÑÈ°½‰©•Ñutè(€€€É½ÕÁ•è‘¥ÑmÑÕÁ±•mÍÑÈ°ÍÑÈ°ÍÑÉt°±¥ÍÑm5…ÁÁ¥¹mÍÑÈ°½‰©•Ñuut€ô‘•™…Õ±Ñ‘¥Ð¡±¥ÍÐ¤(€€€™½È¥Ñ•´¥¸‘¥…¹½ÍÑ¥Ìè(€€€€€€€É½ÕÁ•‘l¡ÍÑÈ¡¥Ñ•´¹•Ð ‰ÍÑ…ÑÕÌˆ°€ˆˆ¤¤°ÍÑÈ¡¥Ñ•´¹•Ð ‰½‘”ˆ°€ˆˆ¤¤°ÍÑÈ¡¥Ñ•´¹•Ð ‰½µÁ½¹•¹Ñ}ÑåÁ”ˆ¤½È¥Ñ•´¹•Ð ‰…™™•Ñ•‘}•±•µ•¹Ñ}ÑåÁ”ˆ¤½È€ˆˆ¤¥t¹…ÁÁ•¹¡¥Ñ•´¤(€€€É•ÑÕÉ¸mì(€€€€€€€€‰ÍÑ…ÑÕÌˆè­•ålÁt°€‰½‘”ˆè­•ålÅt°€‰½Õ¹Ðˆè±•¸¡¥Ñ•µÌ¤°€‰…™™•Ñ•‘}•±•µ•¹Ñ}ÑåÁ”ˆè­•ålÉt½È9½¹”°(€€€€€€€€‰Í…µÁ±•}½µÁ½¹•¹Ñ}¥‘ÌˆèÍ½ÉÑ•¡í}Ñ•áÐ¡¥Ñ•´¹•Ð ‰½µÁ½¹•¹Ñ}¥ˆ¤¤™½È¥Ñ•´¥¸¥Ñ•µÌ¥˜}Ñ•áÐ¡¥Ñ•´¹•Ð ‰½µÁ½¹•¹Ñ}¥ˆ¤¥ô¥lèÕt°(€€€€€€€€‰Í…µÁ±•}Í•Ñ¥½¹ÌˆèÍ½ÉÑ•¡í}Ñ•áÐ¡¥Ñ•´¹•Ð ‰Í•Ñ¥½¸ˆ¤¤™½È¥Ñ•´¥¸¥Ñ•µÌ¥˜}Ñ•áÐ¡¥Ñ•´¹•Ð ‰Í•Ñ¥½¸ˆ¤¥ô¥lèÕt°(€€€ô™½È­•ä°¥Ñ•µÌ¥¸Í½ÉÑ•¡É½ÕÁ•¹¥Ñ•µÌ ¤¥t)‘•˜}Í•Ñ¥½¹}½Ù•É…±°¡É½ÝÌèM•ÅÕ•¹•m5…ÁÁ¥¹mÍÑÈ°½‰©•Ñut¤€´øÍÑÈè(€€€ÍÑ…ÑÕÍ•Ì€ômÍÑÈ¡É½Ü¹•Ð ‰ÍÑ…ÑÕÌˆ¤¤™½ÈÉ½Ü¥¸É½ÝÌ¥˜É½Ü¹•Ð ‰¡•­}¥ˆ¤€„ô€‰µ¥¹¥µÕµ}½µÁ±¥…¹•}Í½Á”‰t(€€€¥˜€‰%0ˆ¥¸ÍÑ…ÑÕÍ•Ìè(€€€€€€€É•ÑÕÉ¸€‰%0ˆ(€€€¥˜€‰	1=-ˆ¥¸ÍÑ…ÑÕÍ•Ìè(€€€€€€€É•ÑÕÉ¸€‰	1=-ˆ(€€€¥˜€‰9=}Qˆ¥¸ÍÑ…ÑÕÍ•Ìè(€€€€€€€É•ÑÕÉ¸€‰9=}Qˆ(€€€É•ÑÕÉ¸€‰=,ˆ¥˜ÍÑ…ÑÕÍ•Ì…¹…±°¡ÍÑ…ÑÕÌ¥¸ì‰=,ˆ°€‰]I9%9‰ô™½ÈÍÑ…ÑÕÌ¥¸ÍÑ…ÑÕÍ•Ì¤•±Í”€‰9=}Qˆ)‘•˜}…‘…ÁÑ•É}‘¥…¹½ÍÑ¥}‘¥Ð¡¥Ñ•´è½‰©•Ð¤€´ø‘¥ÑmÍÑÈ°½‰©•Ñtè(€€€É•ÑÕÉ¸ì(€€€€€€€€‰ÍÑ…ÑÕÌˆè•Ñ…ÑÑÈ¡¥Ñ•´°€‰ÍÑ…ÑÕÌˆ°€‰	1=-ˆ¤°€‰½‘”ˆè€‰=5QIe}!-}%9AUQ}AQHˆ°(€€€€€€€€‰¡•­}¥ˆè•Ñ…ÑÑÈ¡¥Ñ•´°€‰¡•­}¥ˆ°9½¹”¤°€‰½µÁ½¹•¹Ñ}¥ˆè•Ñ…ÑÑÈ¡¥Ñ•´°€‰½µÁ½¹•¹Ñ}¥ˆ°9½¹”¤°(€€€€€€€€‰½µÁ½¹•¹Ñ}ÑåÁ”ˆè•Ñ…ÑÑÈ¡¥Ñ•´°€‰½µÁ½¹•¹Ñ}ÑåÁ”ˆ°9½¹”¤°€‰µ•ÍÍ…”ˆè•Ñ…ÑÑÈ¡¥Ñ•´°€‰É•…Í½¸ˆ°€ˆˆ¤°(€€€€€€€€‰µ¥ÍÍ¥¹}™•…ÑÕÉ•Ìˆè±¥ÍÐ¡•Ñ…ÑÑÈ¡¥Ñ•´°€‰µ¥ÍÍ¥¹}™•…ÑÕÉ•Ìˆ°€ ¤¤¤°€‰¥¹Ù…±¥‘}™•…ÑÕÉ•Ìˆè±¥ÍÐ¡•Ñ…ÑÑÈ¡¥Ñ•´°€‰¥¹Ù…±¥‘}™•…ÑÕÉ•Ìˆ°€ ¤¤¤°(€€€ô)‘•˜}ÁÉ½‘ÕÑ}‘¥…¹½ÍÑ¥Œ¡ÍÑ…ÑÕÌèÍÑÈ°½‘”èÍÑÈ°½µÁ½¹•¹Ñ}¥èÍÑÈ°½µÁ½¹•¹Ñ}ÑåÁ”èÍÑÈ°Í•Ñ¥½¸èÍÑÈð9½¹”°µ•ÍÍ…”èÍÑÈ¤€´ø‘¥ÑmÍÑÈ°½‰©•Ñtè(€€€É•ÑÕÉ¸ì‰ÍÑ…ÑÕÌˆèÍÑ…ÑÕÌ°€‰½‘”ˆè½‘”°€‰½µÁ½¹•¹Ñ}¥ˆè½µÁ½¹•¹Ñ}¥°€‰½µÁ½¹•¹Ñ}ÑåÁ”ˆè½µÁ½¹•¹Ñ}ÑåÁ”°€‰Í•Ñ¥½¸ˆèÍ•Ñ¥½¸°€‰µ•ÍÍ…”ˆèµ•ÍÍ…•ô)‘•˜}™•…ÑÕÉ•}Ù…±Õ”¡Í¹…ÁÍ¡½Ðè5…ÁÁ¥¹mÍÑÈ°½‰©•Ñt°¹…µ”èÍÑÈ¤€´ø½‰©•Ðè(€€€™•…ÑÕÉ•Ì€ôÍ¹…ÁÍ¡½Ð¹•Ð ‰™•…ÑÕÉ•Ìˆ¤¥˜¥Í¥¹ÍÑ…¹”¡Í¹…ÁÍ¡½Ð¹•Ð ‰™•…ÑÕÉ•Ìˆ¤°5…ÁÁ¥¹œ¤•±Í”íô(€€€™•…ÑÕÉ”€ô™•…ÑÕÉ•Ì¹•Ð¡¹…µ”¤¥˜¥Í¥¹ÍÑ…¹”¡™•…ÑÕÉ•Ì¹•Ð¡¹…µ”¤°5…ÁÁ¥¹œ¤•±Í”íô(€€€É•ÑÕÉ¸™•…ÑÕÉ”¹•Ð ‰Ù…±Õ”ˆ¤)‘•˜}™•…ÑÕÉ•}•Ù¥‘•¹”¡Í¹…ÁÍ¡½Ðè5…ÁÁ¥¹mÍÑÈ°½‰©•Ñt°¹…µ”èÍÑÈ¤€´øÑÕÁ±•m½‰©•Ð°€¸¸¹tè(€€€™•…ÑÕÉ•Ì€ôÍ¹…ÁÍ¡½Ð¹•Ð ‰™•…ÑÕÉ•Ìˆ¤¥˜¥Í¥¹ÍÑ…¹”¡Í¹…ÁÍ¡½Ð¹•Ð ‰™•…ÑÕÉ•Ìˆ¤°5…ÁÁ¥¹œ¤•±Í”íô(€€€™•…ÑÕÉ”€ô™•…ÑÕÉ•Ì¹•Ð¡¹…µ”¤¥˜¥Í¥¹ÍÑ…¹”¡™•…ÑÕÉ•Ì¹•Ð¡¹…µ”¤°5…ÁÁ¥¹œ¤•±Í”íô(€€€•Ù¥‘•¹”€ô™•…ÑÕÉ”¹•Ð ‰•Ù¥‘•¹”ˆ¤(€€€É•ÑÕÉ¸ÑÕÁ±”¡•Ù¥‘•¹”¤¥˜¥Í¥¹ÍÑ…¹”¡•Ù¥‘•¹”°M•ÅÕ•¹”¤…¹¹½Ð¥Í¥¹ÍÑ…¹”¡•Ù¥‘•¹”°€¡ÍÑÈ°‰åÑ•Ì°‰åÑ•…ÉÉ…ä¤¤•±Í”€ ¤)‘•˜}¥‘•¹Ñ¥Ñä¡Í¹…ÁÍ¡½Ðè5…ÁÁ¥¹mÍÑÈ°½‰©•Ñt°­•äèÍÑÈ¤€´ø½‰©•Ðè(€€€¥‘•¹Ñ¥Ñä€ôÍ¹…ÁÍ¡½Ð¹•Ð ‰¥‘•¹Ñ¥Ñäˆ¤¥˜¥Í¥¹ÍÑ…¹”¡Í¹…ÁÍ¡½Ð¹•Ð ‰¥‘•¹Ñ¥Ñäˆ¤°5…ÁÁ¥¹œ¤•±Í”íô(€€€É•ÑÕÉ¸¥‘•¹Ñ¥Ñä¹•Ð¡­•ä¤)‘•˜}Í•Ñ¥½¸¡Í¹…ÁÍ¡½Ðè5…ÁÁ¥¹mÍÑÈ°½‰©•Ñt¤€´øÍÑÈð9½¹”è(€€€Ù…±Õ”€ô}¥‘•¹Ñ¥Ñä¡Í¹…ÁÍ¡½Ð°€‰Í•Ñ¥½¸ˆ¤½È}¥‘•¹Ñ¥Ñä¡Í¹…ÁÍ¡½Ð°€‰Í•Ñ¥½¹}¹…µ”ˆ¤(€€€É•ÑÕÉ¸}Ñ•áÐ¡Ù…±Õ”¤½È9½¹”)‘•˜}•Ù¥‘•¹•}Ñ…‰±•Ì¡É•½É‘ÌèM•ÅÕ•¹•m5…ÁÁ¥¹mÍÑÈ°½‰©•Ñut¤€´øÍ•ÑmÍÑÉtè(€€€Ñ…‰±•ÌèÍ•ÑmÍÑÉt€ôÍ•Ð ¤(€€€™½ÈÉ•½É¥¸É•½É‘Ìè(€€€€€€€•Ù¥‘•¹”€ôÉ•½É¹•Ð ‰•Ù¥‘•¹”ˆ¤(€€€€€€€¥˜¹½Ð¥Í¥¹ÍÑ…¹”¡•Ù¥‘•¹”°M•ÅÕ•¹”¤½È¥Í¥¹ÍÑ…¹”¡•Ù¥‘•¹”°€¡ÍÑÈ°‰åÑ•Ì°‰åÑ•…ÉÉ…ä¤¤è(€€€€€€€€€€€½¹Ñ¥¹Õ”(€€€€€€€™½È¥Ñ•´¥¸•Ù¥‘•¹”è(€€€€€€€€€€€¥˜¥Í¥¹ÍÑ…¹”¡¥Ñ•´°5…ÁÁ¥¹œ¤è(€€€€€€€€€€€€€€€Ñ…‰±”€ô¥Ñ•´¹•Ð ‰Í½ÕÉ•}Ñ…‰±”ˆ¤½È¥Ñ•´¹•Ð ‰…ÑÕ…±}Ñ…‰±•}¹…µ”ˆ¤(€€€€€€€€€€€€€€€¥˜Ñ…‰±”è(€€€€€€€€€€€€€€€€€€€Ñ…‰±•Ì¹…‘¡ÍÑÈ¡Ñ…‰±”¤¤(€€€€€€€€€€€€€€€™½È¹•ÍÑ•¥¸¥Ñ•´¹•Ð ‰Í½ÕÉ•}Ñ…‰±•Ìˆ°€ ¤¤¥˜¥Í¥¹ÍÑ…¹”¡¥Ñ•´¹•Ð ‰Í½ÕÉ•}Ñ…‰±•Ìˆ¤°M•ÅÕ•¹”¤•±Í”€ ¤è(€€€€€€€€€€€€€€€€€€€Ñ…‰±•Ì¹…‘¡ÍÑÈ¡¹•ÍÑ•¤¤(€€€É•ÑÕÉ¸Ñ…‰±•Ì)‘•˜}•Ù¥‘•¹•}½±Õµ¹Ì¡•Ù¥‘•¹”èM•ÅÕ•¹•m½‰©•Ñt¤€´øÍ•ÑmÍÑÉtè(€€€É•ÑÕÉ¸íÍÑÈ¡¥Ñ•´¹•Ð ‰Í½ÕÉ•}½±Õµ¸ˆ¤¤™½È¥Ñ•´¥¸•Ù¥‘•¹”¥˜¥Í¥¹ÍÑ…¹”¡¥Ñ•´°5…ÁÁ¥¹œ¤…¹¥Ñ•´¹•Ð ‰Í½ÕÉ•}½±Õµ¸ˆ¥ô)‘•˜}•Ù¥‘•¹•}Ù…±Õ•Ì¡•Ù¥‘•¹”èM•ÅÕ•¹•m½‰©•Ñt°­•äèÍÑÈ¤€´ø±¥ÍÑm½‰©•Ñtè(€€€É•ÑÕÉ¸m¥Ñ•´¹•Ð¡­•ä¤™½È¥Ñ•´¥¸•Ù¥‘•¹”¥˜¥Í¥¹ÍÑ…¹”¡¥Ñ•´°5…ÁÁ¥¹œ¤…¹­•ä¥¸¥Ñ•µt)‘•˜}¥¹‘•á}É½ÝÌ¡É½ÝÌèM•ÅÕ•¹•m5…ÁÁ¥¹mÍÑÈ°½‰©•Ñut°­•äèÍÑÈ¤€´ø‘¥Ñm½‰©•Ð°ÑÕÁ±•m5…ÁÁ¥¹mÍÑÈ°½‰©•Ñt°€¸¸¹utè(€€€É½ÕÁ•è‘¥Ñm½‰©•Ð°±¥ÍÑm5…ÁÁ¥¹mÍÑÈ°½‰©•Ñuut€ô‘•™…Õ±Ñ‘¥Ð¡±¥ÍÐ¤(€€€™½ÈÉ½Ü¥¸É½ÝÌè(€€€€€€€É½ÕÁ•‘mÉ½Ü¹•Ð¡­•ä¥t¹…ÁÁ•¹¡É½Ü¤(€€€É•ÑÕÉ¸íÙ…±Õ”èÑÕÁ±”¡¥Ñ•µÌ¤™½ÈÙ…±Õ”°¥Ñ•µÌ¥¸É½ÕÁ•¹¥Ñ•µÌ ¥ô)‘•˜}É½ÝÌ¡Í½ÕÉ”è5…ÁÁ¥¹mÍÑÈ°½‰©•Ñt°­•äèÍÑÈ¤€´ø±¥ÍÑm5…ÁÁ¥¹mÍÑÈ°½‰©•Ñutè(€€€Ù…±Õ”€ôÍ½ÕÉ”¹•Ð¡­•ä°€ ¤¤(€€€É•ÑÕÉ¸m‘¥Ð¡¥Ñ•´¤™½È¥Ñ•´¥¸Ù…±Õ”¥˜¥Í¥¹ÍÑ…¹”¡¥Ñ•´°5…ÁÁ¥¹œ¥t¥˜¥Í¥¹ÍÑ…¹”¡Ù…±Õ”°M•ÅÕ•¹”¤…¹¹½Ð¥Í¥¹ÍÑ…¹”¡Ù…±Õ”°€¡ÍÑÈ°‰åÑ•Ì°‰åÑ•…ÉÉ…ä¤¤•±Í”mt)‘•˜}Ý½ÉÍÑ}ÍÑ…ÑÕÌ¡ÍÑ…ÑÕÍ•ÌèM•ÅÕ•¹•mÍÑÉtð¹ä¤€´øÍÑÈè(€€€Ù…±Õ•Ì€ô±¥ÍÐ¡ÍÑ…ÑÕÍ•Ì¤(€€€É•ÑÕÉ¸µ…à¡Ù…±Õ•Ì°­•äõ±…µ‰‘„Ù…±Õ”è}MQQUM}AI%=I%Qd¹•Ð¡Ù…±Õ”°€À¤¤¥˜Ù…±Õ•Ì•±Í”€‰9=}Qˆ)‘•˜}É…Ñ¥¼¡¹Õµ•É…Ñ½Èè½‰©•Ð°‘•¹½µ¥¹…Ñ½Èè½‰©•Ð¤€´ø™±½…Ðð9½¹”è(€€€É•ÑÕÉ¸™±½…Ð¡¹Õµ•É…Ñ½È¤€¼™±½…Ð¡‘•¹½µ¥¹…Ñ½È¤¥˜}™¥¹¥Ñ”¡¹Õµ•É…Ñ½È¤…¹}™¥¹¥Ñ”¡‘•¹½µ¥¹…Ñ½È¤…¹™±½…Ð¡‘•¹½µ¥¹…Ñ½È¤€„ô€À•±Í”9½¹”)‘•˜}¹Õµ‰•È¡Ù…±Õ”è½‰©•Ð¤€´ø™±½…Ðð9½¹”è(€€€¥˜¥Í¥¹ÍÑ…¹”¡Ù…±Õ”°‰½½°¤è(€€€€€€€É•ÑÕÉ¸9½¹”(€€€¥˜¥Í¥¹ÍÑ…¹”¡Ù…±Õ”°€¡¥¹Ð°™±½…Ð¤¤è(€€€€€€€É•ÑÕÉ¸™±½…Ð¡Ù…±Õ”¤¥˜µ…Ñ ¹¥Í™¥¹¥Ñ”¡™±½…Ð¡Ù…±Õ”¤¤•±Í”9½¹”(€€€¥˜¥Í¥¹ÍÑ…¹”¡Ù…±Õ”°ÍÑÈ¤…¹}9U5I%}I¹™Õ±±µ…Ñ ¡Ù…±Õ”¤è(€€€€€€€Á…ÉÍ•€ô™±½…Ð¡Ù…±Õ”¤(€€€€€€€É•ÑÕÉ¸Á…ÉÍ•¥˜µ…Ñ ¹¥Í™¥¹¥Ñ”¡Á…ÉÍ•¤•±Í”9½¹”(€€€É•ÑÕÉ¸9½¹”)‘•˜}™¥¹¥Ñ”¡Ù…±Õ”è½‰©•Ð¤€´ø‰½½°è(€€€É•ÑÕÉ¸}¹Õµ‰•È¡Ù…±Õ”¤¥Ì¹½Ð9½¹”)‘•˜}Ñ•áÐ¡Ù…±Õ”è½‰©•Ð¤€´øÍÑÈè(€€€É•ÑÕÉ¸€ˆˆ¥˜Ù…±Õ”¥Ì9½¹”•±Í”ÍÑÈ¡Ù…±Õ”¤¹ÍÑÉ¥À ¤)‘•˜}Í¹…ÁÍ¡½Ñ}­•ä¡É½Üè5…ÁÁ¥¹mÍÑÈ°½‰©•Ñt¤€´øÑÕÁ±•mÍÑÈ°ÍÑÈ°ÍÑÈ°ÍÑÉtè(€€€É•ÑÕÉ¸€¡ÍÑÈ¡É½Ü¹•Ð ‰½µÁ½¹•¹Ñ}ÑåÁ”ˆ°€ˆˆ¤¤°ÍÑÈ¡}¥‘•¹Ñ¥Ñä¡É½Ü°€‰ÍÑ½Éäˆ¤½È€ˆˆ¤°ÍÑÈ¡}Í•Ñ¥½¸¡É½Ü¤½È€ˆˆ¤°ÍÑÈ¡É½Ü¹•Ð ‰½µÁ½¹•¹Ñ}¥ˆ°€ˆˆ¤¤¤)‘•˜}¡•­}­•ä¡É½Üè5…ÁÁ¥¹mÍÑÈ°½‰©•Ñt¤€´øÑÕÁ±•mÍÑÈ°ÍÑÈ°ÍÑÈ°ÍÑÉtè(€€€É•ÑÕÉ¸€¡ÍÑÈ¡É½Ü¹•Ð ‰½µÁ½¹•¹Ñ}ÑåÁ”ˆ°€ˆˆ¤¤°ÍÑÈ¡É½Ü¹•Ð ‰Í•Ñ¥½¸ˆ¤½È€ˆˆ¤°ÍÑÈ¡É½Ü¹•Ð ‰½µÁ½¹•¹Ðˆ°€ˆˆ¤¤°ÍÑÈ¡É½Ü¹•Ð ‰¡•­}¥ˆ°€ˆˆ¤¤¤)‘•˜}‘¥…¹½ÍÑ¥}­•ä¡É½Üè5…ÁÁ¥¹mÍÑÈ°½‰©•Ñt¤€´øÑÕÁ±•mÍÑÈ°ÍÑÈ°ÍÑÉtè(€€€É•ÑÕÉ¸€¡ÍÑÈ¡É½Ü¹•Ð ‰½‘”ˆ°€ˆˆ¤¤°ÍÑÈ¡É½Ü¹•Ð ‰½µÁ½¹•¹Ñ}ÑåÁ”ˆ°€ˆˆ¤¤°ÍÑÈ¡É½Ü¹•Ð ‰½µÁ½¹•¹Ñ}¥ˆ°€ˆˆ¤¤¤)‘•˜}ÁÉ•Á…É•}½Ý¹•‘}½ÕÑÁÕÑÌ¡É½½ÐèA…Ñ ¤€´ø9½¹”è(€€€É½½Ð¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”°•á¥ÍÑ}½¬õQÉÕ”¤(€€€™½È¹…µ”¥¸€ ‰É•Á½ÉÐˆ°€‰…ÉÑ¥™…ÑÌˆ¤è(€€€€€€€Á…Ñ €ôÉ½½Ð€¼¹…µ”(€€€€€€€¥˜Á…Ñ ¹¥Í}Íåµ±¥¹¬ ¤½ÈÁ…Ñ ¹¥Í}™¥±” ¤è(€€€€€€€€€€€Á…Ñ ¹Õ¹±¥¹¬ ¤(€€€€€€€•±¥˜Á…Ñ ¹¥Í}‘¥È ¤è(€€€€€€€€€€€Í¡ÕÑ¥°¹ÉµÑÉ•”¡Á…Ñ ¤)‘•˜}É•…‘}©Í½¸¡Á…Ñ èA…Ñ ¤€´ø½‰©•Ðè(€€€É•ÑÕÉ¸©Í½¸¹±½…‘Ì¡Á…Ñ ¹É•…‘}Ñ•áÐ¡•¹½‘¥¹œô‰ÕÑ˜´àˆ¤¤)‘•˜}ÝÉ¥Ñ•}©Í½¸¡Á…Ñ èA…Ñ °Á…å±½…è½‰©•Ð¤€´ø9½¹”è(€€€Á…Ñ ¹Á…É•¹Ð¹µ­‘¥È¡Á…É•¹ÑÌõQÉÕ”°•á¥ÍÑ}½¬õQÉÕ”¤(€€€Á…Ñ ¹ÝÉ¥Ñ•}Ñ•áÐ¡©Í½¸¹‘ÕµÁÌ¡Á…å±½…°¥¹‘•¹ÐôÈ°Í½ÉÑ}­•åÌõQÉÕ”°•¹ÍÕÉ•}…Í¥¤õ…±Í”¤€¬€‰q¸ˆ°•¹½‘¥¹œô‰ÕÑ˜´àˆ¤)}}…±±}|€ôl(€€€€‰ÉÕ¹}±¥Ù•}‰•…µ}½±Õµ¹}µ¥¹¥µÕµ}½µÁ±¥…¹”ˆ°(€€€€‰}•Ù…±Õ…Ñ•}…‰Í½±ÕÑ•}‰•…µ}‘•ÁÑ ˆ°€‰}•Ù…±Õ…Ñ•}‘•ÁÑ¡}ÙÍ}Í±…ˆˆ°€‰}•Ù…±Õ…Ñ•}Ý•‰}‘•Ñ…¥±¥¹}ÑÉ¥•Èˆ°)t(