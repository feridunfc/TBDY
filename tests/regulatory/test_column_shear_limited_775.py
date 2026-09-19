from __future__ import annotations

import pytest

from tbdy_engine.design.columns.column_shear_upper_bounds import (
    ColumnEffectiveDepthResolution,
    EFFECTIVE_DEPTH_PROVEN,
)
from tbdy_engine.regulatory.authority import (
    validate_registry_authority,
)
from tbdy_engine.regulatory.column_shear_limited import (
    COLUMN_SHEAR_LIMITED_775_REGISTRY,
)
from tbdy_engine.regulatory.column_shear_limited_program import (
    run_limited_column_shear_direction,
)
from tbdy_engine.regulatory.sources.column_shear_limited_775 import (
    build_column_shear_limited_775_authority_catalog,
)
from tbdy_engine.regulatory.vs6_column_shear_p7_program import (
    SourceBoundShearDemand,
)


def _vd(value: float = 500.0) -> SourceBoundShearDemand:
    return SourceBoundShearDemand(
        demand_kn=value,
        source_identity="ROW:LD:D_AMPLIFIED",
        output_case="LD_D_COMB",
        case_type="Combination",
        evidence_epoch_id="epoch:a37",
        source_refs=("B5:ROW:LD:D_AMPLIFIED",),
    )


def _effective() -> ColumnEffectiveDepthResolution:
    return ColumnEffectiveDepthResolution(
        component_id="S1:C1:101",
        direction="V2",
        moment_axis="M3",
        moment_sign=1,
        effective_depth_d_mm=450.0,
        web_width_bw_mm=600.0,
        tension_bar_coordinate_mm=200.0,
        status=EFFECTIVE_DEPTH_PROVEN,
        source_refs=("SELECTED_REBAR:D:EXACT",),
    )


def test_limited_775_authority_catalog_validates_exact_source_and_code_fingerprints():
    validated = validate_registry_authority(
        COLUMN_SHEAR_LIMITED_775_REGISTRY,
        build_column_shear_limited_775_authority_catalog(),
    )
    assert len(validated) == 1
    assert (
        validated[0].rule_id.value
        == "TBDY_7_7_5_2_COLUMN_SHEAR_BRITTLE_BOUND"
    )


def test_limited_775_program_uses_d_amplified_vd_for_brittle_and_ts500_web():
    result = run_limited_column_shear_direction(
        component_id="S1:C1:101",
        story="S1",
        section="C1",
        direction="V2",
        vd=_vd(500.0),
        d_amplified_vertical_plus_earthquake_proven=True,
        authority_ref="REVIEW:LD:D_AMPLIFIED",
        width_mm=500.0,
        depth_mm=600.0,
        fck_mpa=30.0,
        fcd_mpa=20.0,
        geometry_source_ref="STRICT_TOPOLOGY:101:C1",
        material_source_refs=("MAT:FCK", "MAT:FCD"),
        effective_depth=_effective(),
        source_refs=("REVIEW:775",),
    )

    assert result.vd_kn == pytest.approx(500.0)
    assert result.tbdy_brittle_result.value == pytest.approx(500.0)
    assert "D-amplified limited Vd" in result.tbdy_brittle_result.pass_rule
    assert result.ts500_web_result.value == pytest.approx(500.0)


def test_limited_7751_fails_closed_without_reviewed_d_amplified_semantics():
    with pytest.raises(
        ValueError,
        match="7.7.5.1",
    ):
        run_limited_column_shear_direction(
            component_id="S1:C1:101",
            story="S1",
            section="C1",
            direction="V2",
            vd=_vd(500.0),
            d_amplified_vertical_plus_earthquake_proven=False,
            authority_ref="REVIEW:UNPROVEN",
            width_mm=500.0,
            depth_mm=600.0,
            fck_mpa=30.0,
            fcd_mpa=20.0,
            geometry_source_ref="STRICT_TOPOLOGY:101:C1",
            material_source_refs=("MAT:FCK", "MAT:FCD"),
            effective_depth=_effective(),
            source_refs=("REVIEW:775",),
        )
