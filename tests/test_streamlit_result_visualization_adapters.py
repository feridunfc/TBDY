from types import SimpleNamespace

from tbdy_engine.design.beams.streamlit_etabs_ui_adapter import (
    summarize_etabs_comparison,
    summarize_region_flexure,
    summarize_shear_design,
    summarize_verification,
)


def test_summarize_region_flexure_supports_regions_contract():
    result = SimpleNamespace(
        regions={
            "top_left": SimpleNamespace(
                As_design_required_cm2=12.5,
                Md_kNm=180.0,
                status="PASS",
            )
        }
    )

    rows = summarize_region_flexure(result)

    assert rows == [{
        "region": "top_left",
        "As_required_cm2": 12.5,
        "Mu_check_kNm": 180.0,
        "status": "PASS",
    }]


def test_summarize_shear_design_supports_shear_result_alias():
    result = SimpleNamespace(
        shear_result=SimpleNamespace(
            Vc_kN=80.0,
            Vs_required_kN=45.0,
            Asw_required_cm2_per_m=4.2,
            s_required_mm=120.0,
            status="PASS",
        )
    )

    summary = summarize_shear_design(result)

    assert summary["Vc_kN"] == 80.0
    assert summary["Vs_required_kN"] == 45.0
    assert summary["Asw_required_cm2_per_m"] == 4.2
    assert summary["s_required_mm"] == 120.0
    assert summary["status"] == "PASS"


def test_summarize_verification_uses_contract_field_names():
    result = SimpleNamespace(
        checks=[
            SimpleNamespace(
                check_id="flexure_top_left",
                status="PASS",
                provided_value=16.0,
                demand_value=12.5,
                utilization=0.78,
                unit="cm2",
                message="ok",
            )
        ]
    )

    rows = summarize_verification(result)

    assert rows == [{
        "check_id": "flexure_top_left",
        "status": "PASS",
        "provided": 16.0,
        "required": 12.5,
        "utilization": 0.78,
        "unit": "cm2",
        "message": "ok",
    }]


def test_summarize_etabs_comparison_supports_items():
    result = SimpleNamespace(
        items=[
            SimpleNamespace(
                comparison_field="top_left_As_cm2",
                engine_value=12.5,
                etabs_value=13.0,
                difference_percent=4.0,
                agreement_status="CLOSE",
            )
        ]
    )

    rows = summarize_etabs_comparison(result)

    assert rows == [{
        "comparison_field": "top_left_As_cm2",
        "engine_value": 12.5,
        "etabs_value": 13.0,
        "difference_percent": 4.0,
        "agreement_status": "CLOSE",
    }]
