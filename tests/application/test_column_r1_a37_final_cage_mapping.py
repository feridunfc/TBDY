from __future__ import annotations

from dataclasses import fields
from math import pi
from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_final_cage as subject
from tbdy_engine.application.contracts import (
    ColumnExecutionRequest,
    ProjectExecutionRequest,
)
from tbdy_engine.design.columns.rebar_catalog import (
    RebarCatalog,
    RebarCatalogEntry,
)
from tbdy_engine.regulatory.column_transverse_confinement import (
    ColumnTransverseConfinementInput,
    TransverseDirectionFacts,
)


COMPONENT = "S1:C1:101"


def _catalog():
    return RebarCatalog(
        entries=(
            RebarCatalogEntry(
                name="T10",
                diameter_mm=10.0,
                source_identity="CATALOG:T10",
            ),
        ),
        status="PROVEN_FACTUAL_REBAR_CATALOG",
    )


def _base():
    return ColumnTransverseConfinementInput(
        component_id=COMPONENT,
        story="S1",
        section="C1",
        high_ductility_applies=True,
        limited_ductility_applies=False,
        cantilever_column=None,
        clear_height_mm=3000.0,
        width_mm=500.0,
        depth_mm=600.0,
        gross_area_ac_mm2=300000.0,
        confined_core_area_ack_mm2=240000.0,
        fck_mpa=30.0,
        fywk_mpa=420.0,
        axial_design_force_nd_n=500000.0,
        transverse_diameter_mm=None,
        confinement_spacing_mm=None,
        middle_spacing_mm=None,
        provided_confinement_region_length_mm=None,
        directions=(
            TransverseDirectionFacts(
                direction="DIR2",
                confined_core_width_bk_mm=410.0,
                provided_ash_mm2=None,
                horizontal_leg_spacing_mm=None,
                source_refs=("BASE:DIR2",),
            ),
            TransverseDirectionFacts(
                direction="DIR3",
                confined_core_width_bk_mm=510.0,
                provided_ash_mm2=None,
                horizontal_leg_spacing_mm=None,
                source_refs=("BASE:DIR3",),
            ),
        ),
        arrangement=None,
        source_refs=("BASE",),
        fywd_mpa=365.0,
        restrained_longitudinal_bar_spacing_mm=None,
        shear_spacing_mm=None,
        model_fingerprint="model:a37",
        evidence_epoch_id="epoch:a37",
        design_result_ref="design-result:a37",
    )


def _reviewed():
    return subject.ReviewedColumnFinalCageContext(
        component_id=COMPONENT,
        section="C1",
        tie_size_name="T10",
        number_2_dir_tie_bars=2,
        number_3_dir_tie_bars=4,
        confinement_spacing_mm=100.0,
        middle_spacing_mm=150.0,
        shear_spacing_mm=100.0,
        provided_confinement_region_length_mm=650.0,
        horizontal_leg_spacing_dir2_mm=180.0,
        horizontal_leg_spacing_dir3_mm=190.0,
        restrained_longitudinal_bar_spacing_mm=250.0,
        cantilever_column=False,
        arrangement=None,
        review_refs=("PROJECT:FINAL_CAGE:REVIEWED",),
    )


def _fake_p7(monkeypatch):
    def direction(name, d, ve):
        return SimpleNamespace(
            direction=name,
            effective_depth=SimpleNamespace(
                resolved=True,
                effective_depth_d_mm=d,
                source_refs=(f"P7:{name}:D",),
            ),
            ve_kn=ve,
            tbdy_vd=SimpleNamespace(
                source_refs=(f"P7:{name}:TBDY_VD",)
            ),
            ts500_vd=SimpleNamespace(
                source_refs=(f"P7:{name}:TS500_VD",)
            ),
        )

    run = SimpleNamespace(
        component_id=COMPONENT,
        directions=(
            direction("V2", 450.0, 120.0),
            direction("V3", 550.0, 130.0),
        ),
    )
    monkeypatch.setattr(
        subject,
        "VS6P7ColumnShearRun",
        type(run),
    )
    return run


def test_final_cage_maps_local_tie_legs_to_distinct_asw_without_aliasing_ash(
    monkeypatch,
):
    result = subject.apply_reviewed_final_cage_to_transverse_input(
        _base(),
        reviewed=_reviewed(),
        rebar_catalog=_catalog(),
        p7_run=_fake_p7(monkeypatch),
    )
    by_direction = {
        item.direction: item for item in result.directions
    }
    one_leg = pi * 10.0**2 / 4.0

    assert by_direction["DIR2"].provided_asw_mm2 == pytest.approx(
        2.0 * one_leg
    )
    assert by_direction["DIR3"].provided_asw_mm2 == pytest.approx(
        4.0 * one_leg
    )
    assert by_direction["DIR2"].provided_ash_mm2 is None
    assert by_direction["DIR3"].provided_ash_mm2 is None

    assert by_direction["DIR2"].effective_depth_mm == pytest.approx(
        450.0
    )
    assert by_direction["DIR3"].effective_depth_mm == pytest.approx(
        550.0
    )
    assert by_direction["DIR2"].p7_ve_kn == pytest.approx(120.0)
    assert by_direction["DIR3"].p7_ve_kn == pytest.approx(130.0)
    assert by_direction["DIR2"].shear_mapping_proven is True
    assert by_direction["DIR3"].shear_mapping_proven is True

    # Vc remains a separate, intentionally unresolved authority here.
    assert by_direction["DIR2"].qualified_vc_kn is None
    assert by_direction["DIR3"].qualified_vc_kn is None

    assert result.transverse_diameter_mm == pytest.approx(10.0)
    assert result.shear_spacing_mm == pytest.approx(100.0)
    assert result.confinement_spacing_mm == pytest.approx(100.0)
    assert subject.LOCAL_AXIS_SHEAR_MAPPING_REF in result.source_refs


def test_final_cage_without_p7_keeps_shear_mapping_unproven():
    result = subject.apply_reviewed_final_cage_to_transverse_input(
        _base(),
        reviewed=_reviewed(),
        rebar_catalog=_catalog(),
        p7_run=None,
    )
    assert all(
        item.shear_mapping_proven is None
        for item in result.directions
    )
    assert all(
        item.p7_ve_kn is None
        for item in result.directions
    )


def test_final_cage_context_is_not_a_production_request_dto_field():
    forbidden = {
        "reviewed_column_final_cage_context",
        "final_transverse_cage",
        "provided_asw_mm2",
        "shear_spacing_mm",
    }
    assert forbidden.isdisjoint(
        {item.name for item in fields(ColumnExecutionRequest)}
    )
    assert forbidden.isdisjoint(
        {item.name for item in fields(ProjectExecutionRequest)}
    )
