from types import SimpleNamespace

from tbdy_engine.application.column_a19_effective_length import (
    A19_READY,
    A19AxisEffectiveLengthMaterialization,
)
from tbdy_engine.application.column_a21_slenderness import (
    A21_EXPLICIT_UNRESOLVED,
    A21_READY,
    materialize_ts500_slenderness_decisions,
)
from tbdy_engine.application.column_public_a5_second_order import (
    _partition_end_moment_ratio_capability,
)
from tbdy_engine.design.columns.slenderness import (
    SIGNED_END_MOMENT_RATIO_REQUIRED_FOR_SLENDERNESS_DECISION,
    SWAY_PREVENTED,
)


COMPONENT = "+4.50:C10:188"

RS_COMBOS = (
    "Crack_SeisX",
    "Crack_SeisX_Soil",
    "Crack_SeisX_Up",
    "Crack_SeisX_UpSoil",
    "Crack_SeisY",
    "Crack_SeisY_Soil",
    "Crack_SeisY_Up",
    "Crack_SeisY_UpSoil",
)


def _combo(name, case_type):
    return SimpleNamespace(
        definition=SimpleNamespace(
            name=name,
        ),
        build=SimpleNamespace(
            states=(
                SimpleNamespace(
                    case_type=case_type,
                ),
            ),
        ),
    )


def _a19(axis, *, ln_mm):
    return A19AxisEffectiveLengthMaterialization(
        component_id=COMPONENT,
        local_bending_axis=axis,
        disposition=A19_READY,
        sway_classification=SWAY_PREVENTED,
        one_end_hinged=False,
        alpha_bottom=1.0,
        alpha_top=1.0,
        k=1.0,
        free_length_ln_mm=ln_mm,
        effective_length_lk_mm=ln_mm,
        controlling_equation="fixture",
        source_refs=(
            f"A19:{axis}",
        ),
    )


def _target():
    return SimpleNamespace(
        component_id=COMPONENT,
        unique_name="188",
        section="C_FIXTURE",
        depth_t3_m=0.5,
        width_t2_m=0.5,
    )


def test_rs_combos_are_partitioned_not_rejected_or_dropped():
    result = SimpleNamespace(
        combo_results=(
            _combo(
                "StaticULS",
                "DesignStaticLinearExact",
            ),
            *tuple(
                _combo(
                    name,
                    "DesignResponseSpectrumPermutation",
                )
                for name in RS_COMBOS
            ),
        )
    )

    exact, nonexact = (
        _partition_end_moment_ratio_capability(
            result
        )
    )

    assert exact == (
        "StaticULS",
    )

    assert nonexact == tuple(
        sorted(RS_COMBOS)
    )

    assert len(nonexact) == 8


def test_a21_can_resolve_sway_prevented_below_22_without_a20_ratio():
    # section dimension = 500 mm
    # i = 150 mm
    # ln = Lk = 3000 mm
    # lambda = 20
    rows = materialize_ts500_slenderness_decisions(
        target_column=_target(),

        a19_rows=(
            _a19(
                "M2",
                ln_mm=3000.0,
            ),
            _a19(
                "M3",
                ln_mm=3000.0,
            ),
        ),

        a20_rows=(),

        qualified_output_case_names=(
            "Crack_SeisX",
        ),
    )

    assert len(rows) == 1

    row = rows[0]

    assert row.disposition == A21_READY

    assert row.basis is not None
    assert row.result is not None

    assert (
        row.result.m2.slenderness_ratio_lk_over_i
        == 20.0
    )

    assert (
        row.result.m3.slenderness_ratio_lk_over_i
        == 20.0
    )

    assert (
        row.result.m2.moment_ratio_m1_over_m2
        is None
    )

    assert (
        row.result.m3.moment_ratio_m1_over_m2
        is None
    )

    assert (
        row.result.m2.status
        == "SLENDERNESS_EFFECTS_NEGLIGIBLE"
    )

    assert (
        row.result.m3.status
        == "SLENDERNESS_EFFECTS_NEGLIGIBLE"
    )


def test_a21_retains_geometry_but_is_unresolved_in_22_to_40_band():
    # section dimension = 500 mm
    # i = 150 mm
    # ln = Lk = 4500 mm
    # lambda = 30
    rows = materialize_ts500_slenderness_decisions(
        target_column=_target(),

        a19_rows=(
            _a19(
                "M2",
                ln_mm=4500.0,
            ),
            _a19(
                "M3",
                ln_mm=4500.0,
            ),
        ),

        a20_rows=(),

        qualified_output_case_names=(
            "Crack_SeisX",
        ),
    )

    row = rows[0]

    assert (
        row.disposition
        == A21_EXPLICIT_UNRESOLVED
    )

    assert row.basis is not None
    assert row.result is not None

    assert (
        row.result.m2.slenderness_ratio_lk_over_i
        == 30.0
    )

    assert (
        row.result.m3.slenderness_ratio_lk_over_i
        == 30.0
    )

    assert (
        row.result.m2.status
        ==
        SIGNED_END_MOMENT_RATIO_REQUIRED_FOR_SLENDERNESS_DECISION
    )

    assert (
        "SIGNED_M1_M2_REQUIRED_FOR_EQ7_17:M2"
        in row.unresolved_reasons
    )

    assert (
        "SIGNED_M1_M2_REQUIRED_FOR_EQ7_17:M3"
        in row.unresolved_reasons
    )
