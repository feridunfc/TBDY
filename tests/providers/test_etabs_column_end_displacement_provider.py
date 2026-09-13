from types import SimpleNamespace

import pytest

import tbdy_engine.providers.etabs_column_end_displacement_provider as provider
from tbdy_engine.design.columns.stability_combo_basis import StabilityComboCandidate
from tbdy_engine.design.columns.stability_output_state import (
    StabilityActionDirectionBinding,
    qualify_signed_linear_add_stability_output,
)
from tbdy_engine.etabs.oapi.joint_displacement_results import (
    JointDisplacementResultFact,
    JointDisplacementResultRow,
)


def _state(direction="X"):
    candidate = StabilityComboCandidate(
        combo_name="COMB_GQE_X",
        load_basis="TS500_FD_1.0G_1.0Q_1.0E",
        horizontal_action_role="E",
        horizontal_case_name="EX",
        horizontal_scale_factor=1.0,
        role_coefficients=(("E", 1.0), ("G", 1.0), ("Q", 1.0)),
        constituent_case_names=("G", "Q", "EX"),
        source_refs=("combo-definition:COMB_GQE_X",),
    )
    return qualify_signed_linear_add_stability_output(
        candidate,
        direction_binding=StabilityActionDirectionBinding(
            case_name="EX",
            global_direction=direction,
            source_refs=(f"factual-direction:EX:{direction}",),
        ),
        analysis_result_ref="analysis-result:abc",
        execution_proof_ref="execution-proof:def",
    )


def _joint_fact(point, output, u1, u2, *, step_type="", step_number=0.0):
    return JointDisplacementResultFact(
        point_object=point,
        output_name=output,
        output_kind="combo",
        rows=(
            JointDisplacementResultRow(
                point_object=point,
                element_name=f"ELM-{point}",
                load_case=output,
                step_type=step_type,
                step_number=step_number,
                u1=u1,
                u2=u2,
                u3=0.0,
                r1=0.0,
                r2=0.0,
                r3=0.0,
            ),
        ),
        return_code=0,
    )


def _column(uid, component, story, bottom, top, z0, z1):
    return SimpleNamespace(
        component_id=component,
        story=story,
        unique_name=uid,
        joint_bottom=bottom,
        joint_top=top,
        bottom_coord_m=(0.0, 0.0, z0),
        top_coord_m=(0.0, 0.0, z1),
        offset_bottom_m=0.10,
        offset_top_m=0.15,
    )


def test_population_covers_every_story_column_and_preserves_b5_state(monkeypatch):
    class FakeSession:
        pass

    class FakeTopology:
        def __init__(self):
            self.columns = (
                _column("U1", "S1:C1:U1", "S1", "P1", "P2", 0.0, 3.0),
                _column("U2", "S1:C2:U2", "S1", "P3", "P4", 0.0, 3.0),
                _column("U3", "S2:C3:U3", "S2", "P5", "P6", 3.0, 6.0),
            )

    values = {
        "P1": (0.001, 0.002),
        "P2": (0.011, 0.005),
        "P3": (-0.002, 0.001),
        "P4": (0.008, 0.004),
    }
    calls = []

    def read(_session, *, point_object, output_name, output_kind, timeout_seconds):
        calls.append((point_object, output_name, output_kind, timeout_seconds))
        u1, u2 = values[point_object]
        return _joint_fact(point_object, output_name, u1, u2)

    monkeypatch.setattr(provider, "EtabsVerifiedSession", FakeSession)
    monkeypatch.setattr(provider, "StrictColumnTopologyBundle", FakeTopology)
    monkeypatch.setattr(provider, "read_joint_displ_from_session", read)

    result = provider.capture_column_end_displacement_population_from_session(
        FakeSession(),
        topology=FakeTopology(),
        story="S1",
        output_state=_state("X"),
        reviewed_displacement_unit="m",
        timeout_seconds=7.0,
    )

    assert tuple(row.column_unique_name for row in result.rows) == ("U1", "U2")
    assert result.expected_column_unique_names == ("U1", "U2")
    assert tuple(row.delta_column_x_mm for row in result.rows) == pytest.approx((10.0, 10.0))
    assert tuple(row.delta_column_y_mm for row in result.rows) == pytest.approx((3.0, 3.0))
    assert {row.analysis_result_ref for row in result.rows} == {"analysis-result:abc"}
    assert {row.execution_proof_ref for row in result.rows} == {"execution-proof:def"}
    assert {row.output_state_ref for row in result.rows} == {result.output_state_ref}
    assert {row.global_direction for row in result.rows} == {"X"}
    assert result.story_bottom_z_mm == pytest.approx(0.0)
    assert result.story_top_z_mm == pytest.approx(3000.0)
    assert all(row.displacement_location_semantics == provider.POINT_OBJECT_BOUNDARY_SEMANTICS for row in result.rows)
    assert calls == [
        ("P1", "COMB_GQE_X", "combo", 7.0),
        ("P2", "COMB_GQE_X", "combo", 7.0),
        ("P3", "COMB_GQE_X", "combo", 7.0),
        ("P4", "COMB_GQE_X", "combo", 7.0),
    ]


