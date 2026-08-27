from __future__ import annotations

import inspect
import subprocess
import sys

import pytest

from tbdy_engine.features.column_concrete_design_evidence import (
    ColumnDesignResultIdentity,
    ColumnDesignSectionEvidence,
    ColumnTopologyEvidenceEnvelope,
    ComponentBindingStatus,
    bind_column_design_result_identity,
)
from tbdy_engine.features.column_shear_topology import (
    ColumnTopologyEvidence,
    StrictColumnTopologyBundle,
)
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.providers.etabs_concrete_design_section_provider import (
    CapturedConcreteColumnDesignSection,
    ConcreteColumnDesignSectionPopulation,
    EtabsConcreteDesignSectionProviderError,
    capture_concrete_column_design_sections,
)


def _column(
    unique_name: str = "C-U1",
    *,
    label: str = "C1",
    story: str = "Story1",
    section: str = "ANALYSIS_SEC",
    x: float = 0.0,
) -> ColumnTopologyEvidence:
    return ColumnTopologyEvidence(
        unique_name=unique_name,
        column_label=label,
        story=story,
        section=section,
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
        assignment_row={"UniqueName": unique_name, "Section": section},
        end_offset_row={"UniqueName": unique_name},
        section_row={"Name": section},
        local_axis_row={"UniqueName": unique_name},
    )


def _envelope(
    *columns: ColumnTopologyEvidence,
    model: str = "model:1",
    epoch_id: str = "e1",
) -> ColumnTopologyEvidenceEnvelope:
    cols = columns or (_column(),)
    topology = StrictColumnTopologyBundle(tuple(cols), 2 * len(cols), 0, 0, 0, "m")
    epoch = EvidenceEpoch(epoch_id, model, EvidenceEpochOrigin.FIXTURE_REPLAY)
    return ColumnTopologyEvidenceEnvelope.bind(
        topology=topology,
        epoch=epoch,
        source_refs=("strict-topology:fixture",),
    )


class _DesignConcrete:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls: list[tuple[str, str]] = []
        self.mutation_calls: list[str] = []

    def GetDesignSection(self, frame_name):
        self.calls.append(("GetDesignSection", frame_name))
        response = self.responses[frame_name]
        if isinstance(response, BaseException):
            raise response
        return response

    def SetDesignSection(self, *args):
        self.mutation_calls.append("SetDesignSection")
        raise AssertionError("mutation forbidden")

    def SetComboStrength(self, *args):
        self.mutation_calls.append("SetComboStrength")
        raise AssertionError("mutation forbidden")

    def StartDesign(self, *args):
        self.mutation_calls.append("StartDesign")
        raise AssertionError("mutation forbidden")


def _capture(
    response=("DESIGN_SEC", 0),
    *,
    envelope: ColumnTopologyEvidenceEnvelope | None = None,
):
    topology = envelope or _envelope()
    fake = _DesignConcrete({item.unique_name: response for item in topology.topology.columns})
    population = capture_concrete_column_design_sections(fake, topology=topology)
    return topology, fake, population


def _result(
    *,
    frame_name="C-U1",
    story="Story1",
    label="C1",
    model="model:1",
    epoch_id="e1",
    result_design_section="DESIGN_SEC",
):
    return ColumnDesignResultIdentity(
        frame_name,
        story,
        label,
        model,
        epoch_id,
        result_design_section,
        (f"result:{frame_name}",),
    )


def test_01_exact_canonical_component_and_get_design_section_is_bindable():
    topology, fake, population = _capture()
    row = population.rows[0]
    binding = bind_column_design_result_identity(
        result=_result(),
        topology=topology,
        design_section=row.design_section_evidence,
    )
    assert binding.status is ComponentBindingStatus.BOUND
    assert binding.component_id == topology.topology.column("C-U1").component_id
    assert binding.unique_name == "C-U1"
    assert binding.story == "Story1"
    assert binding.label == "C1"
    assert binding.assigned_section == "ANALYSIS_SEC"
    assert binding.design_section == "DESIGN_SEC"
    assert fake.calls == [("GetDesignSection", "C-U1")]


