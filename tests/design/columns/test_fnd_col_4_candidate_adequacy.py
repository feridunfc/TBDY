"""Focused FND-COL-4C1B exhaustive candidate adequacy proofs."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import ast
import importlib.util
from pathlib import Path
import sys

import pytest

import tbdy_engine.design.columns.column_candidate_adequacy as subject

from tbdy_engine.design.columns.column_candidate_adequacy import (
    BLOCKED,
    BLOCK_GEOMETRY_BINDING,
    BLOCK_SELECTION_CONTRACT,
    CandidateAdequacyAssessment,
    evaluate_column_candidate_adequacy_population,
)
from tbdy_engine.design.columns.column_longitudinal_selection_contract import (
    reconcile_column_longitudinal_selection_contract,
)
from tbdy_engine.regulatory.column_candidate_adequacy_authority import (
    CANDIDATE_INADEQUATE,
    authorize_candidate_adequacy_policy,
)
from tbdy_engine.regulatory.sources.fnd_col_4_candidate_adequacy import (
    FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG,
)


def _load_b2_fixture_module():
    name = "_fnd_col_4_b2_test_fixture"

    if name in sys.modules:
        return sys.modules[name]

    path = Path(__file__).with_name(
        "test_fnd_col_4_pmm_assessment.py"
    )

    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "cannot load COL-4B2 test fixtures"
        )

    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)

    return module


FIX = _load_b2_fixture_module()


def _adequacy_policy():
    return authorize_candidate_adequacy_policy(
        authority_catalog=(
            FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG
        )
    )


def _replace_requirements(
    inputs,
    requirements,
):
    population = inputs.etabs_required_rebar
    component = population.components[0]

    requirements = tuple(requirements)

    new_component = replace(
        component,
        requirements=requirements,
        blocked_rows=(),
        source_design_row_count=len(requirements),
        promoted_requirement_count=len(requirements),
        blocked_requirement_count=0,
    )

    new_population = replace(
        population,
        source_result_row_count=len(requirements),
        source_design_row_count=len(requirements),
        promoted_requirement_count=len(requirements),
        blocked_requirement_count=0,
        components=(new_component,),
    )

    return replace(
        inputs,
        etabs_required_rebar=new_population,
    )


def _single_required_as(
    inputs,
    value: Decimal,
):
    original = (
        inputs.etabs_required_rebar
        .components[0]
        .requirements[0]
    )

    requirement = replace(
        original,
        required_as_mm2=value,
    )

    return _replace_requirements(
        inputs,
        (requirement,),
    )


def _run(
    *,
    inputs,
    contract,
):
    return evaluate_column_candidate_adequacy_population(
        inputs=inputs,
        selection_contract=contract,
        numerical_policy=FIX._policy(),
        material_context=FIX._material(),
        adequacy_policy=_adequacy_policy(),
    )


def test_every_candidate_x_every_p8a_and_pmm_row_is_retained(
    monkeypatch,
):
    FIX._patch_capacity(monkeypatch)

    inputs, _ = FIX._selection_context()

    inputs = _single_required_as(
        inputs,
        Decimal("0"),
    )

    contract = (
        reconcile_column_longitudinal_selection_contract(
            inputs
        )
    )

    assert contract.reconciled

    result = _run(
        inputs=inputs,
        contract=contract,
    )

    assert result.complete

    assert (
        len(result.required_area_rows)
        == len(result.candidate_ids)
        * len(result.requirement_ids)
    )

    assert (
        len(result.pmm_rows)
        == len(result.candidate_ids)
        * len(result.demand_state_ids)
    )

    assert (
        len(result.candidate_assessments)
        == len(result.candidate_ids)
    )

    assert result.expected_required_area_decision_count == 2
    assert result.expected_pmm_decision_count == 4


def test_multiple_p8a_rows_are_never_collapsed_to_one_maximum(
    monkeypatch,
):
    FIX._patch_capacity(monkeypatch)

    inputs, _ = FIX._selection_context()

    original = (
        inputs.etabs_required_rebar
        .components[0]
        .requirements[0]
    )

    low = replace(
        original,
        requirement_id="requirement:low",
        source_row_id="source-row:low",
        required_as_mm2=Decimal("0"),
    )

    high = replace(
        original,
        requirement_id="requirement:high",
        source_row_id="source-row:high",
        required_as_mm2=Decimal("1000000000"),
    )

    inputs = _replace_requirements(
        inputs,
        (high, low),
    )

    contract = (
        reconcile_column_longitudinal_selection_contract(
            inputs
        )
    )

    assert contract.reconciled

    result = _run(
        inputs=inputs,
        contract=contract,
    )

    assert result.complete
    assert len(result.requirement_ids) == 2
    assert len(result.required_area_rows) == 4

    for candidate_id in result.candidate_ids:
        rows = tuple(
            row
            for row in result.required_area_rows
            if row.candidate_id == candidate_id
        )

        assert {
            row.requirement_id
            for row in rows
        } == {
            "requirement:low",
            "requirement:high",
        }

    assert all(
        assessment.status
        == CANDIDATE_INADEQUATE
        for assessment
        in result.candidate_assessments
    )


def test_stale_selection_contract_blocks_without_partial_decisions(
    monkeypatch,
):
    FIX._patch_capacity(monkeypatch)

    inputs, old_contract = FIX._selection_context()

    changed_policy = replace(
        inputs.policy,
        policy_version="v2",
    )

    changed_inputs = replace(
        inputs,
        policy=changed_policy,
    )

    result = _run(
        inputs=changed_inputs,
        contract=old_contract,
    )

    assert result.status == BLOCKED

    assert (
        BLOCK_SELECTION_CONTRACT
        in result.blockers
    )

    assert result.required_area_rows == ()
    assert result.pmm_rows == ()
    assert result.candidate_assessments == ()


def test_tampered_pmm_geometry_binding_blocks_before_decision(
    monkeypatch,
):
    FIX._patch_capacity(monkeypatch)

    inputs, _ = FIX._selection_context()

    inputs = _single_required_as(
        inputs,
        Decimal("0"),
    )

    contract = (
        reconcile_column_longitudinal_selection_contract(
            inputs
        )
    )

    real_assess = (
        subject.assess_all_column_pmm_candidate_demands
    )

    def tampered_assess(**kwargs):
        population = real_assess(**kwargs)

        target = population.candidate_ids[0]

        fake = (
            "candidate-geometry-binding:sha256:"
            + "0" * 64
        )

        rows = tuple(
            replace(
                row,
                candidate_geometry_fingerprint=fake,
            )
            if row.candidate_id == target
            else row
            for row in population.assessment_rows
        )

        summaries = tuple(
            replace(
                summary,
                candidate_geometry_fingerprint=fake,
            )
            if summary.candidate_id == target
            else summary
            for summary
            in population.candidate_assessments
        )

        return replace(
            population,
            assessment_rows=rows,
            candidate_assessments=summaries,
        )

    monkeypatch.setattr(
        subject,
        "assess_all_column_pmm_candidate_demands",
        tampered_assess,
    )

    result = _run(
        inputs=inputs,
        contract=contract,
    )

    assert result.status == BLOCKED

    assert (
        BLOCK_GEOMETRY_BINDING
        in result.blockers
    )

    assert result.required_area_rows == ()
    assert result.pmm_rows == ()
    assert result.candidate_assessments == ()


def test_candidate_and_demand_input_order_do_not_change_output(
    monkeypatch,
):
    FIX._patch_capacity(monkeypatch)

    inputs, _ = FIX._selection_context()

    inputs = _single_required_as(
        inputs,
        Decimal("0"),
    )

    contract = (
        reconcile_column_longitudinal_selection_contract(
            inputs
        )
    )

    first = _run(
        inputs=inputs,
        contract=contract,
    )

    reversed_layout = replace(
        inputs.layout_authority,
        eligible_candidates=tuple(
            reversed(
                inputs.layout_authority
                .eligible_candidates
            )
        ),
    )

    reversed_readiness = replace(
        inputs.readiness_binding.readiness,
        demand_states=tuple(
            reversed(
                inputs.readiness_binding
                .readiness
                .demand_states
            )
        ),
    )

    reversed_binding = replace(
        inputs.readiness_binding,
        readiness=reversed_readiness,
    )

    reversed_inputs = replace(
        inputs,
        layout_authority=reversed_layout,
        readiness_binding=reversed_binding,
    )

    reversed_contract = (
        reconcile_column_longitudinal_selection_contract(
            reversed_inputs
        )
    )

    assert reversed_contract.reconciled

    second = _run(
        inputs=reversed_inputs,
        contract=reversed_contract,
    )

    assert first == second


def test_c1b_contains_no_ranking_or_final_selection_authority():
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
            "rebar_selection_authority"
        ),
        (
            "tbdy_engine.design.columns."
            "column_rebar_design_engine"
        ),
        "tbdy_engine.features.etabs_com_attach",
    }

    assert imports.isdisjoint(forbidden)
