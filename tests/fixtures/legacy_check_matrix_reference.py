from __future__ import annotations

"""Reduced legacy CHECK_MATRIX metadata for Sprint 4C-4 audit tests.

Test-only reference derived from Supervisor-provided legacy/check_matrix.py.
It contains metadata only; no formulas are executed and no production contract is defined here.
"""

CHECK_MATRIX_VERSION = "2026-04-27.v16"
DEFAULT_TOLERANCE = {"ok": 0.10, "warning": 0.20}
STRICT_TOLERANCE = {"ok": 0.05, "warning": 0.10}

LEGACY_CHECK_MATRIX = {
    "beam_shear": {
        "check": "beam_shear",
        "required_data": ["beam_design_summary", "beam_geometry", "ETABS design Av/s", "ETABS design rebar", "fck", "fyk"],
        "etabs_table": "Concrete Beam Design Summary",
        "etabs_canonical": "beam_design_summary",
        "design_table_required": ["beam_design_summary"],
        "cross_check": True,
        "tolerance": DEFAULT_TOLERANCE,
        "notes": "Uses ETABS Beam Design Summary first; fallback remains screening/manual formula.",
    },
    "column_shear": {
        "check": "column_shear",
        "required_data": ["column_design_summary", "column_forces", "section", "ETABS design longitudinal rebar", "transverse_rebar if available", "fck", "fyk"],
        "etabs_table": "Concrete Column Design Summary",
        "etabs_canonical": "column_design_summary",
        "design_table_required": ["column_design_summary"],
        "cross_check": True,
        "tolerance": DEFAULT_TOLERANCE,
        "notes": "Uses ETABS Column Design Summary first; full shear audit requires transverse/tie data.",
    },
    "column_confinement": {
        "check": "column_confinement",
        "required_data": ["rebar_layout", "tie_spacing", "core_dimension", "fyk"],
        "etabs_table": "Column Reinforcement Details / Concrete Column Reinforcing",
        "etabs_canonical": "column_rebar_defs",
        "cross_check": False,
        "tolerance": None,
        "notes": "Spacing, hook, crosstie, and coverage rules; low coverage downgrades to screening.",
    },
    "column_axial": {
        "check": "column_axial",
        "required_data": ["column_forces", "section_area", "fck"],
        "etabs_table": "Concrete Column Design Summary / Element Forces - Columns",
        "etabs_canonical": "column_forces",
        "design_table_required": ["column_design_summary"],
        "cross_check": True,
        "tolerance": DEFAULT_TOLERANCE,
        "notes": "Can be design-level from force envelope plus section geometry and material strength.",
    },
    "scwb": {
        "check": "scwb",
        "required_data": ["column_moment_capacity", "beam_moment_capacity", "joint_topology"],
        "etabs_table": "SCWB Ratio Table / Concrete Column Capacity Check",
        "etabs_canonical": "scwb_design",
        "design_table_required": ["scwb_design"],
        "cross_check": True,
        "tolerance": STRICT_TOLERANCE,
        "notes": "Use ETABS beam/column design rebar plus topology for manual hierarchy; ETABS ACI SCWB is reference only.",
    },
    "beam_flexure": {
        "check": "beam_flexure",
        "required_data": ["moment", "section", "longitudinal_rebar", "fck", "fyk"],
        "etabs_table": "Beam Flexural Design / Concrete Beam Design Summary",
        "etabs_canonical": "beam_design_summary",
        "design_table_required": ["beam_design_summary"],
        "cross_check": True,
        "tolerance": DEFAULT_TOLERANCE,
        "notes": "Reference target for beam flexure; ETABS design summary is the design-result candidate.",
    },
    "joint_shear": {
        "check": "joint_shear",
        "required_data": ["joint_topology", "beam_design_summary", "column_forces", "frame_section_geometry", "fck"],
        "etabs_table": "Joint Shear Design if available; otherwise manual from ETABS design rebar",
        "etabs_canonical": "joint_shear_design/beam_design_summary",
        "cross_check": True,
        "tolerance": DEFAULT_TOLERANCE,
        "notes": "Manual joint shear uses ETABS-found beam design reinforcement when joint shear table is absent.",
    },
    "joint_dimensions": {
        "check": "joint_dimensions",
        "required_data": ["joint_topology", "column_section_geometry", "beam_section_geometry"],
        "etabs_table": "Objects/Connectivity + Frame Section Properties",
        "etabs_canonical": "frame_rect_sections/frame_assigns_section/topology",
        "cross_check": False,
        "tolerance": None,
        "notes": "Geometry-level design check from topology and assigned section dimensions.",
    },
    "drift": {
        "check": "drift",
        "required_data": ["story_displacement", "story_height"],
        "etabs_table": "Story Drifts / Story Max Over Avg Drifts",
        "etabs_canonical": "story_drifts",
        "design_table_required": ["story_drifts", "story_definitions"],
        "cross_check": False,
        "tolerance": None,
        "notes": "Direct ETABS output; exactness depends on selected load cases and drift scaling.",
    },
    "modal": {
        "check": "modal",
        "required_data": ["modal_results"],
        "etabs_table": "Modal Participating Mass Ratios",
        "etabs_canonical": "modal_mass",
        "design_table_required": ["modal_mass"],
        "cross_check": False,
        "tolerance": None,
        "notes": "Minimum modal mass participation reference requirement.",
    },
    "second_order": {
        "check": "second_order",
        "required_data": ["axial_force", "drift", "height", "story_shear"],
        "etabs_table": "Story Forces + Story Drifts",
        "etabs_canonical": "story_forces/story_drifts",
        "design_table_required": ["story_forces", "story_drifts"],
        "cross_check": False,
        "tolerance": None,
        "notes": "Stability coefficient requires story shear and drift tables.",
    },
}

REQUIRED_MATRIX_FIELDS = ["check", "required_data", "etabs_table", "etabs_canonical", "notes"]