def test_02_unknown_frame_name_blocks_component_identity():
    topology, _, population = _capture()
    binding = bind_column_design_result_identity(
        result=_result(frame_name="UNKNOWN"),
        topology=topology,
        design_section=population.rows[0].design_section_evidence,
    )
    assert binding.status is ComponentBindingStatus.BLOCKED_COMPONENT_IDENTITY


def test_03_story_mismatch_blocks_component_identity():
    topology, _, population = _capture()
    binding = bind_column_design_result_identity(
        result=_result(story="OtherStory"),
        topology=topology,
        design_section=population.rows[0].design_section_evidence,
    )
    assert binding.status is ComponentBindingStatus.BLOCKED_COMPONENT_IDENTITY


def test_04_label_mismatch_blocks_component_identity():
    topology, _, population = _capture()
    binding = bind_column_design_result_identity(
        result=_result(label="OtherLabel"),
        topology=topology,
        design_section=population.rows[0].design_section_evidence,
    )
    assert binding.status is ComponentBindingStatus.BLOCKED_COMPONENT_IDENTITY


def test_05_get_design_section_frame_name_mismatch_blocks_component_identity():
    topology = _envelope()
    mismatched = ColumnDesignSectionEvidence(
        "C-U2",
        "DESIGN_SEC",
        "model:1",
        "e1",
        "DesignConcrete.GetDesignSection",
        "CSI:DesignConcrete.GetDesignSection:C-U2:DESIGN_SEC",
    )
    binding = bind_column_design_result_identity(
        result=_result(),
        topology=topology,
        design_section=mismatched,
    )
    assert binding.status is ComponentBindingStatus.BLOCKED_COMPONENT_IDENTITY


def test_06_result_design_section_mismatch_blocks_section_identity():
    topology, _, population = _capture()
    binding = bind_column_design_result_identity(
        result=_result(result_design_section="OTHER_DESIGN_SEC"),
        topology=topology,
        design_section=population.rows[0].design_section_evidence,
    )
    assert binding.status is ComponentBindingStatus.BLOCKED_SECTION_IDENTITY


def test_07_assigned_section_may_differ_from_design_section():
    topology, _, population = _capture()
    row = population.rows[0]
    assert row.assigned_section == "ANALYSIS_SEC"
    assert row.design_section == "DESIGN_SEC"
    binding = bind_column_design_result_identity(
        result=_result(),
        topology=topology,
        design_section=row.design_section_evidence,
    )
    assert binding.status is ComponentBindingStatus.BOUND


def test_08_topology_model_mismatch_blocks_evidence_epoch():
    topology = _envelope(model="model:2")
    design_section = ColumnDesignSectionEvidence(
        "C-U1",
        "DESIGN_SEC",
        "model:1",
        "e1",
        "DesignConcrete.GetDesignSection",
        "section:C-U1",
    )
    binding = bind_column_design_result_identity(
        result=_result(),
        topology=topology,
        design_section=design_section,
    )
    assert binding.status is ComponentBindingStatus.BLOCKED_EVIDENCE_EPOCH


def test_09_design_section_model_mismatch_blocks_evidence_epoch():
    topology = _envelope()
    design_section = ColumnDesignSectionEvidence(
        "C-U1",
        "DESIGN_SEC",
        "model:2",
        "e1",
        "DesignConcrete.GetDesignSection",
        "section:C-U1",
    )
    binding = bind_column_design_result_identity(
        result=_result(),
        topology=topology,
        design_section=design_section,
    )
    assert binding.status is ComponentBindingStatus.BLOCKED_EVIDENCE_EPOCH


def test_10_evidence_epoch_mismatch_blocks_evidence_epoch():
    topology = _envelope()
    design_section = ColumnDesignSectionEvidence(
        "C-U1",
        "DESIGN_SEC",
        "model:1",
        "e2",
        "DesignConcrete.GetDesignSection",
        "section:C-U1",
    )
    binding = bind_column_design_result_identity(
        result=_result(),
        topology=topology,
        design_section=design_section,
    )
    assert binding.status is ComponentBindingStatus.BLOCKED_EVIDENCE_EPOCH


