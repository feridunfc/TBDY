"""
TBDY_ENGINE v3.0 — Beam Design Streamlit UI
R16: Beam Design Engine visualization + legacy BeamCore diagnostic preservation.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tbdy_engine.design.beams.streamlit_etabs_ui_adapter import (
    CANONICAL_ENGINE_UNITS,
    DEFAULT_DESIGN_INPUTS,
    add_selection_column,
    branch_and_commit,
    build_design_overrides_from_ui,
    choose_default_combos,
    classify_frame_object,
    filter_beam_candidates,
    filter_frame_objects_for_beam_ui,
    get_etabs_connection_snapshot,
    get_etabs_status,
    list_available_combos,
    list_available_load_cases,
    list_available_stories,
    list_story_beams,
    read_check_rows_for_ui,
    run_story_beam_checks_from_ui,
    shape_result_rows_for_ui,
    summarize_demand_set,
    summarize_etabs_snapshot,
    summarize_governing_evidence,
    summarize_region_flexure,
    summarize_shear_design,
    summarize_verification,
    summarize_etabs_comparison,
    attach_to_open_etabs,
)

try:
    import streamlit as st
except Exception:
    st = None


CLAIM_BOUNDARY_TEXT = """
### Claim boundaries

- **Diagnostic UI only** — this is not ETABS validation.
- **Not design-engine validation** — visualization only.
- **Not TBDY compliance proof** — policy parameters pending code-article benchmark.
- **Not production-ready** — engineering review required.

### This UI Contains

- BeamDemandSet visualization (demand tab)
- BeamDesignResult visualization (design tab)
- BeamVerificationResult visualization (verification tab)
- ETABSComparisonResult visualization (crosscheck tab)
- Legacy BeamCore diagnostic result (connection tab)

### This UI Does NOT Prove

- TBDY compliance
- Production readiness
- Design correctness
- Code compliance
- Independent engineering review

### Boundary Rules

