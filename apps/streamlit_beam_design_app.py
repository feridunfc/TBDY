from __future__ import annotations

from pathlib import Path

from tbdy_engine.design.beams.streamlit_etabs_ui_adapter import (
    DEFAULT_DESIGN_INPUTS,
    branch_and_commit,
    build_design_overrides_from_ui,
    choose_default_combos,
    get_etabs_status,
    list_available_combos,
    list_available_load_cases,
    list_available_stories,
    list_story_beams,
    filter_beam_candidates,
    add_selection_column,
    shape_result_rows_for_ui,
    read_check_rows_for_ui,
    run_story_beam_checks_from_ui,
)


try:
    import streamlit as st
except Exception:  # pragma: no cover - exercised by import-safety tests
    st = None


def main() -> None:
    if st is None:
        print("Streamlit is not installed. Install streamlit to run the diagnostic UI.")
        return

    st.set_page_config(page_title="BeamCore ETABS Diagnostic UI", layout="wide")
    st.title("BeamCore ETABS Diagnostic UI")
    st.warning("Diagnostic UI only. Not design validation. Not production-ready. Not TBDY compliance proof.")

    design_values = render_sidebar()
    status = get_etabs_status()

    beam_tab, reports_tab, diagnostics_tab, about_tab = st.tabs(["Beam", "Reports", "Diagnostics", "Settings / About"])

    with beam_tab:
        render_beam_tab(status=status, design_values=design_values)

    with reports_tab:
        render_reports_tab(Path(str(design_values["output_dir"])))

    with diagnostics_tab:
        render_diagnostics_tab(Path(str(design_values["output_dir"])))

    with about_tab:
        render_about_tab()


def render_sidebar() -> dict[str, object]:
    assert st is not None
    st.sidebar.header("Diagnostic input assumptions")
    st.sidebar.caption("These values are temporary override assumptions unless read from ETABS/model metadata.")
    st.sidebar.subheader("Temporary section geometry override")
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
        "top_selected_area_cm2": st.sidebar.number_input("top_selected_area_cm2", value=float(DEFAULT_DESIGN_INPUTS["top_selected_area_cm2"])),
        "bottom_selected_area_cm2": st.sidebar.number_input("bottom_selected_area_cm2", value=float(DEFAULT_DESIGN_INPUTS["bottom_selected_area_cm2"])),
        "force_unit": st.sidebar.selectbox("force_unit", ["kN"], index=0),
        "moment_unit": st.sidebar.selectbox("moment_unit", ["kNm"], index=0),
        "length_unit": st.sidebar.selectbox("length_unit", ["mm"], index=0),
        "output_dir": st.sidebar.text_input("output_dir", value=str(DEFAULT_DESIGN_INPUTS["output_dir"])),
    }
    status = get_etabs_status()
    st.sidebar.header("ETABS connection status")
    st.sidebar.write(status["status"])
    if status.get("stage"):
        st.sidebar.caption(f"{status.get('stage')}: {status.get('message')}")
    if status.get("model_name"):
        st.sidebar.caption(str(status["model_name"]))
    return values


def render_beam_tab(*, status: dict[str, object], design_values: dict[str, object]) -> None:
    assert st is not None
    git_info = branch_and_commit()
    st.subheader("Connection/status")
    cols = st.columns(4)
    cols[0].metric("ETABS", str(status["status"]))
    cols[1].metric("Model", str(status.get("model_name") or "-"))
    cols[2].metric("Branch", str(git_info.get("branch") or "-"))
    cols[3].metric("Commit", str(git_info.get("commit") or "-"))
    st.info("Warnings: diagnostic UI only; not design validation; not production-ready.")

    if status["status"] != "ONLINE":
        st.warning("Open ETABS and enable live mode.")
        return

    sap_model = status["sap_model"]
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
    if not selected_combos:
        st.warning("Select at least one combination/case.")

    beams = list_story_beams(sap_model, selected_story, include_non_beams=True)
    st.subheader("Beams on selected story")
    include_non_beams = st.checkbox("Show columns / unknown frame objects", value=False)
    if include_non_beams:
        st.warning("Probable column — excluded from BeamCore beam checks by default.")
    section_filter = st.text_input("Filter by section", value="")
    label_filter = st.text_input("Filter by label text", value="")
    beam_candidates = filter_beam_candidates(beams, include_non_beams=include_non_beams, section_filter=section_filter, label_filter=label_filter)
    select_all_beams = st.button("Select all beams")
    clear_selection = st.button("Clear selection")
    editable_rows = add_selection_column(beam_candidates, select_all=select_all_beams and not clear_selection)
    edited_rows = st.data_editor(editable_rows, use_container_width=True, disabled=["object_name", "label", "story", "section", "element_type", "classification_source", "classification_warning"])
    st.caption("Probable column — excluded from BeamCore beam checks by default.")
    max_beams = st.number_input("Max beams", value=10, min_value=1, max_value=500)
    selected_object_names = [row["object_name"] for row in edited_rows if row.get("selected")]

    if st.button("Run BeamCore checks"):
        if not selected_combos:
            st.error("Cannot run: no combination selected.")
            return
        if not selected_object_names:
            st.error("Cannot run: no beam selected.")
            return
        try:
            result = run_story_beam_checks_from_ui(
                sap_model=sap_model,
                story=selected_story,
                combos=selected_combos,
                selected_object_names=selected_object_names,
                design_values=design_values,
                output_dir=Path(str(design_values["output_dir"])),
                max_beams=int(max_beams),
            )
        except Exception as exc:
            st.error(str(exc))
            return
        render_results(result)


