# /etabs/table_reader.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional
import pandas as pd

from .connection import get_sap

@dataclass
class TableResult:
    ok: bool
    df: pd.DataFrame
    error: Optional[str] = None
    warning: Optional[str] = None

    @property
    def has_data(self) -> bool:
        return self.df is not None and not self.df.empty


def _parse_table_result(raw) -> pd.DataFrame:
    """
    ETABS DatabaseTables.GetTableForDisplayArray dönüşünü DataFrame'e çevirir.
    Farklı ETABS sürümlerindeki tuple formatlarına toleranslıdır.
    """
    if not isinstance(raw, (list, tuple)):
        return pd.DataFrame()

    fields = None
    data = None
    n_records = None

    for item in raw:
        if isinstance(item, (list, tuple)):
            # field list genelde string kolon isimleri
            if item and all(isinstance(x, str) for x in item):
                if fields is None:
                    fields = list(item)
                else:
                    # ikinci string list bazen flat data olabilir
                    data = list(item)
            elif item:
                data = list(item)

        elif isinstance(item, int):
            n_records = item

    if fields is None:
        return pd.DataFrame()

    if data is None:
        # bazı comtypes dönüşlerinde son eleman data olabilir
        for item in reversed(raw):
            if isinstance(item, (list, tuple)) and item is not fields:
                data = list(item)
                break

    if not data:
        return pd.DataFrame(columns=fields)

    n_cols = len(fields)
    if n_cols == 0:
        return pd.DataFrame()

    rows = []
    flat = list(data)

    for i in range(0, len(flat), n_cols):
        row = flat[i:i + n_cols]
        if len(row) == n_cols:
            rows.append(row)

    return pd.DataFrame(rows, columns=fields)

def _fix_mojibake(s: str) -> str:
    fixes = {
        "Â§": "§",
        "Ä±": "ı", "Ä°": "İ",
        "ÅŸ": "ş", "Åž": "Ş",
        "Ã§": "ç", "Ã‡": "Ç",
        "Ã¼": "ü", "Ãœ": "Ü",
        "Ã¶": "ö", "Ã–": "Ö",
        "ÄŸ": "ğ", "Äž": "Ğ",
        "Î¸": "θ",
    }
    for bad, good in fixes.items():
        s = s.replace(bad, good)
    return s


def _fix_df_mojibake(df):
    return df.map(lambda x: _fix_mojibake(x) if isinstance(x, str) else x)

async def get_table_df(
    table_name: str,
    case: Optional[str] = None,
    combo: Optional[str] = None,
    limit: Optional[int] = None,
) -> TableResult:
    try:
        sap = get_sap()

        # ETABS önce seçili case/combo ister.
        try:
            sap.DatabaseTables.SetLoadCasesSelectedForDisplay([])
            sap.DatabaseTables.SetLoadCombinationsSelectedForDisplay([])
        except Exception:
            pass

        if case:
            try:
                sap.DatabaseTables.SetLoadCasesSelectedForDisplay([case])
            except Exception:
                pass

        if combo:
            try:
                sap.DatabaseTables.SetLoadCombinationsSelectedForDisplay([combo])
            except Exception:
                pass

        raw = sap.DatabaseTables.GetTableForDisplayArray(
            table_name,
            [],
            "",
            0,
            [],
            0,
            [],
        )

        df = _parse_table_result(raw)
        df = _fix_df_mojibake(df)
        if limit and not df.empty:
            df = df.head(limit)

        return TableResult(ok=True, df=df)

    except Exception as e:
        return TableResult(ok=False, df=pd.DataFrame(), error=str(e))


async def get_many_case_tables(
    table_name: str,
    cases: List[str],
    limit: Optional[int] = None,
) -> TableResult:
    frames = []
    errors = []

    for case in cases:
        tr = await get_table_df(table_name, case=case, limit=limit)
        if tr.ok and tr.has_data:
            df = tr.df.copy()
            if "Output Case" not in df.columns and "output_case" not in df.columns:
                df["Output Case"] = case
            frames.append(df)
        elif tr.error:
            errors.append(f"{case}: {tr.error}")

    if not frames:
        return TableResult(
            ok=True,
            df=pd.DataFrame(),
            warning="No data for selected cases. " + " | ".join(errors[:5]),
        )

    return TableResult(ok=True, df=pd.concat(frames, ignore_index=True))