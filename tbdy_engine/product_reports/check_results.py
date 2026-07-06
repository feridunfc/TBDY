"""Formal CheckResult artifact builder for the P2.6 product slice.

P2.6 promotes the already-executed P2.0-P2.5 product logic into explicit,
machine-readable CheckResult artifacts.  It does not introduce a CheckEngine,
does not add new engineering checks, and does not claim full TBDY compliance.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

FULL_TBDY_STATUS = "NOT_EVALUATED"
CHECKED_OBJECT_STATUS = {"OK": "PASS", "FAIL": "FAIL", "NO_DATA": "NO_DATA"}

BEAM_CHECK_ID = "CONCRETE_BEAM_MIN_GEOMETRY"
COLUMN_CHECK_ID = "CONCRETE_COLUMN_MIN_GEOMETRY"
MODAL_CHECK_ID = "MODAL_MASS_PARTICIPATION"

BEAM_LIMIT_CONTRACT_ID = "CONCRETE_BEAM_MIN_GEOMETRY_LIMITS_V1"
COLUMN_LIMIT_CONTRACT_ID = "CONCRETE_COLUMN_MIN_GEOMETRY_LIMITS_V1"
MODAL_LIMIT_CONTRACT_ID = "MODAL_MASS_PARTICIPATION_LIMITS_V1"


def _status_from_product_status(status: Any) -> str:
    return CHECKED_OBJECT_STATUS.get(str(status or "NO_DATA"), "NO_DATA")


def _overall_status(statuses: Sequence[str]) -> str:
    if not statuses:
        return "NO_DATA"
    if "FAIL" in statuses:
        return "FAIL"
    if "BLOCKED" in statuses:
        return "BLOCKED"
    if "NO_DATA" in statuses:
        return "NO_DATA"
    return "PASS"


def _input_status_for_status(status: str) -> str:
    if status in {"PASS", "FAIL"}:
        return "RESOLVED"
    if status == "NO_DATA":
        return "NO_DATA"
    if status == "BLOCKED":
        return "BLOCKED_INPUT"
    return "NOT_REQUIRED"


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _section_key(element_type: str, section: Any) -> tuple[str, str]:
    return str(element_type), str(section or "")


def _section_material_map(material_evidence_rows: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], Mapping[str, Any]]:
    out: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in material_evidence_rows:
        if not isinstance(row, Mapping):
            continue
        out[_section_key(str(row.get("element_type") or ""), row.get("section"))] = row
    return out


def _detail_rows_by_section(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    out: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if isinstance(row, Mapping):
            out[str(row.get("section") or "")].append(row)
    return dict(out)


def _geometry_row_map(report: Mapping[str, Any], element_type: str) -> dict[str, Mapping[str, Any]]:
    key = "concrete_beam_section_geometry_checks" if element_type == "Beam" else "concrete_column_section_geometry_checks"
    out: dict[str, Mapping[str, Any]] = {}
    for row in report.get(key, []) or []:
        if isinstance(row, Mapping):
            out[str(row.get("section") or "")] = row
    return out


def build_check_catalog() -> dict[str, Any]:
    return {
        "schema_version": "check_catalog.v1",
        "artifact_type": "CHECK_CATALOG",
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        "checks": [
            {
                "check_id": BEAM_CHECK_ID,
                "check_title": "Concrete beam minimum geometry",
                "check_family": "CONCRETE_BEAM_GEOMETRY",
                "check_level": "OBJECT",
                "implemented_in_product_slice": True,
                "result_file": "check_results_concrete_beam_min_geometry.json",
                "scope_note": "Concrete rectangular beam assignments only.",
                "code_clause_status": "PENDING_CLAUSE_BINDING",
            },
            {
                "check_id": COLUMN_CHECK_ID,
                "check_title": "Concrete column minimum geometry",
                "check_family": "CONCRETE_COLUMN_GEOMETRY",
                "check_level": "OBJECT",
                "implemented_in_product_slice": True,
                "result_file": "check_results_concrete_column_min_geometry.json",
                "scope_note": "Concrete rectangular column assignments only.",
                "code_clause_status": "PENDING_CLAUSE_BINDING",
            },
            {
                "check_id": MODAL_CHECK_ID,
                "check_title": "Modal mass participation",
                "check_family": "MODAL_DYNAMIC_CHECKS",
                "check_level": "MODEL",
                "implemented_in_product_slice": True,
                "result_file": "check_results_modal_mass_participation.json",
                "scope_note": "UX and UY cumulative modal mass ratios from the available ETABS modal mass table.",
                "code_clause_status": "PENDING_CLAUSE_BINDING",
            },
        ],
    }


def build_check_limit_contract() -> dict[str, Any]:
    return {
        "schema_version": "check_limit_contract.v1",
        "artifact_type": "CHECK_LIMIT_CONTRACT",
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        "contracts": [
            {
                "contract_id": BEAM_LIMIT_CONTRACT_ID,
                "check_id": BEAM_CHECK_ID,
                "code_clause_status": "PENDING_CLAUSE_BINDING",
                "limits": {"min_width_mm": 250.0, "min_depth_mm": 300.0, "max_h_over_bw": 3.5},
                "units": {"width": "mm", "depth": "mm", "h_over_bw": "ratio"},
                "status_semantics": {
                    "pass": "All subchecks pass according to the frozen product limit contract.",
                    "fail": "At least one subcheck fails according to the frozen product limit contract.",
                    "blocked": "Required inputs are unavailable.",
                },
            },
            {
                "contract_id": COLUMN_LIMIT_CONTRACT_ID,
                "check_id": COLUMN_CHECK_ID,
                "code_clause_status": "PENDING_CLAUSE_BINDING",
                "limits": {"min_dimension_mm": 300.0, "min_area_mm2": 75000.0, "min_aspect_ratio": 0.4},
                "units": {"dimension": "mm", "area": "mm2", "aspect_ratio": "ratio"},
                "status_semantics": {
                    "pass": "All subchecks pass according to the frozen product limit contract.",
                    "fail": "At least one subcheck fails according to the frozen product limit contract.",
                    "blocked": "Required inputs are unavailable.",
                },
            },
            {
                "contract_id": MODAL_LIMIT_CONTRACT_ID,
                "check_id": MODAL_CHECK_ID,
                "code_clause_status": "PENDING_CLAUSE_BINDING",
                "limits": {"modal_mass_threshold": 0.95},
                "units": {"modal_mass": "ratio"},
                "status_semantics": {
                    "pass": "UX and UY cumulative modal mass values pass according to the frozen product limit contract.",
                    "fail": "At least one of UX or UY cumulative modal mass values fails according to the frozen product limit contract.",
                    "no_data": "The modal mass table or cumulative values are unavailable.",
                },
            },
        ],
    }


def _beam_subcheck(detail: Mapping[str, Any]) -> dict[str, Any]:
    mapping = {
        "beam_geometry_min_width": ("beam_min_width", "Minimum beam width", ">="),
        "beam_geometry_min_depth": ("beam_min_depth", "Minimum beam depth", ">="),
        "beam_depth_width_ratio": ("beam_depth_width_ratio", "Beam depth/width ratio", "<="),
    }
    subcheck_id, title, operator = mapping.get(str(detail.get("check_id")), (str(detail.get("check_id")), str(detail.get("check_title") or ""), ""))
    return {
        "subcheck_id": subcheck_id,
        "title": title,
        "value": detail.get("value"),
        "limit": detail.get("limit"),
        "unit": detail.get("unit"),
        "operator": operator,
        "comparison": detail.get("comparison"),
        "ratio": detail.get("ratio"),
        "status": _status_from_product_status(detail.get("status")),
    }


def _column_subcheck(detail: Mapping[str, Any]) -> dict[str, Any]:
    mapping = {
        "column_geometry_min_dimension": ("column_min_dimension", "Minimum column dimension", ">="),
        "column_geometry_min_area": ("column_min_area", "Minimum column area", ">="),
        "column_geometry_aspect_ratio": ("column_aspect_ratio", "Column aspect ratio", ">="),
    }
    subcheck_id, title, operator = mapping.get(str(detail.get("check_id")), (str(detail.get("check_id")), str(detail.get("check_title") or ""), ""))
    return {
        "subcheck_id": subcheck_id,
        "title": title,
        "value": detail.get("value"),
        "limit": detail.get("limit"),
        "unit": detail.get("unit"),
        "operator": operator,
        "comparison": detail.get("comparison"),
        "ratio": detail.get("ratio"),
        "status": _status_from_product_status(detail.get("status")),
    }


def _object_result_id(check_id: str, ledger_row: Mapping[str, Any]) -> str:
    label = str(ledger_row.get("object_label") or "UNKNOWN_LABEL")
    story = str(ledger_row.get("story") or "UNKNOWN_STORY")
    object_id = str(ledger_row.get("object_id") or ledger_row.get("source_row_index") or "UNKNOWN_OBJECT")
    return f"{check_id}:{label}:{story}:{object_id}"


def _object_payload(ledger_row: Mapping[str, Any], element_type: str, geometry_row: Mapping[str, Any] | None, material_row: Mapping[str, Any] | None) -> dict[str, Any]:
    section_type = "ConcreteRectangular" if geometry_row else None
    return {
        "object_id": ledger_row.get("object_id"),
        "object_label": ledger_row.get("object_label"),
        "object_type": element_type,
        "story": ledger_row.get("story"),
        "section": ledger_row.get("section"),
        "section_type": section_type,
        "material": material_row.get("material_name") if isinstance(material_row, Mapping) else None,
    }


def _input_refs(ledger_row: Mapping[str, Any], element_type: str, material_row: Mapping[str, Any] | None) -> dict[str, Any]:
    section = ledger_row.get("section")
    refs: dict[str, Any] = {
        "object_scope_row": ledger_row.get("source_row_index"),
        "object_scope_reference": ledger_row.get("stable_source_reference"),
        "section_geometry_ref": f"Frame Section Property Definitions - Concrete Rectangular:section={section}",
    }
    if isinstance(material_row, Mapping) and material_row.get("material_name"):
        refs["material_ref"] = f"Material Properties - Concrete Data:material={material_row.get('material_name')}"
        refs["material_source_row_index"] = material_row.get("source_row_index")
    return refs


def _beam_object_result(ledger_row: Mapping[str, Any], details: Sequence[Mapping[str, Any]], geometry_row: Mapping[str, Any] | None, material_row: Mapping[str, Any] | None) -> dict[str, Any]:
    subchecks = [_beam_subcheck(row) for row in details]
    status = _overall_status([row["status"] for row in subchecks])
    values = {
        "width_mm": geometry_row.get("width_mm") if geometry_row else None,
        "depth_mm": geometry_row.get("depth_mm") if geometry_row else None,
        "h_over_bw": geometry_row.get("h_over_bw_value") if geometry_row else None,
    }
    return {
        "schema_version": "check_result.v1",
        "artifact_type": "OBJECT_CHECK_RESULT",
        "check_id": BEAM_CHECK_ID,
        "check_title": "Concrete beam minimum geometry",
        "check_family": "CONCRETE_BEAM_GEOMETRY",
        "check_level": "OBJECT",
        "result_id": _object_result_id(BEAM_CHECK_ID, ledger_row),
        "object": _object_payload(ledger_row, "Beam", geometry_row, material_row),
        "scope": {"scope_status": "CHECKED", "scope_reason": "Concrete rectangular beam assignment is inside this check scope."},
        "input": {"input_status": _input_status_for_status(status), "missing_inputs": [], "input_refs": _input_refs(ledger_row, "Beam", material_row)},
        "status": status,
        "subchecks": subchecks,
        "values": values,
        "limits": {"min_width_mm": 250.0, "min_depth_mm": 300.0, "max_h_over_bw": 3.5},
        "comparisons": {"width": geometry_row.get("width_check_status") and f"{geometry_row.get('width_value_mm')} >= {geometry_row.get('width_limit_mm')}", "depth": geometry_row.get("depth_check_status") and f"{geometry_row.get('depth_value_mm')} >= {geometry_row.get('depth_limit_mm')}", "h_over_bw": geometry_row.get("h_over_bw_status") and f"{geometry_row.get('h_over_bw_value')} <= {geometry_row.get('h_over_bw_limit')}"} if geometry_row else {},
        "limit_contract": {"contract_id": BEAM_LIMIT_CONTRACT_ID, "contract_file": "check_limit_contract.json", "code_clause_status": "PENDING_CLAUSE_BINDING"},
        "diagnostics": {"warnings": [], "notes": ["Status is according to frozen product limit contract, not full TBDY compliance."]},
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
    }


def _column_object_result(ledger_row: Mapping[str, Any], details: Sequence[Mapping[str, Any]], geometry_row: Mapping[str, Any] | None, material_row: Mapping[str, Any] | None) -> dict[str, Any]:
    subchecks = [_column_subcheck(row) for row in details]
    status = _overall_status([row["status"] for row in subchecks])
    values = {
        "width_mm": geometry_row.get("width_mm") if geometry_row else None,
        "depth_mm": geometry_row.get("depth_mm") if geometry_row else None,
        "min_dimension_mm": geometry_row.get("min_dimension_value_mm") if geometry_row else None,
        "area_mm2": geometry_row.get("area_value_mm2") if geometry_row else None,
        "aspect_ratio": geometry_row.get("aspect_ratio_value") if geometry_row else None,
    }
    return {
        "schema_version": "check_result.v1",
        "artifact_type": "OBJECT_CHECK_RESULT",
        "check_id": COLUMN_CHECK_ID,
        "check_title": "Concrete column minimum geometry",
        "check_family": "CONCRETE_COLUMN_GEOMETRY",
        "check_level": "OBJECT",
        "result_id": _object_result_id(COLUMN_CHECK_ID, ledger_row),
        "object": _object_payload(ledger_row, "Column", geometry_row, material_row),
        "scope": {"scope_status": "CHECKED", "scope_reason": "Concrete rectangular column assignment is inside this check scope."},
        "input": {"input_status": _input_status_for_status(status), "missing_inputs": [], "input_refs": _input_refs(ledger_row, "Column", material_row)},
        "status": status,
        "subchecks": subchecks,
        "values": values,
        "limits": {"min_dimension_mm": 300.0, "min_area_mm2": 75000.0, "min_aspect_ratio": 0.4},
        "comparisons": {"min_dimension": geometry_row.get("min_dimension_status") and f"{geometry_row.get('min_dimension_value_mm')} >= {geometry_row.get('min_dimension_limit_mm')}", "area": geometry_row.get("area_status") and f"{geometry_row.get('area_value_mm2')} >= {geometry_row.get('area_limit_mm2')}", "aspect_ratio": geometry_row.get("aspect_ratio_status") and f"{geometry_row.get('aspect_ratio_value')} >= {geometry_row.get('aspect_ratio_limit')}"} if geometry_row else {},
        "limit_contract": {"contract_id": COLUMN_LIMIT_CONTRACT_ID, "contract_file": "check_limit_contract.json", "code_clause_status": "PENDING_CLAUSE_BINDING"},
        "diagnostics": {"warnings": [], "notes": ["Status is according to frozen product limit contract, not full TBDY compliance."]},
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
    }


def _section_summary(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for result in results:
        obj = result.get("object") if isinstance(result.get("object"), Mapping) else {}
        grouped[str(obj.get("section") or "")].append(result)
    rows = []
    for section in sorted(grouped):
        section_results = grouped[section]
        pass_count = sum(1 for result in section_results if result.get("status") == "PASS")
        fail_count = sum(1 for result in section_results if result.get("status") == "FAIL")
        no_data_count = sum(1 for result in section_results if result.get("status") == "NO_DATA")
        rows.append({
            "section": section,
            "checked_object_count": len(section_results),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "no_data_count": no_data_count,
            "status": _overall_status([str(result.get("status")) for result in section_results]),
        })
    return rows


def _unsupported_objects(report: Mapping[str, Any], element_type: str) -> list[dict[str, Any]]:
    key = "unsupported_beam_sections" if element_type == "Beam" else "unsupported_column_sections"
    count_key = "assigned_beam_count" if element_type == "Beam" else "assigned_column_count"
    rows = []
    for row in report.get(key, []) or []:
        if not isinstance(row, Mapping):
            continue
        rows.append({
            "object_type": element_type,
            "section": row.get("section"),
            "assigned_object_count": row.get(count_key, 0),
            "stories": _as_list(row.get("stories")),
            "sample_labels": _as_list(row.get("sample_labels")),
            "scope_status": "UNSUPPORTED",
            "status": "NOT_APPLICABLE",
            "input_status": "NOT_REQUIRED",
            "reason": row.get("reason"),
        })
    return rows


def build_object_check_result_file(*, check_id: str, element_type: str, report: Mapping[str, Any], object_scope_ledger: Sequence[Mapping[str, Any]], material_evidence_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    is_beam = element_type == "Beam"
    checked_bucket = "CHECKED_CONCRETE_BEAM" if is_beam else "CHECKED_CONCRETE_COLUMN"
    detail_key = "beam_section_detail" if is_beam else "column_section_detail"
    title = "Concrete beam minimum geometry" if is_beam else "Concrete column minimum geometry"
    family = "CONCRETE_BEAM_GEOMETRY" if is_beam else "CONCRETE_COLUMN_GEOMETRY"
    geometry_by_section = _geometry_row_map(report, element_type)
    detail_by_section = _detail_rows_by_section(report.get(detail_key, []) or [])
    material_by_section = _section_material_map(material_evidence_rows)
    results = []
    for ledger_row in object_scope_ledger:
        if not isinstance(ledger_row, Mapping) or ledger_row.get("scope_bucket") != checked_bucket:
            continue
        section = str(ledger_row.get("section") or "")
        geometry_row = geometry_by_section.get(section)
        material_row = material_by_section.get(_section_key(element_type, section))
        details = detail_by_section.get(section, [])
        if is_beam:
            results.append(_beam_object_result(ledger_row, details, geometry_row, material_row))
        else:
            results.append(_column_object_result(ledger_row, details, geometry_row, material_row))
    pass_count = sum(1 for result in results if result.get("status") == "PASS")
    fail_count = sum(1 for result in results if result.get("status") == "FAIL")
    no_data_count = sum(1 for result in results if result.get("status") == "NO_DATA")
    blocked_count = sum(1 for result in results if result.get("status") == "BLOCKED")
    unsupported = _unsupported_objects(report, element_type)
    summary_status = _overall_status([str(result.get("status")) for result in results])
    return {
        "schema_version": "check_result_file.v1",
        "artifact_type": "CHECK_RESULT_FILE",
        "check_id": check_id,
        "check_title": title,
        "summary": {
            "status": summary_status,
            "input_status": _input_status_for_status(summary_status),
            "checked_object_count": len(results),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "no_data_count": no_data_count,
            "blocked_count": blocked_count,
            "unsupported_count": sum(int(row.get("assigned_object_count") or 0) for row in unsupported),
            "excluded_count": 0,
            "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        },
        "section_summary": _section_summary(results),
        "unsupported_objects": unsupported,
        "results": results,
    }


def build_modal_mass_check_result_file(report: Mapping[str, Any]) -> dict[str, Any]:
    verdict_rows = [row for row in report.get("modal_mass_final_verdict", []) or [] if isinstance(row, Mapping)]
    modal_by_direction = {str(row.get("direction")): row for row in verdict_rows}
    subchecks = []
    for direction in ("UX", "UY"):
        row = modal_by_direction.get(direction, {})
        status = _status_from_product_status(row.get("status"))
        subchecks.append({
            "subcheck_id": f"modal_mass_{direction.lower()}",
            "title": f"{direction} cumulative modal mass",
            "value": row.get("value"),
            "limit": row.get("limit"),
            "unit": "ratio",
            "operator": ">=",
            "comparison": row.get("comparison"),
            "selected_mode": row.get("selected_mode"),
            "selected_row_index": row.get("selected_row_index"),
            "status": status,
        })
    status = _overall_status([row["status"] for row in subchecks])
    ux = modal_by_direction.get("UX", {})
    uy = modal_by_direction.get("UY", {})
    rows_considered = ux.get("rows_considered") or uy.get("rows_considered") or 0
    selected_mode = ux.get("selected_mode") or uy.get("selected_mode")
    result = {
        "schema_version": "check_result.v1",
        "artifact_type": "MODEL_CHECK_RESULT",
        "check_id": MODAL_CHECK_ID,
        "check_title": "Modal mass participation",
        "check_family": "MODAL_DYNAMIC_CHECKS",
        "check_level": "MODEL",
        "result_id": "MODAL_MASS_PARTICIPATION:MODEL",
        "model_scope": {"scope_status": "CHECKED", "scope_reason": "Modal participating mass ratios table is available."},
        "input": {
            "input_status": _input_status_for_status(status),
            "missing_inputs": [] if status in {"PASS", "FAIL"} else ["modal_participating_mass"],
            "input_refs": {
                "source_table": "Modal Participating Mass Ratios",
                "rows_considered": rows_considered,
                "ux_source_column": ux.get("source_column") or "SumUX",
                "uy_source_column": uy.get("source_column") or "SumUY",
            },
        },
        "status": status,
        "subchecks": subchecks,
        "values": {"ux": ux.get("value"), "uy": uy.get("value"), "rows_considered": rows_considered, "selected_mode": selected_mode},
        "limits": {"modal_mass_threshold": ux.get("limit") or uy.get("limit") or 0.95},
        "comparisons": {"ux": ux.get("comparison"), "uy": uy.get("comparison")},
        "limit_contract": {"contract_id": MODAL_LIMIT_CONTRACT_ID, "contract_file": "check_limit_contract.json", "code_clause_status": "PENDING_CLAUSE_BINDING"},
        "diagnostics": {"warnings": [], "notes": ["Status is according to frozen product limit contract, not full TBDY compliance."]},
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
    }
    return {
        "schema_version": "check_result_file.v1",
        "artifact_type": "CHECK_RESULT_FILE",
        "check_id": MODAL_CHECK_ID,
        "check_title": "Modal mass participation",
        "summary": {
            "status": status,
            "input_status": _input_status_for_status(status),
            "checked_object_count": 1 if status in {"PASS", "FAIL"} else 0,
            "pass_count": 1 if status == "PASS" else 0,
            "fail_count": 1 if status == "FAIL" else 0,
            "no_data_count": 1 if status == "NO_DATA" else 0,
            "blocked_count": 1 if status == "BLOCKED" else 0,
            "unsupported_count": 0,
            "excluded_count": 0,
            "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        },
        "result": result,
        "results": [result],
    }


def build_blocked_checks() -> dict[str, Any]:
    blocked_checks = [
        {
            "check_id": "CONCRETE_BEAM_SHEAR_CAPACITY",
            "check_family": "CONCRETE_BEAM_CAPACITY",
            "status": "BLOCKED",
            "input_status": "BLOCKED_INPUT",
            "missing_inputs": ["design_force_envelope", "shear_rebar", "load_combination_basis", "capacity_model"],
            "next_required_slice": "force_and_rebar_inputs",
            "reason": "Required force and reinforcement inputs are not available in the current product slice.",
        },
        {
            "check_id": "CONCRETE_BEAM_FLEXURE_CAPACITY",
            "check_family": "CONCRETE_BEAM_CAPACITY",
            "status": "BLOCKED",
            "input_status": "BLOCKED_INPUT",
            "missing_inputs": ["longitudinal_rebar", "design_moment_envelope", "load_combination_basis", "capacity_model"],
            "next_required_slice": "force_and_rebar_inputs",
            "reason": "Flexural capacity cannot be evaluated without reinforcement and design moment inputs.",
        },
        {
            "check_id": "CONCRETE_COLUMN_CAPACITY",
            "check_family": "CONCRETE_COLUMN_CAPACITY",
            "status": "BLOCKED",
            "input_status": "BLOCKED_INPUT",
            "missing_inputs": ["column_rebar", "axial_force_envelope", "moment_envelope", "interaction_model"],
            "next_required_slice": "column_force_and_rebar_inputs",
            "reason": "Column capacity cannot be evaluated without axial/moment/reinforcement inputs.",
        },
        {
            "check_id": "CAPACITY_DESIGN",
            "check_family": "CAPACITY_DESIGN",
            "status": "BLOCKED",
            "input_status": "BLOCKED_INPUT",
            "missing_inputs": ["beam_capacity_results", "column_capacity_results", "joint_force_chain", "capacity_design_rules"],
            "next_required_slice": "capacity_hierarchy_inputs",
            "reason": "Capacity design requires upstream flexure/shear/capacity results.",
        },
    ]
    return {
        "schema_version": "blocked_checks.v1",
        "artifact_type": "BLOCKED_CHECK_LIST",
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        "blocked_checks": blocked_checks,
    }


def build_check_results_summary(*, beam_file: Mapping[str, Any], column_file: Mapping[str, Any], modal_file: Mapping[str, Any], blocked_checks: Mapping[str, Any], product_summary: Mapping[str, Any]) -> dict[str, Any]:
    entries = []
    for check_id, result_file, payload in (
        (BEAM_CHECK_ID, "check_results_concrete_beam_min_geometry.json", beam_file),
        (COLUMN_CHECK_ID, "check_results_concrete_column_min_geometry.json", column_file),
        (MODAL_CHECK_ID, "check_results_modal_mass_participation.json", modal_file),
    ):
        summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
        entries.append({
            "check_id": check_id,
            "status": summary.get("status"),
            "input_status": summary.get("input_status"),
            "checked_object_count": summary.get("checked_object_count"),
            "pass_count": summary.get("pass_count"),
            "fail_count": summary.get("fail_count"),
            "unsupported_count": summary.get("unsupported_count"),
            "result_file": result_file,
        })
    blocked_count = len(blocked_checks.get("blocked_checks", []) or [])
    return {
        "schema_version": "check_results_summary.v1",
        "artifact_type": "CHECK_RESULTS_SUMMARY",
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        "checked_scope_status": product_summary.get("checked_scope_status"),
        "model_scope_status": product_summary.get("model_scope_status"),
        "summary": {
            "total_formal_checks": len(entries),
            "pass_count": sum(1 for entry in entries if entry.get("status") == "PASS"),
            "fail_count": sum(1 for entry in entries if entry.get("status") == "FAIL"),
            "blocked_count": blocked_count,
            "partial_input_count": sum(1 for entry in entries if entry.get("input_status") == "PARTIAL_INPUT"),
            "not_applicable_count": sum(1 for entry in entries if entry.get("status") == "NOT_APPLICABLE"),
        },
        "check_results": entries,
        "blocked_checks_file": "blocked_checks.json",
    }


def build_formal_check_artifacts(*, report: Mapping[str, Any], object_scope_ledger: Sequence[Mapping[str, Any]], material_evidence_rows: Sequence[Mapping[str, Any]], product_summary: Mapping[str, Any]) -> dict[str, Any]:
    beam = build_object_check_result_file(
        check_id=BEAM_CHECK_ID,
        element_type="Beam",
        report=report,
        object_scope_ledger=object_scope_ledger,
        material_evidence_rows=material_evidence_rows,
    )
    column = build_object_check_result_file(
        check_id=COLUMN_CHECK_ID,
        element_type="Column",
        report=report,
        object_scope_ledger=object_scope_ledger,
        material_evidence_rows=material_evidence_rows,
    )
    modal = build_modal_mass_check_result_file(report)
    blocked = build_blocked_checks()
    return {
        "check_catalog.json": build_check_catalog(),
        "check_limit_contract.json": build_check_limit_contract(),
        "check_results_concrete_beam_min_geometry.json": beam,
        "check_results_concrete_column_min_geometry.json": column,
        "check_results_modal_mass_participation.json": modal,
        "blocked_checks.json": blocked,
        "check_results_summary.json": build_check_results_summary(
            beam_file=beam,
            column_file=column,
            modal_file=modal,
            blocked_checks=blocked,
            product_summary=product_summary,
        ),
    }
