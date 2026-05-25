from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

import tbdy_engine.etabs.table_access as table_access
from tbdy_engine.etabs.table_access import (
    EtabsTableAccessResult,
    EtabsTableAccessStatus,
    read_etabs_table_on_demand,
)


ROOT = Path(__file__).resolve().parents[1]
STORY_DEFINITIONS_TABLE = "Story Definitions"
FORBIDDEN_IMPORT_PREFIXES = (
    "tbdy_engine.design",
    "tbdy_engine.engine.context_builder",
    "tbdy_engine.engine.forces",
    "tbdy_engine.engine.topology",
    "tbdy_engine.adapters",
    "tbdy_engine.reports",
    "tbdy_engine.runner",
    "tbdy_engine.runner_v2",
    "tbdy_engine.contracts",
)


@dataclass(frozen=True)
class FakeDatabaseTables:
    tables: tuple[str, ...]

    def GetAvailableTables(self):
        return (0, list(self.tables))


@dataclass(frozen=True)
class FakeSap:
    model_filename: object = r"C:\\models\\demo.edb"
    tables: tuple[str, ...] = (STORY_DEFINITIONS_TABLE,)

    @property
    def DatabaseTables(self):
        return FakeDatabaseTables(self.tables)

    def GetModelFilename(self):
        return self.model_filename


def _patch_connected(monkeypatch, *, sap: object | None = None, message: str = "connected") -> object:
    fake_sap = sap if sap is not None else FakeSap()
    monkeypatch.setattr(table_access, "check_etabs_connection", lambda: (True, message))
    monkeypatch.setattr(table_access, "get_sap", lambda: fake_sap)
    return fake_sap


def _patch_reader(monkeypatch, *, ok: bool = True, df=None, error: str | None = None):
    if df is None:
        df = pd.DataFrame({"Story": ["S1"], "Height": [3.0]})

    async def fake_get_table_df(table_name: str):
        return SimpleNamespace(
            ok=ok,
            df=df,
            error=error,
            has_data=not df.empty,
        )

    monkeypatch.setattr(table_access, "get_table_df", fake_get_table_df)


def test_empty_table_name_returns_read_error():
    result = read_etabs_table_on_demand("  ")

    assert result.status is EtabsTableAccessStatus.READ_ERROR
    assert result.ok is False
    assert result.has_data is False
    assert result.error == "table_name is required"


def test_check_etabs_connection_false_returns_etabs_unavailable(monkeypatch):
    monkeypatch.setattr(table_access, "check_etabs_connection", lambda: (False, "not connected"))

    result = read_etabs_table_on_demand(STORY_DEFINITIONS_TABLE)

    assert result.status is EtabsTableAccessStatus.ETABS_UNAVAILABLE
    assert result.error == "not connected"


def test_connected_but_empty_model_filename_returns_no_open_model(monkeypatch):
    _patch_connected(monkeypatch, sap=FakeSap(model_filename=""))

    result = read_etabs_table_on_demand(STORY_DEFINITIONS_TABLE)

    assert result.status is EtabsTableAccessStatus.NO_OPEN_MODEL
    assert result.model_filename == ""


def test_requested_table_not_available_returns_table_unavailable(monkeypatch):
    _patch_connected(monkeypatch, sap=FakeSap(tables=("Other Table",)))

    result = read_etabs_table_on_demand(STORY_DEFINITIONS_TABLE)

    assert result.status is EtabsTableAccessStatus.TABLE_UNAVAILABLE
    assert result.model_filename.endswith(".edb")
    assert STORY_DEFINITIONS_TABLE in result.error


def test_get_table_df_not_ok_returns_read_error(monkeypatch):
    _patch_connected(monkeypatch)
    _patch_reader(monkeypatch, ok=False, error="read failed")

    result = read_etabs_table_on_demand(STORY_DEFINITIONS_TABLE)

    assert result.status is EtabsTableAccessStatus.READ_ERROR
    assert result.error == "read failed"


def test_get_table_df_ok_but_empty_returns_table_empty(monkeypatch):
    _patch_connected(monkeypatch)
    _patch_reader(monkeypatch, ok=True, df=pd.DataFrame(columns=["Story", "Height"]))

    result = read_etabs_table_on_demand(STORY_DEFINITIONS_TABLE)

    assert result.status is EtabsTableAccessStatus.TABLE_EMPTY
    assert result.row_count == 0
    assert result.column_count == 2
    assert result.df is not None


def test_successful_dataframe_returns_ok_with_counts_and_df(monkeypatch):
    df = pd.DataFrame({"Story": ["S1", "S2"], "Height": [3.0, 3.5]})
    _patch_connected(monkeypatch)
    _patch_reader(monkeypatch, df=df)

    result = read_etabs_table_on_demand(STORY_DEFINITIONS_TABLE)

    assert result.status is EtabsTableAccessStatus.OK
    assert result.ok is True
    assert result.has_data is True
    assert result.row_count == 2
    assert result.column_count == 2
    assert result.df is df


def test_to_dict_excludes_raw_dataframe():
    result = EtabsTableAccessResult(
        table_name=STORY_DEFINITIONS_TABLE,
        status=EtabsTableAccessStatus.OK,
        model_filename="demo.edb",
        row_count=1,
        column_count=2,
        df=pd.DataFrame({"a": [1]}),
    )

    payload = result.to_dict()

    assert list(payload) == [
        "table_name",
        "status",
        "model_filename",
        "row_count",
        "column_count",
        "error",
    ]
    assert "df" not in payload
    assert payload["status"] == "OK"


def test_production_import_guard():
    source_path = ROOT / "tbdy_engine" / "etabs" / "table_access.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    assert "tbdy_engine.etabs.connection" in imported_modules
    assert "tbdy_engine.etabs.table_reader" in imported_modules

    forbidden_imports = sorted(
        module_name
        for module_name in imported_modules
        if any(
            module_name == prefix or module_name.startswith(prefix + ".")
            for prefix in FORBIDDEN_IMPORT_PREFIXES
        )
    )
    assert forbidden_imports == []


def test_live_etabs_story_definitions_on_demand_read_optional():
    if os.environ.get("TBDY_RUN_ETABS_LIVE_SMOKE") != "1":
        pytest.skip("Live ETABS on-demand table access disabled; set TBDY_RUN_ETABS_LIVE_SMOKE=1")

    result = read_etabs_table_on_demand(STORY_DEFINITIONS_TABLE)

    if result.status is EtabsTableAccessStatus.ETABS_UNAVAILABLE:
        pytest.skip(f"ETABS unavailable: {result.error}")
    if result.status is EtabsTableAccessStatus.NO_OPEN_MODEL:
        pytest.skip(f"No open ETABS model: {result.error}")

    assert result.status is EtabsTableAccessStatus.OK
    assert result.ok is True
    assert result.has_data is True
    assert result.row_count > 0
    assert result.column_count > 0