def test_population_rejects_multiple_joint_rows(monkeypatch):
    class FakeSession:
        pass

    class FakeTopology:
        def __init__(self):
            self.columns = (_column("U1", "S1:C1:U1", "S1", "P1", "P2", 0.0, 3.0),)

    def read(_session, *, point_object, output_name, output_kind, timeout_seconds):
        fact = _joint_fact(point_object, output_name, 0.0, 0.0)
        row = fact.rows[0]
        return JointDisplacementResultFact(
            point_object=point_object,
            output_name=output_name,
            output_kind=output_kind,
            rows=(row, row),
            return_code=0,
        )

    monkeypatch.setattr(provider, "EtabsVerifiedSession", FakeSession)
    monkeypatch.setattr(provider, "StrictColumnTopologyBundle", FakeTopology)
    monkeypatch.setattr(provider, "read_joint_displ_from_session", read)

    with pytest.raises(provider.ColumnEndDisplacementProviderError, match="exactly one exact row"):
        provider.capture_column_end_displacement_population_from_session(
            FakeSession(),
            topology=FakeTopology(),
            story="S1",
            output_state=_state(),
            reviewed_displacement_unit="m",
        )


def test_population_rejects_envelope_like_step_state(monkeypatch):
    class FakeSession:
        pass

    class FakeTopology:
        def __init__(self):
            self.columns = (_column("U1", "S1:C1:U1", "S1", "P1", "P2", 0.0, 3.0),)

    def read(_session, *, point_object, output_name, output_kind, timeout_seconds):
        return _joint_fact(point_object, output_name, 0.0, 0.0, step_type="Max")

    monkeypatch.setattr(provider, "EtabsVerifiedSession", FakeSession)
    monkeypatch.setattr(provider, "StrictColumnTopologyBundle", FakeTopology)
    monkeypatch.setattr(provider, "read_joint_displ_from_session", read)

    with pytest.raises(provider.ColumnEndDisplacementProviderError, match="StepType"):
        provider.capture_column_end_displacement_population_from_session(
            FakeSession(),
            topology=FakeTopology(),
            story="S1",
            output_state=_state(),
            reviewed_displacement_unit="m",
        )


def test_population_rejects_noncommon_story_boundaries(monkeypatch):
    class FakeSession:
        pass

    class FakeTopology:
        def __init__(self):
            self.columns = (
                _column("U1", "S1:C1:U1", "S1", "P1", "P2", 0.0, 3.0),
                _column("U2", "S1:C2:U2", "S1", "P3", "P4", 0.1, 3.0),
            )

    monkeypatch.setattr(provider, "EtabsVerifiedSession", FakeSession)
    monkeypatch.setattr(provider, "StrictColumnTopologyBundle", FakeTopology)
    with pytest.raises(provider.ColumnEndDisplacementProviderError, match="bottom-joint elevation"):
        provider.capture_column_end_displacement_population_from_session(
            FakeSession(),
            topology=FakeTopology(),
            story="S1",
            output_state=_state(),
            reviewed_displacement_unit="m",
        )


def test_population_rejects_unreviewed_displacement_unit(monkeypatch):
    class FakeSession:
        pass

    class FakeTopology:
        columns = ()

    monkeypatch.setattr(provider, "EtabsVerifiedSession", FakeSession)
    monkeypatch.setattr(provider, "StrictColumnTopologyBundle", FakeTopology)
    with pytest.raises(provider.ColumnEndDisplacementProviderError, match="explicitly 'm' or 'mm'"):
        provider.capture_column_end_displacement_population_from_session(
            FakeSession(),
            topology=FakeTopology(),
            story="S1",
            output_state=_state(),
            reviewed_displacement_unit="cm",
        )
