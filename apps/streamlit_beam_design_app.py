from __future__ import annotations

from pathlib import Path

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
    summarize_etabs_snapshot,
)

try:
    import streamlit as st
except Exception:  # pragma: no cover - import safety
    st = None


CLAIM_BOUNDARY_TEXT = """
Claim boundaries:
- Diagnostic UI only; this is not ETABS validation.
- This is not design-engine validation.
- This is not TBDY compliance proof.
- This is not production-ready.
- ETABS disagreement is diagnostic only and does not mutate engine or verification results.
- COLUMN_LIKELY objects are never silently designed as beams.
"""



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
        "online": False,
        "status": "OFFLINE",
        "model_name": None,
        "model_path": None,
        "present_units": None,
        "database_units": None,
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
        "status": "OFFLINE",
        "stage": "etabs_attach",
        "message": last_error,
        "model_name": None,
        "sap_model": None,
    }


def _initialize_beam_design_session_state() -> None:
    """Initialize R17A beam design session-state slots."""
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


def _store_r17a_legacy_and_demand_state(result: dict[str, object]) -> None:
    """Store legacy BeamCore result and a UI-level demand view.

    R17A does not run BeamDesignEngine yet. It extracts demand-facing
    visualization data from the existing legacy BeamCore diagnostic summary.
    """
    assert st is not None
    st.session_state["legacy_beamcore_result"] = result
    st.session_state["beam_demand_set"] = _build_ui_demand_view_from_legacy_result(result)
    st.session_state["beam_design_result"] = None
    st.session_state["beam_verification_result"] = None
    st.session_state["etabs_comparison_result"] = None


def _build_ui_demand_view_from_legacy_result(result: dict[str, object]) -> dict[str, object]:
    """Build a Demand-tab view from legacy BeamCore diagnostic output.

    This is a UI view, not a deterministic BeamDemandSet contract object.
    The purpose is R17A visibility without changing R7/R8/R9 acceptance paths.
    """
    summary = result.get("summary") or {}
    beams = []
    for beam in summary.get("beams", []) if isinstance(summary, dict) else []:
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


def _demand_summary_rows_from_session() -> list[dict[str, object]]:
    """Return Demand Summary rows for the Demand tab."""
    assert st is not None
    demand_view = st.session_state.get("beam_demand_set") or {}
    if not isinstance(demand_view, dict):
        return []
    rows = []
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
            "Ve_left_kN": beam.get("Ve_left_kN"),
            "axial_kN": beam.get("axial_kN"),
        })
    return rows


def _governing_evidence_rows_from_session() -> list[dict[str, object]]:
    """Return governing combo/station evidence rows for the Demand tab."""
    assert st is not None
    demand_view = st.session_state.get("beam_demand_set") or {}
    if not isinstance(demand_view, dict):
        return []
    rows = []
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

def main() -> None:
    if st is None:
        print("Streamlit is not installed. Install streamlit to run the diagnostic UI.")
        return

    st.set_page_config(page_title="BeamCore ETABS Diagnostic UI", layout="wide")
    st.title("BeamCore ETABS Diagnostic UI")
    st.warning("Diagnostic UI only. Not design validation. Not production-ready. Not TBDY compliance proof.")

    design_values = render_sidebar()
    status = _persistent_etabs_status()

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


