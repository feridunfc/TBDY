from __future__ import annotations

import pytest

from tbdy_engine.regulatory.column_shear_vc import qualify_column_vc


def _base(**overrides):
    data = dict(
        component_id="S1:C1:101",
        direction="V2",
        fck_mpa=30.0,
        fcd_mpa=20.0,
        gross_area_ac_mm2=300000.0,
        web_width_bw_mm=500.0,
        effective_depth_d_mm=450.0,
        ts500_axial_nd_signed_compression_n=500000.0,
        high_ductility_applies=False,
        limited_ductility_applies=True,
        source_refs=("TEST:SOURCE",),
    )
    data.update(overrides)
    return data


def test_ts500_vc_uses_source_bound_strengths_and_compression_gamma():
    result = qualify_column_vc(**_base())
    assert result.gamma_mc == pytest.approx(1.5)
    assert result.fctk_mpa == pytest.approx(0.35 * 30.0**0.5)
    assert result.fctd_mpa == pytest.approx(0.35 * 30.0**0.5 / 1.5)
    assert result.axial_gamma == pytest.approx(0.07)
    assert result.vc_kn == pytest.approx(0.8 * result.vcr_kn)


def test_high_vc_zero_requires_both_tbd_y_conditions():
    result = qualify_column_vc(**_base(
        high_ductility_applies=True,
        limited_ductility_applies=False,
        earthquake_only_shear_kn=60.0,
        total_seismic_shear_kn=100.0,
        suppression_axial_nd_signed_compression_n=300000.0,
        suppression_concurrency_proven=True,
    ))
    assert result.high_ductility_suppression_applied is True
    assert result.vc_kn == pytest.approx(0.0)


def test_high_vc_zero_does_not_apply_when_shear_condition_is_false():
    result = qualify_column_vc(**_base(
        high_ductility_applies=True,
        limited_ductility_applies=False,
        earthquake_only_shear_kn=40.0,
        total_seismic_shear_kn=100.0,
        suppression_axial_nd_signed_compression_n=300000.0,
        suppression_concurrency_proven=True,
    ))
    assert result.high_ductility_suppression_applied is False
    assert result.vc_kn > 0.0


def test_high_vc_fails_closed_without_concurrency_proof():
    with pytest.raises(ValueError, match="requires proven concurrent"):
        qualify_column_vc(**_base(
            high_ductility_applies=True,
            limited_ductility_applies=False,
            earthquake_only_shear_kn=60.0,
            total_seismic_shear_kn=100.0,
            suppression_axial_nd_signed_compression_n=300000.0,
            suppression_concurrency_proven=False,
        ))