def render_results(result: dict[str, object]) -> None:
    assert st is not None
    st.success("BeamCore checks completed.")
    st.json(
        {
            "selected_story": result.get("selected_story"),
            "selected_combos": result.get("selected_combos"),
            "beam_count_discovered": result.get("beam_count_discovered"),
            "beam_count_processed": result.get("beam_count_processed"),
            "beam_count_failed": result.get("beam_count_failed"),
            "actions_source": result.get("actions_source"),
            "json_path": str(result.get("json_path")),
            "md_path": str(result.get("md_path")),
        }
    )
    summary = result.get("summary") or {}
    rows = []
    for beam in summary.get("beams", []):
        actions = beam.get("actions", {})
        governing = beam.get("governing", {})
        rows.append(
            {
                "object_name": beam.get("object_name"),
                "label": beam.get("label"),
                "section": beam.get("section"),
                "BeamCore status": beam.get("beam_core_status"),
                "Vd_left_kN": actions.get("Vd_left_kN"),
                "Ve_left_kN": actions.get("Ve_left_kN"),
                "Md_left_neg_kNm": actions.get("Md_left_neg_kNm"),
                "Md_mid_pos_kNm": actions.get("Md_mid_pos_kNm"),
                "Md_right_neg_kNm": actions.get("Md_right_neg_kNm"),
                "axial_kN": actions.get("axial_kN"),
                "governing_Ve_combo": (governing.get("Ve_left_kN") or {}).get("combo"),
                "check_count": beam.get("check_count"),
                "capacity_design_check_statuses": beam.get("capacity_design_check_statuses"),
                "json path": (beam.get("artifact_paths") or {}).get("json"),
                "xlsx path": (beam.get("artifact_paths") or {}).get("xlsx"),
            }
        )
    st.dataframe(rows, use_container_width=True)

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


def render_reports_tab(output_dir: Path) -> None:
    assert st is not None
    st.subheader("Generated diagnostic files")
    paths = [
        output_dir / "story_beam_batch_summary.json",
        output_dir / "story_beam_batch_summary.md",
        output_dir / "failure_diagnosis_summary.json",
        output_dir / "failure_diagnosis_summary.md",
    ]
    for path in paths:
        st.write(str(path), "exists" if path.exists() else "not found")


def render_diagnostics_tab(output_dir: Path) -> None:
    assert st is not None
    st.subheader("Diagnostics")
    try:
        from tbdy_engine.design.beams.beam_core_failure_diagnosis import diagnose_r7b_batch_summary
    except Exception:
        st.info("Diagnostics will use BeamCore ETABS diagnostic report.")
        return

    summary_path = output_dir / "story_beam_batch_summary.json"
    if st.button("Run failure diagnosis"):
        if not summary_path.exists():
            st.error(f"Batch summary not found: {summary_path}")
            return
        result = diagnose_r7b_batch_summary(summary_path=summary_path, output_dir=output_dir)
        st.success("Diagnostic output generated.")
        st.write(str(result["json_path"]))
        st.write(str(result["md_path"]))
        st.markdown(Path(result["md_path"]).read_text(encoding="utf-8"))


def render_about_tab() -> None:
    assert st is not None
    st.markdown(
        """
        This app is diagnostic.

        - ETABS actions are from FrameForce.
        - Ve currently uses ETABS envelope/proxy unless capacity-design Ve is separately computed.
        - This is not ETABS validation.
        - This is not TBDY compliance proof.
        - This is not production-ready.
        """
    )


if __name__ == "__main__":
    main()
