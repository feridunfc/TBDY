"""Product-package CheckResult serialization and unrelated legacy product checks.

B1 rule: beam/column engineering authority is canonical CheckResult only.  This
module does not calculate member geometry, member limits, member ratios, member
applicability, units, or member PASS/FAIL.  It only projects already-canonical
member result rows supplied by the report.  Existing modal/material/drift/
torsion product checks remain separate legacy product concerns and retain their
pre-B1 behavior.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

FULL_TBDY_STATUS = "NOT_EVALUATED"
CHECKED_OBJECT_STATUS = {"OK": "PASS", "PASS": "PASS", "FAIL": "FAIL", "NO_DATA": "NO_DATA"}

# B1 canonical formal member ids.  Numeric limits live only in domain registrations
# and are serialized on canonical CheckResult rows; this module owns none of them.
COLUMN_MIN_DIMENSION = "column_geometry_min_dimension"
BEAM_MIN_WIDTH = "beam_geometry_min_width"
BEAM_MIN_DEPTH_300 = "beam_geometry_min_depth"
BEAM_DEPTH_WIDTH_RATIO = "beam_depth_width_ratio"
MEMBER_FORMAL_CHECK_IDS = (
    COLUMN_MIN_DIMENSION,
    BEAM_MIN_WIDTH,
    BEAM_MIN_DEPTH_300,
    BEAM_DEPTH_WIDTH_RATIO,
)
RETIRED_LEGACY_CHECK_IDS = (
    "column_geometry_min_area",
    "column_geometry_aspect_ratio",
)

# Compatibility collection names are artifact groupings, not formal engineering checks.
BEAM_CHECK_ID = "CANONICAL_BEAM_GEOMETRY_CHECK_RESULTS"
COLUMN_CHECK_ID = "CANONICAL_COLUMN_GEOMETRY_CHECK_RESULTS"
MODAL_CHECK_ID = "MODAL_MASS_PARTICIPATION"
MATERIAL_CHECK_ID = "CONCRETE_MATERIAL_MIN_STRENGTH"
STORY_DRIFT_CHECK_ID = "STORY_DRIFT"
TORSION_A1_CHECK_ID = "TORSIONAL_IRREGULARITY_A1"

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
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _comparison(value: float | None, operator: str, limit: float) -> str | None:
    if value is None:
        return None
    return f"{value:g} {operator} {limit:g}"


def _section_summary(results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for result in results:
        obj = result.get("object") if isinstance(result.get("object"), Mapping) else {}
        section = obj.get("section") if obj else result.get("section")
        grouped[str(section or "")].append(result)
    rows: list[dict[str, Any]] = []
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


def _canonical_member_rows(report: Mapping[str, Any], component_type: str) -> list[dict[str, Any]]:
    key = "beam_section_detail" if component_type == "beam" else "column_section_detail"
    rows: list[dict[str, Any]] = []
    for row in report.get(key, []) or []:
        if not isinstance(row, Mapping):
            continue
        check_id = str(row.get("check_id") or "")
        if check_id not in MEMBER_FORMAL_CHECK_IDS:
            continue
        if str(row.get("element_type") or "").strip().casefold() != component_type:
            continue
        # Projection only.  Do not normalize, map, compare, or recompute these fields.
        rows.append({
            "schema_version": "canonical_check_result_projection.v1",
            "artifact_type": "CANONICAL_CHECK_RESULT_PROJECTION",
            "check_id": check_id,
            "component": row.get("component"),
            "component_type": component_type,
            "story": row.get("story"),
            "section": row.get("section"),
            "status": row.get("status"),
            "value": row.get("value"),
            "limit": row.get("limit"),
            "ratio": row.get("ratio"),
            "ratio_type": row.get("ratio_type"),
            "pass_rule": row.get("pass_rule"),
            "unit": row.get("unit"),
            "evidence": row.get("evidence"),
            "messages": row.get("messages"),
            "code_ref": row.get("code_ref"),
            "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        })
    return rows


def _member_collection(report: Mapping[str, Any], component_type: str) -> dict[str, Any]:
    results = _canonical_member_rows(report, component_type)
    statuses = [str(row.get("status")) for row in results]
    collection_id = BEAM_CHECK_ID if component_type == "beam" else COLUMN_CHECK_ID
    return {
        "schema_version": "canonical_check_result_collection.v1",
        "artifact_type": "CANONICAL_CHECK_RESULT_COLLECTION",
        "collection_id": collection_id,
        "component_type": component_type,
        "formal_check_ids": [
            check_id for check_id in MEMBER_FORMAL_CHECK_IDS
            if (check_id.startswith("beam_") if component_type == "beam" else check_id.startswith("column_"))
        ],
        "retired_legacy_check_ids": list(RETIRED_LEGACY_CHECK_IDS) if component_type == "column" else [],
        "summary": {
            "canonical_result_count": len(results),
            "ok_count": sum(1 for status in statuses if status == "OK"),
            "fail_count": sum(1 for status in statuses if status == "FAIL"),
            "blocked_count": sum(1 for status in statuses if status == "BLOCKED"),
            "no_data_count": sum(1 for status in statuses if status == "NO_DATA"),
            "out_of_scope_count": sum(1 for status in statuses if status == "OUT_OF_SCOPE"),
            "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        },
        "results": results,
    }


def build_check_catalog() -> dict[str, Any]:
    member_checks = [
        {
            "check_id": COLUMN_MIN_DIMENSION,
            "check_title": "Rectangular column minimum section dimension",
            "check_family": "CONCRETE_COLUMN_GEOMETRY",
            "check_level": "OBJECT",
            "implemented_in_product_slice": True,
            "result_file": "check_results_concrete_column_min_geometry.json",
            "authority": "canonical CheckResult / member geometry registration",
            "code_clause_status": "BOUND_IN_CANONICAL_RESULT",
        },
        {
            "check_id": BEAM_MIN_WIDTH,
            "check_title": "Beam web minimum width",
            "check_family": "CONCRETE_BEAM_GEOMETRY",
            "check_level": "OBJECT",
            "implemented_in_product_slice": True,
            "result_file": "check_results_concrete_beam_min_geometry.json",
            "authority": "canonical CheckResult / member geometry registration",
            "code_clause_status": "BOUND_IN_CANONICAL_RESULT",
        },
        {
            "check_id": BEAM_MIN_DEPTH_300,
            "check_title": "Beam minimum height 300 mm sub-condition",
            "check_family": "CONCRETE_BEAM_GEOMETRY",
            "check_level": "OBJECT",
            "implemented_in_product_slice": True,
            "result_file": "check_results_concrete_beam_min_geometry.json",
            "authority": "canonical CheckResult / member geometry registration",
            "scope_note": "300-mm sub-condition only; not complete §7.4.1.1(b) compliance.",
            "code_clause_status": "BOUND_IN_CANONICAL_RESULT",
        },
        {
            "check_id": BEAM_DEPTH_WIDTH_RATIO,
            "check_title": "Beam height/web-width maximum ratio",
            "check_family": "CONCRETE_BEAM_GEOMETRY",
            "check_level": "OBJECT",
            "implemented_in_product_slice": True,
            "result_file": "check_results_concrete_beam_min_geometry.json",
            "authority": "canonical CheckResult / member geometry registration",
            "code_clause_status": "BOUND_IN_CANONICAL_RESULT",
        },
    ]
    unrelated = [
        {"check_id": MODAL_CHECK_ID, "check_title": "Modal mass participation", "check_family": "MODAL_DYNAMIC_CHECKS", "check_level": "MODEL", "implemented_in_product_slice": True, "result_file": "check_results_modal_mass_participation.json", "scope_note": "UX and UY cumulative modal mass ratios from the available ETABS modal mass table.", "code_clause_status": "PENDING_CLAUSE_BINDING"},
        {"check_id": MATERIAL_CHECK_ID, "check_title": "Concrete material minimum strength", "check_family": "CONCRETE_MATERIAL_INPUT_CHECKS", "check_level": "SECTION", "implemented_in_product_slice": True, "result_file": "check_results_concrete_material_min_strength.json", "scope_note": "Checked concrete beam/column sections only; PASS/FAIL is according to the frozen product limit contract.", "code_clause_status": "PENDING_CLAUSE_BINDING"},
        {"check_id": STORY_DRIFT_CHECK_ID, "check_title": "Story drift", "check_family": "STORY_DRIFT_CHECKS", "check_level": "STORY_DIRECTION_CASE", "implemented_in_product_slice": True, "result_file": "check_results_story_drift.json", "scope_note": "Uses only available Story Drifts source rows; no displacement reconstruction is performed.", "code_clause_status": "PENDING_CLAUSE_BINDING"},
        {"check_id": TORSION_A1_CHECK_ID, "check_title": "Torsional irregularity A1", "check_family": "TORSIONAL_IRREGULARITY_CHECKS", "check_level": "STORY_DIRECTION_CASE", "implemented_in_product_slice": True, "result_file": "check_results_torsional_irregularity_a1.json", "scope_note": "Uses only available Story Max Over Avg Drifts source rows; eta_bi is not fabricated.", "code_clause_status": "PENDING_CLAUSE_BINDING"},
    ]
    return {
        "schema_version": "check_catalog.v1",
        "artifact_type": "CHECK_CATALOG",
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        "retired_legacy_check_ids": list(RETIRED_LEGACY_CHECK_IDS),
        "checks": member_checks + unrelated,
    }


def build_check_limit_contract() -> dict[str, Any]:
    # Member numeric limits are deliberately absent: canonical CheckResult already carries
    # the domain-owned value/limit/ratio.  This contract retains unrelated product checks.
    return {
        "schema_version": "check_limit_contract.v1",
        "artifact_type": "CHECK_LIMIT_CONTRACT",
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        "member_geometry_limit_authority": "canonical CheckResult / domain registration",
        "retired_legacy_check_ids": list(RETIRED_LEGACY_CHECK_IDS),
        "contracts": [
            {"contract_id": MODAL_LIMIT_CONTRACT_ID, "check_id": MODAL_CHECK_ID, "code_clause_status": "PENDING_CLAUSE_BINDING", "limits": {"modal_mass_threshold": 0.95}, "units": {"modal_mass": "ratio"}},
            {"contract_id": MATERIAL_LIMIT_CONTRACT_ID, "check_id": MATERIAL_CHECK_ID, "code_clause_status": "PENDING_CLAUSE_BINDING", "limit_basis": "Frozen product limit contract; clause binding pending.", "limits": {"min_concrete_class_label": MIN_CONCRETE_CLASS_LABEL, "min_fck_mpa": MIN_FCK_MPA}, "units": {"fck": "MPa"}},
            {"contract_id": STORY_DRIFT_LIMIT_CONTRACT_ID, "check_id": STORY_DRIFT_CHECK_ID, "code_clause_status": "PENDING_CLAUSE_BINDING", "limit_basis": "Frozen product limit contract; clause binding pending.", "limits": {"max_drift_ratio": MAX_STORY_DRIFT_RATIO}, "units": {"story_drift": "ratio"}},
            {"contract_id": TORSION_A1_LIMIT_CONTRACT_ID, "check_id": TORSION_A1_CHECK_ID, "code_clause_status": "PENDING_CLAUSE_BINDING", "limit_basis": "Frozen product limit contract; clause binding pending.", "limits": {"max_torsion_irregularity_coefficient": MAX_TORSION_A1_COEFFICIENT, "symbol": "eta_bi"}, "units": {"eta_bi": "ratio"}},
        ],
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
        "schema_version": "check_result.v1", "artifact_type": "MODEL_CHECK_RESULT",
        "check_id": MODAL_CHECK_ID, "check_title": "Modal mass participation",
        "check_family": "MODAL_DYNAMIC_CHECKS", "check_level": "MODEL",
        "result_id": "MODAL_MASS_PARTICIPATION:MODEL",
        "model_scope": {"scope_status": "CHECKED", "scope_reason": "Modal participating mass ratios table is available."},
        "input": {"input_status": _summary_input_status(statuses), "missing_inputs": [] if status in {"PASS", "FAIL"} else ["modal_participating_mass"], "input_refs": {"source_table": "Modal Participating Mass Ratios", "rows_considered": rows_considered, "ux_source_column": ux.get("source_column") or "SumUX", "uy_source_column": uy.get("source_column") or "SumUY"}},
        "status": status, "subchecks": subchecks,
        "values": {"ux": ux.get("value"), "uy": uy.get("value"), "rows_considered": rows_considered, "selected_mode": selected_mode},
        "limits": {"modal_mass_threshold": ux.get("limit") or uy.get("limit") or 0.95},
        "comparisons": {"ux": ux.get("comparison"), "uy": uy.get("comparison")},
        "limit_contract": {"contract_id": MODAL_LIMIT_CONTRACT_ID, "contract_file": "check_limit_contract.json", "code_clause_status": "PENDING_CLAUSE_BINDING"},
        "diagnostics": {"warnings": [], "notes": ["Status is according to frozen product limit contract, not full TBDY compliance."]},
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
    }
    return {
        "schema_version": "check_result_file.v1", "artifact_type": "CHECK_RESULT_FILE",
        "check_id": MODAL_CHECK_ID, "check_title": "Modal mass participation",
        "summary": {"status": status, "input_status": _summary_input_status(statuses), "checked_object_count": 1 if status in {"PASS", "FAIL"} else 0, "pass_count": 1 if status == "PASS" else 0, "fail_count": 1 if status == "FAIL" else 0, "no_data_count": 1 if status == "NO_DATA" else 0, "blocked_count": 1 if status in {"BLOCKED", "BLOCKED_INPUT"} else 0, "unsupported_count": 0, "excluded_count": 0, "full_tbdy_compliance_status": FULL_TBDY_STATUS},
        "result": result, "results": [result],
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
        "schema_version": "check_result.v1", "artifact_type": "SECTION_CHECK_RESULT",
        "check_id": MATERIAL_CHECK_ID, "check_title": "Concrete material minimum strength",
        "check_family": "CONCRETE_MATERIAL_INPUT_CHECKS", "check_level": "SECTION",
        "result_id": f"{MATERIAL_CHECK_ID}:{element_type}:{section}", "result_scope": "SECTION",
        "section": section, "element_type": element_type, "assigned_object_count": row.get("assigned_object_count"),
        "material_name": row.get("material_name"), "input_status": input_status,
        "input": {"input_status": input_status, "missing_inputs": missing_inputs, "input_refs": {"material_input_ref": f"{row.get('evidence_table')}:material={row.get('material_name')}", "material_source_row_index": row.get("source_row_index"), "section_source_table": row.get("section_source_table"), "section_source_row_index": row.get("section_source_row_index")}},
        "status": status, "demand": {"fck_mpa": fck},
        "limit": {"min_fck_mpa": MIN_FCK_MPA, "min_concrete_class_label": MIN_CONCRETE_CLASS_LABEL},
        "comparison": {"fck_mpa": comparison},
        "source_refs": {"material_input_ref": f"{row.get('evidence_table')}:material={row.get('material_name')}", "section": section, "source_row_index": row.get("source_row_index")},
        "code_clause_status": "PENDING_CLAUSE_BINDING",
        "limit_contract": {"contract_id": MATERIAL_LIMIT_CONTRACT_ID, "contract_file": "check_limit_contract.json", "code_clause_status": "PENDING_CLAUSE_BINDING"},
        "diagnostics": {"warnings": [] if status in {"PASS", "FAIL"} else ["Concrete fck input is missing or unparseable."], "notes": ["Status is according to frozen product limit contract, not full TBDY material compliance."]},
        "full_tbdy_compliance_status": FULL_TBDY_STATUS,
    }


def build_material_strength_check_result_file(material_evidence_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    results = [_material_strength_row(row) for row in material_evidence_rows if isinstance(row, Mapping)]
    statuses = [str(row.get("status")) for row in results]
    return {
        "schema_version": "check_result_file.v1", "artifact_type": "CHECK_RESULT_FILE",
        "check_id": MATERIAL_CHECK_ID, "check_title": "Concrete material minimum strength",
        "summary": {"status": _overall_status(statuses), "input_status": _summary_input_status(statuses), "checked_section_count": len(results), "checked_object_count": len(results), "pass_count": sum(1 for row in results if row.get("status") == "PASS"), "fail_count": sum(1 for row in results if row.get("status") == "FAIL"), "no_data_count": sum(1 for row in results if row.get("status") == "NO_DATA"), "blocked_count": sum(1 for row in results if row.get("status") in {"BLOCKED", "BLOCKED_INPUT"}), "unsupported_count": 0, "excluded_count": 0, "min_fck_mpa": MIN_FCK_MPA, "min_concrete_class_label": MIN_CONCRETE_CLASS_LABEL, "full_tbdy_compliance_status": FULL_TBDY_STATUS},
        "section_summary": _section_summary(results), "results": results,
    }


def _row_context(row: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    story = _first_present_value(row, ("Story", "StoryName", "Story Name"))
    direction = _first_present_value(row, ("Direction", "Dir"))
    case = _first_present_value(row, ("OutputCase", "Output Case", "Case", "LoadCase", "Load Case", "Load Case/Combo"))
    return story, direction, case


def _case_type_from_row(row: Mapping[str, Any]) -> str | None:
    value = _first_present_value(row, ("CaseType", "Case Type", "LoadCaseType", "Load Case Type", "AnalysisType", "Analysis Type", "ComboType", "Combo Type"))
    return str(value).strip() if value not in (None, "") else None


def _case_type_map_from_source_tables(source_tables: Mapping[str, Any] | None) -> dict[str, str]:
    if not isinstance(source_tables, Mapping):
        return {}
    tables = source_tables.get("tables") if isinstance(source_tables.get("tables"), Mapping) else {}
    out: dict[str, str] = {}
    for table_key, table in tables.items() if isinstance(tables, Mapping) else []:
        if not any(token in str(table_key).casefold() for token in ("case", "combo", "load")):
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
    if any(token in name for token in ("ex", "ey", "eq", "dd", "deprem", "seis", "rs", "rsp", "spectrum")):
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
        observed.append({"source_row_index": index, "load_case_or_combo": case, "case_type": case_type, "case_selection_method": method, "selected": include})
        if include:
            selected.append((index, row, case_type, method))
    diagnostics = {"case_selection_policy": "Use source case/combo type metadata first; use conservative name-pattern fallback only when metadata is unavailable.", "case_type_metadata_available": metadata_seen, "name_pattern_fallback_used": fallback_used, "observed_case_count": len(observed), "selected_case_count": len(selected), "observed_cases": observed, "warnings": []}
    if fallback_used:
        diagnostics["warnings"].append("Case type metadata was unavailable for at least one selected story drift row; NAME_PATTERN_FALLBACK was used.")
    return selected, diagnostics


def _story_drift_result(row: Mapping[str, Any], *, row_index: int, source_table: str, case_type: str | None, case_selection_method: str) -> dict[str, Any]:
    story, direction, case = _row_context(row)
    drift_value = _parse_float(_first_present_value(row, ("Drift", "DriftRatio", "Drift Ratio", "StoryDrift", "Story Drift", "Drift/")))
    status = "NO_DATA" if drift_value is None else ("PASS" if drift_value <= MAX_STORY_DRIFT_RATIO else "FAIL")
    input_status = _input_status_for_status(status)
    source_refs = {"source_table": source_table, "source_row_index": row_index, "load_case_or_combo": case, "case_type": case_type, "case_selection_method": case_selection_method}
    return {
        "schema_version": "check_result.v1", "artifact_type": "STORY_DIRECTION_CASE_CHECK_RESULT",
        "check_id": STORY_DRIFT_CHECK_ID, "check_title": "Story drift", "check_family": "STORY_DRIFT_CHECKS", "check_level": "STORY_DIRECTION_CASE",
        "result_id": f"{STORY_DRIFT_CHECK_ID}:{story or 'UNKNOWN_STORY'}:{direction or 'UNKNOWN_DIRECTION'}:{case or 'UNKNOWN_CASE'}:{row_index}", "result_scope": "STORY_DIRECTION_CASE",
        "story": story, "direction": direction, "load_case_or_combo": case, "case_type": case_type, "case_selection_method": case_selection_method,
        "input_status": input_status, "input": {"input_status": input_status, "missing_inputs": [] if drift_value is not None else ["drift_ratio"], "input_refs": source_refs},
        "status": status, "demand": {"drift_ratio": drift_value}, "limit": {"max_drift_ratio": MAX_STORY_DRIFT_RATIO},
        "comparison": {"drift_ratio": _comparison(drift_value, "<=", MAX_STORY_DRIFT_RATIO)}, "source_refs": source_refs,
        "code_clause_status": "PENDING_CLAUSE_BINDING", "limit_contract": {"contract_id": STORY_DRIFT_LIMIT_CONTRACT_ID, "contract_file": "check_limit_contract.json", "code_clause_status": "PENDING_CLAUSE_BINDING"},
        "diagnostics": {"warnings": [] if drift_value is not None else ["Story drift ratio input is missing or unparseable."], "notes": ["Status is according to frozen product limit contract, not full TBDY compliance."]}, "full_tbdy_compliance_status": FULL_TBDY_STATUS,
    }


def build_story_drift_check_result_file(source_tables: Mapping[str, Any] | None) -> dict[str, Any]:
    rows = _source_rows(source_tables, "story_drifts")
    source_table = _actual_table_name(source_tables, "story_drifts", "Story Drifts")
    selected_rows, diagnostics = _story_drift_selector(rows, source_tables)
    results = [_story_drift_result(row, row_index=index, source_table=source_table, case_type=case_type, case_selection_method=method) for index, row, case_type, method in selected_rows]
    return _story_case_file(check_id=STORY_DRIFT_CHECK_ID, check_title="Story drift", results=results, missing_table_input="story_drifts", diagnostics={"selector_diagnostics": diagnostics})


def _select_torsion_a1_case(case_name: Any, case_type: str | None) -> tuple[bool, str]:
    normalized_type = str(case_type or "").replace("_", " ").replace("-", " ").casefold()
    if normalized_type:
        if "response" in normalized_type and "spectrum" in normalized_type:
            return True, "CASE_TYPE_RESPONSE_SPECTRUM"
        if "seismic" in normalized_type or "earthquake" in normalized_type or "quake" in normalized_type:
            return True, "CASE_TYPE_SEISMIC"
        if any(blocked in normalized_type for blocked in ("wind", "gravity", "dead", "live", "modal")):
            return False, "NOT_SELECTED"
    name = str(case_name or "").strip().casefold()
    if any(token in name for token in ("ex", "ey", "eq", "dd", "deprem", "seis", "rs", "rsp", "spectrum")):
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
        observed.append({"source_row_index": index, "load_case_or_combo": case, "case_type": case_type, "case_selection_method": method, "selected": include})
        if include:
            selected.append((index, row, case_type, method))
    diagnostics = {"case_selection_policy": "Use source case/combo type metadata first; use conservative name-pattern fallback only when metadata is unavailable or generic.", "case_type_metadata_available": metadata_seen, "name_pattern_fallback_used": fallback_used, "observed_case_count": len(observed), "selected_case_count": len(selected), "observed_cases": observed, "warnings": []}
    if fallback_used:
        diagnostics["warnings"].append("Case type metadata was unavailable or generic for at least one selected torsion row; NAME_PATTERN_FALLBACK was used.")
    return selected, diagnostics


def _torsion_a1_result(row: Mapping[str, Any], *, row_index: int, source_table: str, case_type: str | None, case_selection_method: str) -> dict[str, Any]:
    story, direction, case = _row_context(row)
    eta = _parse_float(_first_present_value(row, ("Ratio", "MaxOverAvg", "Max Over Avg", "eta_bi", "EtaBi", "Torsion", "TorsionRatio")))
    status = "NO_DATA" if eta is None else ("PASS" if eta <= MAX_TORSION_A1_COEFFICIENT else "FAIL")
    input_status = _input_status_for_status(status)
    source_refs = {"source_table": source_table, "source_row_index": row_index, "load_case_or_combo": case, "case_type": case_type, "case_selection_method": case_selection_method}
    return {
        "schema_version": "check_result.v1", "artifact_type": "STORY_DIRECTION_CASE_CHECK_RESULT",
        "check_id": TORSION_A1_CHECK_ID, "check_title": "Torsional irregularity A1", "check_family": "TORSIONAL_IRREGULARITY_CHECKS", "check_level": "STORY_DIRECTION_CASE",
        "result_id": f"{TORSION_A1_CHECK_ID}:{story or 'UNKNOWN_STORY'}:{direction or 'UNKNOWN_DIRECTION'}:{case or 'UNKNOWN_CASE'}:{row_index}", "result_scope": "STORY_DIRECTION_CASE",
        "story": story, "direction": direction, "load_case_or_combo": case, "case_type": case_type, "case_selection_method": case_selection_method,
        "input_status": input_status, "input": {"input_status": input_status, "missing_inputs": [] if eta is not None else ["torsion_irregularity_coefficient"], "input_refs": source_refs},
        "status": status, "demand": {"torsion_irregularity_coefficient": eta}, "limit": {"max_torsion_irregularity_coefficient": MAX_TORSION_A1_COEFFICIENT},
        "comparison": {"eta_bi": _comparison(eta, "<=", MAX_TORSION_A1_COEFFICIENT)}, "source_refs": source_refs,
        "code_clause_status": "PENDING_CLAUSE_BINDING", "limit_contract": {"contract_id": TORSION_A1_LIMIT_CONTRACT_ID, "contract_file": "check_limit_contract.json", "code_clause_status": "PENDING_CLAUSE_BINDING"},
        "diagnostics": {"warnings": [] if eta is not None else ["Torsional irregularity coefficient input is missing or unparseable."], "notes": ["Status is according to frozen product limit contract, not full TBDY compliance."]}, "full_tbdy_compliance_status": FULL_TBDY_STATUS,
    }


def build_torsional_irregularity_a1_check_result_file(source_tables: Mapping[str, Any] | None) -> dict[str, Any]:
    rows = _source_rows(source_tables, "story_max_over_avg_drifts")
    source_table = _actual_table_name(source_tables, "story_max_over_avg_drifts", "Story Max Over Avg Drifts")
    selected_rows, diagnostics = _torsion_a1_selector(rows, source_tables)
    results = [_torsion_a1_result(row, row_index=index, source_table=source_table, case_type=case_type, case_selection_method=method) for index, row, case_type, method in selected_rows]
    return _story_case_file(check_id=TORSION_A1_CHECK_ID, check_title="Torsional irregularity A1", results=results, missing_table_input="story_max_over_avg_drifts", diagnostics={"selector_diagnostics": diagnostics})


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
        "schema_version": "check_result_file.v1", "artifact_type": "CHECK_RESULT_FILE", "check_id": check_id, "check_title": check_title,
        "summary": {"status": summary_status, "input_status": input_status, "checked_object_count": len(results), "checked_row_count": len(results), "pass_count": sum(1 for row in results if row.get("status") == "PASS"), "fail_count": sum(1 for row in results if row.get("status") == "FAIL"), "no_data_count": sum(1 for row in results if row.get("status") == "NO_DATA"), "blocked_count": blocked_count, "unsupported_count": 0, "excluded_count": 0, "missing_inputs": [] if results else [missing_table_input], "full_tbdy_compliance_status": FULL_TBDY_STATUS},
        "results": list(results),
    }
    if diagnostics:
        payload["diagnostics"] = dict(diagnostics)
    return payload


def build_blocked_checks() -> dict[str, Any]:
    blocked_checks = [
        {"check_id": "CONCRETE_BEAM_SHEAR_CAPACITY", "check_family": "CONCRETE_BEAM_CAPACITY", "status": "BLOCKED", "input_status": "BLOCKED_INPUT", "missing_inputs": ["design_force_envelope", "shear_rebar", "load_combination_basis", "capacity_model"], "next_required_slice": "force_and_rebar_inputs", "reason": "Required force and reinforcement inputs are not available in the current product slice."},
        {"check_id": "CONCRETE_BEAM_FLEXURE_CAPACITY", "check_family": "CONCRETE_BEAM_CAPACITY", "status": "BLOCKED", "input_status": "BLOCKED_INPUT", "missing_inputs": ["longitudinal_rebar", "design_moment_envelope", "load_combination_basis", "capacity_model"], "next_required_slice": "force_and_rebar_inputs", "reason": "Flexural capacity cannot be evaluated without reinforcement and design moment inputs."},
        {"check_id": "CONCRETE_COLUMN_CAPACITY", "check_family": "CONCRETE_COLUMN_CAPACITY", "status": "BLOCKED", "input_status": "BLOCKED_INPUT", "missing_inputs": ["column_rebar", "axial_force_envelope", "moment_envelope", "interaction_model"], "next_required_slice": "column_force_and_rebar_inputs", "reason": "Column capacity cannot be evaluated without axial/moment/reinforcement inputs."},
        {"check_id": "CAPACITY_DESIGN", "check_family": "CAPACITY_DESIGN", "status": "BLOCKED", "input_status": "BLOCKED_INPUT", "missing_inputs": ["beam_capacity_results", "column_capacity_results", "joint_force_chain", "capacity_design_rules"], "next_required_slice": "capacity_hierarchy_inputs", "reason": "Capacity design requires upstream flexure/shear/capacity results."},
    ]
    return {"schema_version": "blocked_checks.v1", "artifact_type": "BLOCKED_CHECK_LIST", "full_tbdy_compliance_status": FULL_TBDY_STATUS, "blocked_checks": blocked_checks}


def _summary_entry(check_id: str, result_file: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    if payload.get("artifact_type") == "CANONICAL_CHECK_RESULT_COLLECTION":
        return {
            "check_id": check_id,
            "status": None,
            "input_status": "CANONICAL_RESULTS",
            "checked_object_count": summary.get("canonical_result_count", 0),
            "pass_count": summary.get("ok_count", 0),
            "fail_count": summary.get("fail_count", 0),
            "no_data_count": summary.get("no_data_count", 0),
            "blocked_count": summary.get("blocked_count", 0),
            "unsupported_count": summary.get("out_of_scope_count", 0),
            "result_file": result_file,
        }
    return {
        "check_id": check_id, "status": summary.get("status"), "input_status": summary.get("input_status"),
        "checked_object_count": summary.get("checked_object_count") if summary.get("checked_object_count") is not None else summary.get("checked_section_count"),
        "pass_count": summary.get("pass_count", 0), "fail_count": summary.get("fail_count", 0), "no_data_count": summary.get("no_data_count", 0), "blocked_count": summary.get("blocked_count", 0), "unsupported_count": summary.get("unsupported_count", 0), "result_file": result_file,
    }


def build_check_results_summary(*, check_files: Sequence[tuple[str, str, Mapping[str, Any]]], blocked_checks: Mapping[str, Any], product_summary: Mapping[str, Any]) -> dict[str, Any]:
    entries = [_summary_entry(check_id, result_file, payload) for check_id, result_file, payload in check_files]
    blocked_count = len(blocked_checks.get("blocked_checks", []) or [])
    return {
        "schema_version": "check_results_summary.v1", "artifact_type": "CHECK_RESULTS_SUMMARY", "full_tbdy_compliance_status": FULL_TBDY_STATUS,
        "checked_scope_status": product_summary.get("checked_scope_status"), "model_scope_status": product_summary.get("model_scope_status"),
        "summary": {"total_formal_checks": len(entries), "pass_count": sum(int(entry.get("pass_count") or 0) for entry in entries), "fail_count": sum(int(entry.get("fail_count") or 0) for entry in entries), "no_data_count": sum(int(entry.get("no_data_count") or 0) for entry in entries), "blocked_input_count": sum(1 for entry in entries if entry.get("status") == "BLOCKED_INPUT"), "blocked_count": blocked_count, "partial_input_count": sum(1 for entry in entries if entry.get("input_status") == "PARTIAL_INPUT"), "not_applicable_count": sum(int(entry.get("unsupported_count") or 0) for entry in entries)},
        "check_results": entries, "blocked_checks_file": "blocked_checks.json",
    }


def build_formal_check_artifacts(*, report: Mapping[str, Any], object_scope_ledger: Sequence[Mapping[str, Any]], material_evidence_rows: Sequence[Mapping[str, Any]], product_summary: Mapping[str, Any], source_tables: Mapping[str, Any] | None = None) -> dict[str, Any]:
    # object_scope_ledger is intentionally unused for B1 member verdicts.  It remains
    # part of this compatibility signature for unrelated product package callers.
    _ = object_scope_ledger
    beam = _member_collection(report, "beam")
    column = _member_collection(report, "column")
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
        "check_results_summary.json": build_check_results_summary(check_files=check_files, blocked_checks=blocked, product_summary=product_summary),
    }


__all__ = [
    "BEAM_CHECK_ID", "COLUMN_CHECK_ID", "MEMBER_FORMAL_CHECK_IDS", "RETIRED_LEGACY_CHECK_IDS",
    "build_check_catalog", "build_check_limit_contract", "build_formal_check_artifacts",
    "build_modal_mass_check_result_file", "build_material_strength_check_result_file",
    "build_story_drift_check_result_file", "build_torsional_irregularity_a1_check_result_file",
    "build_blocked_checks", "build_check_results_summary",
]