def test_11_missing_get_design_section_result_fails_closed():
    topology = _envelope()
    fake = _DesignConcrete({"C-U1": None})
    with pytest.raises(EtabsConcreteDesignSectionProviderError, match="factual capture failed"):
        capture_concrete_column_design_sections(fake, topology=topology)


def test_12_nonzero_get_design_section_return_fails_closed():
    topology = _envelope()
    fake = _DesignConcrete({"C-U1": ("DESIGN_SEC", 1)})
    with pytest.raises(EtabsConcreteDesignSectionProviderError, match="factual capture failed"):
        capture_concrete_column_design_sections(fake, topology=topology)


def test_13_duplicate_component_evidence_fails_closed():
    topology, _, population = _capture()
    row = population.rows[0]
    with pytest.raises(EtabsConcreteDesignSectionProviderError, match="duplicate captured"):
        ConcreteColumnDesignSectionPopulation(
            model_fingerprint="model:1",
            evidence_epoch_id="e1",
            expected_component_ids=(row.component_id,),
            expected_frame_names=(row.unique_name,),
            rows=(row, row),
            topology_source_refs=("strict-topology:fixture",),
        )


def test_14_capture_is_deterministic_independent_of_topology_input_order():
    c1 = _column("C-U1", label="C1", x=0.0)
    c2 = _column("C-U2", label="C2", x=4.0)
    topo_a = _envelope(c2, c1)
    topo_b = _envelope(c1, c2)
    fake_a = _DesignConcrete({"C-U1": ("DS1", 0), "C-U2": ("DS2", 0)})
    fake_b = _DesignConcrete({"C-U1": ("DS1", 0), "C-U2": ("DS2", 0)})
    pop_a = capture_concrete_column_design_sections(fake_a, topology=topo_a)
    pop_b = capture_concrete_column_design_sections(fake_b, topology=topo_b)
    assert pop_a == pop_b
    assert fake_a.calls == fake_b.calls == [
        ("GetDesignSection", "C-U1"),
        ("GetDesignSection", "C-U2"),
    ]


def test_15_provider_is_fresh_interpreter_import_safe():
    code = (
        "import sys; "
        "import tbdy_engine.providers.etabs_concrete_design_section_provider; "
        "assert 'tbdy_engine.regulatory' not in sys.modules; "
        "assert 'comtypes' not in sys.modules"
    )
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


def test_16_capture_path_is_read_only_and_has_no_free_form_component_population():
    topology = _envelope()
    fake = _DesignConcrete({"C-U1": ("DESIGN_SEC", 0)})
    capture_concrete_column_design_sections(fake, topology=topology)
    assert fake.calls == [("GetDesignSection", "C-U1")]
    assert fake.mutation_calls == []

    parameters = inspect.signature(capture_concrete_column_design_sections).parameters
    assert tuple(parameters) == ("design_concrete", "topology")
    source = inspect.getsource(capture_concrete_column_design_sections)
    for forbidden in (
        "StartDesign",
        "RunAnalysis",
        "SetDesignSection",
        "SetComboStrength",
        "SetPresentUnits",
        "PMMArea",
        "GetSummaryResultsColumn",
    ):
        assert forbidden not in source


def test_population_row_rejects_get_design_section_frame_name_rebinding():
    _, _, population = _capture()
    row = population.rows[0]
    other = ColumnDesignSectionEvidence(
        "C-U2",
        "DESIGN_SEC",
        "model:1",
        "e1",
        "DesignConcrete.GetDesignSection",
        "section:C-U2",
    )
    with pytest.raises(EtabsConcreteDesignSectionProviderError, match="FrameName"):
        CapturedConcreteColumnDesignSection(
            component_id=row.component_id,
            unique_name=row.unique_name,
            story=row.story,
            label=row.label,
            assigned_section=row.assigned_section,
            design_section_evidence=other,
            model_fingerprint=row.model_fingerprint,
            evidence_epoch_id=row.evidence_epoch_id,
            source_refs=("strict-topology:fixture", "section:C-U2"),
        )
