from types import SimpleNamespace

import pytest

import tbdy_engine.providers.etabs_column_end_displacement_provider as provider
from tbdy_engine.etabs.oapi.joint_displacement_results import (
    JointDisplacementResultFact,
    JointDisplacementResultRow,
)


def _joint_fact(point, output, u1, u2):
    return JointDisplacementResultFact(
        point_object=point,
        output_name=output,
        output_kind="combo",
        rows=(
            JointDisplacementResultRow(
                point_object=point,
                element_name=f"ELM-{point}",
                load_case=output,
                step_type="",
                step_number=0.0,
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


def test_population_covers_every_story_column_and_preserves_b5_identity(monkeypatch):
    class FakeSession:
        pass

    class FakeTopology:
        def __init__(self):
            self.columns = (
                SimpleNamespace(
                    component_id="S1:C1:U1",
                    story="S1",
                    unique_name="U1",
                    joint_bottom="P1",
                    joint_top="P2",
                ),
                SimpleNamespace(
                    component_id="S1:C2:U2",
                    story="S1",
                    unique_name="U2",
                    joint_bottom="P3",
                    joint_top="P4",
                ),
                SimpleNamespace(
                    component_id="S2:C3:U3",
                    story="S2",
                    unique_name="U3",
                    joint_bottom="P5",
                    joint_top="P6",
                ),
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
        output_name="COMB_GQE_X",
        analysis_result_ref="analysis-result:abc",
        execution_proof_ref="execution-proof:def",
        reviewed_displacement_unit="m",
        timeout_seconds=7.0,
    )

    assert tuple(row.column_unique_name for row in result.rows) == ("U1", "U2")
    assert tuple(row.delta_column_x_mm for row in result.rows) == pytest.approx((10.0, 10.0))
    assert tuple(row.delta_column_y_mm for row in result.rows) == pytest.approx((3.0, 3.0))
    assert {row.analysis_result_ref for row in result.rows} == {"analysis-result:abc"}
    assert {row.execution_proof_ref for row in result.rows} == {"execution-proof:def"}
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
            self.columns = (
                SimpleNamespace(
                    component_id="S1:C1:U1",
                    story="S1",
                    unique_name="U1",
                    joint_bottom="P1",
                    joint_top="P2",
                ),
            )

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
            output_name="COMB_GQE_X",
            analysis_result_ref="analysis-result:abc",
            execution_proof_ref="execution-proof:def",
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
            output_name="COMB_GQE_X",
            analysis_result_ref="analysis-result:abc",
            execution_proof_ref="execution-proof:def",
            reviewed_displacement_unit="cm",
        )
