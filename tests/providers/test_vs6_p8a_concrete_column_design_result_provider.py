from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from tbdy_engine.features.column_concrete_design_evidence import ColumnTopologyEvidenceEnvelope
from tbdy_engine.features.column_shear_topology import ColumnTopologyEvidence, StrictColumnTopologyBundle
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.providers.etabs_concrete_design_section_provider import capture_concrete_column_design_sections
from tbdy_engine.providers.etabs_concrete_column_design_result_provider import (
    EtabsConcreteColumnDesignResultProviderError,
    capture_concrete_column_design_results,
)


def _column(unique_name="U1", label="C1", x=0.0):
    return ColumnTopologyEvidence(
        unique_name=unique_name,
        column_label=label,
        story="Story1",
        section="ASSIGNED",
        width_t2_m=0.4,
        depth_t3_m=0.5,
        object_length_m=3.0,
        coordinate_length_m=3.0,
        joint_bottom=f"{unique_name}:P1",
        joint_top=f"{unique_name}:P2",
        bottom_coord_m=(x, 0.0, 0.0),
        top_coord_m=(x, 0.0, 3.0),
        offset_bottom_m=0.0,
        offset_top_m=0.0,
        analysis_clear_length_candidate_m=3.0,
        local_axis_angle_deg=0.0,
        local_axis_explicit=True,
        beams_at_bottom=(),
        beams_at_top=(),
        connectivity_row={"UniqueName": unique_name},
        assignment_row={"UniqueName": unique_name, "Section": "ASSIGNED"},
        end_offset_row={"UniqueName": unique_name},
        section_row={"Name": "ASSIGNED"},
        local_axis_row={"UniqueName": unique_name},
    )


def _topology(*columns):
    cols = columns or (_column(),)
    strict = StrictColumnTopologyBundle(tuple(cols), 2 * len(cols), 0, 0, 0, "m")
    epoch = EvidenceEpoch("epoch:1", "model:1", EvidenceEpochOrigin.FIXTURE_REPLAY)
    return ColumnTopologyEvidenceEnvelope.bind(
        topology=strict,
        epoch=epoch,
        source_refs=("strict-topology:fixture",),
    )


class _DesignSections:
    def __init__(self, names):
        self.names = dict(names)

    def GetDesignSection(self, name):
        return self.names[name], 0


class _DesignResults:
    def __init__(self, rows_by_name):
        self.rows_by_name = dict(rows_by_name)
        self.calls = []
        self.mutations = []

    def GetSummaryResultsColumn(self, name):
        self.calls.append(name)
        return self.rows_by_name[name]

    def StartDesign(self, *args):
        self.mutations.append("StartDesign")
        raise AssertionError("mutation forbidden")


def _raw(name="U1", *, area1=0.004, area2=0.005, combo1="ULS1", combo2="ULS2"):
    return (
        2,
        [name, name],
        [2, 2],
        [0.0, 3.0],
        [combo1, combo2],
        [area1, area2],
        [0.0, 0.0],
        ["", ""],
        [0.0, 0.0],
        ["", ""],
        [0.0, 0.0],
        ["", ""],
        ["", ""],
        0,
    )


class _Sap:
    def __init__(self, design):
        self.DesignConcrete = design
        self.unit_reads = 0

    def GetPresentUnits_2(self):
        self.unit_reads += 1
        return 4, 6, 2, 0  # kN, m, C, ret


def _capture(*columns, raw_by_name=None):
    topology = _topology(*columns)
    sections = capture_concrete_column_design_sections(
        _DesignSections({item.unique_name: "DESIGN" for item in topology.topology.columns}),
        topology=topology,
    )
    raws = raw_by_name or {item.unique_name: _raw(item.unique_name) for item in topology.topology.columns}
    design = _DesignResults(raws)
    sap = _Sap(design)
    population = capture_concrete_column_design_results(
        sap,
        topology=topology,
        design_sections=sections,
        session_provenance_ref="session:fixture",
    )
    return topology, sections, design, sap, population


def test_exact_complete_population_and_all_rows_are_preserved():
    c1 = _column("U1", "C1", 0.0)
    c2 = _column("U2", "C2", 4.0)
    _, _, design, sap, population = _capture(c2, c1)
    assert population.capture_complete
    assert population.expected_component_count == 2
    assert population.attempted_component_count == 2
    assert population.captured_component_count == 2
    assert population.reported_result_row_count == 4
    assert population.captured_result_row_count == 4
    assert population.design_result_row_count == 4
    assert design.calls == ["U1", "U2"]
    assert sap.unit_reads == 2
    assert design.mutations == []


def test_explicit_m_source_unit_is_squared_for_longitudinal_area_without_guessing():
    _, _, _, _, population = _capture()
    component = population.components[0]
    assert component.rows[0].location_mm == 0
    assert component.rows[1].location_mm == 3000
    assert component.rows[0].pmm_area_mm2 == 4000
    assert component.rows[1].pmm_area_mm2 == 5000
    assert population.source_length_unit.value == "m"


def test_duplicate_equal_values_remain_two_distinct_source_rows_by_position():
    raw = _raw(area1=0.004, area2=0.004, combo1="ULS1", combo2="ULS1")
    _, _, _, _, population = _capture(raw_by_name={"U1": raw})
    rows = population.components[0].rows
    assert len(rows) == 2
    assert rows[0].source_row_id != rows[1].source_row_id
    assert rows[0].source_index == 0
    assert rows[1].source_index == 1


def test_wrong_frame_name_fails_closed_instead_of_rebinding_by_label_or_regex():
    raw = list(_raw())
    raw[1] = ["OTHER", "OTHER"]
    with pytest.raises(EtabsConcreteColumnDesignResultProviderError, match="FrameName"):
        _capture(raw_by_name={"U1": tuple(raw)})


def test_reported_and_captured_array_count_mismatch_fails_closed():
    raw = list(_raw())
    raw[1] = ["U1"]
    with pytest.raises(EtabsConcreteColumnDesignResultProviderError, match="reported/captured"):
        _capture(raw_by_name={"U1": tuple(raw)})


def test_zero_result_population_fails_closed():
    raw = (0, [], [], [], [], [], [], [], [], [], [], [], [], 0)
    with pytest.raises(EtabsConcreteColumnDesignResultProviderError, match="no result rows"):
        _capture(raw_by_name={"U1": raw})


def test_capture_signature_has_no_free_form_frame_population_and_source_is_read_only():
    params = inspect.signature(capture_concrete_column_design_results).parameters
    assert tuple(params) == ("sap_model", "topology", "design_sections", "session_provenance_ref")
    source = inspect.getsource(capture_concrete_column_design_results)
    for forbidden in (
        "StartDesign(",
        "RunAnalysis(",
        "SetDesignSection(",
        "SetPresentUnits(",
        "GetNameList(",
    ):
        assert forbidden not in source
