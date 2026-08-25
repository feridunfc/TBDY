from types import SimpleNamespace

import pytest

import tbdy_engine.providers.etabs_rebar_catalog_provider as provider
from tbdy_engine.etabs.safety import RuntimeCaptureStatus
from tbdy_engine.providers.etabs_rebar_catalog_provider import (
    EtabsRebarCatalogProviderError,
    capture_etabs_rebar_catalog_evidence,
    promote_etabs_rebar_catalog,
)


def _fetch(*, fields=("Name", "Diameter"), rows=None, status=RuntimeCaptureStatus.FULL):
    if rows is None:
        rows = (
            {"Name": "10", "Diameter": "0.010"},
            {"Name": "14", "Diameter": "0.014"},
            {"Name": "16", "Diameter": "0.016"},
        )
    return SimpleNamespace(
        parsed=SimpleNamespace(
            field_keys=tuple(fields),
            rows=tuple(rows),
            return_code=0,
            row_count_reported=len(rows),
        ),
        capture_status=status,
        selected_signature_reason="fixture",
    )


def test_capture_preserves_factual_headers_and_rows(monkeypatch):
    monkeypatch.setattr(provider, "fetch_display_table", lambda *args, **kwargs: _fetch())
    evidence = capture_etabs_rebar_catalog_evidence(object())

    assert evidence.status == "PROVEN_FACTUAL_REBAR_CATALOG_TABLE"
    assert evidence.field_keys == ("Name", "Diameter")
    assert len(evidence.rows) == 3
    assert evidence.rows[1]["Name"] == "14"


def test_promotion_requires_explicit_existing_field_binding(monkeypatch):
    monkeypatch.setattr(provider, "fetch_display_table", lambda *args, **kwargs: _fetch())
    evidence = capture_etabs_rebar_catalog_evidence(object())

    with pytest.raises(EtabsRebarCatalogProviderError, match="name_field"):
        promote_etabs_rebar_catalog(
            evidence,
            name_field="BarName",
            diameter_field="Diameter",
            diameter_unit="m",
            source_name="ETABS Reinforcing Bar Sizes",
        )


def test_promotion_uses_factual_catalog_and_keeps_below_column_minimum_visible(monkeypatch):
    monkeypatch.setattr(provider, "fetch_display_table", lambda *args, **kwargs: _fetch())
    evidence = capture_etabs_rebar_catalog_evidence(object())
    catalog = promote_etabs_rebar_catalog(
        evidence,
        name_field="Name",
        diameter_field="Diameter",
        diameter_unit="m",
        source_name="ETABS Reinforcing Bar Sizes",
    )

    assert catalog.diameters_mm == pytest.approx((10.0, 14.0, 16.0))
    assert catalog.column_longitudinal_diameters_mm == pytest.approx((14.0, 16.0))
    assert [item.name for item in catalog.excluded_below_column_minimum] == ["10"]


def test_partial_capture_fails_closed(monkeypatch):
    monkeypatch.setattr(
        provider,
        "fetch_display_table",
        lambda *args, **kwargs: _fetch(status=RuntimeCaptureStatus.PARTIAL),
    )
    with pytest.raises(EtabsRebarCatalogProviderError, match="FULL"):
        capture_etabs_rebar_catalog_evidence(object())
