from __future__ import annotations

import pytest

from tbdy_engine.etabs.connection import check_etabs_connection, get_sap
from tbdy_engine.etabs.table_reader import get_table_df


pytestmark = pytest.mark.etabs_smoke

REQUIRED_SMOKE_TABLES = [
    "Story Definitions",
    "Concrete Column Design Summary - TS 500-2000(R2018)",
    "Concrete Beam Design Summary - TS 500-2000(R2018)",
    "Concrete Column PMM Envelope - TS 500-2000(R2018)",
    "Concrete Joint Design Summary - TS 500-2000(R2018)",
]

OPTIONAL_EMPTY_TABLES = [
    "Concrete Column Shear Envelope - TS 500-2000(R2018)",
    "Concrete Beam Flexure Envelope - TS 500-2000(R2018)",
    "Concrete Beam Shear Envelope - TS 500-2000(R2018)",
    "Concrete Joint Envelope - TS 500-2000(R2018)",
]


def _skip_unless_marker_selected(request):
    markexpr = str(getattr(request.config.option, "markexpr", "") or "")
    if "etabs_smoke" not in markexpr:
        pytest.skip("ETABS smoke tests are opt-in; run with: pytest -q tests -m etabs_smoke")


def _connected_sap_or_skip(request):
    _skip_unless_marker_selected(request)
    connected, message = check_etabs_connection()
    if not connected:
        pytest.skip(f"ETABS unavailable: {message}")
    return get_sap()


def _available_table_names(sap) -> set[str]:
    result = sap.DatabaseTables.GetAvailableTables()
    for item in result if isinstance(result, (list, tuple)) else []:
        if isinstance(item, (list, tuple)) and item:
            return {str(table) for table in item}
    return set()


def test_etabs_connection_and_model_loaded(request):
    _skip_unless_marker_selected(request)
    connected, message = check_etabs_connection()
    if not connected:
        pytest.skip(f"ETABS unavailable: {message}")

    assert connected is True
    sap = get_sap()
    model = str(sap.GetModelFilename() or "")

    assert model
    assert model.lower().endswith(".edb")


def test_etabs_available_tables_include_required_smoke_tables(request):
    sap = _connected_sap_or_skip(request)
    available_tables = _available_table_names(sap)

    assert len(available_tables) > 0
    for table_name in REQUIRED_SMOKE_TABLES:
        assert table_name in available_tables


@pytest.mark.asyncio
async def test_etabs_required_smoke_tables_have_data(request):
    sap = _connected_sap_or_skip(request)

    for table_name in REQUIRED_SMOKE_TABLES:
        result = await get_table_df(table_name, sap)

        assert result.ok is True, table_name
        assert result.error is None, table_name
        assert result.has_data is True, table_name
        assert result.df.shape[0] > 0, table_name
        assert result.df.shape[1] > 0, table_name


@pytest.mark.asyncio
async def test_etabs_optional_envelope_tables_are_readable_or_empty_without_error(request):
    sap = _connected_sap_or_skip(request)

    for table_name in OPTIONAL_EMPTY_TABLES:
        result = await get_table_df(table_name, sap)

        assert result.ok is True, table_name
        assert result.error is None, table_name
