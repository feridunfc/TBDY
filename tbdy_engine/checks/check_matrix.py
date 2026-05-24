
from __future__ import annotations

"""TS500 / TBDY reference check matrix.

This file is the single source of truth for:
- code clause shown in reports,
- data required for design/screening level execution,
- governing formula text,
- ETABS design table used for cross-check,
- tolerance policy.

The matrix does not execute calculations. It standardizes dependency
validation, registry metadata, cross-check policy, report narratives, and UI
contracts around the same engineering definition.
"""

from copy import deepcopy
from typing import Any, Dict, Mapping

CHECK_MATRIX_VERSION = "2026-04-27.v16"
DEFAULT_TOLERANCE = {"ok": 0.10, "warning": 0.20}
STRICT_TOLERANCE = {"ok": 0.05, "warning": 0.10}

CHECK_MATRIX: Dict[str, Dict[str, Any]] = {
    "beam_shear": {
        "check": "beam_shear",
        "code": "TS500 / TBDY 2018",
        "clause": "TS500 §7.4; TBDY 2018 §7.4.2",
        "level": "DESIGN",
        "required_data": ["beam_design_summary", "beam_geometry", "ETABS design Av/s", "ETABS design rebar", "fck", "fyk"],
        "design_required": ["beam_transverse_rebar_defs", "design_basis.materials_verified"],
        "screening_required": ["beam_forces", "frame_rect_sections"],
        "formula": "V_rd = V_c + V_s",
        "detail": {
            "V_c": "0.65 * f_ctd * b_w * d",
            "V_s": "(A_sw / s) * f_yd * d",
            "demand": "V_ed = max(V_analysis, (M_pi + M_pj) / l_n)",
            "condition": "V_ed <= V_rd",
        },
        "etabs_table": "Concrete Beam Design Summary",
        "etabs_canonical": "beam_design_summary",
        "design_table_required": ["beam_design_summary"],
        "manual_design_required": ["beam_transverse_rebar_defs", "design_basis.materials_verified"],
        "data_source_policy": ["ETABS_DESIGN_RESULT", "MANUAL_FORMULA", "SCREENING_FALLBACK", "NO_DATA"],
        "cross_check": True,
        "tolerance": DEFAULT_TOLERANCE,
        "notes": "V16 uses ETABS Beam Design Summary first. ETABS-found design reinforcement and Av/s feed TS500 Vc+Vs audit; if the table is absent, fallback remains screening/manual formula.",
    },
    "column_shear": {
        "check": "column_shear",
        "code": "TBDY 2018 / TS500",
        "clause": "TBDY 2018 §7.3.7; TS500 shear capacity basis",
        "level": "DESIGN",
        "required_data": ["column_design_summary", "column_forces", "section", "ETABS design longitudinal rebar", "transverse_rebar if available", "fck", "fyk"],
        "design_required": ["column_transverse_rebar_defs", "design_basis.materials_verified"],
        "screening_required": ["column_forces", "frame_rect_sections"],
        "formula": "V_rd = V_c + V_s",
        "detail": {
            "V_c": "0.65 * f_ctd * b_w * d",
            "V_s": "(A_sw / s) * f_ywd * d",
            "demand": "V_ed = max(V_analysis, (M_a + M_u) / l_n)",
            "condition": "V_ed <= V_rd",
        },
        "etabs_table": "Concrete Column Design Summary",
        "etabs_canonical": "column_design_summary",
        "design_table_required": ["column_design_summary"],
        "manual_design_required": ["column_transverse_rebar_defs", "design_basis.materials_verified"],
        "data_source_policy": ["ETABS_DESIGN_RESULT", "MANUAL_FORMULA", "SCREENING_FALLBACK", "NO_DATA"],
        "cross_check": True,
        "tolerance": DEFAULT_TOLERANCE,
        "notes": "V16 uses ETABS Column Design Summary first. ETABS-found longitudinal design rebar is used for capacity-demand audit; full Vc+Vs audit requires transverse/tie data.",
    },
    "column_confinement": {
        "check": "column_confinement",
        "code": "TBDY 2018",
        "clause": "TBDY 2018 §7.3.4.2",
        "level": "DESIGN",
        "required_data": ["rebar_layout", "tie_spacing", "core_dimension", "fyk"],
        "design_required": ["column_rebar_defs", "design_basis.materials_verified"],
        "screening_required": ["frame_rect_sections"],
        "formula": "s <= min(s_max, 8*d_b, 150 mm)",
        "detail": {
            "spacing": "s <= min(100 mm, b_min/3) for high-ductility critical confinement regions unless project basis overrides",
            "coverage": "element-level rebar definition coverage must be adequate",
        },
        "etabs_table": "Column Reinforcement Details / Concrete Column Reinforcing",
        "etabs_canonical": "column_rebar_defs",
        "cross_check": False,
        "tolerance": None,
        "notes": "Spacing, hook, crosstie, and coverage rules. Low rebar coverage downgrades to SCREENING.",
    },
    "column_axial": {
        "check": "column_axial",
        "code": "TBDY 2018 / TS500",
        "clause": "TBDY 2018 §7.3.1; TS500 axial/PMM basis",
        "level": "DESIGN",
        "required_data": ["column_forces", "section_area", "fck"],
        "design_required": ["column_forces", "frame_rect_sections", "design_basis.materials_present"],
        "screening_required": ["column_forces", "frame_rect_sections"],
        "formula": "N_d / (A_c * f_ck) <= 0.40",
        "detail": {
            "capacity": "N_cap = A_c * f_ck",
            "condition": "N_d / N_cap <= 0.40",
            "note": "Uses force envelope and section area; PMM design table, if present, remains preferred source-of-truth."
        },
        "etabs_table": "Concrete Column Design Summary / Element Forces - Columns",
        "etabs_canonical": "column_forces",
        "design_table_required": ["column_design_summary"],
        "manual_design_required": ["column_forces", "frame_rect_sections", "design_basis.materials_present"],
        "data_source_policy": ["ETABS_DESIGN_RESULT", "MANUAL_FORMULA", "NO_DATA"],
        "cross_check": True,
        "tolerance": DEFAULT_TOLERANCE,
        "notes": "Can be design-level from existing force envelope + section geometry + material strength. PMM ratio from ETABS is used when available.",
    },
    "scwb": {
        "check": "scwb",
        "code": "TBDY 2018",
        "clause": "TBDY 2018 §7.3.5",
        "level": "DESIGN",
        "required_data": ["column_moment_capacity", "beam_moment_capacity", "joint_topology"],
        "design_required": ["beam_design_summary", "column_design_summary", "joint_topology"],
        "screening_required": ["scwb_capacity_inputs"],
        "fallback_level": "APPROXIMATE",
        "formula": "ΣM_column >= 1.2 * ΣM_beam",
        "detail": {
            "condition": "sum(Mp_column) / max(sum(Mp_beam), eps) >= 1.2",
            "warning": "manual capacity without PMM interaction remains APPROXIMATE",
        },
        "etabs_table": "SCWB Ratio Table / Concrete Column Capacity Check",
        "etabs_canonical": "scwb_design",
        "design_table_required": ["scwb_design"],
        "manual_design_required": ["scwb_capacity_inputs", "design_basis.materials_verified"],
        "data_source_policy": ["MANUAL_TBDY_WITH_ETABS_DESIGN_REBAR", "ETABS_ACI_REFERENCE_ONLY", "SCREENING_FALLBACK", "NO_DATA"],
        "cross_check": True,
        "tolerance": STRICT_TOLERANCE,
        "notes": "ETABS TBDY SCWB table may not exist. V16 policy is to use ETABS beam/column design rebar plus topology for manual TBDY hierarchy; ACI SCWB is reference only.",
    },
    "beam_flexure": {
        "check": "beam_flexure",
        "code": "TS500",
        "clause": "TS500 §7.2",
        "level": "DESIGN",
        "required_data": ["moment", "section", "longitudinal_rebar", "fck", "fyk"],
        "design_required": ["beam_rebar_defs", "beam_forces", "design_basis.materials_verified"],
        "screening_required": ["beam_forces", "frame_rect_sections"],
        "formula": "M_rd >= M_ed",
        "detail": {"capacity": "rectangular stress block / section capacity model", "condition": "M_ed <= M_rd"},
        "etabs_table": "Beam Flexural Design / Concrete Beam Design Summary",
        "etabs_canonical": "beam_design_summary",
        "design_table_required": ["beam_design_summary"],
        "manual_design_required": ["beam_transverse_rebar_defs", "design_basis.materials_verified"],
        "data_source_policy": ["ETABS_DESIGN_RESULT", "MANUAL_FORMULA", "SCREENING_FALLBACK", "NO_DATA"],
        "cross_check": True,
        "tolerance": DEFAULT_TOLERANCE,
        "notes": "Planned design check; currently used as reference matrix/golden-test target unless check function is registered.",
    },
    "joint_shear": {
        "check": "joint_shear",
        "code": "TBDY 2018",
        "clause": "TBDY 2018 §7.4.5 / §7.5",
        "level": "DESIGN",
        "required_data": ["joint_topology", "beam_design_summary", "column_forces", "frame_section_geometry", "fck"],
        "design_required": ["beam_design_summary", "joint_topology", "column_forces"],
        "screening_required": ["joint_topology", "beam_forces", "column_forces"],
        "formula": "V_joint = Σ(M_p,beam/l_n) - V_col <= 1.7√fck b_j h_j",
        "detail": {"capacity": "Vmax = 1.7*sqrt(fck)*bj*hj*confinement_factor", "demand": "beam probable moments from ETABS design rebar"},
        "etabs_table": "Joint Shear Design if available; otherwise manual from ETABS design rebar",
        "etabs_canonical": "joint_shear_design/beam_design_summary",
        "cross_check": True,
        "tolerance": DEFAULT_TOLERANCE,
        "notes": "V16 manual joint shear uses ETABS-found beam design reinforcement. Missing topology/rebar lowers confidence to APPROXIMATE or NO_DATA.",
    },
    "joint_dimensions": {
        "check": "joint_dimensions",
        "code": "TBDY 2018",
        "clause": "TBDY 2018 §7.4.5(c)",
        "level": "DESIGN",
        "required_data": ["joint_topology", "column_section_geometry", "beam_section_geometry"],
        "design_required": ["topology", "frame_rect_sections", "frame_assigns_section"],
        "screening_required": ["topology", "frame_rect_sections"],
        "formula": "b_j >= min(b_b, b_c + h_c) and beam width compatible with column/joint width",
        "detail": {"condition": "joint geometric compatibility must be satisfied for every beam-column joint"},
        "etabs_table": "Objects/Connectivity + Frame Section Properties",
        "etabs_canonical": "frame_rect_sections/frame_assigns_section/topology",
        "cross_check": False,
        "tolerance": None,
        "notes": "Geometry-level design check from topology and assigned section dimensions; joint shear still requires separate design table or capacity model.",
    },
    "drift": {
        "check": "drift",
        "code": "TBDY 2018",
        "clause": "TBDY 2018 §4.9",
        "level": "EXACT",
        "required_data": ["story_displacement", "story_height"],
        "design_required": ["story_drifts", "story_definitions"],
        "screening_required": ["story_drifts"],
        "formula": "Δ / h <= limit",
        "detail": {"limit": "TBDY drift limit from project wall/connection condition"},
        "etabs_table": "Story Drifts / Story Max Over Avg Drifts",
        "etabs_canonical": "story_drifts",
        "cross_check": False,
        "tolerance": None,
        "notes": "Direct ETABS output; exactness depends on selected load cases and drift scaling.",
    },
    "modal": {
        "check": "modal",
        "code": "TBDY 2018",
        "clause": "TBDY 2018 §4.8.1",
        "level": "EXACT",
        "required_data": ["modal_results"],
        "design_required": ["modal_mass"],
        "screening_required": ["modal_mass"],
        "formula": "ΣUX >= 0.90 and ΣUY >= 0.90",
        "detail": {"minimum_mass_participation": 0.90},
        "etabs_table": "Modal Participating Mass Ratios",
        "etabs_canonical": "modal_mass",
        "cross_check": False,
        "tolerance": None,
        "notes": "Minimum 90% mass participation in each horizontal direction.",
    },
    "second_order": {
        "check": "second_order",
        "code": "TBDY 2018",
        "clause": "TBDY 2018 §4.9.3",
        "level": "DESIGN",
        "required_data": ["axial_force", "drift", "height", "story_shear"],
        "design_required": ["story_forces", "story_drifts"],
        "screening_required": ["story_drifts"],
        "formula": "θ = (ΣP * Δ) / (V * h)",
        "detail": {"limit": 0.12, "condition": "θ <= 0.12"},
        "etabs_table": "Story Forces + Story Drifts",
        "etabs_canonical": "story_forces/story_drifts",
        "cross_check": False,
        "tolerance": None,
        "notes": "Stability coefficient. Design-level requires story shear and vertical load basis.",
    },
}

