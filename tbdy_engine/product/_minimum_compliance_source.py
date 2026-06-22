"""C14.1-P1 locked source loading and inventory classification."""
from __future__ import annotations
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
import shutil
from tbdy_engine.features.etabs_com_attach import EtabsAttachResult
from tbdy_engine.features.live_etabs_concrete_material_probe import ConcreteMaterialProbeInput, FixtureConcreteMaterialProbeProvider, create_live_etabs_concrete_material_provider, probe_concrete_material_feature_snapshots
from tbdy_engine.features.live_etabs_geometry_probe import read_live_etabs_table_for_geometry
from tbdy_engine.product._minimum_compliance_util import _read_json, _index_rows, _text, _worst_status
_COMPONENT_TABLE = "Frame Assignments - Summary"
_ASSIGNMENT_TABLE = "Frame Assignments - Section Properties"
_SECTION_TABLE = "Frame Section Property Definitions - Concrete Rectangular"
_CONNECTIVITY_TABLE = "Beam Object Connectivity"
_OFFSET_TABLE = "Frame Assignments - End Length Offsets"
class _ExactColumnsAdapter:
    def __init__(self, database_tables: object, required_columns: frozenset[str]) -> None:
        self._database_tables = database_tables
        self._required_columns = required_columns
    def GetTableForDisplayArray(self, table_key: str, *args: object) -> object:
        raw_result = self._database_tables.GetTableForDisplayArray(table_key, *args)
        return _exact_table_mapping(raw_result, self._required_columns)
def _exact_table_mapping(raw_result: object, required_columns: frozenset[str]) -> object:
    if isinstance(raw_result, Mapping):
        return raw_result
    if not isinstance(raw_result, Sequence) or isinstance(raw_result, (str, bytes, bytearray)):
        return raw_result
    sequences = tuple(item for item in raw_result if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)))
    for index, sequence in enumerate(sequences):
        if not all(isinstance(value, str) for value in sequence):
            continue
        columns = tuple(str(value) for value in sequence)
        if not required_columns.issubset(set(columns)):
            continue
        for flat_data in sequences[index + 1:]:
            if tuple(flat_data) != columns:
                return {"columns": list(columns), "flat_data": list(flat_data)}
        return {"columns": list(columns), "flat_data": []}
    return raw_result
def _load_live_source(attach_result: EtabsAttachResult, work_dir: Path) -> Mapping[str, object]:
    sap_model = attach_result.sap_model
    if sap_model is None:
        raise RuntimeError("ETABS attach succeeded without SapModel")
    database_tables = sap_model.DatabaseTables
    provider = create_live_etabs_concrete_material_provider(attach_result=attach_result)
    probe_input = provider.read_probe_input()
    fixture_provider = FixtureConcreteMaterialProbeProvider(ConcreteMaterialProbeInput(
        geometry_rows=probe_input.geometry_rows, section_columns=probe_input.section_columns,
        material_rows=probe_input.material_rows, material_columns=probe_input.material_columns,
        material_table_status=probe_input.material_table_status, unit_evidence=probe_input.unit_evidence,
        source_diagnostics=probe_input.source_diagnostics,
    ))
    probe_result = probe_concrete_material_feature_snapshots(provider=fixture_provider, output_dir=work_dir, max_rows=max(1, len(probe_input.geometry_rows)))
    payload = _read_json(probe_result.feature_snapshot_path)
    diagnostics = _read_json(probe_result.diagnostics_path)
    table_rows = {}
    table_specs = (
        ("component_rows", _COMPONENT_TABLE, frozenset()),
        ("assignment_rows", _ASSIGNMENT_TABLE, frozenset()),
        ("section_rows", _SECTION_TABLE, frozenset()),
        ("connectivity_rows", _CONNECTIVITY_TABLE, frozenset({"UniqueName", "Length"})),
        ("offset_rows", _OFFSET_TABLE, frozenset({"UniqueName", "OffsetI", "OffsetJ"})),
    )
    for key, table_name, required_columns in table_specs:
        table_source = _ExactColumnsAdapter(database_tables, required_columns) if required_columns else database_tables
        result = read_live_etabs_table_for_geometry(table_source, table_name)
        table_rows[key] = [dict(row) for row in result.rows]
        if result.status != "FETCHED":
            diagnostics.append({"status": "NO_DATA" if result.status == "EMPTY" else "BLOCKED", "code": "PRODUCT_SOURCE_TABLE_UNAVAILABLE", "source_table": table_name, "message": result.message or f"{table_name} is unavailable"})
    shutil.rmtree(work_dir, ignore_errors=True)
    return {**table_rows, "material_rows": [dict(row) for row in probe_input.material_rows], "snapshots": list(payload.get("snapshots", [])) if isinstance(payload, Mapping) else [], "source_diagnostics": diagnostics if isinstance(diagnostics, list) else [], "unit_evidence": probe_input.unit_evidence}
