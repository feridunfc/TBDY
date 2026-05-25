from __future__ import annotations

import asyncio
import os
from typing import Iterable

import pytest


pytestmark = pytest.mark.etabs_smoke

STORY_DEFINITIONS_TABLE = "Story Definitions"
OPTIONAL_DESIGN_TABLES = (
    "Concrete Column Design Summary - TS 500-2000(R2018)",
    "Concrete Beam Design Summary - TS 500-2000(R2018)",
    "Concrete Column PMM Envelope - TS 500-2000(R2018)",
    "Concrete Joint Design Summary - TS 500-2000(R2018)",
)


def _skip_unless_live_enabled() -> None:
    if os.environ.get("TBDY_RUN_ETABS_LIVE_SMOKE") != "1":
        pytest.skip(
            "Live ETABS smoke disabled; set TBDY_RUN_ETABS_LIVE_SMOKE=1 "
            "with ETABS open and a model loaded"
        )


def _production_etabs_modules():
    _skip_unless_live_enabled()
    from tbdy_engine.etabs.connection import check_etabs_connection, get_sap
    from tbdy_engine.etabs.table_reader import get_table_df

    return check_etabs_connection, get_sap, get_table_df


def _connected_sap_or_skip():
    check_etabs_connection, get_sap, _get_table_df = _production_etabs_modules()
    connected, message = check_etabs_connection()
    if not connected:
        pytest.skip(f"ETABS connection unavailable: {message}")

    sap = get_sap()
    if sap is None:
        pytest.skip("ETABS connection returned no SapModel-like object")
    return sap, message


def _string_from_etabs_return(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
        return str(value)
    return str(value).strip() if value is not None else ""


def _parse_available_tables(raw: object) -> set[str]:
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, (list, tuple)) and item:
                return {str(table) for table in item}
        if len(raw) >= 2 and isinstance(raw[1], (list, tuple)):
            return {str(table) for table in raw[1]}
    return set()


def _available_table_names(sap) -> set[str]:
    raw = sap.DatabaseTables.GetAvailableTables()
    return _parse_available_tables(raw)


def _read_table(table_name: str):
    _check_etabs_connection, _get_sap, get_table_df = _production_etabs_modules()

    async def _run():
        return await get_table_df(table_name)

    return asyncio.run(_run())


def _present_tables(available_tables: set[str], candidate_tables: Iterable[str]) -> tuple[str, ...]:
    return tuple(table for table in candidate_tables if table in available_tables)


def test_live_etabs_connection_and_open_model():
    sap, connection_message = _connected_sap_or_skip()

    try:
        model_filename = _string_from_etabs_return(sap.GetModelFilename())
    except Exception as exc:
        pytest.skip(f"Unable to read open ETABS model filename: {exc}; connection={connection_message}")

    if not model_filename or model_filename.lower() == "unknown":
        pytest.skip(f"No open ETABS model detected; connection={connection_message}")

    assert model_filename
    if "." in model_filename:
        assert model_filename.lower().endswith(".edb")


def test_live_etabs_available_tables_include_story_definitions():
    sap, _connection_message = _connected_sap_or_skip()

    available_tables = _available_table_names(sap)

    assert available_tables
    assert STORY_DEFINITIONS_TABLE in available_tables


def test_live_etabs_story_definitions_table_read():
    sap, _connection_message = _connected_sap_or_skip()
    available_tables = _available_table_names(sap)

    assert STORY_DEFINITIONS_TABLE in available_tables

    result = _read_table(STORY_DEFINITIONS_TABLE)

    assert result.ok is True
    assert result.error is None
    assert result.has_data is True
    assert result.df.shape[0] > 0
    assert result.df.shape[1] > 0


def test_live_etabs_optional_design_tables_are_readable_if_present():
    sap, _connection_message = _connected_sap_or_skip()
    available_tables = _available_table_names(sap)
    present_tables = _present_tables(available_tables, OPTIONAL_DESIGN_TABLES)

    if not present_tables:
        pytest.skip("No optional design summary/envelope tables are available in the open ETABS model")

    for table_name in present_tables:
        result = _read_table(table_name)
        assert result.ok is True, table_name
        assert result.error is None, table_name


def test_live_smoke_source_is_env_gated_and_uses_production_modules_only():
    source_path = __import__("pathlib").Path(__file__)
    source = source_path.read_text(encoding="utf-8")
    forbidden_raw_com_import = "win32com" + "." + "client"
    forbidden_raw_com_call = "Get" + "Active" + "Object"

    assert "TBDY_RUN_ETABS_LIVE_SMOKE" in source
    assert "check_etabs_connection" in source
    assert "get_sap" in source
    assert "get_table_df" in source
    assert forbidden_raw_com_import not in source
    assert forbidden_raw_com_call not in source
    assert "pytest.skip" in source