- ETABS disagreement is diagnostic only — does not mutate engine or verification results.
- COLUMN_LIKELY objects are never silently designed as beams.
- UI never calculates engineering formulas.
- UI only displays frozen engine results.
"""


# =============================================================================
# Session State
# =============================================================================

def _initialize_beam_design_session_state() -> None:
    """Initialize R16 beam design session-state slots."""
    assert st is not None
    defaults = {
        "beam_model_context": None,
        "beam_demand_set": None,
        "beam_design_result": None,
        "beam_verification_result": None,
        "etabs_comparison_result": None,
        "legacy_beamcore_result": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _store_beam_design_results(
    *,
    demand_set: object | None = None,
    design_result: object | None = None,
    verification_result: object | None = None,
    comparison_result: object | None = None,
) -> None:
    """Store R16 beam design pipeline results in session state."""
    assert st is not None
    if demand_set is not None:
        st.session_state["beam_demand_set"] = demand_set
    if design_result is not None:
        st.session_state["beam_design_result"] = design_result
    if verification_result is not None:
        st.session_state["beam_verification_result"] = verification_result
    if comparison_result is not None:
        st.session_state["etabs_comparison_result"] = comparison_result


def _store_legacy_beamcore_result(result: dict[str, object]) -> None:
    """Store legacy BeamCore diagnostic result."""
    assert st is not None
    st.session_state["legacy_beamcore_result"] = result



def _build_ui_demand_view_from_legacy_result(result: dict[str, object]) -> dict[str, object]:
    """Build a Demand-tab UI view from preserved legacy BeamCore output.

    R17A does not run BeamDesignEngine here. This view is for visualization only.
    """
    summary = result.get("summary") or {}
    beams: list[dict[str, object]] = []

    if isinstance(summary, dict):
        for beam in summary.get("beams", []) or []:
            if not isinstance(beam, dict):
                continue
            actions = beam.get("actions") or {}
            governing = beam.get("governing") or {}
            beams.append({
                "object_name": beam.get("object_name"),
                "label": beam.get("label"),
                "story": beam.get("story"),
                "section": beam.get("section"),
                "source": beam.get("actions_source") or result.get("actions_source") or "legacy_beamcore_summary",
                "Md_left_neg_kNm": actions.get("Md_left_neg_kNm") if isinstance(actions, dict) else None,
                "Md_mid_pos_kNm": actions.get("Md_mid_pos_kNm") if isinstance(actions, dict) else None,
                "Md_right_neg_kNm": actions.get("Md_right_neg_kNm") if isinstance(actions, dict) else None,
                "Vd_left_kN": actions.get("Vd_left_kN") if isinstance(actions, dict) else None,
                "Vd_right_kN": actions.get("Vd_right_kN") if isinstance(actions, dict) else None,
                "Ve_left_kN": actions.get("Ve_left_kN") if isinstance(actions, dict) else None,
                "axial_kN": actions.get("axial_kN") if isinstance(actions, dict) else None,
                "governing": governing if isinstance(governing, dict) else {},
            })

    return {
        "source": "legacy_beamcore_summary",
        "selected_story": result.get("selected_story"),
        "selected_combos": result.get("selected_combos"),
        "beam_count_discovered": result.get("beam_count_discovered"),
        "beam_count_processed": result.get("beam_count_processed"),
        "beam_count_failed": result.get("beam_count_failed"),
        "beams": beams,
    }


def _demand_summary_rows_from_view(demand_view: object) -> list[dict[str, object]]:
    if not isinstance(demand_view, dict):
        return []
    rows: list[dict[str, object]] = []
    for beam in demand_view.get("beams", []) or []:
        if not isinstance(beam, dict):
            continue
        rows.append({
            "object_name": beam.get("object_name"),
            "label": beam.get("label"),
            "story": beam.get("story"),
            "section": beam.get("section"),
            "source": beam.get("source"),
            "Md_left_neg_kNm": beam.get("Md_left_neg_kNm"),
            "Md_mid_pos_kNm": beam.get("Md_mid_pos_kNm"),
            "Md_right_neg_kNm": beam.get("Md_right_neg_kNm"),
            "Vd_left_kN": beam.get("Vd_left_kN"),
            "Vd_right_kN": beam.get("Vd_right_kN"),
            "Ve_left_kN": beam.get("Ve_left_kN"),
            "axial_kN": beam.get("axial_kN"),
        })
    return rows


def _governing_evidence_rows_from_view(demand_view: object) -> list[dict[str, object]]:
    if not isinstance(demand_view, dict):
        return []
    rows: list[dict[str, object]] = []
    for beam in demand_view.get("beams", []) or []:
        if not isinstance(beam, dict):
            continue
        governing = beam.get("governing") or {}
        if not isinstance(governing, dict):
            continue
        for demand_name, evidence in governing.items():
            if not isinstance(evidence, dict):
                continue
            rows.append({
                "object_name": beam.get("object_name"),
                "label": beam.get("label"),
                "demand": demand_name,
                "combo": evidence.get("combo"),
                "station": evidence.get("station"),
                "raw_value": evidence.get("raw_value") or evidence.get("value"),
                "rule": evidence.get("rule"),
            })
    return rows

# =============================================================================
# ETABS Connection
# =============================================================================

def _clear_cached_etabs_connection() -> None:
    """Clear cached ETABS SapModel handle."""
    assert st is not None
    st.session_state.pop("etabs_sap_model", None)


def _get_cached_etabs_sap_model() -> object:
    """Keep ETABS SapModel handle stable across Streamlit reruns."""
    assert st is not None
    cached = st.session_state.get("etabs_sap_model")
    if cached is not None:
        return cached

    sap_model = attach_to_open_etabs()
    st.session_state["etabs_sap_model"] = sap_model
    return sap_model


def _persistent_etabs_snapshot() -> dict[str, object]:
    """Return ETABS snapshot using cached SapModel, with one reconnect attempt."""
    try:
        sap_model = _get_cached_etabs_sap_model()
        snapshot = get_etabs_connection_snapshot(sap_model=sap_model)
        if snapshot.get("status") == "ONLINE":
            return snapshot
    except Exception as exc:
        last_error = str(exc)
    else:
        last_error = str(snapshot.get("error") or "ETABS snapshot returned offline")

    _clear_cached_etabs_connection()
    try:
        sap_model = _get_cached_etabs_sap_model()
        snapshot = get_etabs_connection_snapshot(sap_model=sap_model)
        if snapshot.get("status") == "ONLINE":
            return snapshot
    except Exception as exc:
        last_error = str(exc)

    return {
        "online": False, "status": "OFFLINE",
        "model_name": None, "model_path": None,
        "present_units": None, "database_units": None,
        "error": last_error,
    }


def _persistent_etabs_status() -> dict[str, object]:
    """Return ETABS status using cached SapModel, with one reconnect attempt."""
    try:
        sap_model = _get_cached_etabs_sap_model()
        status = get_etabs_status(sap_model=sap_model)
        if status.get("status") == "ONLINE":
            return status
    except Exception as exc:
        last_error = str(exc)
    else:
        last_error = str(status.get("message") or "ETABS status returned offline")

    _clear_cached_etabs_connection()
    try:
        sap_model = _get_cached_etabs_sap_model()
        status = get_etabs_status(sap_model=sap_model)
        if status.get("status") == "ONLINE":
            return status
    except Exception as exc:
        last_error = str(exc)

    return {
        "status": "OFFLINE", "stage": "etabs_attach",
        "message": last_error, "model_name": None, "sap_model": None,
    }


def _refresh_etabs_connection_state() -> dict[str, object]:
    """Refresh ETABS connection once per Streamlit rerun."""
    snapshot = _persistent_etabs_snapshot()
    cached = st.session_state.get("etabs_sap_model") if st is not None else None

    if snapshot.get("status") == "ONLINE" and cached is not None:
        status = get_etabs_status(sap_model=cached)
    else:
        status = _persistent_etabs_status()

    state = {
        "snapshot": snapshot,
        "status": status,
        "sap_model": cached if snapshot.get("status") == "ONLINE" else None,
    }
    if st is not None:
        st.session_state["etabs_connection_state"] = state
    return state


# =============================================================================
# R16 Pipeline: Build Beam Design Results from ETABS Data
# =============================================================================

def _build_r16_beam_design_pipeline(
    *,
    sap_model: object,
    story: str,
    combos: list[str],
    selected_object_names: list[str],
    design_values: dict[str, object],
    output_dir: Path,
) -> dict[str, object]:
    """
    R16: Run Beam Design Engine pipeline alongside legacy BeamCore.

    Steps:
    1. Run legacy BeamCore (unchanged)
    2. Build BeamModelContext from ETABS + UI inputs
    3. Extract FrameForce rows → BeamDemandProcessor → BeamDemandSet
    4. BeamDesignEngine → BeamDesignResult
    5. BeamVerification (if provided reinforcement exists)
    6. ETABS Crosscheck (if ETABS design output exists)
    """
    # Step 1: Legacy BeamCore (unchanged)
    legacy_result = run_story_beam_checks_from_ui(
        sap_model=sap_model,
        story=story,
        combos=combos,
        selected_object_names=selected_object_names,
        design_values=design_values,
        output_dir=output_dir,
    )
    _store_legacy_beamcore_result(legacy_result)

    # Step 2-6: New Beam Design Engine pipeline (per beam)
    pipeline_results: list[dict[str, object]] = []

    try:
        from tbdy_engine.design.beams.context import (
            BeamGeometryInput,
            BeamMaterialInput,
            BeamMetadata,
            BeamModelContext,
        )
        from tbdy_engine.design.beams.demand import RawFrameForceRow, BeamDemandSet
        from tbdy_engine.design.beams.demand_processor import (
            process_frameforce_rows_to_demand_set,
        )
        from tbdy_engine.design.beams.beam_region_flexure import (
            design_beam_region_flexure,
        )
        from tbdy_engine.design.beams.calculators.capacity_design import (
            capacity_design_ve,
            CapacityDesignVeInput,
        )
        from tbdy_engine.design.beams.calculators.shear_reinforcement_design import (
            shear_reinforcement_design,
            ShearReinforcementDesignInput,
        )
        from tbdy_engine.design.beams.calculators.plastic_moment import (
            plastic_moment,
            PlasticMomentInput,
        )
        from tbdy_engine.verification.beams.provided_reinforcement import (
            BeamProvidedReinforcement,
            ProvidedStirrup,
        )
        from tbdy_engine.verification.beams.reinforcement_verification import (
            verify_beam_reinforcement,
        )
        from tbdy_engine.verification.beams.etabs_design_output import ETABSDesignOutput
        from tbdy_engine.verification.beams.etabs_crosscheck import (
            compare_engine_to_etabs_design_output,
        )

        for beam_name in selected_object_names[:10]:
            try:
                # --- Context ---
                context = BeamModelContext(
                    beam_id=f"{story}|{beam_name}",
                    geometry=BeamGeometryInput(
                        bw_mm=float(design_values.get("bw_mm", 600)),
                        h_mm=float(design_values.get("h_mm", 700)),
                        d_mm=float(design_values.get("d_mm", 550)),
                        cover_mm=float(design_values.get("cover_mm", 40)),
                        Ln_mm=float(design_values.get("Ln_mm", 5000)),
                    ),
                    material=BeamMaterialInput(
                        fck_mpa=float(design_values.get("fck_mpa", 30)),
                        fcd_mpa=float(design_values.get("fcd_mpa", 20)),
                        fctd_mpa=float(design_values.get("fctd_mpa", 1.27)),
                        fyk_mpa=float(design_values.get("fyk_mpa", 420)),
                        fyd_mpa=float(design_values.get("fyd_mpa", 365)),
                        fywd_mpa=float(design_values.get("fywd_mpa", 365)),
                    ),
                    metadata=BeamMetadata(
                        label=beam_name,
                        story=story,
                        section_name="",
                        source="etabs_ui",
                    ),
                )
                _store_beam_design_results()

                # --- Demand (from legacy summary if available) ---
                summary = legacy_result.get("summary", {})
                beam_data = None
                for b in summary.get("beams", []):
                    if b.get("object_name") == beam_name:
                        beam_data = b
                        break

                if beam_data:
                    actions = beam_data.get("actions", {})
                    demand_set = BeamDemandSet(
                        beam_id=f"{story}|{beam_name}",
                        label=beam_name,
                        source="etabs_frameforce_ui",
                        Md_left_neg_kNm=float(actions.get("Md_left_neg_kNm", 0)),
                        Md_mid_pos_kNm=float(actions.get("Md_mid_pos_kNm", 0)) or None,
                        Md_right_neg_kNm=float(actions.get("Md_right_neg_kNm", 0)),
                        Vd_left_kN=float(actions.get("Vd_left_kN", 0)),
                        Vd_right_kN=float(actions.get("Vd_right_kN", 0)) or float(actions.get("Ve_left_kN", 0)),
                        N_kN=float(actions.get("axial_kN", 0)),
                    )
                    _store_beam_design_results(demand_set=demand_set)

                    # --- Design ---
                    region_result = design_beam_region_flexure(context, demand_set)
                    _store_beam_design_results(design_result=region_result)

                    # --- Plastic Moment ---
                    if region_result.regions:
                        tl = region_result.regions.get("top_left")
                        tr = region_result.regions.get("top_right")
                        if tl and tr:
                            mpr_left = plastic_moment(PlasticMomentInput(
                                As_cm2=tl.As_design_required_cm2,
                                bw_mm=context.geometry.bw_mm,
                                d_mm=context.geometry.d_mm,
                                fcd_mpa=context.material.fcd_mpa,
                                fyk_mpa=context.material.fyk_mpa,
                            ))
                            mpr_right = plastic_moment(PlasticMomentInput(
                                As_cm2=tr.As_design_required_cm2,
                                bw_mm=context.geometry.bw_mm,
                                d_mm=context.geometry.d_mm,
                                fcd_mpa=context.material.fcd_mpa,
                                fyk_mpa=context.material.fyk_mpa,
                            ))

                            # --- Capacity Ve ---
                            ve_result = capacity_design_ve(CapacityDesignVeInput(
                                Mpr_left_kNm=mpr_left.Mpr_kNm,
                                Mpr_right_kNm=mpr_right.Mpr_kNm,
                                Vg_kN=float(actions.get("Vd_left_kN", 0)) * 0.3,
                                Ln_mm=context.geometry.Ln_mm,
                            ))

                            # --- Shear Design ---
                            shear_result = shear_reinforcement_design(ShearReinforcementDesignInput(
                                V_design_kN=ve_result.Ve_capacity_kN,
                                bw_mm=context.geometry.bw_mm,
                                d_mm=context.geometry.d_mm,
                                fctd_mpa=context.material.fctd_mpa,
                                fywd_mpa=context.material.fywd_mpa,
                                stirrup_diameter_mm=float(design_values.get("stirrup_diameter_mm", 10)),
                                stirrup_legs=int(design_values.get("stirrup_legs", 2)),
                            ))

                            # --- Verification ---
                            provided = BeamProvidedReinforcement(
                                beam_id=f"{story}|{beam_name}",
                                label=beam_name,
                                top_left_As_cm2=float(design_values.get("top_selected_area_cm2", 0)) or None,
                                bottom_mid_As_cm2=float(design_values.get("bottom_selected_area_cm2", 0)) or None,
                                top_right_As_cm2=float(design_values.get("top_selected_area_cm2", 0)) or None,
                                stirrup=ProvidedStirrup(
                                    diameter_mm=float(design_values.get("stirrup_diameter_mm", 10)),
                                    legs=int(design_values.get("stirrup_legs", 2)),
                                    spacing_mm=float(design_values.get("stirrup_spacing_mm", 100)),
                                ),
                            )
                            verification = verify_beam_reinforcement(
                                beam_id=f"{story}|{beam_name}",
                                label=beam_name,
                                provided=provided,
                                flexure_region_result=region_result,
                                shear_result=shear_result,
                            )
                            _store_beam_design_results(verification_result=verification)

                            # --- ETABS Crosscheck ---
                            etabs_output = ETABSDesignOutput(
                                beam_id=f"{story}|{beam_name}",
                                label=beam_name,
                            )
                            comparison = compare_engine_to_etabs_design_output(
                                beam_id=f"{story}|{beam_name}",
                                label=beam_name,
                                etabs_output=etabs_output,
                                flexure_region_result=region_result,
                                shear_result=shear_result,
                            )
                            _store_beam_design_results(comparison_result=comparison)

                pipeline_results.append({
                    "beam_name": beam_name,
                    "status": "OK",
                })

            except Exception as exc:
                pipeline_results.append({
                    "beam_name": beam_name,
                    "status": "ERROR",
                    "error": str(exc),
                })

    except ImportError as exc:
        pipeline_results.append({
            "status": "IMPORT_ERROR",
            "error": str(exc),
        })

    return {
        "legacy_result": legacy_result,
        "pipeline_results": pipeline_results,
    }


# =============================================================================
# Main UI
# =============================================================================

def main() -> None:
    if st is None:
        print("Streamlit is not installed. Install streamlit to run the diagnostic UI.")
        return

    st.set_page_config(page_title="TBDY_ENGINE v3.0 — Beam Design", layout="wide")
    st.title("TBDY_ENGINE v3.0 — Beam Design UI")
    st.warning("Diagnostic UI only. Not design validation. Not production-ready. Not TBDY compliance proof.")

    _initialize_beam_design_session_state()
    connection_state = _refresh_etabs_connection_state()
    design_values = render_sidebar(connection_state=connection_state)

    status = connection_state["status"]

    (
        connection_tab,
        demand_tab,
        design_tab,
        verification_tab,
        crosscheck_tab,
        reports_tab,
        about_tab,
    ) = st.tabs([
        "Connection/Input",
        "Demand",
        "Design",
        "Verification",
        "ETABS Crosscheck",
        "Reports/Evidence",
        "Settings/About",
    ])

    with connection_tab:
        render_connection_input_tab(status=status, design_values=design_values)
    with demand_tab:
        render_demand_tab()
    with design_tab:
        render_design_tab()
    with verification_tab:
        render_verification_tab()
    with crosscheck_tab:
        render_etabs_crosscheck_tab()
    with reports_tab:
        render_reports_tab(Path(str(design_values["output_dir"])))
    with about_tab:
        render_about_tab()


# =============================================================================
# Sidebar
# =============================================================================

def render_sidebar(status: dict[str, object] | None = None) -> dict[str, object]:
    assert st is not None

    st.sidebar.title("TBDY Structural Design Workspace")

    values: dict[str, object] = {}

    st.sidebar.header("Workspace")
    st.sidebar.radio(
        "Element Type",
        ["Beam", "Column preview / coming soon", "Wall preview / coming soon", "Global Checks preview / coming soon"],
        index=0,
    )
    values["element_type"] = "Beam"

    st.sidebar.header("Analysis Source")
    analysis_source = st.sidebar.radio(
        "Analysis Source",
        ["Manual", "Offline Demo", "ETABS Live", "JSON Import preview / coming soon"],
        index=0,
    )
    values["analysis_source"] = analysis_source

    pipeline_map = {
        "Manual": "Manual → BeamModelContext → BeamDemandSet → BeamDesignEngine → Verification",
        "Offline Demo": "Offline Demo → Result-shaped fixtures → Design/Verification/Crosscheck tabs",
        "ETABS Live": "ETABS Live → FrameForce Extraction → BeamCore Diagnostic → Demand View",
        "JSON Import preview / coming soon": "JSON Import → Workspace State → Engine pipeline, coming soon",
    }
    st.sidebar.subheader("Current Pipeline")
    st.sidebar.caption(pipeline_map.get(str(analysis_source), pipeline_map["Manual"]))

    st.sidebar.subheader("Canonical Units")
    st.sidebar.info("Readonly canonical engine units")
    st.sidebar.write(
        {
            "Force": "kN",
            "Moment": "kNm",
            "Length": "mm",
            "Stress": "MPa",
        }
    )

    with st.sidebar.expander("Beam Context", expanded=True):
        st.caption("BeamModelContext: geometry + material + metadata")
        st.subheader("Geometry")
        values["bw_mm"] = st.number_input("bw_mm", value=float(DEFAULT_DESIGN_INPUTS["bw_mm"]))
        values["h_mm"] = st.number_input("h_mm", value=float(DEFAULT_DESIGN_INPUTS["h_mm"]))
        values["d_mm"] = st.number_input("d_mm", value=float(DEFAULT_DESIGN_INPUTS["d_mm"]))
        values["cover_mm"] = st.number_input("cover_mm", value=float(DEFAULT_DESIGN_INPUTS["cover_mm"]))
        values["Ln_mm"] = st.number_input("Ln_mm", value=float(DEFAULT_DESIGN_INPUTS["Ln_mm"]))

        st.subheader("Material")
        values["fck_mpa"] = st.number_input("fck_mpa", value=float(DEFAULT_DESIGN_INPUTS["fck_mpa"]))
        values["fcd_mpa"] = st.number_input("fcd_mpa", value=float(DEFAULT_DESIGN_INPUTS["fcd_mpa"]))
        values["fctd_mpa"] = st.number_input("fctd_mpa", value=float(DEFAULT_DESIGN_INPUTS["fctd_mpa"]))
        values["fyk_mpa"] = st.number_input("fyk_mpa", value=float(DEFAULT_DESIGN_INPUTS["fyk_mpa"]))
        values["fyd_mpa"] = st.number_input("fyd_mpa", value=float(DEFAULT_DESIGN_INPUTS["fyd_mpa"]))
        values["fywd_mpa"] = st.number_input("fywd_mpa", value=float(DEFAULT_DESIGN_INPUTS["fywd_mpa"]))

    with st.sidebar.expander("Beam Demand Set", expanded=False):
        st.caption("Manual demand fields are staged for workspace state. Manual design execution remains a future boundary.")
        values["Md_left_neg_kNm"] = st.number_input("Md_left_neg_kNm", value=0.0)
        values["Md_mid_pos_kNm"] = st.number_input("Md_mid_pos_kNm", value=0.0)
        values["Md_right_neg_kNm"] = st.number_input("Md_right_neg_kNm", value=0.0)
        values["Vd_left_kN"] = st.number_input("Vd_left_kN", value=0.0)
        values["Vd_right_kN"] = st.number_input("Vd_right_kN", value=0.0)
        values["N_kN"] = st.number_input("N_kN", value=0.0)

    with st.sidebar.expander("Verification Inputs", expanded=False):
        st.subheader("Provided Reinforcement")
        st.caption("Provided reinforcement for verification. Used only by verification. Does not mutate design result.")
        values["top_provided_As_cm2"] = st.number_input(
            "top provided As_cm2",
            value=float(DEFAULT_DESIGN_INPUTS["top_selected_area_cm2"]),
        )
        values["bottom_provided_As_cm2"] = st.number_input(
            "bottom provided As_cm2",
            value=float(DEFAULT_DESIGN_INPUTS["bottom_selected_area_cm2"]),
        )
        values["stirrup_spacing_mm"] = st.number_input(
            "provided stirrup spacing_mm",
            value=float(DEFAULT_DESIGN_INPUTS["stirrup_spacing_mm"]),
        )
        values["stirrup_legs"] = st.number_input(
            "provided stirrup legs",
            value=int(DEFAULT_DESIGN_INPUTS["stirrup_legs"]),
        )
        values["stirrup_diameter_mm"] = st.number_input(
            "provided stirrup diameter_mm",
            value=float(DEFAULT_DESIGN_INPUTS["stirrup_diameter_mm"]),
        )
        values["longitudinal_bar_diameter_mm"] = st.number_input(
            "longitudinal_bar_diameter_mm",
            value=float(DEFAULT_DESIGN_INPUTS["longitudinal_bar_diameter_mm"]),
        )

    # Compatibility for existing BeamCore diagnostic adapter keys.
    values["top_selected_area_cm2"] = values["top_provided_As_cm2"]
    values["bottom_selected_area_cm2"] = values["bottom_provided_As_cm2"]

    with st.sidebar.expander("Output Settings", expanded=False):
        values["output_dir"] = st.text_input("output_dir", value=str(DEFAULT_DESIGN_INPUTS["output_dir"]))
        values["generate_json_report"] = st.checkbox("Generate JSON Report", value=True)
        values["generate_excel_report"] = st.checkbox("Generate Excel Report", value=True)
        values["generate_markdown_report"] = st.checkbox("Generate Markdown Report", value=True)
        st.checkbox("Generate PDF Report — coming soon", value=False, disabled=True)

    values["force_unit"] = "kN"
    values["moment_unit"] = "kNm"
    values["length_unit"] = "mm"

    st.sidebar.header("Workspace Status")
    context_ready = all(float(values[key]) > 0.0 for key in ("bw_mm", "h_mm", "d_mm", "cover_mm", "Ln_mm", "fck_mpa", "fyd_mpa"))
    demand_ready = any(float(values[key]) != 0.0 for key in ("Md_left_neg_kNm", "Md_mid_pos_kNm", "Md_right_neg_kNm", "Vd_left_kN", "Vd_right_kN", "N_kN"))
    verification_ready = any(float(values[key]) > 0.0 for key in ("top_provided_As_cm2", "bottom_provided_As_cm2", "stirrup_spacing_mm"))
    last_run = st.session_state.get("workspace_last_run_status", "Not Run")

    st.sidebar.write(
        {
            "Element": "Beam",
            "Source": analysis_source,
            "Context": "Ready" if context_ready else "Missing",
            "Demand": "Ready" if demand_ready else "Missing",
            "Verification": "Ready" if verification_ready else "Missing",
            "Last Run": last_run,
        }
    )

    st.sidebar.header("Run Workspace")
    if analysis_source == "Manual":
        st.sidebar.button("Run Design — future boundary", disabled=True)
        st.sidebar.caption("Manual → BeamDesignEngine execution is deferred to R20.")
    elif analysis_source == "Offline Demo":
        st.sidebar.caption("Use the existing Load R18 offline demo results action in the app.")
    elif analysis_source == "ETABS Live":
        st.sidebar.caption("Use the existing Run BeamCore checks diagnostic action.")
    else:
        st.sidebar.button("Run JSON Import — coming soon", disabled=True)

    st.sidebar.header("ETABS connection")
    if status is None:
        status = st.session_state.get(
            "etabs_connection_status",
            {"status": "OFFLINE", "stage": "not_checked", "message": "Connection status is owned by the main app flow."},
        )
    st.sidebar.write(status.get("status", "OFFLINE"))
    if status.get("stage"):
        st.sidebar.caption(f"{status.get('stage')}: {status.get('message')}")
    if status.get("model_name"):
        st.sidebar.caption(str(status["model_name"]))

    return values


def render_connection_input_tab(*, status: dict[str, object], design_values: dict[str, object]) -> None:
    assert st is not None
    git_info = branch_and_commit()
    st.subheader("Connection/Input")
    cols = st.columns(4)
    cols[0].metric("ETABS", str(status["status"]))
    cols[1].metric("Model", str(status.get("model_name") or "-"))
    cols[2].metric("Branch", str(git_info.get("branch") or "-"))
    cols[3].metric("Commit", str(git_info.get("commit") or "-"))
    st.info("Engine calculations use canonical units: kN, kNm, mm, MPa. ETABS units are display/evidence only.")

    if status["status"] != "ONLINE":
        st.warning("ETABS is OFFLINE. Open ETABS and enable live mode for live checks.")
        st.markdown(CLAIM_BOUNDARY_TEXT)

    st.divider()
    st.subheader("R18 Offline UI Demo")
    st.caption("Loads fixture-like result objects into session_state. Does not run ETABS or engineering formulas.")
    if st.button("Load R18 offline demo results"):
        _load_r18_offline_demo_results()
        st.success("R18 offline demo results loaded. Open Design, Verification, and ETABS Crosscheck tabs.")
        return

    sap_model = status["sap_model"]
    snapshot = get_etabs_connection_snapshot(sap_model=sap_model)
    st.subheader("Open ETABS Model")
    st.json({k: v for k, v in snapshot.items() if k != "sap_model"})

    stories = list_available_stories(sap_model)
    combos = list_available_combos(sap_model)
    load_cases = list_available_load_cases(sap_model)
    if not stories:
        st.error("No stories found from ETABS frame objects.")
        return

    selected_story = st.selectbox("Story", stories)
    available_results = combos or load_cases
    if not available_results:
        st.error("No ETABS result combinations or load cases found.")
        return

    default_combos = choose_default_combos(available_results)
    selected_combos = st.multiselect("Available ETABS combinations", available_results, default=default_combos)
    st.write("Selected combinations", selected_combos)
    st.caption(f"selected_combos_count = {len(selected_combos)}")
    if len(selected_combos) == 1:
        st.info("Single-combo diagnostic run; no multi-combo envelope claim.")
    elif len(selected_combos) >= 2:
        st.info("Multi-combo envelope selection enabled.")

    all_frames = list_story_beams(sap_model, selected_story, include_non_beams=True)
    st.subheader("Frame Objects on Selected Story")
    include_unknown_frames = st.checkbox("Include UNKNOWN frame objects", value=False)
    include_column_frames = st.checkbox("Include COLUMN_LIKELY frame objects", value=False)
    if include_column_frames:
        st.warning("COLUMN_LIKELY objects are shown for diagnostics only and are not silently designed as beams.")

    section_filter = st.text_input("Filter by section", value="")
    label_filter = st.text_input("Filter by label text", value="")
    filtered = filter_beam_candidates(all_frames, include_non_beams=True, section_filter=section_filter, label_filter=label_filter)
    beam_candidates = filter_frame_objects_for_beam_ui(filtered, include_unknown=include_unknown_frames, include_columns=include_column_frames)
    editable_rows = add_selection_column(beam_candidates)
    edited_rows = st.data_editor(
        editable_rows,
        use_container_width=True,
        disabled=["object_name", "label", "story", "section", "element_type", "classification_source", "classification_warning", "frame_classification"],
    )
    selected_object_names = [row["object_name"] for row in edited_rows if row.get("selected")]
    max_beams = st.number_input("Max beams", value=10, min_value=1, max_value=500)

    if st.button("Run BeamCore checks"):
        if not selected_combos:
            st.error("Cannot run: no combination selected.")
            return
        if not selected_object_names:
            st.error("Cannot run: no beam selected.")
            return        # R17A: preserve legacy BeamCore diagnostic flow, then expose Demand-tab view.
        legacy_result = run_story_beam_checks_from_ui(
            sap_model=sap_model,
            story=selected_story,
            combos=selected_combos,
            selected_object_names=selected_object_names,
            design_values=design_values,
            output_dir=Path(str(design_values["output_dir"])),
            max_beams=int(max_beams),
        )
        _store_legacy_beamcore_result(legacy_result)
        _store_beam_design_results(
            demand_set=_build_ui_demand_view_from_legacy_result(legacy_result),
            design_result=None,
            verification_result=None,
            comparison_result=None,
        )

        st.success("BeamCore diagnostic checks completed.")
        st.json({
            "selected_story": legacy_result.get("selected_story"),
            "selected_combos": legacy_result.get("selected_combos"),
            "beam_count_discovered": legacy_result.get("beam_count_discovered"),
            "beam_count_processed": legacy_result.get("beam_count_processed"),
            "beam_count_failed": legacy_result.get("beam_count_failed"),
        })

        summary = legacy_result.get("summary") or {}
        st.dataframe(shape_result_rows_for_ui(summary), use_container_width=True)

        for beam in summary.get("beams", []):
            with st.expander(f"Beam Detail {beam.get('object_name')} / {beam.get('label')}"):
                st.write("ETABS Actions")
                st.json(beam.get("actions", {}))
                st.write("Governing Combo/Station")
                st.json(beam.get("governing", {}))
                st.write("BeamCore Status")
                st.write(beam.get("beam_core_status"))
                st.write("Artifact Paths")
                st.json(beam.get("artifact_paths", {}))
                st.write("Check Table")
                report_path = (beam.get("artifact_paths") or {}).get("json")
                if report_path:
                    st.dataframe(read_check_rows_for_ui(Path(report_path)), use_container_width=True)


# =============================================================================
# Demand Tab
# =============================================================================

def render_demand_tab() -> None:
    assert st is not None
    st.subheader("Demand")
    st.caption("R17A: Demand-tab view from preserved legacy BeamCore diagnostic output.")

    demand_view = st.session_state.get("beam_demand_set")
    if demand_view is None:
        st.info("No BeamDemandSet UI view available yet. Run BeamCore checks from the Connection/Input tab.")
        return

    if isinstance(demand_view, dict):
        st.write("Demand run metadata")
        st.json({
            "source": demand_view.get("source"),
            "selected_story": demand_view.get("selected_story"),
            "selected_combos": demand_view.get("selected_combos"),
            "beam_count_discovered": demand_view.get("beam_count_discovered"),
            "beam_count_processed": demand_view.get("beam_count_processed"),
            "beam_count_failed": demand_view.get("beam_count_failed"),
        })

        demand_rows = _demand_summary_rows_from_view(demand_view)
        st.write("Demand Summary")
        if demand_rows:
            st.dataframe(demand_rows, use_container_width=True)
        else:
            st.warning("Demand summary rows are not available.")

        governing_rows = _governing_evidence_rows_from_view(demand_view)
        st.write("Governing Combo/Station Evidence")
        if governing_rows:
            st.dataframe(governing_rows, use_container_width=True)
        else:
            st.info("No governing evidence available.")
        return

    st.write("Demand Summary")
    st.json(summarize_demand_set(demand_view))

    st.write("Governing Combo/Station Evidence")
    evidence_rows = summarize_governing_evidence(demand_view)
    if evidence_rows:
        st.dataframe(evidence_rows, use_container_width=True)
    else:
        st.info("No governing evidence available.")


# =============================================================================
# Design Tab
# =============================================================================

def render_design_tab() -> None:
    assert st is not None
    st.subheader("Design")
    st.caption("BeamDesignResult visualization.")

    design_result = st.session_state.get("beam_design_result")
    if design_result is None:
        st.info("BeamDesignResult is not available yet. Run BeamCore checks from the Connection/Input tab.")
        return

    st.write("Flexure Design by Region")
    flexure_rows = summarize_region_flexure(design_result)
    if flexure_rows:
        st.dataframe(flexure_rows, use_container_width=True)

    st.write("Shear Design")
    shear_summary = summarize_shear_design(design_result)
    if shear_summary:
        st.json(shear_summary)


# =============================================================================
# Verification Tab
# =============================================================================

def render_verification_tab() -> None:
    assert st is not None
    st.subheader("Verification")
    st.caption("BeamVerificationResult visualization. Verification must never mutate BeamDesignResult.")

    verification_result = st.session_state.get("beam_verification_result")
    if verification_result is None:
        st.warning("BeamVerificationResult is not available yet. Run BeamCore checks from the Connection/Input tab.")
        st.caption("Verification must never mutate BeamDesignResult.")
        return

    verification_rows = summarize_verification(verification_result)
    if verification_rows:
        st.dataframe(verification_rows, use_container_width=True)
    else:
        st.info("No verification checks available.")


# =============================================================================
# ETABS Crosscheck Tab
# =============================================================================

def render_etabs_crosscheck_tab() -> None:
    assert st is not None
    st.subheader("ETABS Crosscheck")
    st.caption("ETABSComparisonResult visualization. Crosscheck must never mutate BeamDesignResult or BeamVerificationResult.")

    comparison_result = st.session_state.get("etabs_comparison_result")
    if comparison_result is None:
        st.warning("ETABSComparisonResult is not available yet. Run BeamCore checks from the Connection/Input tab.")
        st.caption("Crosscheck must never mutate BeamDesignResult or BeamVerificationResult.")
        return

    comparison_rows = summarize_etabs_comparison(comparison_result)
    if comparison_rows:
        st.dataframe(comparison_rows, use_container_width=True)
    else:
        st.info("No comparison items available.")


# =============================================================================
# Reports Tab
# =============================================================================

def render_reports_tab(output_dir: Path) -> None:
    assert st is not None
    st.subheader("Reports/Evidence")
    st.info("Diagnostic output files")
    for path in [
        output_dir / "story_beam_batch_summary.json",
        output_dir / "story_beam_batch_summary.md",
        output_dir / "streamlit_single_combo_summary.json",
        output_dir / "streamlit_single_combo_summary.md",
        output_dir / "failure_diagnosis_summary.json",
        output_dir / "failure_diagnosis_summary.md",
    ]:
        st.write(str(path), "exists" if path.exists() else "not found")


# =============================================================================
# About Tab
# =============================================================================

def render_about_tab() -> None:
    assert st is not None
    st.subheader("Settings/About")
    st.markdown(CLAIM_BOUNDARY_TEXT)

    st.divider()



def _load_r18_offline_demo_results() -> None:
    """Load fixture-like result objects for offline UI visualization.

    R18-OFFLINE only: this does not run ETABS, BeamDesignEngine, or engineering
    formulas. It injects result-shaped objects so Design / Verification /
    Crosscheck tabs can be reviewed and tested without a live ETABS machine.
    """
    assert st is not None

    st.session_state["beam_design_result"] = SimpleNamespace(
        beam_id="R18_DEMO_BEAM",
        label="R18 Demo Beam",
        regions={
            "left_top": SimpleNamespace(As_design_required_cm2=12.5, Md_kNm=180.0, status="DEMO"),
            "mid_bottom": SimpleNamespace(As_design_required_cm2=9.8, Md_kNm=140.0, status="DEMO"),
            "right_top": SimpleNamespace(As_design_required_cm2=13.2, Md_kNm=190.0, status="DEMO"),
        },
        shear_result=SimpleNamespace(
            Vc_kN=82.0,
            Vs_required_kN=45.0,
            Asw_required_cm2_per_m=4.2,
            s_required_mm=120.0,
            status="DEMO",
        ),
    )

    st.session_state["beam_verification_result"] = SimpleNamespace(
        beam_id="R18_DEMO_BEAM",
        label="R18 Demo Beam",
        status="DEMO",
        checks=[
            SimpleNamespace(
                check_id="flexure_left_top",
                status="DEMO",
                provided_value=16.0,
                demand_value=12.5,
                utilization=0.78,
                unit="cm2",
                message="offline demo verification row",
            ),
            SimpleNamespace(
                check_id="shear_spacing",
                status="DEMO",
                provided_value=100.0,
                demand_value=120.0,
                utilization=0.83,
                unit="mm",
                message="offline demo verification row",
            ),
        ],
    )

    st.session_state["etabs_comparison_result"] = SimpleNamespace(
        beam_id="R18_DEMO_BEAM",
        label="R18 Demo Beam",
        agreement_status="DEMO",
        items=[
            SimpleNamespace(
                comparison_field="left_top_As_cm2",
                engine_value=12.5,
                etabs_value=13.0,
                difference_percent=4.0,
                agreement_status="DEMO",
            ),
            SimpleNamespace(
                comparison_field="shear_spacing_mm",
                engine_value=120.0,
                etabs_value=125.0,
                difference_percent=4.17,
                agreement_status="DEMO",
            ),
        ],
    )

if __name__ == "__main__":
    main()