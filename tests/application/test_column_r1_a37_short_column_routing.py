
from __future__ import annotations

from dataclasses import fields
import inspect

import pytest

import tbdy_engine.application.column_execution as subject
import tbdy_engine.application.project_execution as project_execution
from tbdy_engine.application.column_p7_runtime import (
    ReviewedColumnShortColumnContext,
)
from tbdy_engine.application.contracts import (
    ColumnExecutionRequest,
    ProjectExecutionRequest,
)


COMPONENT = "S1:C1:101"


def _short(applies: bool):
    return ReviewedColumnShortColumnContext(
        component_id=COMPONENT,
        short_column_applies=applies,
        short_free_length_mm=(900.0 if applies else None),
        infill_fully_adjacent=(False if applies else None),
        story_height_mm=None,
        review_refs=("REVIEW:SHORT",),
    )


def test_unreviewed_short_applicability_fails_closed_for_p7_route():
    with pytest.raises(
        subject.ColumnExecutionContractError,
        match="short-column applicability",
    ):
        subject._resolve_a37_shear_route(
            high_ductility_applies=True,
            limited_ductility_applies=False,
            short_column_context=None,
            p7_context_present=True,
            limited_context_present=False,
            downstream_shear_required=False,
        )


def test_limited_short_routes_to_existing_p7_and_forbids_775():
    route = subject._resolve_a37_shear_route(
        high_ductility_applies=False,
        limited_ductility_applies=True,
        short_column_context=_short(True),
        p7_context_present=True,
        limited_context_present=False,
        downstream_shear_required=True,
    )
    assert route == subject.A37_SHEAR_ROUTE_P7_SHORT

    with pytest.raises(
        subject.ColumnExecutionContractError,
        match="forbids ordinary",
    ):
        subject._resolve_a37_shear_route(
            high_ductility_applies=False,
            limited_ductility_applies=True,
            short_column_context=_short(True),
            p7_context_present=True,
            limited_context_present=True,
            downstream_shear_required=True,
        )


def test_ordinary_limited_preserves_775_route():
    route = subject._resolve_a37_shear_route(
        high_ductility_applies=False,
        limited_ductility_applies=True,
        short_column_context=_short(False),
        p7_context_present=False,
        limited_context_present=True,
        downstream_shear_required=True,
    )
    assert route == subject.A37_SHEAR_ROUTE_LIMITED_775


def test_short_context_is_keyword_dependency_not_request_truth():
    forbidden = {
        "reviewed_column_short_column_context",
        "short_column_context",
        "short_column_applies",
        "short_free_length_mm",
    }
    assert forbidden.isdisjoint(
        {item.name for item in fields(ColumnExecutionRequest)}
    )
    assert forbidden.isdisjoint(
        {item.name for item in fields(ProjectExecutionRequest)}
    )
    assert (
        "reviewed_column_short_column_context"
        in inspect.signature(subject.execute_column_domain).parameters
    )
    assert (
        "reviewed_column_short_column_context"
        in inspect.signature(project_execution.execute_project).parameters
    )
