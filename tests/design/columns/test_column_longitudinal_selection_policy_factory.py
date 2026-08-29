from __future__ import annotations

from dataclasses import replace
import inspect

import pytest

from tbdy_engine.design.columns.column_longitudinal_ranking_authority import (
    INPUT_REVIEW_REF,
    POLICY_ID,
    POLICY_VERSION,
    PRIMARY_OBJECTIVE,
    TIE_BREAKERS,
    ColumnLongitudinalRankingAuthorityError,
    authorize_column_longitudinal_ranking_policy,
)
from tbdy_engine.design.columns.column_longitudinal_selection_contract import (
    ColumnLongitudinalSelectionPolicyInput,
)
from tbdy_engine.design.columns.column_longitudinal_selection_policy_factory import (
    build_reviewed_column_longitudinal_selection_policy_input,
)


def test_factory_materializes_exact_reviewed_policy_input() -> None:
    policy = build_reviewed_column_longitudinal_selection_policy_input()

    assert isinstance(policy, ColumnLongitudinalSelectionPolicyInput)
    assert policy.policy_id == POLICY_ID
    assert policy.policy_version == POLICY_VERSION
    assert policy.primary_objective == PRIMARY_OBJECTIVE
    assert policy.tie_breakers == TIE_BREAKERS
    assert policy.review_ref == INPUT_REVIEW_REF


def test_factory_has_no_runtime_policy_arguments_or_defaults() -> None:
    signature = inspect.signature(
        build_reviewed_column_longitudinal_selection_policy_input
    )
    assert tuple(signature.parameters) == ()


def test_factory_is_deterministic() -> None:
    first = build_reviewed_column_longitudinal_selection_policy_input()
    second = build_reviewed_column_longitudinal_selection_policy_input()

    assert first == second


def test_factory_output_binds_to_existing_reviewed_ranking_authority() -> None:
    policy = build_reviewed_column_longitudinal_selection_policy_input()

    validated = authorize_column_longitudinal_ranking_policy(policy)

    assert validated.policy_id == POLICY_ID
    assert validated.policy_version == POLICY_VERSION
    assert validated.primary_objective == PRIMARY_OBJECTIVE
    assert validated.tie_breakers == TIE_BREAKERS
    assert validated.input_review_ref == INPUT_REVIEW_REF


def test_modified_policy_remains_fail_closed() -> None:
    policy = build_reviewed_column_longitudinal_selection_policy_input()
    changed = replace(policy, primary_objective="UNREVIEWED_OBJECTIVE")

    with pytest.raises(ColumnLongitudinalRankingAuthorityError):
        authorize_column_longitudinal_ranking_policy(changed)
