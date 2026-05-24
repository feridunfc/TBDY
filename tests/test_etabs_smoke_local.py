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


def _connected_sap_or_skip():
    connected, message = check_etabs_connection()
    if not connected:
        pytest.skip(f"ETABS unavailable: {message}")
    return get_sap()


def _available_table_names(sap) -> set[str]:
    result = sap.DatabaseTables.GetAvailableTables()
    tables = result[1] if len(result) > 1 else []
    return {str(table) for table in tables}


def test_etabs_connection_and_model_loaded():
    connected, message = check_etabs_connection()
    if not connected:
        pytest.skip(f"ETABS unavailable: {message}")

    assert connected is True
    sap = get_sap()
    model = str(sap.GetModelFilename() or "")

    assert model
    assert model.lower().endswith(".edb")


def test_etabs_available_tables_include_required_smoke_tables():
    sap = _connected_sap_or_skip()
    available_tables = _available_table_names(sap)

    assert len(available_tables) > 0
    for table_name in REQUIRED_SMOKE_TABLES:
        assert table_name in available_tables


@pytest.mark.asyncio
async def test_etabs_required_smoke_tables_have_data():
    sap = _connected_sap_or_skip()

    for table_name in REQUIRED_SMOKE_TABLES:
        result = await get_table_df(table_name, sap)

        assert result.ok is True, table_name
        assert result.error is None, table_name
        assert result.has_data is True, table_name
        assert result.df.shape[0] > 0, table_name
        assert result.df.shape[1] > 0, table_name


@pytest.mark.asyncio
async def test_etabs_optional_envelope_tables_are_readable_or_empty_without_error():
    sap = _connected_sap_or_skip()

    for table_name in OPTIONAL_EMPTY_TABLES:
        result = await get_table_df(table_name, sap)

        assert result.ok is True, table_name
        assert result.error is None, table_name
