import pytest

from tbdy_engine.design.columns.rebar_catalog import (
    RebarCatalogError,
    build_rebar_catalog_from_rows,
)


def test_catalog_uses_project_rows_and_keeps_below_minimum_as_explicit_exclusions():
    catalog = build_rebar_catalog_from_rows(
        (
            {"Name": "10", "Diameter": 0.010},
            {"Name": "14", "Diameter": 0.014},
            {"Name": "20", "Diameter": 0.020},
        ),
        name_field="Name",
        diameter_field="Diameter",
        diameter_unit="m",
        source_name="ETABS:Reinforcing Bar Sizes",
    )
    assert catalog.status == "PROVEN_FACTUAL_REBAR_CATALOG"
    assert catalog.diameters_mm == pytest.approx((10.0, 14.0, 20.0))
    assert catalog.column_longitudinal_diameters_mm == pytest.approx((14.0, 20.0))
    assert tuple(item.name for item in catalog.excluded_below_column_minimum) == ("10",)


def test_duplicate_diameter_is_rejected_instead_of_silently_collapsed():
    with pytest.raises(RebarCatalogError, match="duplicate rebar catalog diameter"):
        build_rebar_catalog_from_rows(
            (
                {"Name": "D14-A", "Diameter": 14.0},
                {"Name": "D14-B", "Diameter": 14.0},
            ),
            name_field="Name",
            diameter_field="Diameter",
            diameter_unit="mm",
            source_name="fixture",
        )
