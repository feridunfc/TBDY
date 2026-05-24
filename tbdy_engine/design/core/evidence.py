from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(slots=True)
class Evidence:
    source: str
    key: str
    value: Any
    unit: str | None = None
    note: str | None = None

@dataclass(slots=True)
class DataRequest:
    key: str
    reason: str
    required_for: str
    severity: str = "HIGH"
