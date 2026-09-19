from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.providers.etabs_frame_eq713_population_provider as subject


def _beam_row(
    name="B200",
    *,
    point_i="P1",
    point_j="P2",
):
    return {
        "UniqueName": name,
        "BeamBay": f"LBL-{name}",
        "Story": "Story1",
        "UniquePtI": point_i,
        "UniquePtJ": point_j,
    }


def _point(name, x, y, z):
    return {
        "UniqueName": name,
        "Story": "Story1",
        "X": x,
        "Y": y,
        "Z": z,
    }


def test_supported_beam_not_attached_to_column_gets_exact_endpoint_mechanics():
    facts = subject._build_supported_beam_mechanics(
        supported_frame_names=("B200",),
        beam_connectivity_rows=(_beam_row(),),
        point_rows=(
            _point("P1", 1.0, 2.0, 3.0),
            _point("P2", 4.0, 6.0, 3.5),
        ),
        local_axis_rows=(),
        source_refs=("session:verified", "scratch:owned"),
    )

    fact = facts["B200"]
    assert fact.member_role == "BEAM"
    assert fact.point_i_unique_name == "P1"
    assert fact.point_j_unique_name == "P2"
    assert fact.point_i_coord_m == (1.0, 2.0, 3.0)
    assert fact.point_j_coord_m == (4.0, 6.0, 3.5)
    assert fact.member_axis_vector == (3.0, 4.0, 0.5)
    assert fact.local_axis_explicit is False
    assert fact.local_axis_angle_degrees is None
    assert any(
        "FULL_TABLE_NO_EXPLICIT_ROW:B200" in ref
        for ref in fact.source_refs
    )


def test_explicit_local_axis_is_preserved_exactly():
    facts = subject._build_supported_beam_mechanics(
        supported_frame_names=("B200",),
        beam_connectivity_rows=(_beam_row(),),
        point_rows=(
            _point("P1", 0.0, 0.0, 0.0),
            _point("P2", 5.0, 0.0, 0.0),
        ),
        local_axis_rows=(
            {"UniqueName": "B200", "Angle": 17.5},
        ),
        source_refs=("session:verified",),
    )

    fact = facts["B200"]
    assert fact.local_axis_explicit is True
    assert fact.local_axis_angle_degrees == 17.5


@pytest.mark.parametrize(
    "point_rows",
    (
        (_point("P1", 0.0, 0.0, 0.0),),
        (
            _point("P1", 0.0, 0.0, 0.0),
            _point("P1", 1.0, 0.0, 0.0),
            _point("P2", 2.0, 0.0, 0.0),
        ),
    ),
)
def test_missing_or_duplicate_endpoint_point_identity_fails_closed(point_rows):
    with pytest.raises(subject.EtabsFrameEq713PopulationError):
        subject._build_supported_beam_mechanics(
            supported_frame_names=("B200",),
            beam_connectivity_rows=(_beam_row(),),
            point_rows=point_rows,
            local_axis_rows=(),
            source_refs=("session:verified",),
        )


def test_zero_length_beam_vector_fails_closed():
    with pytest.raises(
        subject.EtabsFrameEq713PopulationError,
        match="zero-length",
    ):
        subject._build_supported_beam_mechanics(
            supported_frame_names=("B200",),
            beam_connectivity_rows=(_beam_row(),),
            point_rows=(
                _point("P1", 1.0, 2.0, 3.0),
                _point("P2", 1.0, 2.0, 3.0),
            ),
            local_axis_rows=(),
            source_refs=("session:verified",),
        )


def test_duplicate_local_axis_identity_fails_closed():
    with pytest.raises(
        subject.EtabsFrameEq713PopulationError,
        match="duplicate",
    ):
        subject._build_supported_beam_mechanics(
            supported_frame_names=("B200",),
            beam_connectivity_rows=(_beam_row(),),
            point_rows=(
                _point("P1", 0.0, 0.0, 0.0),
                _point("P2", 1.0, 0.0, 0.0),
            ),
            local_axis_rows=(
                {"UniqueName": "B200", "Angle": 0.0},
                {"UniqueName": "B200", "Angle": 10.0},
            ),
            source_refs=("session:verified",),
        )


