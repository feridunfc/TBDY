from __future__ import annotations

from pathlib import Path


APP_SOURCE = Path("apps/streamlit_beam_design_app.py")
ADAPTER_SOURCE = Path("tbdy_engine/design/beams/streamlit_etabs_ui_adapter.py")


def _source() -> str:
    return APP_SOURCE.read_text(encoding="utf-8-sig")


def test_r19_sidebar_workspace_semantic_sections_visible() -> None:
    source = _source()
    required = [
        "TBDY Structural Design Workspace",
        "Element Type",
        "Analysis Source",
        "Current Pipeline",
        "Canonical Units",
        "Beam Context",
        "Beam Demand Set",
        "Verification Inputs",
        "Output Settings",
        "Workspace Status",
        "Run Workspace",
    ]
    for text in required:
        assert text in source


def test_r19_design_inputs_label_removed() -> None:
    assert "Design Inputs" not in _source()


def test_r19_sidebar_does_not_call_get_etabs_status_directly() -> None:
    source = _source()
    start = source.index("def render_sidebar(")
    end = source.find("\ndef ", start + 1)
    render_sidebar_source = source[start:end if end != -1 else len(source)]

    assert "get_etabs_status()" not in render_sidebar_source
    assert "etabs_connection_status" in render_sidebar_source


def test_r19_preview_element_labels_visible() -> None:
    source = _source()
    assert "Column preview / coming soon" in source
    assert "Wall preview / coming soon" in source
    assert "Global Checks preview / coming soon" in source


def test_r19_analysis_source_labels_visible() -> None:
    source = _source()
    assert "Manual" in source
    assert "Offline Demo" in source
    assert "ETABS Live" in source
    assert "JSON Import preview / coming soon" in source


def test_r19_pipeline_descriptions_visible() -> None:
    source = _source()
    assert "Manual → BeamModelContext → BeamDemandSet → BeamDesignEngine → Verification" in source
    assert "Offline Demo → Result-shaped fixtures → Design/Verification/Crosscheck tabs" in source
    assert "ETABS Live → FrameForce Extraction → BeamCore Diagnostic → Demand View" in source
    assert "JSON Import → Workspace State → Engine pipeline, coming soon" in source


def test_r19_beam_context_demand_and_verification_fields_visible() -> None:
    source = _source()
    for text in [
        "bw_mm", "h_mm", "d_mm", "cover_mm", "Ln_mm",
        "fck_mpa", "fcd_mpa", "fctd_mpa", "fyk_mpa", "fyd_mpa", "fywd_mpa",
        "Md_left_neg_kNm", "Md_mid_pos_kNm", "Md_right_neg_kNm",
        "Vd_left_kN", "Vd_right_kN", "N_kN",
        "top provided As_cm2", "bottom provided As_cm2",
        "top_provided_As_cm2", "bottom_provided_As_cm2",
        "provided stirrup spacing_mm", "provided stirrup legs", "provided stirrup diameter_mm",
    ]:
        assert text in source


def test_r19_legacy_keys_only_as_compatibility_layer() -> None:
    source = _source()

    assert 'values["top_provided_As_cm2"]' in source
    assert 'values["bottom_provided_As_cm2"]' in source
    assert 'values["top_selected_area_cm2"] = values["top_provided_As_cm2"]' in source
    assert 'values["bottom_selected_area_cm2"] = values["bottom_provided_As_cm2"]' in source


def test_r19_canonical_units_readonly_visible() -> None:
    source = _source()
    assert "Readonly canonical engine units" in source
    assert '"Force": "kN"' in source
    assert '"Moment": "kNm"' in source
    assert '"Length": "mm"' in source
    assert '"Stress": "MPa"' in source


def test_r19_workspace_status_fields_visible() -> None:
    source = _source()
    for text in ["Element", "Source", "Context", "Demand", "Verification", "Last Run"]:
        assert text in source


def test_r19_no_forbidden_ui_formulas() -> None:
    combined = _source() + "\n" + ADAPTER_SOURCE.read_text(encoding="utf-8-sig")
    for term in ["rho_min =", "As_required =", "Mpr =", "Ve_capacity =", "s = Asw"]:
        assert term not in combined


def test_r19_no_top_level_com_imports() -> None:
    combined = _source() + "\n" + ADAPTER_SOURCE.read_text(encoding="utf-8-sig")
    for term in ["import comtypes", "from comtypes", "from pythoncom"]:
        assert term not in combined
