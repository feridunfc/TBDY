"""Focused COL-4C2A reviewed ranking-policy authority proofs."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import ast
from pathlib import Path

import pytest

import tbdy_engine.design.columns.column_longitudinal_ranking_authority as subject

from tbdy_engine.design.columns.column_longitudinal_ranking_authority import (
    BINDING_REVIEW_REF,
    ColumnLongitudinalRankingAuthorityError,
    ColumnLongitudinalRankingCandidate,
    INPUT_REVIEW_REF,
    POLICY_ID,
    POLICY_VERSION,
    PRIMARY_OBJECTIVE,
    RANKING_DOMAIN,
    STABLE_RESOLUTION,
    TIE_BREAKERS,
    ValidatedColumnLongitudinalRankingPolicy,
    authorize_column_longitudinal_ranking_policy,
    ranking_key_for_candidate,
)
from tbdy_engine.design.columns.column_longitudinal_selection_contract import (
    ColumnLongitudinalSelectionPolicyInput,
)


def _input():
    return ColumnLongitudinalSelectionPolicyInput(
        policy_id="PROJECT_COLUMN_REBAR_POLICY",
        policy_version="v1",
        primary_objective="MIN_TOTAL_AS",
        tie_breakers=(
            "MIN_BAR_COUNT",
            "MIN_BAR_DIAMETER",
        ),
        review_ref=(
            "review:column-selection-policy:v1"
        ),
    )


def _candidate(
    candidate_id: str,
    *,
    as_total: str,
    count: int,
    diameter: str,
):
    return ColumnLongitudinalRankingCandidate(
        candidate_id=candidate_id,
        as_total_mm2=Decimal(as_total),
        bar_count=count,
        bar_diameter_mm=Decimal(diameter),
    )


def test_policy_is_factory_only_and_binds_exact_col4a_input():
    with pytest.raises(
        TypeError,
        match="authority-created only",
    ):
        ValidatedColumnLongitudinalRankingPolicy()

    policy = (
        authorize_column_longitudinal_ranking_policy(
            _input()
        )
    )

    assert policy.policy_id == POLICY_ID
    assert policy.policy_version == POLICY_VERSION

    assert (
        policy.primary_objective
        == PRIMARY_OBJECTIVE
        == "MIN_TOTAL_AS"
    )

    assert (
        policy.tie_breakers
        == TIE_BREAKERS
        == (
            "MIN_BAR_COUNT",
            "MIN_BAR_DIAMETER",
        )
    )

    assert policy.input_review_ref == INPUT_REVIEW_REF
    assert (
        policy.binding_review_ref
        == BINDING_REVIEW_REF
    )

    assert (
        policy.stable_resolution
        == STABLE_RESOLUTION
        == "CANDIDATE_ID_ASC"
    )

    assert policy.ranking_domain == RANKING_DOMAIN

    assert policy.require_complete_adequacy_population
    assert policy.require_zero_unresolved_candidates


def test_any_policy_semantic_drift_fails_closed():
    base = _input()

    drifts = (
        replace(
            base,
            policy_id="OTHER_POLICY",
        ),
        replace(
            base,
            policy_version="v2",
        ),
        replace(
            base,
            primary_objective="MAX_TOTAL_AS",
        ),
        replace(
            base,
            tie_breakers=(
                "MIN_BAR_DIAMETER",
                "MIN_BAR_COUNT",
            ),
        ),
        replace(
            base,
            review_ref="review:unapproved",
        ),
    )

    for drift in drifts:
        with pytest.raises(
            ColumnLongitudinalRankingAuthorityError,
            match="does not match",
        ):
            authorize_column_longitudinal_ranking_policy(
                drift
            )


def test_ranking_precedence_is_exact_and_not_generator_order():
    policy = (
        authorize_column_longitudinal_ranking_policy(
            _input()
        )
    )

    candidates = (
        _candidate(
            "candidate:z",
            as_total="5000",
            count=8,
            diameter="20",
        ),
        _candidate(
            "candidate:d",
            as_total="4000",
            count=8,
            diameter="20",
        ),
        _candidate(
            "candidate:c",
            as_total="4000",
            count=6,
            diameter="25",
        ),
        _candidate(
            "candidate:b",
            as_total="4000",
            count=6,
            diameter="20",
        ),
        _candidate(
            "candidate:a",
            as_total="4000",
            count=6,
            diameter="20",
        ),
    )

    ranked = tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                ranking_key_for_candidate(
                    policy=policy,
                    candidate=candidate,
                )
            ),
        )
    )

    assert tuple(
        item.candidate_id
        for item in ranked
    ) == (
        "candidate:a",
        "candidate:b",
        "candidate:c",
        "candidate:d",
        "candidate:z",
    )


def test_candidate_id_is_only_final_explicit_stable_resolution():
    policy = (
        authorize_column_longitudinal_ranking_policy(
            _input()
        )
    )

    first = _candidate(
        "candidate:b",
        as_total="4000",
        count=6,
        diameter="20",
    )

    second = _candidate(
        "candidate:a",
        as_total="4000",
        count=6,
        diameter="20",
    )

    first_key = ranking_key_for_candidate(
        policy=policy,
        candidate=first,
    )

    second_key = ranking_key_for_candidate(
        policy=policy,
        candidate=second,
    )

    assert (
        first_key.total_as_mm2
        == second_key.total_as_mm2
    )

    assert first_key.bar_count == second_key.bar_count

    assert (
        first_key.bar_diameter_mm
        == second_key.bar_diameter_mm
    )

    assert second_key < first_key


def test_ranking_is_input_order_invariant():
    policy = (
        authorize_column_longitudinal_ranking_policy(
            _input()
        )
    )

    candidates = (
        _candidate(
            "candidate:c",
            as_total="4200",
            count=8,
            diameter="20",
        ),
        _candidate(
            "candidate:a",
            as_total="4000",
            count=8,
            diameter="20",
        ),
        _candidate(
            "candidate:b",
            as_total="4000",
            count=10,
            diameter="16",
        ),
    )

    def rank(values):
        return tuple(
            item.candidate_id
            for item in sorted(
                values,
                key=lambda item: (
                    ranking_key_for_candidate(
                        policy=policy,
                        candidate=item,
                    )
                ),
            )
        )

    assert rank(candidates) == rank(
        tuple(reversed(candidates))
    )


def test_policy_fingerprint_is_deterministic_and_no_selection_emitter_exists():
    first = (
        authorize_column_longitudinal_ranking_policy(
            _input()
        )
    )

    second = (
        authorize_column_longitudinal_ranking_policy(
            _input()
        )
    )

    assert (
        first.policy_fingerprint
        == second.policy_fingerprint
    )

    assert first.policy_fingerprint.startswith(
        "sha256:"
    )

    path = Path(subject.__file__).resolve()

    source = path.read_text(
        encoding="utf-8-sig"
    )

    assert "ENGINE_SELECTED_REBAR" not in source
    assert "select_engine_rebar" not in source
    assert "selected_candidate" not in source

    tree = ast.parse(source)

    imports = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)

        elif isinstance(node, ast.Import):
            imports.update(
                alias.name
                for alias in node.names
            )

    forbidden = {
        (
            "tbdy_engine.design.columns."
            "rebar_selection"
        ),
        (
            "tbdy_engine.design.columns."
            "rebar_selection_authority"
        ),
        (
            "tbdy_engine.design.columns."
            "column_rebar_design_engine"
        ),
        "tbdy_engine.features.etabs_com_attach",
    }

    assert imports.isdisjoint(forbidden)
