# tbdy_engine/__init__.py
from __future__ import annotations

__version__ = "0.1.0-sprint1"

from .runner import run
from .engine.context_builder import build_model_context, ModelContext
from .etabs.connection import get_sap, check_etabs_connection
from .etabs.table_reader import get_table_df, get_many_case_tables
from .checks.registry import CheckRegistry

__all__ = [
    "run",
    "build_model_context",
    "ModelContext",
    "get_sap",
    "check_etabs_connection",
    "get_table_df",
    "CheckRegistry",
]