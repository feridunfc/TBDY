# /etabs/table_catalog.py
"""
Canonical ETABS table catalog.

Single source of truth for:
- canonical table keys
- ETABS table names / aliases
- Excel sheet aliases
- required normalized columns
- unit metadata
- check dependencies

Target verified against ETABS v23.x table names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TableSpec:
    canonical: str
    etabs_names: List[str] = field(default_factory=list)
    excel_sheets: List[str] = field(default_factory=list)
    required_cols: List[str] = field(default_factory=list)
    units: Dict[str, str] = field(default_factory=dict)
    required_for: List[str] = field(default_factory=list)
    parser: Optional[str] = None
    description: str = ""


TABLE_CATALOG: Dict[str, TableSpec] = {
    # ============================================================
    # CORE ANALYSIS
    # ============================================================

    "story_definitions": TableSpec(
        canonical="story_definitions",
        etabs_names=[
            "Story Definitions",
        ],
        excel_sheets=[
            "Story Definitions",
            "Stories",
        ],
        required_cols=["story", "height_m"],
        units={"height_m": "m", "elevation_m": "m"},
        required_for=[
            "building_height_class",
            "drift",
            "soft_story",
            "second_order",
        ],
        description="Story names, elevations and heights.",
    ),

    "story_drifts": TableSpec(
        canonical="story_drifts",
        etabs_names=[
            "Story Max Over Avg Drifts",
            "Story Drifts",
        ],
        excel_sheets=[
            "Story Max Over Avg Drifts",
            "Story Drifts",
        ],
        required_cols=["story", "output_case", "direction", "max_drift"],
        units={"max_drift": "m", "avg_drift": "m"},
        required_for=[
            "drift",
            "torsion",
            "soft_story",
            "second_order",
        ],
        description="Story max/average drifts and torsion ratio.",
    ),

    "story_forces": TableSpec(
        canonical="story_forces",
        etabs_names=[
            "Story Forces",
        ],
        excel_sheets=[
            "Story Forces",
            "Story Shears",
        ],
        required_cols=["story", "output_case", "vx", "vy"],
        units={"p_kn": "kN", "vx": "kN", "vy": "kN"},
        required_for=[
            "second_order",
            "b1_weak_story",
        ],
        description="Story shears and vertical load resultants.",
    ),

    "base_reactions": TableSpec(
        canonical="base_reactions",
        etabs_names=[
            "Base Reactions",
            "Base Reactions (Global)",
            "Base Reactions - Global",
        ],
        excel_sheets=[
            "Base Reactions",
            "Base Reactions (Global)",
            "Base Reactions - Global",
        ],
        required_cols=["output_case", "fx", "fy"],
        units={"fx": "kN", "fy": "kN", "fz": "kN"},
        required_for=[
            "beta_x",
            "beta_y",
            "base_shear_limit",
        ],
        description="Base reactions for RS/EQ cases.",
    ),

    "modal_mass": TableSpec(
        canonical="modal_mass",
        etabs_names=[
            "Modal Participating Mass Ratios",
            "Modal Participation",
        ],
        excel_sheets=[
            "Modal Participating Mass Ratios",
            "Modal Participation",
        ],
        required_cols=["sum_ux", "sum_uy"],
        required_for=["modal"],
        description="Modal participating mass ratios.",
    ),

    "modal_periods": TableSpec(
        canonical="modal_periods",
        etabs_names=[
            "Modal Periods And Frequencies",
            "Modal Periods",
        ],
        excel_sheets=[
            "Modal Periods And Frequencies",
            "Modal Periods",
        ],
        required_cols=["period"],
        units={"period": "s"},
        required_for=["modal"],
        description="Modal periods and frequencies.",
    ),

    "response_spectrum_modal_info": TableSpec(
        canonical="response_spectrum_modal_info",
        etabs_names=[
            "Response Spectrum Modal Info",
        ],
        excel_sheets=[
            "Response Spectrum Modal Info",
        ],
        required_cols=[],
        required_for=["spectrum", "modal"],
        description="Response spectrum modal information.",
    ),

    "auto_seismic": TableSpec(
        canonical="auto_seismic",
        etabs_names=[
            "Load Pattern Definitions - Auto Seismic - TSC 2018",
            "Auto Seismic - TSC 2018",
            "Auto Seismic",
        ],
        excel_sheets=[
            "Load Pattern Definitions - Auto Seismic - TSC 2018",
            "Auto Seismic - TSC 2018",
            "Auto Seismic",
        ],
        required_cols=["name"],
        required_for=[
            "beta_x",
            "beta_y",
            "base_shear_limit",
            "spectrum",
        ],
        description="TBDY/TSC automatic seismic parameters.",
    ),

    "rs_cases": TableSpec(
        canonical="rs_cases",
        etabs_names=[
            "Load Case Definitions - Response Spectrum",
            "Load Cases - Response Spectrum",
        ],
        excel_sheets=[
            "Load Case Definitions - Response Spectrum",
            "Load Cases - Response Spectrum",
        ],
        required_cols=["name", "load_name"],
        required_for=["case_discovery"],
        description="Response spectrum load cases.",
    ),

    "linear_static_cases": TableSpec(
        canonical="linear_static_cases",
        etabs_names=[
            "Load Case Definitions - Linear Static",
            "Load Cases - Linear Static",
        ],
        excel_sheets=[
            "Load Case Definitions - Linear Static",
            "Load Cases - Linear Static",
        ],
        required_cols=["name", "load_name"],
        required_for=["eq_discovery"],
        description="Linear static load cases.",
    ),

    "load_case_summary": TableSpec(
        canonical="load_case_summary",
        etabs_names=[
            "Load Case Definitions - Summary",
        ],
        excel_sheets=[
            "Load Case Definitions - Summary",
        ],
        required_cols=[],
        required_for=["case_discovery"],
        description="Load case summary.",
    ),

    "load_patterns": TableSpec(
        canonical="load_patterns",
        etabs_names=[
            "Load Pattern Definitions",
        ],
        excel_sheets=[
            "Load Pattern Definitions",
        ],
        required_cols=["name"],
        required_for=["mass_source", "load_audit"],
        description="Load pattern definitions.",
    ),

    "load_combos": TableSpec(
        canonical="load_combos",
        etabs_names=[
            "Load Combination Definitions",
            "Load Combinations",
            "Combo Definitions",
        ],
        excel_sheets=[
            "Load Combination Definitions",
            "Load Combinations",
            "Combo Definitions",
        ],
        required_cols=["name"],
        required_for=["combo_discovery"],
        description="Load combination definitions.",
    ),

    "mass_source": TableSpec(
        canonical="mass_source",
        etabs_names=[
            "Mass Source Definition",
        ],
        excel_sheets=[
            "Mass Source Definition",
        ],
        required_cols=[],
        required_for=["modal", "mass_audit"],
        description="Mass source definition.",
    ),

    "mass_summary_story": TableSpec(
        canonical="mass_summary_story",
        etabs_names=[
            "Mass Summary by Story",
        ],
        excel_sheets=[
            "Mass Summary by Story",
        ],
        required_cols=[],
        required_for=["mass_audit"],
        description="Mass summary by story.",
    ),

    "assembled_joint_masses": TableSpec(
        canonical="assembled_joint_masses",
        etabs_names=[
            "Assembled Joint Masses",
        ],
        excel_sheets=[
            "Assembled Joint Masses",
        ],
        required_cols=[],
        required_for=["mass_audit"],
        description="Assembled joint masses.",
    ),

    # ============================================================
    # GEOMETRY / TOPOLOGY
    # ============================================================

    "frame_objects": TableSpec(
        canonical="frame_objects",
        etabs_names=[
            "Objects and Elements - Frames",
        ],
        excel_sheets=[
            "Objects and Elements - Frames",
        ],
        required_cols=["story"],
        required_for=["topology"],
        description="Frame objects/elements and connectivity.",
    ),

    "joint_objects": TableSpec(
        canonical="joint_objects",
        etabs_names=[
            "Objects and Elements - Joints",
            "Point Object Connectivity",
        ],
        excel_sheets=[
            "Objects and Elements - Joints",
            "Point Object Connectivity",
        ],
        required_cols=["name", "x", "y", "z"],
        units={"x": "m", "y": "m", "z": "m"},
        required_for=[
            "topology",
            "a3_plan_irregularity",
        ],
        description="Joint coordinates.",
    ),

    "area_objects": TableSpec(
        canonical="area_objects",
        etabs_names=[
            "Objects and Elements - Areas",
        ],
        excel_sheets=[
            "Objects and Elements - Areas",
        ],
        required_cols=["story"],
        required_for=[
            "a2_slab_discontinuity",
            "a3_plan_irregularity",
            "wall_mapping",
        ],
        description="Area objects/elements.",
    ),

    "column_connectivity": TableSpec(
        canonical="column_connectivity",
        etabs_names=[
            "Column Object Connectivity",
        ],
        excel_sheets=[
            "Column Object Connectivity",
        ],
        required_cols=["story", "unique_name"],
        units={"length_m": "m"},
        required_for=[
            "topology",
            "column_shear",
            "column_confinement",
        ],
        description="Column object connectivity and clear height fallback.",
    ),

    "beam_connectivity": TableSpec(
        canonical="beam_connectivity",
        etabs_names=[
            "Beam Object Connectivity",
        ],
        excel_sheets=[
            "Beam Object Connectivity",
        ],
        required_cols=["story", "unique_name"],
        units={"length_m": "m"},
        required_for=[
            "topology",
            "beam_shear",
        ],
        description="Beam object connectivity and span fallback.",
    ),

    "wall_connectivity": TableSpec(
        canonical="wall_connectivity",
        etabs_names=[
            "Wall Object Connectivity",
        ],
        excel_sheets=[
            "Wall Object Connectivity",
        ],
        required_cols=[],
        required_for=[
            "wall_mapping",
            "wall_shear",
        ],
        description="Wall object connectivity.",
    ),

    "floor_connectivity": TableSpec(
        canonical="floor_connectivity",
        etabs_names=[
            "Floor Object Connectivity",
        ],
        excel_sheets=[
            "Floor Object Connectivity",
        ],
        required_cols=[],
        required_for=[
            "a2_slab_discontinuity",
        ],
        description="Floor object connectivity.",
    ),

    "frame_assigns_section": TableSpec(
        canonical="frame_assigns_section",
        etabs_names=[
            "Frame Assignments - Section Properties",
            "Frame Assigns - Sect Prop",
        ],
        excel_sheets=[
            "Frame Assignments - Section Properties",
            "Frame Assigns - Sect Prop",
        ],
        required_cols=["section"],
        required_for=[
            "topology",
            "column_dimensions",
            "beam_dimensions",
            "column_axial",
            "column_shear",
        ],
        description="Frame-to-section assignments.",
    ),

    "frame_assigns_releases": TableSpec(
        canonical="frame_assigns_releases",
        etabs_names=[
            "Frame Assignments - Releases and Partial Fixity",
        ],
        excel_sheets=[
            "Frame Assignments - Releases and Partial Fixity",
        ],
        required_cols=[],
        required_for=[
            "model_audit",
            "stability_audit",
        ],
        description="Frame releases and partial fixity assignments.",
    ),

    "joint_diaphragms": TableSpec(
        canonical="joint_diaphragms",
        etabs_names=[
            "Joint Assignments - Diaphragms",
            "Joint Assigns - Diaphragms",
        ],
        excel_sheets=[
            "Joint Assignments - Diaphragms",
            "Joint Assigns - Diaphragms",
        ],
        required_cols=[],
        required_for=[
            "a2_slab_discontinuity",
            "a3_plan_irregularity",
        ],
        description="Diaphragm assignments.",
    ),

    "joint_restraints": TableSpec(
        canonical="joint_restraints",
        etabs_names=[
            "Joint Assignments - Restraints",
        ],
        excel_sheets=[
            "Joint Assignments - Restraints",
        ],
        required_cols=[],
        required_for=[
            "model_audit",
            "stability_audit",
        ],
        description="Joint restraint assignments.",
    ),

    # ============================================================
    # SECTION DEFINITIONS
    # ============================================================

    "frame_rect_sections": TableSpec(
        canonical="frame_rect_sections",
        etabs_names=[
            "Frame Section Property Definitions - Concrete Rectangular",
            "Frame Sec Def - Conc Rect",
        ],
        excel_sheets=[
            "Frame Section Property Definitions - Concrete Rectangular",
            "Frame Sec Def - Conc Rect",
        ],
        required_cols=["name", "width_m", "depth_m"],
        units={"width_m": "m", "depth_m": "m"},
        required_for=[
            "column_dimensions",
            "beam_dimensions",
            "column_axial",
            "column_shear",
            "beam_shear",
        ],
        description="Concrete rectangular frame section properties.",
    ),

    "frame_prop_summary": TableSpec(
        canonical="frame_prop_summary",
        etabs_names=[
            "Frame Section Property Definitions - Summary",
            "Frame Assignments - Summary",
            "Frame Prop - Summary",
        ],
        excel_sheets=[
            "Frame Section Property Definitions - Summary",
            "Frame Assignments - Summary",
            "Frame Prop - Summary",
        ],
        required_cols=["name"],
        units={"area_m2": "m2", "i33_m4": "m4", "i22_m4": "m4"},
        required_for=["section_fallback"],
        description="Frame section summary fallback.",
    ),

    "area_section_summary": TableSpec(
        canonical="area_section_summary",
        etabs_names=[
            "Area Section Property Definitions - Summary",
        ],
        excel_sheets=[
            "Area Section Property Definitions - Summary",
        ],
        required_cols=[],
        required_for=["wall_mapping"],
        description="Area section property summary.",
    ),

    "wall_property_defs": TableSpec(
        canonical="wall_property_defs",
        etabs_names=[
            "Wall Property Definitions - Specified",
        ],
        excel_sheets=[
            "Wall Property Definitions - Specified",
        ],
        required_cols=[],
        required_for=[
            "wall_mapping",
            "wall_shear",
        ],
        description="Wall property definitions.",
    ),

    # ============================================================
    # FORCES
    # ============================================================

    "column_forces": TableSpec(
        canonical="column_forces",
        etabs_names=[
            "Element Forces - Columns",
            "Frame Forces - Columns",
            "Design Forces - Columns",
        ],
        excel_sheets=[
            "Element Forces - Columns",
            "Frame Forces - Columns",
            "Design Forces - Columns",
        ],
        required_cols=[
            "p_kn",
            "v2_kn",
            "v3_kn",
            "m2_knm",
            "m3_knm",
        ],
        units={
            "station_m": "m",
            "p_kn": "kN",
            "v2_kn": "kN",
            "v3_kn": "kN",
            "m2_knm": "kNm",
            "m3_knm": "kNm",
        },
        required_for=[
            "column_axial",
            "column_shear",
            "scwb",
            "joint_shear",
        ],
        description="Column internal force rows.",
    ),

    "beam_forces": TableSpec(
        canonical="beam_forces",
        etabs_names=[
            "Element Forces - Beams",
            "Frame Forces - Beams",
            "Design Forces - Beams",
        ],
        excel_sheets=[
            "Element Forces - Beams",
            "Frame Forces - Beams",
            "Design Forces - Beams",
        ],
        required_cols=[
            "v2_kn",
            "v3_kn",
            "m2_knm",
            "m3_knm",
        ],
        units={
            "station_m": "m",
            "p_kn": "kN",
            "v2_kn": "kN",
            "v3_kn": "kN",
            "m2_knm": "kNm",
            "m3_knm": "kNm",
        },
        required_for=[
            "beam_shear",
            "scwb",
            "joint_shear",
        ],
        description="Beam internal force rows.",
    ),

    "pier_forces": TableSpec(
        canonical="pier_forces",
        etabs_names=[
            "Pier Forces",
            "Design Forces - Piers",
        ],
        excel_sheets=[
            "Pier Forces",
            "Design Forces - Piers",
        ],
        required_cols=[
            "pier",
            "p_kn",
            "v2_kn",
            "v3_kn",
            "m2_knm",
            "m3_knm",
        ],
        units={
            "p_kn": "kN",
            "v2_kn": "kN",
            "v3_kn": "kN",
            "m2_knm": "kNm",
            "m3_knm": "kNm",
        },
        required_for=[
            "wall_shear",
            "wall_design_forces",
        ],
        description="Pier force result rows.",
    ),

    # ============================================================
    # REBAR / DESIGN METADATA
    # ============================================================

    "column_rebar_defs": TableSpec(
        canonical="column_rebar_defs",
        etabs_names=[
            "Frame Section Property Definitions - Concrete Column Reinforcing",
            "Frame Section Property Definitions - Concrete Column Reinforcement",
            "Frame Sec Def - Conc Col Reinf",
        ],
        excel_sheets=[
            "Frame Section Property Definitions - Concrete Column Reinforcing",
            "Frame Section Property Definitions - Concrete Column Reinforcement",
            "Frame Sec Def - Conc Col Reinf",
        ],
        required_cols=["name"],
        required_for=[
            "column_confinement",
            "column_shear",
        ],
        description="Column reinforcement definitions from ETABS section definitions.",
    ),

    "beam_rebar_defs": TableSpec(
        canonical="beam_rebar_defs",
        etabs_names=[
            "Frame Section Property Definitions - Concrete Beam Reinforcing",
            "Frame Section Property Definitions - Concrete Beam Reinforcement",
            "Frame Sec Def - Conc Beam Reinf",
        ],
        excel_sheets=[
            "Frame Section Property Definitions - Concrete Beam Reinforcing",
            "Frame Section Property Definitions - Concrete Beam Reinforcement",
            "Frame Sec Def - Conc Beam Reinf",
        ],
        required_cols=["name"],
        required_for=[
            "beam_shear",
        ],
        description="Beam reinforcement definitions.",
    ),

    "rebar_sizes": TableSpec(
        canonical="rebar_sizes",
        etabs_names=[
            "Reinforcing Bar Sizes",
        ],
        excel_sheets=[
            "Reinforcing Bar Sizes",
        ],
        required_cols=[],
        required_for=[
            "column_confinement",
            "beam_shear",
        ],
        description="Reinforcing bar sizes.",
    ),

    "column_design_overwrites": TableSpec(
        canonical="column_design_overwrites",
        etabs_names=[
            "Concrete Column Overwrites - TS 500-2000(R2018)",
            "Conc Col Over TS 500-2000R2018",
        ],
        excel_sheets=[
            "Concrete Column Overwrites - TS 500-2000(R2018)",
            "Conc Col Over TS 500-2000R2018",
        ],
        required_cols=["story"],
        required_for=["column_design_metadata"],
        description="Column design overwrites, not final design results.",
    ),

    "beam_design_overwrites": TableSpec(
        canonical="beam_design_overwrites",
        etabs_names=[
            "Concrete Beam Overwrites - TS 500-2000(R2018)",
            "Conc Bm Over TS 500-2000R2018",
        ],
        excel_sheets=[
            "Concrete Beam Overwrites - TS 500-2000(R2018)",
            "Conc Bm Over TS 500-2000R2018",
        ],
        required_cols=["story"],
        required_for=["beam_design_metadata"],
        description="Beam design overwrites, not final design results.",
    ),

    "conc_design_combos": TableSpec(
        canonical="conc_design_combos",
        etabs_names=[
            "Concrete Frame Design Load Combination Data",
            "Conc Frame Design Combo Data",
        ],
        excel_sheets=[
            "Concrete Frame Design Load Combination Data",
            "Conc Frame Design Combo Data",
        ],
        required_cols=["combo_name"],
        required_for=["design_combo_selection"],
        description="Concrete frame design combination set.",
    ),

    "conc_design_prefs": TableSpec(
        canonical="conc_design_prefs",
        etabs_names=[
            "Concrete Frame Design Preferences - TS 500-2000(R2018)",
        ],
        excel_sheets=[
            "Concrete Frame Design Preferences - TS 500-2000(R2018)",
        ],
        required_cols=[],
        required_for=["design_metadata"],
        description="Concrete frame design preferences.",
    ),

    # ============================================================
    # CONCRETE FRAME DESIGN RESULTS
    # ============================================================

    "column_design_summary": TableSpec(
        canonical="column_design_summary",
        etabs_names=[
            "Concrete Column Design Summary - TS 500-2000(R2018)",
            "Concrete Frame Design Summary - Columns",
            "Concrete Column Design Summary",
            "Column Design Summary",
        ],
        excel_sheets=[
            "Concrete Column Design Summary - TS 500-2000(R2018)",
            "Concrete Frame Design Summary - Columns",
            "Concrete Column Design Summary",
            "Column Design Summary",
        ],
        required_cols=[],
        required_for=[
            "column_axial",
            "column_shear",
            "column_confinement",
        ],
        description="Column design result summary.",
    ),

    "beam_design_summary": TableSpec(
        canonical="beam_design_summary",
        etabs_names=[
            "Concrete Beam Design Summary - TS 500-2000(R2018)",
            "Concrete Frame Design Summary - Beams",
            "Concrete Beam Design Summary",
            "Beam Design Summary",
        ],
        excel_sheets=[
            "Concrete Beam Design Summary - TS 500-2000(R2018)",
            "Concrete Frame Design Summary - Beams",
            "Concrete Beam Design Summary",
            "Beam Design Summary",
        ],
        required_cols=[],
        required_for=[
            "beam_shear",
        ],
        description="Beam design result summary.",
    ),

    "column_pmm_envelope": TableSpec(
        canonical="column_pmm_envelope",
        etabs_names=[
            "Concrete Column PMM Envelope - TS 500-2000(R2018)",
        ],
        excel_sheets=[
            "Concrete Column PMM Envelope - TS 500-2000(R2018)",
        ],
        required_cols=[],
        required_for=[
            "column_axial",
        ],
        description="Concrete column PMM envelope.",
    ),

    "column_shear_envelope": TableSpec(
        canonical="column_shear_envelope",
        etabs_names=[
            "Concrete Column Shear Envelope -  TS 500-2000(R2018)",
            "Concrete Column Shear Envelope - TS 500-2000(R2018)",
        ],
        excel_sheets=[
            "Concrete Column Shear Envelope -  TS 500-2000(R2018)",
            "Concrete Column Shear Envelope - TS 500-2000(R2018)",
        ],
        required_cols=[],
        required_for=[
            "column_shear",
        ],
        description="Concrete column shear design envelope.",
    ),

    "beam_flexure_envelope": TableSpec(
        canonical="beam_flexure_envelope",
        etabs_names=[
            "Concrete Beam Flexure Envelope -  TS 500-2000(R2018)",
            "Concrete Beam Flexure Envelope - TS 500-2000(R2018)",
        ],
        excel_sheets=[
            "Concrete Beam Flexure Envelope -  TS 500-2000(R2018)",
            "Concrete Beam Flexure Envelope - TS 500-2000(R2018)",
        ],
        required_cols=[],
        required_for=[
            "beam_flexure",
        ],
        description="Concrete beam flexure design envelope.",
    ),

    "beam_shear_envelope": TableSpec(
        canonical="beam_shear_envelope",
        etabs_names=[
            "Concrete Beam Shear Envelope -  TS 500-2000(R2018)",
            "Concrete Beam Shear Envelope - TS 500-2000(R2018)",
        ],
        excel_sheets=[
            "Concrete Beam Shear Envelope -  TS 500-2000(R2018)",
            "Concrete Beam Shear Envelope - TS 500-2000(R2018)",
        ],
        required_cols=[],
        required_for=[
            "beam_shear",
        ],
        description="Concrete beam shear design envelope.",
    ),

    # ETABS may not expose SCWB as a separate table for TS500.
    # Keep this canonical key for future versions / Excel imports.
    # Runtime checks should fall back to case-wise directional SCWB if missing.
    "scwb_design": TableSpec(
        canonical="scwb_design",
        etabs_names=[
            "Concrete Column Capacity Check",
            "Concrete Column SCWB",
            "Column Capacity Check",
        ],
        excel_sheets=[
            "Concrete Column Capacity Check",
            "Concrete Column SCWB",
            "Column Capacity Check",
        ],
        required_cols=[],
        required_for=["scwb"],
        description="Strong column weak beam design table if available. Usually unavailable in ETABS TS500; fallback expected.",
    ),

    "joint_shear_design": TableSpec(
        canonical="joint_shear_design",
        etabs_names=[
            "Concrete Joint Design Summary - TS 500-2000(R2018)",
            "Concrete Joint Envelope -  TS 500-2000(R2018)",
            "Concrete Joint Envelope - TS 500-2000(R2018)",
            "Concrete Column Joint Shear",
            "Column Joint Shear",
        ],
        excel_sheets=[
            "Concrete Joint Design Summary - TS 500-2000(R2018)",
            "Concrete Joint Envelope -  TS 500-2000(R2018)",
            "Concrete Joint Envelope - TS 500-2000(R2018)",
            "Concrete Column Joint Shear",
            "Column Joint Shear",
        ],
        required_cols=[],
        required_for=[
            "joint_shear",
        ],
        description="Concrete joint design summary / envelope.",
    ),

    "joint_design_reactions": TableSpec(
        canonical="joint_design_reactions",
        etabs_names=[
            "Joint Design Reactions",
        ],
        excel_sheets=[
            "Joint Design Reactions",
        ],
        required_cols=[],
        required_for=[
            "joint_shear",
        ],
        description="Joint design reactions.",
    ),

    # ============================================================
    # WALL / PIER
    # ============================================================

    "pier_sections": TableSpec(
        canonical="pier_sections",
        etabs_names=[
            "Pier Section Properties",
        ],
        excel_sheets=[
            "Pier Section Properties",
        ],
        required_cols=["pier"],
        units={
            "width_m": "m",
            "thickness_m": "m",
            "area_m2": "m2",
        },
        required_for=[
            "wall_shear",
            "wall_design_forces",
        ],
        description="Pier section properties.",
    ),

    "pier_labels": TableSpec(
        canonical="pier_labels",
        etabs_names=[
            "Pier Label Definitions",
        ],
        excel_sheets=[
            "Pier Label Definitions",
        ],
        required_cols=[],
        required_for=[
            "wall_mapping",
        ],
        description="Pier label definitions.",
    ),

    "area_pier_labels": TableSpec(
        canonical="area_pier_labels",
        etabs_names=[
            "Area Assignments - Pier Labels",
            "Area Assigns - Pier Labels",
        ],
        excel_sheets=[
            "Area Assignments - Pier Labels",
            "Area Assigns - Pier Labels",
        ],
        required_cols=["area", "pier"],
        required_for=[
            "wall_mapping",
        ],
        description="Area to pier labels.",
    ),

    "area_section_assigns": TableSpec(
        canonical="area_section_assigns",
        etabs_names=[
            "Area Assignments - Section Properties",
            "Area Assigns - Sect Prop",
        ],
        excel_sheets=[
            "Area Assignments - Section Properties",
            "Area Assigns - Sect Prop",
        ],
        required_cols=["area", "section"],
        required_for=[
            "wall_mapping",
        ],
        description="Area to section property assignments.",
    ),

    "wall_design_combos": TableSpec(
        canonical="wall_design_combos",
        etabs_names=[
            "Shear Wall Design Combo Data",
        ],
        excel_sheets=[
            "Shear Wall Design Combo Data",
        ],
        required_cols=[],
        required_for=[
            "wall_design",
        ],
        description="Wall design combination data if available.",
    ),

    "wall_design_prefs": TableSpec(
        canonical="wall_design_prefs",
        etabs_names=[
            "Shear Wall Design Preferences - TS 500-2000(R2018)",
            "Shear Wall Pref - TS 500-R2018",
        ],
        excel_sheets=[
            "Shear Wall Design Preferences - TS 500-2000(R2018)",
            "Shear Wall Pref - TS 500-R2018",
        ],
        required_cols=[],
        required_for=[
            "wall_design",
        ],
        description="Wall design preferences.",
    ),

    "wall_design_overwrites": TableSpec(
        canonical="wall_design_overwrites",
        etabs_names=[
            "Shear Wall Pier Design Overwrites - TS 500-2000(R2018)",
        ],
        excel_sheets=[
            "Shear Wall Pier Design Overwrites - TS 500-2000(R2018)",
        ],
        required_cols=[],
        required_for=[
            "wall_design",
        ],
        description="Wall pier design overwrites.",
    ),

    # ETABS TS500 may not expose a pier design summary table.
    # Keep aliases for Excel/manual workflows, but fallback to Pier Forces + Pier Section Properties.
    "wall_design_summary": TableSpec(
        canonical="wall_design_summary",
        etabs_names=[
            "Shear Wall Pier Design Summary",
            "Wall Pier Design Summary",
            "Pier Design Summary",
        ],
        excel_sheets=[
            "Shear Wall Pier Design Summary",
            "Wall Pier Design Summary",
            "Pier Design Summary",
        ],
        required_cols=[],
        required_for=[
            "wall_shear",
            "wall_design_forces",
        ],
        description="Wall pier design result summary if available. Usually unavailable in ETABS TS500; fallback expected.",
    ),

    # ============================================================
    # LOADS / MODEL AUDIT
    # ============================================================

    "area_loads_uniform": TableSpec(
        canonical="area_loads_uniform",
        etabs_names=[
            "Area Load Assignments - Uniform",
            "Area Loads - Uniform",
        ],
        excel_sheets=[
            "Area Load Assignments - Uniform",
            "Area Loads - Uniform",
        ],
        required_cols=[],
        required_for=[
            "load_audit",
            "mass_audit",
        ],
        description="Uniform area load assignments.",
    ),

    "area_loads_nonuniform": TableSpec(
        canonical="area_loads_nonuniform",
        etabs_names=[
            "Area Load Assignments - Non-uniform",
        ],
        excel_sheets=[
            "Area Load Assignments - Non-uniform",
        ],
        required_cols=[],
        required_for=[
            "load_audit",
        ],
        description="Non-uniform area load assignments.",
    ),

    "frame_loads_distributed": TableSpec(
        canonical="frame_loads_distributed",
        etabs_names=[
            "Frame Loads Assignments - Distributed",
            "Frame Loads - Distributed",
        ],
        excel_sheets=[
            "Frame Loads Assignments - Distributed",
            "Frame Loads - Distributed",
        ],
        required_cols=[],
        required_for=[
            "load_audit",
            "mass_audit",
        ],
        description="Distributed frame load assignments.",
    ),

    "joint_loads_force": TableSpec(
        canonical="joint_loads_force",
        etabs_names=[
            "Joint Loads Assignments - Force",
        ],
        excel_sheets=[
            "Joint Loads Assignments - Force",
        ],
        required_cols=[],
        required_for=[
            "load_audit",
        ],
        description="Joint force load assignments.",
    ),

    "material_general": TableSpec(
        canonical="material_general",
        etabs_names=[
            "Material Properties - General",
        ],
        excel_sheets=[
            "Material Properties - General",
        ],
        required_cols=[],
        required_for=[
            "material_audit",
        ],
        description="Material general properties.",
    ),

    "material_concrete": TableSpec(
        canonical="material_concrete",
        etabs_names=[
            "Material Properties - Concrete Data",
        ],
        excel_sheets=[
            "Material Properties - Concrete Data",
        ],
        required_cols=[],
        required_for=[
            "material_audit",
        ],
        description="Concrete material data.",
    ),

    "program_control": TableSpec(
        canonical="program_control",
        etabs_names=[
            "Program Control",
        ],
        excel_sheets=[
            "Program Control",
        ],
        required_cols=[],
        required_for=[
            "metadata",
            "unit_audit",
        ],
        description="Program control and current units.",
    ),

    "project_information": TableSpec(
        canonical="project_information",
        etabs_names=[
            "Project Information",
        ],
        excel_sheets=[
            "Project Information",
        ],
        required_cols=[],
        required_for=[
            "metadata",
        ],
        description="ETABS project information.",
    ),
    "area_load_uniform": TableSpec(
        canonical="area_load_uniform",
        etabs_names=[
            "Area Load Assignments - Uniform",
        ],
        required_cols=[],
    ),

    "area_load_nonuniform": TableSpec(
        canonical="area_load_nonuniform",
        etabs_names=[
            "Area Load Assignments - Non-uniform",
        ],
        required_cols=[],
    ),
}


def _norm_name(name: str) -> str:
    """
    Normalize an ETABS table name for fuzzy comparison.

    Handles:
    - extra spaces
    - hyphen spacing
    - capitalization
    - common punctuation
    """
    return (
        str(name)
        .strip()
        .lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("_", "")
        .replace("(", "")
        .replace(")", "")
    )


def resolve_etabs_name(canonical: str, available_tables: List[str]) -> Optional[str]:
    """
    Resolve canonical key to an available ETABS table name.

    Resolution order:
    1. exact case-sensitive match
    2. exact case-insensitive match
    3. normalized exact match
    4. conservative containment match
    """
    spec = TABLE_CATALOG.get(canonical)
    if spec is None:
        return None

    available_set = set(available_tables)

    # 1. Exact match
    for name in spec.etabs_names:
        if name in available_set:
            return name

    # 2. Case-insensitive exact match
    available_lower = {a.lower(): a for a in available_tables}
    for name in spec.etabs_names:
        key = name.lower()
        if key in available_lower:
            return available_lower[key]

    # 3. Normalized exact match
    available_norm = {_norm_name(a): a for a in available_tables}
    for name in spec.etabs_names:
        key = _norm_name(name)
        if key in available_norm:
            return available_norm[key]

    # 4. Conservative containment match
    for name in spec.etabs_names:
        n = _norm_name(name)
        if not n:
            continue
        for a in available_tables:
            al = _norm_name(a)
            if n in al or al in n:
                return a

    return None


def get_required_for_check(check_name: str) -> List[str]:
    return [k for k, spec in TABLE_CATALOG.items() if check_name in spec.required_for]


def get_all_canonical_keys() -> List[str]:
    return list(TABLE_CATALOG.keys())


def get_table_description(canonical: str) -> str:
    spec = TABLE_CATALOG.get(canonical)
    return spec.description if spec else ""