def render_sidebar() -> dict[str, object]:
    assert st is not None
    st.sidebar.header("ETABS connection")
    snapshot = _persistent_etabs_snapshot()
    snapshot_summary = summarize_etabs_snapshot(snapshot)
    st.sidebar.write(f"ETABS: {snapshot_summary['ETABS']}")
    st.sidebar.write(f"Model: {snapshot_summary['model_name']}")
    st.sidebar.write(f"Path: {snapshot_summary['model_path']}")
    if st.sidebar.button("Reconnect ETABS"):
        _clear_cached_etabs_connection()
        st.rerun()
    if snapshot_summary.get("error"):
        st.sidebar.caption(str(snapshot_summary["error"]))

    st.sidebar.header("Model defaults")
    st.sidebar.caption("Temporary section geometry override; these are diagnostic assumptions unless read from ETABS/model metadata.")
    values = {
        "bw_mm": st.sidebar.number_input("bw_mm", value=float(DEFAULT_DESIGN_INPUTS["bw_mm"])),
        "h_mm": st.sidebar.number_input("h_mm", value=float(DEFAULT_DESIGN_INPUTS["h_mm"])),
        "d_mm": st.sidebar.number_input("d_mm", value=float(DEFAULT_DESIGN_INPUTS["d_mm"])),
        "cover_mm": st.sidebar.number_input("cover_mm", value=float(DEFAULT_DESIGN_INPUTS["cover_mm"])),
        "Ln_mm": st.sidebar.number_input("Ln_mm", value=float(DEFAULT_DESIGN_INPUTS["Ln_mm"])),
        "fck_mpa": st.sidebar.number_input("fck_mpa", value=float(DEFAULT_DESIGN_INPUTS["fck_mpa"])),
        "fcd_mpa": st.sidebar.number_input("fcd_mpa", value=float(DEFAULT_DESIGN_INPUTS["fcd_mpa"])),
        "fctd_mpa": st.sidebar.number_input("fctd_mpa", value=float(DEFAULT_DESIGN_INPUTS["fctd_mpa"])),
        "fyk_mpa": st.sidebar.number_input("fyk_mpa", value=float(DEFAULT_DESIGN_INPUTS["fyk_mpa"])),
        "fyd_mpa": st.sidebar.number_input("fyd_mpa", value=float(DEFAULT_DESIGN_INPUTS["fyd_mpa"])),
        "fywd_mpa": st.sidebar.number_input("fywd_mpa", value=float(DEFAULT_DESIGN_INPUTS["fywd_mpa"])),
        "stirrup_legs": st.sidebar.number_input("stirrup_legs", value=int(DEFAULT_DESIGN_INPUTS["stirrup_legs"])),
        "stirrup_diameter_mm": st.sidebar.number_input("stirrup_diameter_mm", value=float(DEFAULT_DESIGN_INPUTS["stirrup_diameter_mm"])),
        "stirrup_spacing_mm": st.sidebar.number_input("stirrup_spacing_mm", value=float(DEFAULT_DESIGN_INPUTS["stirrup_spacing_mm"])),
        "longitudinal_bar_diameter_mm": st.sidebar.number_input("longitudinal_bar_diameter_mm", value=float(DEFAULT_DESIGN_INPUTS["longitudinal_bar_diameter_mm"])),
        "force_unit": st.sidebar.selectbox("force_unit", ["kN"], index=0),
        "moment_unit": st.sidebar.selectbox("moment_unit", ["kNm"], index=0),
        "length_unit": st.sidebar.selectbox("length_unit", ["mm"], index=0),
        "output_dir": st.sidebar.text_input("output_dir", value=str(DEFAULT_DESIGN_INPUTS["output_dir"])),
    }

    st.sidebar.header("ETABS units")
    st.sidebar.write("Present units")
    st.sidebar.json(snapshot.get("present_units") or {"message": "ETABS units unavailable"})
    st.sidebar.write("Database units")
    st.sidebar.json(snapshot.get("database_units") or {"message": "ETABS units unavailable"})
    st.sidebar.warning("Engine calculations use canonical units: kN, kNm, mm, MPa. ETABS units are shown as evidence. Conversion must happen in provider layer.")

    st.sidebar.header("Design policy parameters")
    st.sidebar.caption("Policy parameters are displayed as evidence; engineering formulas are not implemented in UI.")

    st.sidebar.header("Provided reinforcement for verification")
    st.sidebar.caption("Provided reinforcement is verification input, not design input.")
    st.sidebar.number_input("top provided As_cm2", value=0.0)
    st.sidebar.number_input("bottom provided As_cm2", value=0.0)
    st.sidebar.number_input("provided stirrup diameter_mm", value=0.0)
    st.sidebar.number_input("provided stirrup spacing_mm", value=0.0)

    st.sidebar.header("Output settings")
    st.sidebar.caption(f"Canonical engine units: {CANONICAL_ENGINE_UNITS}")
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
        return

    sap_model = status["sap_model"]
    snapshot = get_etabs_connection_snapshot(sap_model=sap_model)
    st.subheader("Open ETABS model")
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
    st.subheader("Frame objects on selected story")
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
            return
        result = run_story_beam_checks_from_ui(
            sap_model=sap_model,
            story=selected_story,
            combos=selected_combos,
            selected_object_names=selected_object_names,
            design_values=design_values,
            output_dir=Path(str(design_values["output_dir"])),
            max_beams=int(max_beams),
        )
        result.setdefault("ui_context_metadata", {})["etabs_units"] = snapshot.get("present_units")
        result.setdefault("ui_context_metadata", {})["database_units"] = snapshot.get("database_units")
        _store_r17a_legacy_and_demand_state(result)
        render_results(result)