_REQUIRED_MATRIX_FIELDS = ["check", "code", "clause", "level", "required_data", "formula", "etabs_table", "cross_check", "notes"]


def get_check_spec(check_name: str) -> Dict[str, Any]:
    return deepcopy(CHECK_MATRIX.get(check_name, {}))


def registry_metadata_from_matrix(check_name: str) -> Dict[str, Any]:
    spec = CHECK_MATRIX.get(check_name, {})
    if not spec:
        return {}
    return {
        "category": _category_for(check_name),
        "level": spec.get("level", "APPROXIMATE"),
        "code_ref": f"{spec.get('code', '')} {spec.get('clause', '')}".strip(),
        "clause": spec.get("clause"),
        "formula": spec.get("formula"),
        "formula_detail": spec.get("detail", {}),
        "required_data": list(spec.get("required_data", [])),
        "required_tables": [spec.get("etabs_canonical") or spec.get("etabs_table")],
        "etabs_table": spec.get("etabs_table"),
        "cross_check": bool(spec.get("cross_check")),
        "tolerance": spec.get("tolerance"),
        "notes": spec.get("notes", ""),
    }


def dependency_spec_from_matrix(check_name: str) -> Dict[str, Any]:
    spec = CHECK_MATRIX.get(check_name, {})
    if not spec:
        return {}
    impact_screening = (
        f"{check_name} kontrolü {spec.get('level', 'DESIGN')} hedefli bir kontroldür; "
        "design-level için gerekli veri eksik olduğundan sonuç SCREENING/APPROXIMATE seviyesinde değerlendirilmelidir. "
        f"Eksik veri etkisi: {spec.get('notes', '')}"
    )
    impact_no_data = (
        f"{check_name} kontrolü için minimum veri seti eksiktir; "
        "bu kontrol güvenilir biçimde çalıştırılamaz."
    )
    return {
        "code_ref": f"{spec.get('code', '')} {spec.get('clause', '')}".strip(),
        "design_required": list(spec.get("design_required", [])),
        "design_table_required": list(spec.get("design_table_required", [])),
        "manual_design_required": list(spec.get("manual_design_required", [])),
        "screening_required": list(spec.get("screening_required", [])),
        "fallback_level": spec.get("fallback_level"),
        "impact_screening": impact_screening,
        "impact_no_data": impact_no_data,
        "matrix": get_check_spec(check_name),
    }


