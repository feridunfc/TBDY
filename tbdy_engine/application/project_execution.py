"""Production application-intent contracts for PRODUCT-SPINE-COL-1.

These DTOs intentionally contain only project/component intent.  They do not
carry ETABS runtime capabilities, regulatory compile inputs, factual evidence,
reviewed policy objects, PMM/adequacy authority inputs, or test-fixture truth.
"""
from __future__ import annotations

from dataclasses import dataclass


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


@dataclass(frozen=True, slots=True)
class ColumnExecutionRequest:
    """Application intent for one column component."""

    component_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _text(self.component_id, "component_id"))


@dataclass(frozen=True, slots=True)
class ProjectExecutionRequest:
    """Application intent for the first supported project vertical cut."""

    project_id: str
    report_id: str
    title: str
    column: ColumnExecutionRequest

    def __post_init__(self) -> None:
        object.__setattr__(self, "project_id", _text(self.project_id, "project_id"))
        object.__setattr__(self, "report_id", _text(self.report_id, "report_id"))
        object.__setattr__(self, "title", _text(self.title, "title"))
        if not isinstance(self.column, ColumnExecutionRequest):
            raise TypeError("column must be ColumnExecutionRequest")


__all__ = ["ColumnExecutionRequest", "ProjectExecutionRequest"]