def _build_inventory(component_rows: Sequence[Mapping[str, object]], assignment_rows: Sequence[Mapping[str, object]], element_type: str | None, story: str | None, section: str | None) -> list[dict[str, object]]:
    assignments = _index_rows(assignment_rows, "UniqueName")
    inventory: list[dict[str, object]] = []
    for row in component_rows:
        unique_raw, type_raw = row.get("UniqueName"), row.get("Type")
        if unique_raw in (None, "") or type_raw not in {"Beam", "Column", "Brace", "Null"}:
            continue
        raw_type = str(type_raw)
        if element_type and raw_type.casefold() != element_type:
            continue
        matches = assignments.get(unique_raw, ())
        if story is not None and not any(item.get("Story") == story for item in matches):
            continue
        if section is not None and not any(item.get("SectProp") == section for item in matches):
            continue
        first = matches[0] if matches else {}
        inventory.append({"unique_name": str(unique_raw), "join_unique_name": unique_raw, "raw_type": raw_type, "element_type": raw_type.casefold(), "assignment_rows": [dict(item) for item in matches], "story": first.get("Story"), "label": first.get("Label"), "section": first.get("SectProp"), "section_raw": first.get("SectProp"), "shape": first.get("Shape")})
    inventory.sort(key=lambda item: (str(item["raw_type"]), str(item.get("story") or ""), str(item.get("label") or ""), str(item["unique_name"])))
    return inventory
def _classify_inventory(*, inventory: Sequence[Mapping[str, object]], section_rows: Sequence[Mapping[str, object]], material_rows: Sequence[Mapping[str, object]], snapshot_by_component: Mapping[str, Mapping[str, object]], source_diagnostics: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    sections = _index_rows(section_rows, "Name")
    materials = _index_rows(material_rows, "Material")
    diagnostics_by_component: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for diagnostic in source_diagnostics:
        component_id = _text(diagnostic.get("component_id"))
        if component_id:
            diagnostics_by_component[component_id].append(diagnostic)
    output: list[dict[str, object]] = []
    for item in inventory:
        unique = str(item["unique_name"])
        base = {key: item.get(key) for key in ("unique_name", "element_type", "story", "label", "section", "shape")}
        if item["raw_type"] in {"Brace", "Null"}:
            output.append({**base, "status": "OUT_OF_SCOPE", "section_family": item["raw_type"], "reason": f"{item['raw_type']} objects are outside beam/column engineering scope"}); continue
        assignment_matches = item.get("assignment_rows") or []
        if not assignment_matches:
            output.append({**base, "status": "NO_DATA", "section_family": None, "reason": "Section assignment is missing"}); continue
        if len(assignment_matches) > 1:
            output.append({**base, "status": "BLOCKED", "section_family": item.get("shape"), "reason": "Duplicate section assignment rows"}); continue
        section_matches = sections.get(item.get("section_raw"), ())
        if not section_matches:
            shape = _text(item.get("shape"))
            status = "OUT_OF_SCOPE" if shape and shape != "Concrete Rectangular" else "NO_DATA"
            reason = f"Section belongs to {shape} family" if status == "OUT_OF_SCOPE" else "Concrete Rectangular definition is missing"
            output.append({**base, "status": status, "section_family": shape or None, "reason": reason}); continue
        if len(section_matches) > 1:
            output.append({**base, "status": "BLOCKED", "section_family": "Concrete Rectangular", "reason": "Duplicate Concrete Rectangular definitions"}); continue
        material_name = section_matches[0].get("Material")
        material_matches = materials.get(material_name, ())
        base["material"] = material_name
        if material_name in (None, ""):
            output.append({**base, "status": "NO_DATA", "section_family": "Concrete Rectangular", "reason": "Section material is missing"}); continue
        if not material_matches:
            output.append({**base, "status": "NO_DATA", "section_family": "Concrete Rectangular", "reason": "Concrete material definition is missing"}); continue
        if len(material_matches) > 1:
            output.append({**base, "status": "BLOCKED", "section_family": "Concrete Rectangular", "reason": "Duplicate concrete material definitions"}); continue
        if material_matches[0].get("Fc") in (None, ""):
            output.append({**base, "status": "NO_DATA", "section_family": "Concrete Rectangular", "reason": "Concrete Fc is missing"}); continue
        if unique not in snapshot_by_component:
            diagnostic_status = _worst_status(str(row.get("status", "BLOCKED")) for row in diagnostics_by_component.get(unique, ()))
            output.append({**base, "status": diagnostic_status if diagnostic_status in {"BLOCKED", "NO_DATA"} else "BLOCKED", "section_family": "Concrete Rectangular", "reason": "Geometry/material resolver did not emit a usable snapshot"}); continue
        output.append({**base, "status": "SUPPORTED", "section_family": "Concrete Rectangular", "reason": "Supported"})
    return output
__all__ = ["_load_live_source", "_build_inventory", "_classify_inventory"]
