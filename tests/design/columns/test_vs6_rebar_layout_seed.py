import pytest

from tbdy_engine.design.columns.rebar_catalog import build_rebar_catalog_from_rows
from tbdy_engine.design.columns.rebar_layout_seed import (
    ColumnRebarLayoutSeedError,
    resolve_column_rebar_layout_seed,
)


def _catalog():
    return build_rebar_catalog_from_rows(
        (
            {"Name": "10", "Diameter": 10.0},
            {"Name": "14", "Diameter": 14.0},
            {"Name": "20", "Diameter": 20.0},
            {"Name": "25", "Diameter": 25.0},
        ),
        name_field="Name",
        diameter_field="Diameter",
        diameter_unit="mm",
        source_name="ETABS Reinforcing Bar Sizes",
    )


def test_etabs_design_intent_can_seed_cover_and_tie_geometry_without_becoming_rebar_authority():
    seed = resolve_column_rebar_layout_seed(
        section_name="Column_80x80",
        clear_cover_mm=40.0,
        tie_size_name="10",
        longitudinal_size_name="20",
        intent_authority="DESIGN_INTENT_ONLY",
        rebar_catalog=_catalog(),
        source_ref="GetRebarColumn:Column_80x80",
    )

    assert seed.authority == "ETABS_SECTION_REBAR_INTENT_LAYOUT_SEED"
    assert seed.clear_cover_mm == pytest.approx(40.0)
    assert seed.tie_diameter_mm == pytest.approx(10.0)
    assert seed.intent_longitudinal_diameter_mm == pytest.approx(20.0)
    assert seed.final_or_provided_rebar_authority is False
    # Current intent bar size is comparator only; it does not replace the full
    # factual catalog used by candidate generation.
    assert _catalog().column_longitudinal_diameters_mm == pytest.approx((14.0, 20.0, 25.0))


def test_section_check_input_may_seed_geometry_but_still_has_no_final_rebar_authority():
    seed = resolve_column_rebar_layout_seed(
        section_name="C80",
        clear_cover_mm=35.0,
        tie_size_name="10",
        longitudinal_size_name="20",
        intent_authority="SECTION_REBAR_CHECK_INPUT",
        rebar_catalog=_catalog(),
        source_ref="GetRebarColumn:C80",
    )
    assert seed.intent_authority == "SECTION_REBAR_CHECK_INPUT"
    assert seed.final_or_provided_rebar_authority is False


def test_tie_size_name_must_resolve_exactly_in_factual_catalog():
    with pytest.raises(ColumnRebarLayoutSeedError, match="tie bar-size name"):
        resolve_column_rebar_layout_seed(
            section_name="C80",
            clear_cover_mm=40.0,
            tie_size_name="T10",
            longitudinal_size_name="20",
            intent_authority="DESIGN_INTENT_ONLY",
            rebar_catalog=_catalog(),
            source_ref="GetRebarColumn:C80",
        )


def test_longitudinal_intent_size_must_resolve_but_does_not_preselect_candidate():
    with pytest.raises(ColumnRebarLayoutSeedError, match="longitudinal intent"):
        resolve_column_rebar_layout_seed(
            section_name="C80",
            clear_cover_mm=40.0,
            tie_size_name="10",
            longitudinal_size_name="22",
            intent_authority="DESIGN_INTENT_ONLY",
            rebar_catalog=_catalog(),
            source_ref="GetRebarColumn:C80",
        )
