"""Focused COL-4C2B canonical selected-rebar authority proofs."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import ast
import importlib.util
from pathlib import Path
import sys

import pytest

import tbdy_engine.design.columns.column_longitudinal_selection as subject
import tbdy_engine.design.columns.column_pmm_assessment as pmm_subject

from tbdy_engine.design.columns.column_longitudinal_selection import (
    BLOCK_NO_ADEQUATE_CANDIDATE,
    BLOCK_RANKING_POLICY,
    BLOCK_UNRESOLVED_CANDIDATES,
    ENGINE_SELECTED_REBAR_AUTHORITY,
    STATUS_BLOCKED_RANKING_POLICY,
    STATUS_BLOCKED_UNRESOLVED_CANDIDATES,
    STATUS_NO_ADEQUATE_CANDIDATE,
    STATUS_SELECTED,
    select_canonical_column_longitudinal_rebar,
)
from tbdy_engine.design.columns.section_capacity import (
    ColumnInteractionEnvelope,
    RadialMomentCapacity,
)
from tbdy_engine.regulatory.column_candidate_adequacy_authority import (
    authorize_candidate_adequacy_policy,
)
from tbdy_engine.regulatory.sources.fnd_col_4_candidate_adequacy import (
    FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG,
)


def _load_b2_fixture_module():
    name = "_fnd_col_4_c2b_b2_fixture"

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


def _patch_all_proven(monkeypatch):
    def envelope(
        *,
        width_mm,
        depth_mm,
        bars,
        material,
        target_n_compression_n,
        angle_count,
        axial_tolerance_n,
    ):
        return ColumnInteractionEnvelope(
            target_n_compression_n=(
                target_n_compression_n
            ),
            states=(),
            status="PROVEN",
            angle_step_deg=(
                360.0 / float(angle_count)
            ),
        )

    def radial(
        envelope,
        *,
        demand_m2_nmm,
        demand_m3_nmm,
    ):
        return RadialMomentCapacity(
            demand_angle_deg=0.0,
            capacity_nmm=1_000_000_000.0,
            boundary_m2_nmm=1_000_000_000.0,
            boundary_m3_nmm=0.0,
            status="PROVEN",
        )

    monkeypatch.setattr(
        pmm_subject,
        "build_interaction_envelope_at_axial_force",
        envelope,
    )

    monkeypatch.setattr(
        pmm_subject,
        "radial_moment_capacity",
        radial,
    )


def _run(inputs):
    return select_canonical_column_longitudinal_rebar(
        inputs=inputs,
        numerical_policy=FIX._policy(),
        material_context=FIX._material(),
        adequacy_policy=_adequacy_policy(),
    )


def test_complete_zero_unresolved_population_ranks_all_adequate_and_selects_rank_one(
    monkeypatch,
):
    _patch_all_proven(monkeypatch)

    inputs, _ = FIX._selection_context()

    inputs = _single_required_as(
        inputs,
        Decimal("0"),
    )

    result = _run(inputs)

    assert result.status == STATUS_SELECTED
    assert result.selected
    assert result.blockers == ()

    assert (
        result.adequacy_population
        .unresolved_candidate_count
        == 0
    )

    assert (
        len(result.ranking_rows)
        == result.adequacy_population
        .adequate_candidate_count
        == len(
            inputs.layout_authority
            .eligible_candidates
        )
    )

    expected = min(
        inputs.layout_authority.eligible_candidates,
        key=lambda candidate: (
            Decimal(str(candidate.as_total_mm2)),
            candidate.bar_count,
            Decimal(
                str(candidate.bar_diameter_mm)
            ),
            candidate.candidate_id,
        ),
    )

    selected = result.selected_rebar

    assert selected is not None
    assert (
        selected.authority
        == ENGINE_SELECTED_REBAR_AUTHORITY
    )
    assert selected.rank == 1
    assert selected.candidate_id == expected.candidate_id
    assert selected.selected_candidate == expected

    assert tuple(
        row.rank
        for row in result.ranking_rows
    ) == tuple(
        range(
            1,
            len(result.ranking_rows) + 1,
        )
    )

    assert (
        len(selected.required_area_decision_ids)
        == len(
            result.adequacy_population
            .requirement_ids
        )
    )

    assert (
        len(selected.pmm_decision_ids)
        == len(
            result.adequacy_population
            .demand_state_ids
        )
    )


def test_any_unresolved_candidate_blocks_optimization_and_emission(
    monkeypatch,
):
    inputs, _ = FIX._selection_context()

    inputs = _single_required_as(
        inputs,
        Decimal("0"),
    )

    FIX._patch_capacity(monkeypatch)

    result = _run(inputs)

    assert (
        result.status
        == STATUS_BLOCKED_UNRESOLVED_CANDIDATES
    )

    assert (
        BLOCK_UNRESOLVED_CANDIDATES
        in result.blockers
    )

    assert (
        result.adequacy_population
        .unresolved_candidate_count
        > 0
    )

    assert result.ranking_rows == ()
    assert result.selected_rebar is None


def test_zero_adequate_candidates_emits_no_selection(
    monkeypatch,
):
    _patch_all_proven(monkeypatch)

    inputs, _ = FIX._selection_context()

    inputs = _single_required_as(
        inputs,
        Decimal("1000000000"),
    )

    result = _run(inputs)

    assert (
        result.status
        == STATUS_NO_ADEQUATE_CANDIDATE
    )

    assert (
        BLOCK_NO_ADEQUATE_CANDIDATE
        in result.blockers
    )

    assert (
        result.adequacy_population
        .adequate_candidate_count
        == 0
    )

    assert (
        result.adequacy_population
        .unresolved_candidate_count
        == 0
    )

    assert result.ranking_rows == ()
    assert result.selected_rebar is None


def test_unreviewed_ranking_semantics_fail_before_selection(
    monkeypatch,
):
    inputs, _ = FIX._selection_context()

    changed_policy = replace(
        inputs.policy,
        primary_objective="MAX_TOTAL_AS",
    )

    changed_inputs = replace(
        inputs,
        policy=changed_policy,
    )

    calls = []

    def should_not_run(*args, **kwargs):
        calls.append(True)
        raise AssertionError(
            "PMM assessment must not run "
            "for unreviewed ranking policy"
        )

    monkeypatch.setattr(
        subject,
        "evaluate_column_candidate_adequacy_population",
        should_not_run,
    )

    result = _run(changed_inputs)

    assert (
        result.status
        == STATUS_BLOCKED_RANKING_POLICY
    )

    assert BLOCK_RANKING_POLICY in result.blockers
    assert result.selected_rebar is None
    assert result.ranking_rows == ()
    assert calls == []


def test_candidate_and_demand_input_order_do_not_change_selection(
    monkeypatch,
):
    _patch_all_proven(monkeypatch)

    inputs, _ = FIX._selection_context()

    inputs = _single_required_as(
        inputs,
        Decimal("0"),
    )

    first = _run(inputs)

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

    second = _run(reversed_inputs)

    assert first == second


def test_same_candidate_id_with_changed_geometry_changes_selected_ref(
    monkeypatch,
):
    _patch_all_proven(monkeypatch)

    inputs, _ = FIX._selection_context()

    inputs = _single_required_as(
        inputs,
        Decimal("0"),
    )

    first = _run(inputs)

    assert first.selected_rebar is not None

    selected_id = (
        first.selected_rebar.candidate_id
    )

    changed_candidates = []

    for candidate in (
        inputs.layout_authority
        .eligible_candidates
    ):
        if candidate.candidate_id != selected_id:
            changed_candidates.append(candidate)
            continue

        bars = list(candidate.bars)

        bars[0] = replace(
            bars[0],
            x2_mm=bars[0].x2_mm + 1.0,
        )

        changed_candidates.append(
            replace(
                candidate,
                bars=tuple(bars),
            )
        )

    changed_layout = replace(
        inputs.layout_authority,
        eligible_candidates=tuple(
            changed_candidates
        ),
    )

    changed_inputs = replace(
        inputs,
        layout_authority=changed_layout,
    )

    second = _run(changed_inputs)

    assert second.selected_rebar is not None

    assert (
        second.selected_rebar.candidate_id
        == selected_id
    )

    assert (
        second.selected_rebar
        .candidate_geometry_fingerprint
        != first.selected_rebar
        .candidate_geometry_fingerprint
    )

    assert (
        second.selected_rebar.selected_rebar_ref
        != first.selected_rebar.selected_rebar_ref
    )


def test_c2b_does_not_import_or_delegate_to_legacy_selector():
    path = Path(subject.__file__).resolve()

    source = path.read_text(
        encoding="utf-8-sig"
    )

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

    assert "select_engine_rebar_for_demands" not in source
    assert (
        "select_engine_rebar_from_authorized_demands"
        not in source
    )

    assert (
        source.count(
            '"ENGINE_SELECTED_REBAR"'
        )
        == 1
    )
