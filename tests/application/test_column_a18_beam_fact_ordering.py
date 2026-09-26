from types import SimpleNamespace

import tbdy_engine.application.column_a18_end_restraint as a18
from tbdy_engine.design.columns.effective_length import (
    EndRestraintMemberContribution,
)


def _contribution(
    member_id: str,
    role: str,
    *,
    inertia_m4: float = 2.0,
    length_m: float = 2.0,
    factor: float = 1.0,
):
    return EndRestraintMemberContribution(
        member_id=member_id,
        member_role=role,
        inertia_m4=inertia_m4,
        member_length_m=length_m,
        inertia_factor=factor,
        source_refs=(f"test:{member_id}",),
    )


def _beam(
    name: str,
    azimuth: float,
):
    return SimpleNamespace(
        beam_unique_name=name,
        horizontal_azimuth_deg=azimuth,
        connectivity_row={"Length": 4.0},
        joint_unique_name="J",
        connected_end="I",
        other_joint_unique_name=f"{name}-OTHER",
        local_axis_row={"Angle": 0.0},
        local_axis_angle_deg=0.0,
        local_axis_explicit=True,
    )


def _target(
    beams,
):
    return SimpleNamespace(
        component_id="+TEST:C1:C1",
        unique_name="C1",
        joint_bottom="JB",
        joint_top="J",
        beams_at_bottom=(),
        beams_at_top=tuple(beams),
        local_axis_row={"Angle": 0.0},
        local_axis_angle_deg=0.0,
        local_axis_explicit=True,
    )


def _topology(
    target,
):
    return SimpleNamespace(
        columns=(target,),
    )


def _patch_column_contribution(
    monkeypatch,
):
    def fake_column_contribution(
        column,
        fact,
        target_axis_azimuth,
        *,
        local_axis_facts,
    ):
        return _contribution(
            column.unique_name,
            "COLUMN",
        )

    monkeypatch.setattr(
        a18,
        "_column_contribution",
        fake_column_contribution,
    )


def test_parallel_missing_fact_is_ignored_before_relevant_fact_lookup(
    monkeypatch,
):
    parallel = _beam(
        "P",
        90.0,
    )
    relevant = _beam(
        "R",
        0.0,
    )
    target = _target(
        (
            parallel,
            relevant,
        )
    )

    _patch_column_contribution(
        monkeypatch
    )

    called = []

    def fake_beam_contribution(
        beam,
        fact,
        *,
        joint,
        target_axis_azimuth,
        local_axis_facts,
    ):
        called.append(
            beam.beam_unique_name
        )

        return _contribution(
            beam.beam_unique_name,
            "BEAM",
            inertia_m4=4.0,
            length_m=2.0,
            factor=0.5,
        )

    monkeypatch.setattr(
        a18,
        "_beam_contribution",
        fake_beam_contribution,
    )

    row = a18._one(
        target_column=target,
        topology=_topology(
            target
        ),
        facts={
            "C1": object(),
            "R": object(),
            # P intentionally has no FrameEq713 fact.
        },
        end_tag="TOP",
        axis="M3",
        local_axis_facts=None,
    )

    assert row.disposition == a18.A18_READY
    assert row.beam_member_ids == ("R",)
    assert called == ["R"]
    assert not any(
        "MISSING_FRAME_FACT:P"
        in reason
        for reason in row.unresolved_reasons
    )


def test_all_parallel_missing_facts_leave_empty_denominator_not_missing_fact(
    monkeypatch,
):
    target = _target(
        (
            _beam(
                "P1",
                90.0,
            ),
            _beam(
                "P2",
                270.0,
            ),
        )
    )

    _patch_column_contribution(
        monkeypatch
    )

    def forbidden_beam_contribution(
        *args,
        **kwargs,
    ):
        raise AssertionError(
            "parallel beam must never reach factual contribution"
        )

    monkeypatch.setattr(
        a18,
        "_beam_contribution",
        forbidden_beam_contribution,
    )

    row = a18._one(
        target_column=target,
        topology=_topology(
            target
        ),
        facts={
            "C1": object(),
        },
        end_tag="TOP",
        axis="M3",
        local_axis_facts=None,
    )

    assert (
        row.disposition
        == a18.A18_EXPLICIT_UNRESOLVED
    )

    assert row.unresolved_reasons == (
        "END_RESTRAINT_RATIO_UNRESOLVED:"
        "Eq.7.16 beam-restraint denominator "
        "is unresolved/empty",
    )

    assert not any(
        "MISSING_FRAME_FACT"
        in reason
        for reason in row.unresolved_reasons
    )


def test_relevant_missing_beam_fact_remains_explicit_unresolved(
    monkeypatch,
):
    relevant = _beam(
        "R",
        0.0,
    )

    target = _target(
        (relevant,)
    )

    _patch_column_contribution(
        monkeypatch
    )

    row = a18._one(
        target_column=target,
        topology=_topology(
            target
        ),
        facts={
            "C1": object(),
            # R intentionally absent.
        },
        end_tag="TOP",
        axis="M3",
        local_axis_facts=None,
    )

    assert (
        row.disposition
        == a18.A18_EXPLICIT_UNRESOLVED
    )

    assert row.unresolved_reasons == (
        "MISSING_FRAME_FACT:R",
    )


def test_relevant_factual_beam_keeps_existing_contribution_behavior(
    monkeypatch,
):
    relevant = _beam(
        "R",
        0.0,
    )

    fact = SimpleNamespace(
        member_role="BEAM",
    )

    monkeypatch.setattr(
        a18,
        "_inertia_m4",
        lambda fact, member_id, mechanics_axis: (
            4.0,
            (
                f"test:inertia:{member_id}:"
                f"{mechanics_axis}",
            ),
        ),
    )

    monkeypatch.setattr(
        a18,
        "_frame_evidence",
        lambda fact, member_id, role: (
            f"test:frame:{member_id}:{role}",
        ),
    )

    contribution = a18._beam_contribution(
        relevant,
        fact,
        joint="J",
        target_axis_azimuth=90.0,
        local_axis_facts=None,
    )

    assert contribution is not None
    assert contribution.member_id == "R"
    assert contribution.member_role == "BEAM"
    assert contribution.inertia_m4 == 4.0
    assert contribution.member_length_m == 4.0
    assert contribution.inertia_factor == 0.5


def test_ambiguous_geometry_fails_before_frame_fact_requirement(
    monkeypatch,
):
    ambiguous = _beam(
        "A",
        45.0,
    )

    target = _target(
        (ambiguous,)
    )

    _patch_column_contribution(
        monkeypatch
    )

    row = a18._one(
        target_column=target,
        topology=_topology(
            target
        ),
        facts={
            "C1": object(),
            # A intentionally absent: geometry must fail first.
        },
        end_tag="TOP",
        axis="M3",
        local_axis_facts=None,
    )

    assert (
        row.disposition
        == a18.A18_EXPLICIT_UNRESOLVED
    )

    assert row.unresolved_reasons == (
        "AMBIGUOUS_BEAM_BENDING_PLANE:A",
    )

    assert not any(
        "MISSING_FRAME_FACT:A"
        in reason
        for reason in row.unresolved_reasons
    )
