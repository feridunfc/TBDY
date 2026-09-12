from __future__ import annotations

from dataclasses import replace

import pytest

from tbdy_engine.etabs.oapi.frame_design_procedure import FrameDesignProcedureFact
from tbdy_engine.features.column_concrete_design_evidence import ColumnTopologyEvidenceEnvelope
from tbdy_engine.features.column_shear_topology import ColumnTopologyEvidence, StrictColumnTopologyBundle
from tbdy_engine.providers.etabs_column_design_procedure_provider import (
    ACCEPTED_CONCRETE_FRAME_DESIGN_PROCEDURE_CODE,
    DESIGN_PROCEDURE_POPULATION_REF_PREFIX,
    EtabsColumnDesignProcedureProviderError,
    build_column_design_procedure_population,
)

MODEL = "model:procedure"
EPOCH = "epoch:procedure"


def _column(uid: str, label: str, *, x: float = 0.0):
    return ColumnTopologyEvidence(
        unique_name=uid,
        column_label=label,
        story="Story1",
        section="SEC_A",
        width_t2_m=0.4,
        depth_t3_m=0.5,
        object_length_m=3.0,
        coordinate_length_m=3.0,
        joint_bottom=f"J:{uid}:B",
        joint_top=f"J:{uid}:T",
        bottom_coord_m=(x, 0.0, 0.0),
        top_coord_m=(x, 0.0, 3.0),
        offset_bottom_m=0.0,
        offset_top_m=0.0,
        analysis_clear_length_candidate_m=3.0,
        local_axis_angle_deg=0.0,
        local_axis_explicit=True,
        beams_at_bottom=(),
        beams_at_top=(),
        connectivity_row={"UniqueName": uid},
        assignment_row={"UniqueName": uid, "SectProp": "SEC_A"},
        end_offset_row={"UniqueName": uid},
        section_row={"Name": "SEC_A"},
        local_axis_row={"UniqueName": uid},
    )


def _topology(*columns):
    return ColumnTopologyEvidenceEnvelope(
        topology=StrictColumnTopologyBundle(
            columns=tuple(columns),
            point_count=2 * len(columns),
            beam_count=0,
            supported_rc_beam_count=0,
            unsupported_beam_count=0,
            reviewed_length_unit="m",
        ),
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        source_refs=("topology:procedure",),
    )


def _fact(name: str, code: int = ACCEPTED_CONCRETE_FRAME_DESIGN_PROCEDURE_CODE):
    return FrameDesignProcedureFact(
        frame_name=name,
        procedure_code=code,
        raw_response=(code, 0),
    )


def test_complete_population_is_order_independent_and_deterministic() -> None:
    c1 = _column("F1", "C1", x=0.0)
    c2 = _column("F2", "C2", x=2.0)
    topology = _topology(c2, c1)

    first = build_column_design_procedure_population(
        topology=topology,
        facts=(_fact("F2"), _fact("F1")),
    )
    second = build_column_design_procedure_population(
        topology=topology,
        facts=(_fact("F1"), _fact("F2")),
    )

    assert first.capture_complete
    assert first.design_procedure_ref == second.design_procedure_ref
    assert first.design_procedure_ref.startswith(DESIGN_PROCEDURE_POPULATION_REF_PREFIX)
    assert tuple(row.frame_name for row in first.rows) == ("F1", "F2")
    assert all(row.procedure_code == 2 for row in first.rows)


@pytest.mark.parametrize("code", [0, 1, 3, 4, 5, 6, 99])
def test_wrong_or_unknown_design_procedure_blocks(code: int) -> None:
    topology = _topology(_column("F1", "C1"))
    with pytest.raises(EtabsColumnDesignProcedureProviderError, match="code 2"):
        build_column_design_procedure_population(
            topology=topology,
            facts=(_fact("F1", code),),
        )


def test_mixed_design_procedure_population_blocks() -> None:
    topology = _topology(_column("F1", "C1"), _column("F2", "C2", x=2.0))
    with pytest.raises(EtabsColumnDesignProcedureProviderError, match="code 2"):
        build_column_design_procedure_population(
            topology=topology,
            facts=(_fact("F1", 2), _fact("F2", 1)),
        )


def test_missing_design_procedure_row_blocks() -> None:
    topology = _topology(_column("F1", "C1"), _column("F2", "C2", x=2.0))
    with pytest.raises(EtabsColumnDesignProcedureProviderError, match="exactly cover"):
        build_column_design_procedure_population(
            topology=topology,
            facts=(_fact("F1"),),
        )


def test_duplicate_frame_fact_blocks() -> None:
    topology = _topology(_column("F1", "C1"))
    with pytest.raises(EtabsColumnDesignProcedureProviderError, match="duplicate"):
        build_column_design_procedure_population(
            topology=topology,
            facts=(_fact("F1"), _fact("F1")),
        )


def test_population_identity_changes_when_factual_population_changes() -> None:
    c1 = _column("F1", "C1")
    one = build_column_design_procedure_population(
        topology=_topology(c1),
        facts=(_fact("F1"),),
    )
    c2 = _column("F2", "C2", x=2.0)
    two = build_column_design_procedure_population(
        topology=_topology(c1, c2),
        facts=(_fact("F1"), _fact("F2")),
    )
    assert one.design_procedure_ref != two.design_procedure_ref


def test_population_identity_is_exact_component_frame_code_payload() -> None:
    column = _column("F1", "C1")
    population = build_column_design_procedure_population(
        topology=_topology(column),
        facts=(_fact("F1"),),
    )
    changed_row = replace(population.rows[0], component_id="Story1:C9:F1")
    changed = replace(
        population,
        expected_component_ids=("Story1:C9:F1",),
        rows=(changed_row,),
        design_procedure_ref="",
    )
    assert changed.design_procedure_ref != population.design_procedure_ref