def test_unsupported_steel_frame_does_not_receive_beam_mechanics_or_rc_fact():
    class _Topology:
        columns = ()

    original = subject.StrictColumnTopologyBundle
    subject.StrictColumnTopologyBundle = _Topology
    try:
        supported, out_of_slice = subject._build_frame_scope_partition(
            expected_frame_names=("STEEL1",),
            topology=_Topology(),
            column_connectivity_rows=(),
            beam_connectivity_rows=({"UniqueName": "STEEL1"},),
            assignment_rows=(
                {"UniqueName": "STEEL1", "SectProp": "HE160A"},
            ),
            section_summary_rows=(
                {
                    "Name": "HE160A",
                    "Shape": "Steel I/Wide Flange",
                    "Material": "S355",
                },
            ),
            rectangular_rows=(),
            concrete_rows=(),
            source_refs=("session:verified",),
        )
    finally:
        subject.StrictColumnTopologyBundle = original

    assert supported == ()
    assert tuple(row.frame_name for row in out_of_slice) == ("STEEL1",)
    assert out_of_slice[0].scope_status is (
        subject.FrameEq713ScopeStatus.OUT_OF_SLICE_UNSUPPORTED_SECTION_OR_MATERIAL
    )
    mechanics = subject._build_supported_beam_mechanics(
        supported_frame_names=supported,
        beam_connectivity_rows=(_beam_row("STEEL1"),),
        point_rows=(
            _point("P1", 0.0, 0.0, 0.0),
            _point("P2", 1.0, 0.0, 0.0),
        ),
        local_axis_rows=(),
        source_refs=("session:verified",),
    )
    assert mechanics == {}


def test_residual_non_column_non_beam_identities_remain_out_of_slice():
    class _Topology:
        columns = ()

    original = subject.StrictColumnTopologyBundle
    subject.StrictColumnTopologyBundle = _Topology
    try:
        supported, out_of_slice = subject._build_frame_scope_partition(
            expected_frame_names=("NULL1", "BRACE1"),
            topology=_Topology(),
            column_connectivity_rows=(),
            beam_connectivity_rows=(),
            assignment_rows=(
                {"UniqueName": "BRACE1", "SectProp": "R1"},
            ),
            section_summary_rows=(
                {
                    "Name": "R1",
                    "Shape": "Concrete Rectangular",
                    "Material": "C35",
                },
            ),
            rectangular_rows=({"Name": "R1"},),
            concrete_rows=({"Material": "C35"},),
            source_refs=("session:verified",),
        )
    finally:
        subject.StrictColumnTopologyBundle = original

    assert supported == ()
    assert tuple(row.frame_name for row in out_of_slice) == (
        "BRACE1",
        "NULL1",
    )
    by_name = {row.frame_name: row for row in out_of_slice}
    assert by_name["BRACE1"].scope_status is (
        subject.FrameEq713ScopeStatus.OUT_OF_SLICE_ROLE_UNRESOLVED
    )
    assert by_name["NULL1"].scope_status is (
        subject.FrameEq713ScopeStatus.OUT_OF_SLICE_FACTUAL_SCOPE_UNRESOLVED
    )


def test_998_equivalent_denominator_preserves_918_supported_and_80_out_of_slice():
    supported = tuple(
        SimpleNamespace(frame_name=f"SUPPORTED-{index:03d}")
        for index in range(918)
    )
    residual = tuple(
        subject.FrameEq713ScopeFact(
            frame_name=f"RESIDUAL-{index:03d}",
            assigned_section_name=None,
            shape=None,
            material_name=None,
            member_role=None,
            scope_status=subject.FrameEq713ScopeStatus.OUT_OF_SLICE_ROLE_UNRESOLVED,
            reason=f"residual {index}",
            source_refs=(f"scope:residual:{index}",),
        )
        for index in range(72)
    )
    steel = tuple(
        subject.FrameEq713ScopeFact(
            frame_name=f"STEEL-{index:03d}",
            assigned_section_name=f"HE-{index}",
            shape="Steel I/Wide Flange",
            material_name="S355",
            member_role="BEAM",
            scope_status=(
                subject.FrameEq713ScopeStatus.OUT_OF_SLICE_UNSUPPORTED_SECTION_OR_MATERIAL
            ),
            reason=f"steel {index}",
            source_refs=(f"scope:steel:{index}",),
        )
        for index in range(8)
    )
    expected = tuple(
        row.frame_name
        for row in (*supported, *residual, *steel)
    )

    population = subject.FrameEq713FactualPopulation(
        expected_frame_names=expected,
        rows=supported,
        out_of_slice_rows=(*residual, *steel),
        source_refs=("population:998",),
    )

    assert len(population.expected_frame_names) == 998
    assert len(population.supported_rows) == 918
    assert len(population.out_of_slice_rows) == 80
    assert len(
        {
            row.frame_name
            for row in population.out_of_slice_rows
            if row.frame_name.startswith("RESIDUAL-")
        }
    ) == 72
