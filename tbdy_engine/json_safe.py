"""JSON-safe conversion helpers for smoke/report payloads.

This module intentionally does not use ``default=str`` because that can hide
contract/reporting leaks. Unsupported objects raise ``TypeError`` so callers can
write an explicit serialization failure report.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any


def to_jsonable(value: Any) -> Any:
    """Recursively convert common immutable/model objects to JSON-safe values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, Path):
        return value.as_posix()

    if isinstance(value, MappingProxyType):
        return {str(k): to_jsonable(v) for k, v in dict(value).items()}

    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_jsonable(getattr(value, field.name)) for field in fields(value)}

    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump())

    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(v) for v in value]

    if hasattr(value, "__dict__"):
        return to_jsonable(vars(value))

    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
