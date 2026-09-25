from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_public_a5_second_order as subject
from tbdy_engine.etabs.source_units import EtabsSourceUnitError


@pytest.mark.parametrize(
    ("code", "expected"),
    ((6, "m"), (4, "mm")),
)
def test_reviewed_displacement_unit_comes_from_verified_snapshot(monkeypatch, code, expected):
    monkeypatch.setattr(
        subject,
        "read_verified_unit_snapshot",
        lambda _session: SimpleNamespace(
            present_length_unit=code,
        ),
    )
    assert (
        subject._reviewed_displacement_unit_from_session(
            object()
        )
        == expected
    )


def test_unreviewed_length_unit_fails_closed(monkeypatch):
    monkeypatch.setattr(
        subject,
        "read_verified_unit_snapshot",
        lambda _session: SimpleNamespace(
            present_length_unit=999,
        ),
    )
    with pytest.raises(EtabsSourceUnitError):
        subject._reviewed_displacement_unit_from_session(
            object()
        )



def test_a18_oapi_local_axis_supplements_missing_table_assignment():
    from types import SimpleNamespace

    import tbdy_engine.application.column_a18_end_restraint as a18

    member = SimpleNamespace(
        local_axis_explicit=False,
        local_axis_row=None,
        local_axis_angle_deg=None,
    )

    fact = a18.A18FrameLocalAxisEvidence(
        frame_name="211",
        angle_degrees=0.0,
        advanced=False,
        source_refs=(
            "ETABS:FrameObj.GetLocalAxes:211",
        ),
    )

    angle, refs = a18._local_axis(
        member,
        "211",
        {
            "211": fact,
        },
    )

    assert angle == 0.0

    assert (
        "ETABS:FrameObj.GetLocalAxes:211"
        in refs
    )

    assert (
        "strict-topology:"
        "frame-local-axis-table-absent:211"
        in refs
    )


def test_a18_oapi_advanced_local_axis_remains_fail_closed():
    from types import SimpleNamespace

    import tbdy_engine.application.column_a18_end_restraint as a18

    member = SimpleNamespace(
        local_axis_explicit=False,
        local_axis_row=None,
        local_axis_angle_deg=None,
    )

    fact = a18.A18FrameLocalAxisEvidence(
        frame_name="211",
        angle_degrees=0.0,
        advanced=True,
        source_refs=(
            "ETABS:FrameObj.GetLocalAxes:211",
        ),
    )

    try:
        a18._local_axis(
            member,
            "211",
            {
                "211": fact,
            },
        )

    except RuntimeError as exc:
        assert str(exc) == (
            "ADVANCED_LOCAL_AXIS_UNSUPPORTED:211"
        )

    else:
        raise AssertionError(
            "advanced local axis must remain unresolved"
        )


def test_a18_existing_explicit_table_axis_remains_supported_without_oapi_fact():
    from types import SimpleNamespace

    import tbdy_engine.application.column_a18_end_restraint as a18

    member = SimpleNamespace(
        local_axis_explicit=True,
        local_axis_row={
            "Angle": "30",
        },
        local_axis_angle_deg=30.0,
    )

    angle, refs = a18._local_axis(
        member,
        "211",
        {},
    )

    assert angle == 30.0

    assert any(
        "Frame Assignments - Local Axes"
        in ref
        for ref in refs
    )


def test_public_a5_a18_missing_axis_supplements_are_cached(
    monkeypatch,
):
    from types import SimpleNamespace

    import tbdy_engine.application.column_public_a5 as public_a5

    target = SimpleNamespace(
        unique_name="211",
        joint_bottom="919",
        joint_top="1045",
        local_axis_explicit=False,
        local_axis_row=None,
        local_axis_angle_deg=None,
        beams_at_bottom=(),
        beams_at_top=(
            SimpleNamespace(
                beam_unique_name="768",
                local_axis_explicit=False,
                local_axis_row=None,
                local_axis_angle_deg=None,
            ),
        ),
    )

    connected = SimpleNamespace(
        unique_name="128",
        joint_bottom="1045",
        joint_top="2000",
        local_axis_explicit=False,
        local_axis_row=None,
        local_axis_angle_deg=None,
    )

    topology = SimpleNamespace(
        columns=(
            target,
            connected,
        ),
    )

    calls = []

    def read(
        session,
        frame_name,
    ):
        calls.append(
            (
                session,
                frame_name,
            )
        )

        return (
            0.0,
            False,
            [
                0.0,
                False,
                0,
            ],
        )

    monkeypatch.setattr(
        public_a5,
        "read_frame_local_axes_from_session",
        read,
    )

    context = SimpleNamespace(
        verified_session="SESSION",
        session_provenance_ref=(
            "session-provenance:test"
        ),
    )

    cache = {}

    first = (
        public_a5
        ._capture_a18_frame_local_axis_supplements(
            context=context,
            target_column=target,
            topology=topology,
            cache=cache,
        )
    )

    second = (
        public_a5
        ._capture_a18_frame_local_axis_supplements(
            context=context,
            target_column=target,
            topology=topology,
            cache=cache,
        )
    )

    assert set(first) == {
        "128",
        "211",
        "768",
    }

    assert set(second) == set(first)

    assert sorted(
        name
        for _session, name
        in calls
    ) == [
        "128",
        "211",
        "768",
    ]

    assert all(
        fact.angle_degrees == 0.0
        and fact.advanced is False
        for fact in first.values()
    )



def test_a17_route_c_static_scope_unions_source_bound_response_cases(
    monkeypatch,
):
    from types import SimpleNamespace

    import tbdy_engine.application.column_public_a5_second_order as second_order

    observed = {}

    def fake_route_c(*, session, static_case_names):
        observed["static_case_names"] = tuple(static_case_names)

        return SimpleNamespace(
            source_refs=("route-c:test",),
            blockers=("TEST_STOP",),
            ready=False,
        )

    monkeypatch.setattr(
        second_order,
        "resolve_route_c_source_bound_directions",
        fake_route_c,
    )

    a18 = tuple(
        SimpleNamespace(
            disposition=second_order.A18_READY,
            source_refs=(),
            end_tag=end,
            local_bending_axis=axis,
        )
        for end, axis in (
            ("BOTTOM", "M2"),
            ("BOTTOM", "M3"),
            ("TOP", "M2"),
            ("TOP", "M3"),
        )
    )

    free_length = SimpleNamespace(
        source_refs=("free-length:test",),
        resolved=True,
    )

    design_states = (
        SimpleNamespace(
            output_case="LC_DL",
            case_type="LinStatic",
        ),
    )

    second_order.build_public_a5_canonical_second_order_payload(
        component_id="+4.50:C10:188",
        session=object(),
        topology=None,
        target_column=None,
        frame_population=None,
        flattened_combos=(),
        constituent_case_demands=design_states,
        a18_rows=a18,
        free_length=free_length,
        analysis_execution=None,
        qualified_response_static_case_names=(
            "LC_EQX",
            "LC_EQY",
        ),
        qualified_response_static_source_refs=(
            "qualified-response-static:test",
        ),
    )

    assert observed["static_case_names"] == (
        "LC_DL",
        "LC_EQX",
        "LC_EQY",
    )