def dependency_specs_from_matrix() -> Dict[str, Dict[str, Any]]:
    return {name: dependency_spec_from_matrix(name) for name in CHECK_MATRIX}


def public_check_matrix() -> Dict[str, Any]:
    return {"version": CHECK_MATRIX_VERSION, "checks": deepcopy(CHECK_MATRIX)}


def validate_check_matrix(matrix: Mapping[str, Mapping[str, Any]] | None = None) -> Dict[str, Any]:
    matrix = matrix or CHECK_MATRIX
    issues = []
    for name, spec in matrix.items():
        for field in _REQUIRED_MATRIX_FIELDS:
            if field not in spec or spec.get(field) in (None, ""):
                issues.append({"severity": "ERROR", "check": name, "code": "MATRIX_FIELD_MISSING", "field": field})
        if spec.get("cross_check") and not spec.get("tolerance"):
            issues.append({"severity": "ERROR", "check": name, "code": "CROSSCHECK_TOLERANCE_MISSING", "field": "tolerance"})
        tol = spec.get("tolerance") or {}
        if tol:
            ok = float(tol.get("ok", 0))
            warn = float(tol.get("warning", 0))
            if not (0 < ok <= warn):
                issues.append({"severity": "ERROR", "check": name, "code": "INVALID_TOLERANCE", "field": "tolerance"})
    return {
        "valid": not any(i["severity"] == "ERROR" for i in issues),
        "version": CHECK_MATRIX_VERSION,
        "issues": issues,
        "total_checks": len(matrix),
    }


def _category_for(check_name: str) -> str:
    if check_name.startswith("beam"):
        return "beams"
    if check_name.startswith("column") or check_name == "scwb":
        return "columns"
    if check_name in {"drift", "modal", "second_order"}:
        return "global"
    return "general"
