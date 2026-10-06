"""Real Eq713/FND2 owners with synthetic facts; no claim of B-BLOK live READY."""
from dataclasses import replace

import pytest

import test_column_public_mixed_vertical as vertical
import tbdy_engine.regulatory.fnd_col_2 as fnd2
from tbdy_engine.design.columns.stability_stiffness_basis import STATUS_BLOCKED_GLOBAL_PROOF
from tools.column_r1_bblok_e1_reviewed_inputs import REVIEWED_TOLERANCE


@pytest.mark.parametrize("tolerance_bound", [False, True])
def test_whole_system_authority_and_limited_modifier_audit_remain_distinct(monkeypatch, tolerance_bound):
    harness = vertical._install(monkeypatch)
    readiness_rows, populations, generations, b6_calls = [], [], [], []
    real_readiness = fnd2.resolve_column_design_demand_readiness
    real_population = vertical.a5._build_a3
    real_generation = vertical.a5._run_a3_generation

    class B6Reached(BaseException):
        """Stop after real readiness/join, before unrelated rebar selection."""

    def capture_readiness(**kwargs):
        result = real_readiness(**kwargs)
        readiness_rows.append(result)
        return result

    def capture_population(**kwargs):
        result = real_population(**kwargs)
        whole = result[0]
        assert tuple(sorted(r.component_uid for r in whole.frame_rows)) == kwargs["frame_population"].expected_frame_names
        assert tuple(sorted(r.area_name for r in whole.area_rows)) == kwargs["area_population"].expected_area_names
        populations.append(whole)
        return result

    def capture_generation(**kwargs):
        result = real_generation(**kwargs)
        _, state, execution = result
        assert execution.qualification.qualified
        assert execution.analysis_result_identity.parent_analysis_state_ref == state.analysis_state_identity.identity_ref
        generations.append(execution.analysis_result_identity.identity_ref)
        return result

    def stop_at_b6(**kwargs):
        b6_calls.append(kwargs)
        raise B6Reached

    monkeypatch.setattr(fnd2, "resolve_column_design_demand_readiness", capture_readiness)
    monkeypatch.setattr(vertical.a5, "_build_a3", capture_population)
    monkeypatch.setattr(vertical.a5, "_run_a3_generation", capture_generation)
    monkeypatch.setattr(vertical.column, "execute_controlled_concrete_design", stop_at_b6)
    basis = replace(vertical._basis(), story_translation_tolerance=REVIEWED_TOLERANCE if tolerance_bound else None)

    def execute():
        return vertical.project.execute_project(
            vertical.population._two_column_request(),
            verified_session=harness.setup.module._FakeSession(),
            column_design_basis=basis,
            expected_combo_policy=vertical._policy(harness.combos),
        )

    if tolerance_bound:
        with pytest.raises(B6Reached):
            execute()
    else:
        result = execute()
        assert all(column.status == "UNRESOLVED" for column in result.columns)

    assert populations and populations[-1].positive
    assert populations[-1].expected_applicable_contributors == populations[-1].qualified_contributors
    assert generations
    assert len(readiness_rows) == 2
    focus = next(row for row in readiness_rows if row.component_id == vertical.C1)
    # The limited I2/I3 owner is deliberately unable to prove global uncracked
    # state; retaining its result must not invent a canonical readiness blocker.
    assert focus.stability_stiffness_basis.status == STATUS_BLOCKED_GLOBAL_PROOF
    assert not focus.stability_stiffness_basis.proves_uncracked
    assert STATUS_BLOCKED_GLOBAL_PROOF not in focus.blocked_items
    if tolerance_bound:
        assert focus.status == "READY"
        assert focus.analysis_basis_status == "MATCH"
        assert focus.blocked_items == ()
        assert REVIEWED_TOLERANCE.source_ref in focus.source_refs
        assert len(b6_calls) == 1
    else:
        assert focus.status == "UNRESOLVED"
        assert focus.blocked_items == ("A17:REVIEWED_STORY_TRANSLATION_TOLERANCE_NOT_BOUND",)
        assert b6_calls == []
    unresolved = next(row for row in readiness_rows if row.component_id == vertical.C2)
    assert unresolved.status == "UNRESOLVED"
    assert any(item.startswith("A18:") for item in unresolved.blocked_items)