def render_results(result: dict[str, object]) -> None:
    assert st is not None
    st.success("BeamCore checks completed.")
    st.json({
        "selected_story": result.get("selected_story"),
        "selected_combos": result.get("selected_combos"),
        "beam_count_discovered": result.get("beam_count_discovered"),
        "beam_count_processed": result.get("beam_count_processed"),
        "beam_count_failed": result.get("beam_count_failed"),
        "actions_source": result.get("actions_source"),
        "json_path": str(result.get("json_path")),
        "md_path": str(result.get("md_path")),
        "ui_context_metadata": result.get("ui_context_metadata"),
    })
    summary = result.get("summary") or {}
    st.dataframe(shape_result_rows_for_ui(summary), use_container_width=True)
    for beam in summary.get("beams", []):
        with st.expander(f"Beam detail {beam.get('object_name')} / {beam.get('label')}"):
            st.write("ETABS actions")
            st.json(beam.get("actions", {}))
            st.write("Governing combo/station")
            st.json(beam.get("governing", {}))
            st.write("BeamCore status")
            st.write(beam.get("beam_core_status"))
            st.write("Artifact paths")
            st.json(beam.get("artifact_paths", {}))
            st.write("Check table")
            report_path = (beam.get("artifact_paths") or {}).get("json")
            if report_path:
                st.dataframe(read_check_rows_for_ui(Path(report_path)), use_container_width=True)


def render_demand_tab() -> None:
    assert st is not None
    st.subheader("Demand")
    st.caption("R17A: Demand tab visualizes demand-facing data from the preserved legacy BeamCore diagnostic result.")

    demand_view = st.session_state.get("beam_demand_set")
    if not demand_view:
        st.info("No BeamDemandSet view available yet. Run BeamCore checks from the Connection/Input tab.")
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

    demand_rows = _demand_summary_rows_from_session()
    st.write("Demand Summary")
    if demand_rows:
        st.dataframe(demand_rows, use_container_width=True)
    else:
        st.warning("Demand summary rows are not available.")

    governing_rows = _governing_evidence_rows_from_session()
    st.write("Governing combo/station evidence")
    if governing_rows:
        st.dataframe(governing_rows, use_container_width=True)
    else:
        st.info("No governing evidence rows are available for the current result.")


def render_design_tab() -> None:
    assert st is not None
    st.subheader("Design")
    result = st.session_state.get("beam_design_result")
    if result is None:
        st.info("BeamDesignResult is not available in R17A. R17A only adds Demand-tab visibility while preserving the legacy BeamCore diagnostic flow.")
        st.caption("R17B will connect BeamDesignResult visualization without implementing engineering formulas in the UI.")
        return
    st.write("BeamDesignResult")
    st.json(str(result))


def render_verification_tab() -> None:
    assert st is not None
    st.subheader("Verification")
    result = st.session_state.get("beam_verification_result")
    if result is None:
        st.warning("BeamVerificationResult is not available in R17A. Provided reinforcement remains separated from design input.")
        st.caption("Verification must never mutate BeamDesignResult.")
        return
    st.write("BeamVerificationResult")
    st.json(str(result))


def render_etabs_crosscheck_tab() -> None:
    assert st is not None
    st.subheader("ETABS Crosscheck")
    result = st.session_state.get("etabs_comparison_result")
    if result is None:
        st.warning("ETABSComparisonResult is not available in R17A. ETABS disagreement remains diagnostic only.")
        st.caption("Crosscheck must never mutate BeamDesignResult or BeamVerificationResult.")
        return
    st.write("ETABSComparisonResult")
    st.json(str(result))


def render_reports_tab(output_dir: Path) -> None:
    assert st is not None
    st.subheader("Reports/Evidence")
    st.info("diagnostic output files")
    for path in [
        output_dir / "story_beam_batch_summary.json",
        output_dir / "story_beam_batch_summary.md",
        output_dir / "streamlit_single_combo_summary.json",
        output_dir / "streamlit_single_combo_summary.md",
        output_dir / "failure_diagnosis_summary.json",
        output_dir / "failure_diagnosis_summary.md",
    ]:
        st.write(str(path), "exists" if path.exists() else "not found")


def render_about_tab() -> None:
    assert st is not None
    st.subheader("Settings/About")
    st.markdown(CLAIM_BOUNDARY_TEXT)


if __name__ == "__main__":
    main()
