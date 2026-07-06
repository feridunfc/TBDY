"""Formal CheckResult artifact builder for the product report package.

This module extends the P2.6 formal CheckResult flow. It does not introduce a
CheckEngine, does not call or mutate ETABS, and does not claim full TBDY
compliance. All statuses are according to frozen product limit contracts with
code-clause binding pending.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

FULL_TBDY_STATUS = "NOT_EVALUATED"
CHECKED_OBJECT_STATUS = {"OK": "PASS", "PASS": "PASS", "FAIL": "FAIL", "NO_DATA": "NO_DATA"}

BEAM_CHECK_ID = "CONCRETE_BEAM_MIN_GEOMETRY"
COLUMN_CHECK_ID = "CONCRETE_COLUMN_MIN_GEOMETRY"
MODAL_CHECK_ID = "MODAL_MASS_PARTICIPATION"
MATERIAL_CHECK_ID = "CONCRETE_MATERIAL_MIN_STRENGTH"
STORY_DRIFT_CHECK_ID = "STORY_DRIFT"
TORSION_A1_CHECK_ID = "TORSIONAL_IRREGULARITY_A1"

BEAM_LIMIT_CONTRACT_ID = "CONCRETE_BEAM_MIN_GEOMETRY_LIMITS_V1"
COLUMN_LIMIT_CONTRACT_ID = "CONCRETE_COLUMN_MIN_GEOMETRY_LIMITS_V1"
MODAL_LIMIT_CONTRACT_ID = "MODAL_MASS_PARTICIPATION_LIMITS_V1"
MATERIAL_LIMIT_CONTRACT_ID = "CONCRETE_MATERIAL_MIN_STRENGTH_LIMITS_V1"
STORY_DRIFT_LIMIT_CONTRACT_ID = "STORY_DRIFT_LIMITS_V1"
TORSION_A1_LIMIT_CONTRACT_ID = "TORSIONAL_IRREGULARITY_A1_LIMITS_V1"

MIN_FCK_MPA = 25.0
MIN_CONCRETE_CLASS_LABEL = "C25/30"
MAX_STORY_DRIFT_RATIO = 0.008
MAX_TORSION_A1_COEFFICIENT = 1.2


def _status_from_product_status(status: Any) -> str:
    return CHECKED_OBJECT_STATUS.get(str(status or "NO_DATA"), "NO_DATA")


def _overall_status(statuses: Sequence[str]) -> str:
    normalized = [str(status) for status in statuses if status not in (None, "")]
    if not normalized:
        return "NO_DATA"
    if "FAIL" in normalized:
        return "FAIL"
    if "BLOCKED" in normalized or "BLOCKED_INPUT" in normalized:
        return "BLOCKED_INPUT"
    if "NO_DATA" in normalized:
        return "NO_DATA"
    return "PASS"


def _input_status_for_status(status: str) -> str:
    if status in {"PASS", "FAIL"}:
        return "RESOLVED"
    if status == "NO_DATA":
        return "NO_DATA"
    if status in {"BLOCKED", "BLOCKED_INPUT"}:
        return "BLOCKED_INPUT"
    return "NOT_REQUIRED"


def _summary_input_status(statuses: Sequence[str]) -> str:
    normalized = [str(status) for status in statuses if status not in (None, "")]
    if not normalized:
        return "NO_DATA"
    if "BLOCKED" in normalized or "BLOCKED_INPUT" in normalized:
        return "BLOCKED_INPUT"
    resolved = any(status in {"PASS", "FAIL"} for status in normalized)
    missing = any(status == "NO_DATA" for status in normalized)
    if resolved and missing:
        return "PARTIAL_INPUT"
    if missing:
        return "NO_DATA"
    return "RESOLVED"


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


def _source_table_payload(source_tables: Mapping[str, Any] | None, table_key: str) -> Mapping[str, Any]:
    if not isinstance(source_tables, Mapping):
        return {}
    tables = source_tables.get("tables") if isinstance(source_tables.get("tables"), Mapping) else {}
    table = tables.get(table_key) if isinstance(tables, Mapping) else None
    return table if isinstance(table, Mapping) else {}


def _source_rows(source_tables: Mapping[str, Any] | None, table_key: str) -> list[Mapping[str, Any]]:
    table = _source_table_payload(source_tables, table_key)
    rows = table.get("rows") or table.get("parsed_rows") or table.get("sample_rows_limited") or []
    return [row for row in rows if isinstance(row, Mapping)]


def _actual_table_name(source_tables: Mapping[str, Any] | None, table_key: str, fallback: str) -> str:
    table = _source_table_payload(source_tables, table_key)
    return str(table.get("actual_table_name") or fallback)


def _first_present_value(row: Mapping[str, Any], aliases: Sequence[str]) -> Any:
    direct = {str(key): key for key in row.keys()}
    folded = {str(key).replace(" ", "").replace("_", "").replace("/", "").casefold(): key for key in row.keys()}
    for alias in aliases:
        if alias in direct:
            value = row.get(direct[alias])
            if value not in (None, ""):
                return value
        folded_key = folded.get(alias.replace(" ", "").replace("_", "").replace("/", "").casefold())
        if folded_key is not None:
            value = row.get(folded_key)
            if value not in (None, ""):
                return value
    return None


def _parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    # ETABS material Fc is commonly exported as kPa/MPa-adjacent numeric text;
    # material_evidence already normalizes fck, but story/torsion source rows are
    # used directly as ratio values here.
    try:
        return float(text)
    except ValueError:
        return None


def _comparison(value: float | None, operator: str, limit: float) -> str | None:
    if value is None:
        return None
    return f"{value:g} {operator} {limit:g}"


def build_check_catalog() -> dict[str, Any]:
    checks = [
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
        {
            "check_id": MATERIAL_CHECK_ID,
            "check_title": "Concrete material minimum strength",
            "check_family": "CONCRETE_MATERIAL_INPUT_CHECKS",
            "check_level": "SECTION",
            "implemented_in_product_slice": True,
            "result_file": "check_results_concrete_material_min_strength.json",
            "scope_note": "Checked concrete beam/column sections only; PASS/FAIL is according to the frozen product limit contract.",
            "code_clause_status": "PENDING_CLAUSE_BINDING",
        },
        {
            "check_id": STORY_DRIFT_CHECK_ID,
            "check_title": "Story drift",
            "check_family": "STORY_DRIFT_CHECKS",
            "check_level": "STORY_DIRECTION_CASE",
            "implemented_in_product_slice": True,
            "result_file": "check_results_story_drift.json",
            "scope_note": "Uses only available Story Drifts source rows; no displacement reconstruction is performed.",
            "code_clause_status": "PENDING_CLAUSE_BINDING",
        },
        {
            "check_id": TORSION_A1_CHECK_ID,
            "check_title": "Torsional irregularity A1",
            "check_family": "TORSIONAL_IRREGULARITY_CHECKS",
            "check_level": "STORY_DIRECTION_CASE",
            "implemented_in_product_slice": True,
            "result_file": "check_results_torsional_irregularity_a1.json",
            "scope_note": "Uses only available Story Max Over Avg Drifts source rows; eta_bi is not fabricated.",
            "code_clause_status": "PENDING_CLAUSE_BINDING",
        },
    ]
    return {
        "schema_version": "check_catalog.v1",
        "artifact_type": "CHECK_CATALOG",
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        "checks": checks,
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
            {
                "contract_id": MATERIAL_LIMIT_CONTRACT_ID,
                "check_id": MATERIAL_CHECK_ID,
                "code_clause_status": "PENDING_CLAUSE_BINDING",
                "limit_basis": "Frozen product limit contract; clause binding pending.",
                "limits": {"min_concrete_class_label": MIN_CONCRETE_CLASS_LABEL, "min_fck_mpa": MIN_FCK_MPA},
                "units": {"fck": "MPa"},
                "status_semantics": {
                    "pass": "fck_mpa is greater than or equal to the frozen product minimum strength threshold.",
                    "fail": "fck_mpa is below the frozen product minimum strength threshold.",
                    "no_data": "fck input is missing or unparseable.",
                },
            },
            {
                "contract_id": STORY_DRIFT_LIMIT_CONTRACT_ID,
                "check_id": STORY_DRIFT_CHECK_ID,
                "code_clause_status": "PENDING_CLAUSE_BINDING",
                "limit_basis": "Frozen product limit contract; clause binding pending.",
                "limits": {"max_drift_ratio": MAX_STORY_DRIFT_RATIO},
                "units": {"story_drift": "ratio"},
                "status_semantics": {
                    "pass": "drift_ratio is less than or equal to the frozen product drift ratio threshold.",
                    "fail": "drift_ratio exceeds the frozen product drift ratio threshold.",
                    "no_data": "Story drift input is missing or unparseable.",
                },
            },
            {
                "contract_id": TORSION_A1_LIMIT_CONTRACT_ID,
                "check_id": TORSION_A1_CHECK_ID,
                "code_clause_status": "PENDING_CLAUSE_BINDING",
                "limit_basis": "Frozen product limit contract; clause binding pending.",
                "limits": {"max_torsion_irregularity_coefficient": MAX_TORSION_A1_COEFFICIENT, "symbol": "eta_bi"},
                "units": {"eta_bi": "ratio"},
                "status_semantics": {
                    "pass": "eta_bi is less than or equal to the frozen product torsional irregularity threshold.",
                    "fail": "eta_bi exceeds the frozen product torsional irregularity threshold.",
                    "no_data": "Torsional irregularity input is missing or unparseable.",
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
        section = obj.get("section") if obj else result.get("section")
        grouped[str(section or "")].append(result)
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
    statuses = [str(result.get("status")) for result in results]
    pass_count = sum(1 for result in results if result.get("status") == "PASS")
    fail_count = sum(1 for result in results if result.get("status") == "FAIL")
    no_data_count = sum(1 for result in results if result.get("status") == "NO_DATA")
    blocked_count = sum(1 for result in results if result.get("status") in {"BLOCKED", "BLOCKED_INPUT"})
    unsupported = _unsupported_objects(report, element_type)
    summary_status = _overall_status(statuses)
    return {
        "schema_version": "check_result_file.v1",
        "artifact_type": "CHECK_RESULT_FILE",
        "check_id": check_id,
        "check_title": title,
        "summary": {
            "status": summary_status,
            "input_status": _summary_input_status(statuses),
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
    statuses = [row["status"] for row in subchecks]
    status = _overall_status(statuses)
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
            "input_status": _summary_input_status(statuses),
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
            "input_status": _summary_input_status(statuses),
            "checked_object_count": 1 if status in {"PASS", "FAIL"} else 0,
            "pass_count": 1 if status == "PASS" else 0,
            "fail_count": 1 if status == "FAIL" else 0,
            "no_data_count": 1 if status == "NO_DATA" else 0,
            "blocked_count": 1 if status in {"BLOCKED", "BLOCKED_INPUT"} else 0,
            "unsupported_count": 0,
            "excluded_count": 0,
            "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        },
        "result": result,
        "results": [result],
    }


def _material_strength_row(row: Mapping[str, Any]) -> dict[str, Any]:
    fck = _parse_float(row.get("fck_value_mpa"))
    material_status = str(row.get("material_status") or "MISSING")
    if material_status == "RESOLVED" and fck is not None:
        status = "PASS" if fck >= MIN_FCK_MPA else "FAIL"
        input_status = "RESOLVED"
        missing_inputs: list[str] = []
    else:
        status = "NO_DATA"
        input_status = "NO_DATA" if material_status == "MISSING" else "PARTIAL_INPUT"
        missing_inputs = ["concrete_fck_mpa"]
    section = str(row.get("section") or "UNKNOWN_SECTION")
    element_type = str(row.get("element_type") or "UNKNOWN_ELEMENT")
    comparison = _comparison(fck, ">=", MIN_FCK_MPA)
    return {
        "schema_version": "check_result.v1",
        "artifact_type": "SECTION_CHECK_RESULT",
        "check_id": MATERIAL_CHECK_ID,
        "check_title": "Concrete material minimum strength",
        "check_family": "CONCRETE_MATERIAL_INPUT_CHECKS",
        "check_level": "SECTION",
        "result_id": f"{MATERIAL_CHECK_ID}:{element_type}:{section}",
        "result_scope": "SECTION",
        "section": section,
        "element_type": element_type,
        "assigned_object_count": row.get("assigned_object_count"),
        "material_name": row.get("material_name"),
        "input_status": input_status,
        "input": {
            "input_status": input_status,
            "missing_inputs": missing_inputs,
            "input_refs": {
                "material_input_ref": f"{row.get('evidence_table')}:material={row.get('material_name')}",
                "material_source_row_index": row.get("source_row_index"),
                "section_source_table": row.get("section_source_table"),
                "section_source_row_index": row.get("section_source_row_index"),
            },
        },
        "status": status,
        "demand": {"fck_mpa": fck},
        "limit": {"min_fck_mpa": MIN_FCK_MPA, "min_concrete_class_label": MIN_CONCRETE_CLASS_LABEL},
        "comparison": {"fck_mpa": comparison},
        "source_refs": {
            "material_input_ref": f"{row.get('evidence_table')}:material={row.get('material_name')}",
            "section": section,
            "source_row_index": row.get("source_row_index"),
        },
        "code_clause_status": "PENDING_CLAUSE_BINDING",
        "limit_contract": {"contract_id": MATERIAL_LIMIT_CONTRACT_ID, "contract_file": "check_limit_contract.json", "code_clause_status": "PENDING_CLAUSE_BINDING"},
        "diagnostics": {"warnings": [] if status in {"PASS", "FAIL"} else ["Concrete fck input is missing or unparseable."], "notes": ["Status is according to frozen product limit contract, not full TBDY material compliance."]},
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
    }


def build_material_strength_check_result_file(material_evidence_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    results = [_material_strength_row(row) for row in material_evidence_rows if isinstance(row, Mapping)]
    statuses = [str(row.get("status")) for row in results]
    summary_status = _overall_status(statuses)
    return {
        "schema_version": "check_result_file.v1",
        "artifact_type": "CHECK_RESULT_FILE",
        "check_id": MATERIAL_CHECK_ID,
        "check_title": "Concrete material minimum strength",
        "summary": {
            "status": summary_status,
            "input_status": _summary_input_status(statuses),
            "checked_section_count": len(results),
            "checked_object_count": len(results),
            "pass_count": sum(1 for row in results if row.get("status") == "PASS"),
            "fail_count": sum(1 for row in results if row.get("status") == "FAIL"),
            "no_data_count": sum(1 for row in results if row.get("status") == "NO_DATA"),
            "blocked_count": sum(1 for row in results if row.get("status") in {"BLOCKED", "BLOCKED_INPUT"}),
            "unsupported_count": 0,
            "excluded_count": 0,
            "min_fck_mpa": MIN_FCK_MPA,
            "min_concrete_class_label": MIN_CONCRETE_CLASS_LABEL,
            "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        },
        "section_summary": _section_summary(results),
        "results": results,
    }


def _row_context(row: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    story = _first_present_value(row, ("Story", "StoryName", "Story Name"))
    direction = _first_present_value(row, ("Direction", "Dir"))
    case = _first_present_value(row, ("OutputCase", "Output Case", "Case", "LoadCase", "Load Case", "Load Case/Combo"))
    return story, direction, case


def _case_type_from_row(row: Mapping[str, Any]) -> str | None:
    value = _first_present_value(
        row,
        (
            "CaseType",
            "Case Type",
            "LoadCaseType",
            "Load Case Type",
            "AnalysisType",
            "Analysis Type",
            "ComboType",
            "Combo Type",
        ),
    )
    return str(value).strip() if value not in (None, "") else None


def _case_type_map_from_source_tables(source_tables: Mapping[str, Any] | None) -> dict[str, str]:
    """Best-effort case/combo type map from source table metadata.

    The product must not primarily rely on EX/EY-style name patterns for story
    drift selection.  This scans available load-case/combo/source metadata tables
    for case name -> analysis/type mappings.  It is intentionally conservative:
    unsupported table shapes simply produce no map and force explicit fallback
    diagnostics rather than fabricated seismic classification.
    """
    if not isinstance(source_tables, Mapping):
        return {}
    tables = source_tables.get("tables") if isinstance(source_tables.get("tables"), Mapping) else {}
    out: dict[str, str] = {}
    for table_key, table in tables.items() if isinstance(tables, Mapping) else []:
        key_text = str(table_key).casefold()
        if not any(token in key_text for token in ("case", "combo", "load")):
            continue
        rows = table.get("rows") or table.get("parsed_rows") or table.get("sample_rows_limited") or [] if isinstance(table, Mapping) else []
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            case = _first_present_value(row, ("Name", "Case", "CaseName", "Case Name", "OutputCase", "Output Case", "LoadCase", "Load Case", "Combo", "Load Case/Combo"))
            case_type = _case_type_from_row(row)
            if case not in (None, "") and case_type:
                out[str(case)] = case_type
    return out


def _select_story_drift_case(case_name: Any, case_type: str | None, *, metadata_available: bool) -> tuple[bool, str]:
    normalized_type = str(case_type or "").replace("_", " ").replace("-", " ").casefold()
    if normalized_type:
        if "response" in normalized_type and "spectrum" in normalized_type:
            return True, "CASE_TYPE_RESPONSE_SPECTRUM"
        if "seismic" in normalized_type or "earthquake" in normalized_type or "quake" in normalized_type:
            return True, "CASE_TYPE_SEISMIC"
        if "drift" in normalized_type and not any(blocked in normalized_type for blocked in ("wind", "gravity", "dead", "live", "modal")):
            return True, "CASE_METADATA"
        return False, "NOT_SELECTED"
    if metadata_available:
        return False, "NOT_SELECTED"
    name = str(case_name or "").strip().casefold()
    fallback_tokens = ("ex", "ey", "eq", "dd", "deprem", "seis", "rs", "rsp", "spectrum")
    if any(token in name for token in fallback_tokens):
        return True, "NAME_PATTERN_FALLBACK"
    return False, "NOT_SELECTED"


def _story_drift_selector(rows: Sequence[Mapping[str, Any]], source_tables: Mapping[str, Any] | None) -> tuple[list[tuple[int, Mapping[str, Any], str | None, str]], dict[str, Any]]:
    case_type_map = _case_type_map_from_source_tables(source_tables)
    selected: list[tuple[int, Mapping[str, Any], str | None, str]] = []
    observed: list[dict[str, Any]] = []
    metadata_seen = False
    fallback_used = False
    for index, row in enumerate(rows):
        _, _, case = _row_context(row)
        row_case_type = _case_type_from_row(row)
        mapped_case_type = case_type_map.get(str(case)) if case not in (None, "") else None
        case_type = row_case_type or mapped_case_type
        row_metadata_available = bool(row_case_type or mapped_case_type)
        metadata_seen = metadata_seen or row_metadata_available
        include, method = _select_story_drift_case(case, case_type, metadata_available=row_metadata_available)
        fallback_used = fallback_used or method == "NAME_PATTERN_FALLBACK"
        observed.append(
            {
                "source_row_index": index,
                "load_case_or_combo": case,
                "case_type": case_type,
                "case_selection_method": method,
                "selected": include,
            }
        )
        if include:
            selected.append((index, row, case_type, method))
    diagnostics = {
        "case_selection_policy": "Use source case/combo type metadata first; use conservative name-pattern fallback only when metadata is unavailable.",
        "case_type_metadata_available": metadata_seen,
        "name_pattern_fallback_used": fallback_used,
        "observed_case_count": len(observed),
        "selected_case_count": len(selected),
        "observed_cases": observed,
        "warnings": [],
    }
    if fallback_used:
        diagnostics["warnings"].append(
            "Case type metadata was unavailable for at least one selected story drift row; NAME_PATTERN_FALLBACK was used."
        )
    return selected, diagnostics


def _story_drift_result(row: Mapping[str, Any], *, row_index: int, source_table: str, case_type: str | None, case_selection_method: str) -> dict[str, Any]:
    story, direction, case = _row_context(row)
    drift_value = _parse_float(_first_present_value(row, ("Drift", "DriftRatio", "Drift Ratio", "StoryDrift", "Story Drift", "Drift/")))
    status = "NO_DATA" if drift_value is None else ("PASS" if drift_value <= MAX_STORY_DRIFT_RATIO else "FAIL")
    input_status = _input_status_for_status(status)
    source_refs = {
        "source_table": source_table,
        "source_row_index": row_index,
        "load_case_or_combo": case,
        "case_type": case_type,
        "case_selection_method": case_selection_method,
    }
    return {
        "schema_version": "check_result.v1",
        "artifact_type": "STORY_DIRECTION_CASE_CHECK_RESULT",
        "check_id": STORY_DRIFT_CHECK_ID,
        "check_title": "Story drift",
        "check_family": "STORY_DRIFT_CHECKS",
        "check_level": "STORY_DIRECTION_CASE",
        "result_id": f"{STORY_DRIFT_CHECK_ID}:{story or 'UNKNOWN_STORY'}:{direction or 'UNKNOWN_DIRECTION'}:{case or 'UNKNOWN_CASE'}:{row_index}",
        "result_scope": "STORY_DIRECTION_CASE",
        "story": story,
        "direction": direction,
        "load_case_or_combo": case,
        "case_type": case_type,
        "case_selection_method": case_selection_method,
        "input_status": input_status,
        "input": {"input_status": input_status, "missing_inputs": [] if drift_value is not None else ["drift_ratio"], "input_refs": source_refs},
        "status": status,
        "demand": {"drift_ratio": drift_value},
        "limit": {"max_drift_ratio": MAX_STORY_DRIFT_RATIO},
        "comparison": {"drift_ratio": _comparison(drift_value, "<=", MAX_STORY_DRIFT_RATIO)},
        "source_refs": source_refs,
        "code_clause_status": "PENDING_CLAUSE_BINDING",
        "limit_contract": {"contract_id": STORY_DRIFT_LIMIT_CONTRACT_ID, "contract_file": "check_limit_contract.json", "code_clause_status": "PENDING_CLAUSE_BINDING"},
        "diagnostics": {"warnings": [] if drift_value is not None else ["Story drift ratio input is missing or unparseable."], "notes": ["Status is according to frozen product limit contract, not full TBDY compliance."]},
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
    }


def build_story_drift_check_result_file(source_tables: Mapping[str, Any] | None) -> dict[str, Any]:
    table_key = "story_drifts"
    rows = _source_rows(source_tables, table_key)
    source_table = _actual_table_name(source_tables, table_key, "Story Drifts")
    selected_rows, selector_diagnostics = _story_drift_selector(rows, source_tables)
    results = [
        _story_drift_result(
            row,
            row_index=index,
            source_table=source_table,
            case_type=case_type,
            case_selection_method=case_selection_method,
        )
        for index, row, case_type, case_selection_method in selected_rows
    ]
    return _story_case_file(
        check_id=STORY_DRIFT_CHECK_ID,
        check_title="Story drift",
        results=results,
        missing_table_input="story_drifts",
        diagnostics={"selector_diagnostics": selector_diagnostics},
    )


def _select_torsion_a1_case(case_name: Any, case_type: str | None) -> tuple[bool, str]:
    """Classify torsion rows with the same explicit selector contract as drift.

    Some ETABS torsion source rows carry generic analysis types such as
    LinStatic even when the case name identifies a cracked seismic result.
    Treat response-spectrum/seismic metadata as authoritative, explicitly
    reject known non-seismic metadata, and use name fallback only for otherwise
    generic or missing metadata.
    """
    normalized_type = str(case_type or "").replace("_", " ").replace("-", " ").casefold()
    if normalized_type:
        if "response" in normalized_type and "spectrum" in normalized_type:
            return True, "CASE_TYPE_RESPONSE_SPECTRUM"
        if "seismic" in normalized_type or "earthquake" in normalized_type or "quake" in normalized_type:
            return True, "CASE_TYPE_SEISMIC"
        if any(blocked in normalized_type for blocked in ("wind", "gravity", "dead", "live", "modal")):
            return False, "NOT_SELECTED"

    name = str(case_name or "").strip().casefold()
    fallback_tokens = ("ex", "ey", "eq", "dd", "deprem", "seis", "rs", "rsp", "spectrum")
    if any(token in name for token in fallback_tokens):
        return True, "NAME_PATTERN_FALLBACK"

    if normalized_type and "drift" in normalized_type:
        return True, "CASE_METADATA"
    return False, "NOT_SELECTED"


def _torsion_a1_selector(rows: Sequence[Mapping[str, Any]], source_tables: Mapping[str, Any] | None) -> tuple[list[tuple[int, Mapping[str, Any], str | None, str]], dict[str, Any]]:
    case_type_map = _case_type_map_from_source_tables(source_tables)
    selected: list[tuple[int, Mapping[str, Any], str | None, str]] = []
    observed: list[dict[str, Any]] = []
    metadata_seen = False
    fallback_used = False
    for index, row in enumerate(rows):
        _, _, case = _row_context(row)
        row_case_type = _case_type_from_row(row)
        mapped_case_type = case_type_map.get(str(case)) if case not in (None, "") else None
        case_type = row_case_type or mapped_case_type
        metadata_seen = metadata_seen or bool(row_case_type or mapped_case_type)
        include, method = _select_torsion_a1_case(case, case_type)
        fallback_used = fallback_used or method == "NAME_PATTERN_FALLBACK"
        observed.append(
            {
                "source_row_index": index,
                "load_case_or_combo": case,
                "case_type": case_type,
                "case_selection_method": method,
                "selected": include,
            }
        )
        if include:
            selected.append((index, row, case_type, method))
    diagnostics = {
        "case_selection_policy": "Use source case/combo type metadata first; use conservative name-pattern fallback only when metadata is unavailable or generic.",
        "case_type_metadata_available": metadata_seen,
        "name_pattern_fallback_used": fallback_used,
        "observed_case_count": len(observed),
        "selected_case_count": len(selected),
        "observed_cases": observed,
        "warnings": [],
    }
    if fallback_used:
        diagnostics["warnings"].append(
            "Case type metadata was unavailable or generic for at least one selected torsion row; NAME_PATTERN_FALLBACK was used."
        )
    return selected, diagnostics


def _torsion_a1_result(row: Mapping[str, Any], *, row_index: int, source_table: str, case_type: str | None, case_selection_method: str) -> dict[str, Any]:
    story, direction, case = _row_context(row)
    eta = _parse_float(_first_present_value(row, ("Ratio", "MaxOverAvg", "Max Over Avg", "eta_bi", "EtaBi", "Torsion", "TorsionRatio")))
    status = "NO_DATA" if eta is None else ("PASS" if eta <= MAX_TORSION_A1_COEFFICIENT else "FAIL")
    input_status = _input_status_for_status(status)
    source_refs = {
        "source_table": source_table,
        "source_row_index": row_index,
        "load_case_or_combo": case,
        "case_type": case_type,
        "case_selection_method": case_selection_method,
    }
    return {
        "schema_version": "check_result.v1",
        "artifact_type": "STORY_DIRECTION_CASE_CHECK_RESULT",
        "check_id": TORSION_A1_CHECK_ID,
        "check_title": "Torsional irregularity A1",
        "check_family": "TORSIONAL_IRREGULARITY_CHECKS",
        "check_level": "STORY_DIRECTION_CASE",
        "result_id": f"{TORSION_A1_CHECK_ID}:{story or 'UNKNOWN_STORY'}:{direction or 'UNKNOWN_DIRECTION'}:{case or 'UNKNOWN_CASE'}:{row_index}",
        "result_scope": "STORY_DIRECTION_CASE",
        "story": story,
        "direction": direction,
        "load_case_or_combo": case,
        "case_type": case_type,
        "case_selection_method": case_selection_method,
        "input_status": input_status,
        "input": {"input_status": input_status, "missing_inputs": [] if eta is not None else ["torsion_irregularity_coefficient"], "input_refs": source_refs},
        "status": status,
        "demand": {"torsion_irregularity_coefficient": eta},
        "limit": {"max_torsion_irregularity_coefficient": MAX_TORSION_A1_COEFFICIENT},
        "comparison": {"eta_bi": _comparison(eta, "<=", MAX_TORSION_A1_COEFFICIENT)},
        "source_refs": source_refs,
        "code_clause_status": "PENDING_CLAUSE_BINDING",
        "limit_contract": {"contract_id": TORSION_A1_LIMIT_CONTRACT_ID, "contract_file": "check_limit_contract.json", "code_clause_status": "PENDING_CLAUSE_BINDING"},
        "diagnostics": {"warnings": [] if eta is not None else ["Torsional irregularity coefficient input is missing or unparseable."], "notes": ["Status is according to frozen product limit contract, not full TBDY compliance."]},
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
    }


def build_torsional_irregularity_a1_check_result_file(source_tables: Mapping[str, Any] | None) -> dict[str, Any]:
    table_key = "story_max_over_avg_drifts"
    rows = _source_rows(source_tables, table_key)
    source_table = _actual_table_name(source_tables, table_key, "Story Max Over Avg Drifts")
    selected_rows, selector_diagnostics = _torsion_a1_selector(rows, source_tables)
    results = [
        _torsion_a1_result(
            row,
            row_index=index,
            source_table=source_table,
            case_type=case_type,
            case_selection_method=case_selection_method,
        )
        for index, row, case_type, case_selection_method in selected_rows
    ]
    return _story_case_file(
        check_id=TORSION_A1_CHECK_ID,
        check_title="Torsional irregularity A1",
        results=results,
        missing_table_input="story_max_over_avg_drifts",
        diagnostics={"selector_diagnostics": selector_diagnostics},
    )


def _story_case_file(*, check_id: str, check_title: str, results: Sequence[Mapping[str, Any]], missing_table_input: str, diagnostics: Mapping[str, Any] | None = None) -> dict[str, Any]:
    statuses = [str(row.get("status")) for row in results]
    if results:
        summary_status = _overall_status(statuses)
        input_status = _summary_input_status(statuses)
        blocked_count = sum(1 for row in results if row.get("status") in {"BLOCKED", "BLOCKED_INPUT"})
    else:
        summary_status = "BLOCKED_INPUT"
        input_status = "BLOCKED_INPUT"
        blocked_count = 1
    payload = {
        "schema_version": "check_result_file.v1",
        "artifact_type": "CHECK_RESULT_FILE",
        "check_id": check_id,
        "check_title": check_title,
        "summary": {
            "status": summary_status,
            "input_status": input_status,
            "checked_object_count": len(results),
            "checked_row_count": len(results),
            "pass_count": sum(1 for row in results if row.get("status") == "PASS"),
            "fail_count": sum(1 for row in results if row.get("status") == "FAIL"),
            "no_data_count": sum(1 for row in results if row.get("status") == "NO_DATA"),
            "blocked_count": blocked_count,
            "unsupported_count": 0,
            "excluded_count": 0,
            "missing_inputs": [] if results else [missing_table_input],
            "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        },
        "results": list(results),
    }
    if diagnostics:
        payload["diagnostics"] = dict(diagnostics)
    return payload


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


def _summary_entry(check_id: str, result_file: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    return {
        "check_id": check_id,
        "status": summary.get("status"),
        "input_status": summary.get("input_status"),
        "checked_object_count": summary.get("checked_object_count") if summary.get("checked_object_count") is not None else summary.get("checked_section_count"),
        "pass_count": summary.get("pass_count", 0),
        "fail_count": summary.get("fail_count", 0),
        "no_data_count": summary.get("no_data_count", 0),
        "blocked_count": summary.get("blocked_count", 0),
        "unsupported_count": summary.get("unsupported_count", 0),
        "result_file": result_file,
    }


def build_check_results_summary(*, check_files: Sequence[tuple[str, str, Mapping[str, Any]]], blocked_checks: Mapping[str, Any], product_summary: Mapping[str, Any]) -> dict[str, Any]:
    entries = [_summary_entry(check_id, result_file, payload) for check_id, result_file, payload in check_files]
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
            "no_data_count": sum(int(entry.get("no_data_count") or 0) for entry in entries),
            "blocked_input_count": sum(1 for entry in entries if entry.get("status") == "BLOCKED_INPUT"),
            "blocked_count": blocked_count,
            "partial_input_count": sum(1 for entry in entries if entry.get("input_status") == "PARTIAL_INPUT"),
            "not_applicable_count": sum(1 for entry in entries if entry.get("status") == "NOT_APPLICABLE"),
        },
        "check_results": entries,
        "blocked_checks_file": "blocked_checks.json",
    }


def build_formal_check_artifacts(*, report: Mapping[str, Any], object_scope_ledger: Sequence[Mapping[str, Any]], material_evidence_rows: Sequence[Mapping[str, Any]], product_summary: Mapping[str, Any], source_tables: Mapping[str, Any] | None = None) -> dict[str, Any]:
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
    material = build_material_strength_check_result_file(material_evidence_rows)
    story_drift = build_story_drift_check_result_file(source_tables)
    torsion_a1 = build_torsional_irregularity_a1_check_result_file(source_tables)
    blocked = build_blocked_checks()
    check_files: tuple[tuple[str, str, Mapping[str, Any]], ...] = (
        (BEAM_CHECK_ID, "check_results_concrete_beam_min_geometry.json", beam),
        (COLUMN_CHECK_ID, "check_results_concrete_column_min_geometry.json", column),
        (MODAL_CHECK_ID, "check_results_modal_mass_participation.json", modal),
        (MATERIAL_CHECK_ID, "check_results_concrete_material_min_strength.json", material),
        (STORY_DRIFT_CHECK_ID, "check_results_story_drift.json", story_drift),
        (TORSION_A1_CHECK_ID, "check_results_torsional_irregularity_a1.json", torsion_a1),
    )
    return {
        "check_catalog.json": build_check_catalog(),
        "check_limit_contract.json": build_check_limit_contract(),
        "check_results_concrete_beam_min_geometry.json": beam,
        "check_results_concrete_column_min_geometry.json": column,
        "check_results_modal_mass_participation.json": modal,
        "check_results_concrete_material_min_strength.json": material,
        "check_results_story_drift.json": story_drift,
        "check_results_torsional_irregularity_a1.json": torsion_a1,
        "blocked_checks.json": blocked,
        "check_results_summary.json": build_check_results_summary(
            check_files=check_files,
            blocked_checks=blocked,
            product_summary=product_summary,
        ),
    }
