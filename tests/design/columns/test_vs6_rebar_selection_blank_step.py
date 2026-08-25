from tbdy_engine.design.columns.rebar_selection import (
    ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION,
    normalize_etabs_column_end_demands,
)


def _row(*, station: float, p: float, m2: float, m3: float) -> dict[str, object]:
    return {
        "Story": "+0.00",
        "Column": "C2",
        "UniqueName": "236",
        "OutputCase": "Grav_Ult",
        "CaseType": "Combination",
        "StepType": "",
        "StepNumber": None,
        "Station": station,
        "P": p,
        "M2": m2,
        "M3": m3,
        "Element": "236",
        "ElemStation": station,
    }


def test_blank_etabs_step_type_is_preserved_as_factual_absence():
    states = normalize_etabs_column_end_demands(
        (
            _row(station=0.0, p=-1000.0, m2=10.0, m3=20.0),
            _row(station=4.45, p=-1100.0, m2=-15.0, m3=-25.0),
        ),
        unique_name="236",
        component_id="+0.00:C2:236",
        reviewed_force_unit="kN",
        reviewed_moment_unit="kN-m",
        axial_sign_policy=ETABS_AXIAL_SIGN_NEGATIVE_COMPRESSION,
    )

    assert len(states) == 2
    assert {state.end_tag for state in states} == {"I_END", "J_END"}
    assert all(state.step_type is None for state in states)
    assert all("|Combination|||" in state.source_identity for state in states)
