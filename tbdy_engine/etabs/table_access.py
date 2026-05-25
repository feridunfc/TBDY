from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any

from tbdy_engine.etabs.connection import check_etabs_connection, get_sap
from tbdy_engine.etabs.table_reader import get_table_df


class EtabsTableAccessStatus(str, Enum):
    OK = "OK"
    ETABS_UNAVAILABLE = "ETABS_UNAVAILABLE"
    NO_OPEN_MODEL = "NO_OPEN_MODEL"
    TABLE_UNAVAILABLE = "TABLE_UNAVAILABLE"
    TABLE_EMPTY = "TABLE_EMPTY"
    READ_ERROR = "READ_ERROR"


@dataclass(frozen=True)
class EtabsTableAccessResult:
    table_name: str
    status: EtabsTableAccessStatus
    model_filename: str = ""
    row_count: int = 0
    column_count: int = 0
    error: str = ""
    df: object | None = None

    @property
    def ok(self) -> bool:
        return self.status is EtabsTableAccessStatus.OK

    @property
    def has_data(self) -> bool:
        return self.ok and self.row_count > 0 and self.column_count > 0

    def to_dict(self) -> dict[str, object]:
        return {
            "table_name": self.table_name,
            "status": self.status.value,
            "model_filename": self.model_filename,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "error": self.error,
        }


def read_etabs_table_on_demand(table_name: str) -> EtabsTableAccessResult:
    requested_table = str(table_name or "").strip()
    if not requested_table:
        return EtabsTableAccessResult(
            table_name=requested_table,
            status=EtabsTableAccessStatus.READ_ERROR,
            error="table_name is required",
        )

    connected, message = check_etabs_connection()
    if not connected:
        return EtabsTableAccessResult(
            table_name=requested_table,
            status=EtabsTableAccessStatus.ETABS_UNAVAILABLE,
            error=str(message or "ETABS unavailable"),
        )

    try:
        sap = get_sap()
    except Exception as exc:
        return EtabsTableAccessResult(
            table_name=requested_table,
            status=EtabsTableAccessStatus.ETABS_UNAVAILABLE,
            error=str(exc) or type(exc).__name__,
        )

    model_filename = _model_filename(sap)
    if not model_filename or model_filename.lower() == "unknown":
        return EtabsTableAccessResult(
            table_name=requested_table,
            status=EtabsTableAccessStatus.NO_OPEN_MODEL,
            error="No open ETABS model detected",
        )

    try:
        available_tables = _available_table_names(sap)
    except Exception as exc:
        return EtabsTableAccessResult(
            table_name=requested_table,
            status=EtabsTableAccessStatus.READ_ERROR,
            model_filename=model_filename,
            error=str(exc) or type(exc).__name__,
        )

    if requested_table not in available_tables:
        return EtabsTableAccessResult(
            table_name=requested_table,
            status=EtabsTableAccessStatus.TABLE_UNAVAILABLE,
            model_filename=model_filename,
            error=f"Table not available: {requested_table}",
        )

    try:
        table_result = asyncio.run(get_table_df(requested_table))
    except RuntimeError:
        return EtabsTableAccessResult(
            table_name=requested_table,
            status=EtabsTableAccessStatus.READ_ERROR,
            model_filename=model_filename,
            error="read_etabs_table_on_demand cannot be called from a running event loop",
        )
    except Exception as exc:
        return EtabsTableAccessResult(
            table_name=requested_table,
            status=EtabsTableAccessStatus.READ_ERROR,
            model_filename=model_filename,
            error=str(exc) or type(exc).__name__,
        )

    if not getattr(table_result, "ok", False):
        return EtabsTableAccessResult(
            table_name=requested_table,
            status=EtabsTableAccessStatus.READ_ERROR,
            model_filename=model_filename,
            error=str(getattr(table_result, "error", "") or "ETABS table read failed"),
        )

    df = getattr(table_result, "df", None)
    row_count, column_count = _dataframe_shape(df)
    if not getattr(table_result, "has_data", False) or row_count == 0 or column_count == 0:
        return EtabsTableAccessResult(
            table_name=requested_table,
            status=EtabsTableAccessStatus.TABLE_EMPTY,
            model_filename=model_filename,
            row_count=row_count,
            column_count=column_count,
            df=df,
        )

    return EtabsTableAccessResult(
        table_name=requested_table,
        status=EtabsTableAccessStatus.OK,
        model_filename=model_filename,
        row_count=row_count,
        column_count=column_count,
        df=df,
    )


def _model_filename(sap: object) -> str:
    try:
        raw = sap.GetModelFilename()
    except Exception:
        return ""
    return _string_from_etabs_return(raw)


def _available_table_names(sap: object) -> set[str]:
    raw = sap.DatabaseTables.GetAvailableTables()
    if isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, (list, tuple)) and item:
                return {str(table) for table in item}
        if len(raw) >= 2 and isinstance(raw[1], (list, tuple)):
            return {str(table) for table in raw[1]}
    return set()


def _string_from_etabs_return(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item.strip()
        return str(value)
    return str(value).strip() if value is not None else ""


def _dataframe_shape(df: object) -> tuple[int, int]:
    shape = getattr(df, "shape", None)
    if isinstance(shape, tuple) and len(shape) >= 2:
        return int(shape[0]), int(shape[1])
    return 0, 0
