from __future__ import annotations

from decimal import Decimal
import inspect
from types import SimpleNamespace

import pytest

from tbdy_engine.etabs.source_units import EtabsLengthUnit
from tbdy_engine.features.column_concrete_design_evidence import (
    ColumnDesignSectionEvidence,
    ColumnTopologyEvidenceEnvelope,
)
from tbdy_engine.features.column_shear_topology import (
    ColumnTopologyEvidence,
    StrictColumnTopologyBundle,
)
from tbdy_engine.providers.etabs_concrete_design_section_provider import (
    CapturedConcreteColumnDesignSection,
    ConcreteColumnDesignSectionPopulation,
)
from tbdy_engine.providers.etabs_concrete_column_design_result_provider import (
    EtabsConcreteColumnDesignResultProviderError,
    capture_concrete_column_design_results,
    decode_summary_results_column,
)
import tbdy_engine.providers.etabs_concrete_column_design_result_provider as subject


MODEL = "model:fixture"
EPOCH = "epoch:fixture"


class _DesignConcrete:
    def __init__(self, raw_by_name):
        self.raw_by_name = dict(raw_by_name)
        self.calls: list[str] = []

    def GetSummaryResultsColumn(self, frame_name):
        self.calls.append(frame_name)
        value = self.raw_by_name[frame_name]
        if isinstance(value, Exception):
            raise value
        return value


class _Sap:
    def __init__(self, raw_by_name):
        self.DesignConcrete = _DesignConcrete(raw_by_name)


def _snapshot(*, length_unit=6, present_units=6, database_units=6):
    return SimpleNamespace(
        present_units_api="GetPresentUnits_2",
        database_units_api="GetDatabaseUnits_2",
        present_units=present_units,
        database_units=database_units,
        present_force_unit=4,
        present_length_unit=length_unit,
        present_temperature_unit=2,
        database_force_unit=4,
        database_length_unit=length_unit,
        database_temperature_unit=2,
    )


def _column(uid: str, label: str, *, story="Story1", section="SEC_A", x=0.0):
    return ColumnTopologyEvidence(
        unique_name=uid,
        column_label=label,
        story=story,
        section=section,
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
        assignment_row={"UniqueName": uid, "SectProp": section},
        end_offset_row={"UniqueName": uid},
        section_row={"Name": section},
        local_axis_row={"UniqueName": uid},
    )


def _topology(*columns):
    bundle = StrictColumnTopologyBundle(
        columns=tuple(columns),
        point_count=2 * len(columns),
        beam_count=0,
        supported_rc_beam_count=0,
        unsupported_beam_count=0,
        reviewed_length_unit="m",
    )
    return ColumnTopologyEvidenceEnvelope(
        topology=bundle,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        source_refs=("topology:fixture",),
    )


def _design_sections(topology, *, assigned_override=None):
    rows = []
    for column in topology.topology.columns:
        assigned = column.section if assigned_override is None else assigned_override.get(
            column.unique_name, column.section
        )
        evidence = ColumnDesignSectionEvidence(
            frame_name=column.unique_name,
            design_section=f"DESIGN_{column.section}",
            model_fingerprint=MODEL,
            evidence_epoch_id=EPOCH,
            source_api="DesignConcrete.GetDesignSection",
            source_ref=f"section:{column.unique_name}",
        )
        rows.append(
            CapturedConcreteColumnDesignSection(
                component_id=column.component_id,
                unique_name=column.unique_name,
                story=column.story,
                label=column.column_label,
                assigned_section=assigned,
                design_section_evidence=evidence,
                model_fingerprint=MODEL,
                evidence_epoch_id=EPOCH,
                source_refs=(f"section-row:{column.unique_name}",),
            )
        )
    return ConcreteColumnDesignSectionPopulation(
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        expected_component_ids=tuple(column.component_id for column in topology.topology.columns),
        expected_frame_names=tuple(column.unique_name for column in topology.topology.columns),
        rows=tuple(rows),
        topology_source_refs=topology.source_refs,
    )


def _row(**overrides):
    row = {
        "FrameName": None,
        "MyOption": 2,
        "Location": 1.25,
        "PMMCombo": "ULS",
        "PMMArea": 0.0064,
        "PMMRatio": 0.75,
        "VMajorCombo": "ULS",
        "AVMajor": 0.0002,
        "VMinorCombo": "ULS",
        "AVMinor": 0.0003,
        "ErrorSummary": "",
        "WarningSummary": "",
    }
    row.update(overrides)
    return row


def _raw(frame_name: str, rows, *, ret=0):
    rows = tuple(rows)
    arrays = []
    for key in (
        "FrameName",
        "MyOption",
        "Location",
        "PMMCombo",
        "PMMArea",
        "PMMRatio",
        "VMajorCombo",
        "AVMajor",
        "VMinorCombo",
        "AVMinor",
        "ErrorSummary",
        "WarningSummary",
    ):
        arrays.append(
            tuple(
                frame_name if key == "FrameName" and row[key] is None else row[key]
                for row in rows
            )
        )
    return [len(rows), *arrays, ret]


def _decode(raw, *, source_length_unit=EtabsLengthUnit.M, frame_name="U1"):
    column = _column(frame_name, "C1")
    return decode_summary_results_column(
        raw,
        component_id=column.component_id,
        unique_name=column.unique_name,
        story=column.story,
        label=column.column_label,
        assigned_section=column.section,
        design_section="DESIGN_SEC_A",
        source_length_unit=source_length_unit,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        source_refs=("source:fixture",),
    )


def test_happy_path_captures_complete_canonical_population_and_converts_m_to_mm(monkeypatch):
    c1 = _column("U1", "C1", x=0.0)
    c2 = _column("U2", "C2", x=2.0)
    topology = _topology(c2, c1)
    sections = _design_sections(topology)
    sap = _Sap(
        {
            "U1": _raw(
                "U1",
                (
                    _row(Location=1.25, PMMArea=0.0064, PMMCombo="ULS"),
                    _row(MyOption=1, Location=2.0, PMMArea=0.0075, PMMCombo="SERVICE"),
                ),
            ),
            "U2": _raw("U2", (_row(Location=0.5, PMMArea=0.0042, PMMCombo="ULS2"),)),
        }
    )
    snapshot = _snapshot(length_unit=6)
    monkeypatch.setattr(subject, "read_etabs_unit_snapshot", lambda _sap: snapshot)

    population = capture_concrete_column_design_results(
        sap,
        topology=topology,
        design_sections=sections,
        session_provenance_ref="session:fixture",
    )

    assert population.capture_complete
    assert population.expected_component_ids == tuple(sorted((c1.component_id, c2.component_id)))
    assert population.attempted_component_ids == population.expected_component_ids
    assert population.captured_component_ids == population.expected_component_ids
    assert population.reported_result_row_count == 3
    assert len(population.rows) == 3
    assert len(population.design_rows) == 2
    assert sap.DesignConcrete.calls == ["U1", "U2"]

    row = next(item for item in population.rows if item.unique_name == "U1" and item.my_option == 2)
    assert row.location_mm == Decimal("1250")
    assert row.pmm_area_mm2 == Decimal("6400")
    assert row.pmm_combo == "ULS"
    assert row.assigned_section == "SEC_A"
    assert row.design_section == "DESIGN_SEC_A"
    assert row.source_row_id.startswith("column-design-result-row:sha256:")
    assert any("DesignConcrete.GetSummaryResultsColumn:U1:row:" in ref for ref in row.source_refs)


def test_mm_source_units_are_preserved_without_magnitude_guessing(monkeypatch):
    column = _column("U1", "C1")
    topology = _topology(column)
    sections = _design_sections(topology)
    sap = _Sap({"U1": _raw("U1", (_row(Location=1250, PMMArea=6400),))})
    snapshot = _snapshot(length_unit=4, present_units=9, database_units=9)
    monkeypatch.setattr(subject, "read_etabs_unit_snapshot", lambda _sap: snapshot)

    population = capture_concrete_column_design_results(
        sap,
        topology=topology,
        design_sections=sections,
        session_provenance_ref="session:fixture",
    )
    row = population.rows[0]
    assert row.location_mm == Decimal("1250")
    assert row.pmm_area_mm2 == Decimal("6400")


def test_live_observed_zero_row_shape_decodes_safely_but_canonical_capture_fails_closed(monkeypatch):
    zero = _raw("U1", ())
    decoded = _decode(zero)
    assert decoded.reported_row_count == 0
    assert decoded.rows == ()

    column = _column("U1", "C1")
    topology = _topology(column)
    sections = _design_sections(topology)
    sap = _Sap({"U1": zero})
    snapshot = _snapshot()
    monkeypatch.setattr(subject, "read_etabs_unit_snapshot", lambda _sap: snapshot)

    with pytest.raises(
        EtabsConcreteColumnDesignResultProviderError,
        match="has no existing concrete-design result rows",
    ):
        capture_concrete_column_design_results(
            sap,
            topology=topology,
            design_sections=sections,
            session_provenance_ref="session:fixture",
        )


def test_decoder_requires_exact_14_slot_shape():
    with pytest.raises(EtabsConcreteColumnDesignResultProviderError, match="expected 14 values"):
        _decode([0] * 13)


def test_decoder_requires_equal_array_lengths():
    raw = _raw("U1", (_row(),))
    raw[5] = ()
    with pytest.raises(EtabsConcreteColumnDesignResultProviderError, match="array lengths differ"):
        _decode(raw)


def test_decoder_requires_exact_requested_frame_name():
    raw = _raw("U1", (_row(FrameName="OTHER"),))
    with pytest.raises(EtabsConcreteColumnDesignResultProviderError, match="does not equal requested canonical frame"):
        _decode(raw)


def test_decoder_rejects_nonzero_return_code():
    with pytest.raises(EtabsConcreteColumnDesignResultProviderError, match="nonzero/invalid code"):
        _decode(_raw("U1", (_row(),), ret=1))


def test_decoder_validates_nonpromoted_arrays_in_the_reviewed_abi():
    raw = _raw("U1", (_row(PMMRatio="NaN"),))
    with pytest.raises(EtabsConcreteColumnDesignResultProviderError, match="PMMRatio must be finite numeric"):
        _decode(raw)


def test_blank_pmm_combo_is_preserved_as_missing_factual_identity():
    decoded = _decode(_raw("U1", (_row(PMMCombo=""),)))
    assert decoded.rows[0].pmm_combo is None


def test_source_unit_change_during_capture_fails_closed(monkeypatch):
    column = _column("U1", "C1")
    topology = _topology(column)
    sections = _design_sections(topology)
    sap = _Sap({"U1": _raw("U1", (_row(),))})
    snapshots = iter((_snapshot(length_unit=6), _snapshot(length_unit=4)))
    monkeypatch.setattr(subject, "read_etabs_unit_snapshot", lambda _sap: next(snapshots))

    with pytest.raises(EtabsConcreteColumnDesignResultProviderError, match="unit provenance changed"):
        capture_concrete_column_design_results(
            sap,
            topology=topology,
            design_sections=sections,
            session_provenance_ref="session:fixture",
        )


def test_unsupported_source_length_unit_fails_closed(monkeypatch):
    column = _column("U1", "C1")
    topology = _topology(column)
    sections = _design_sections(topology)
    sap = _Sap({"U1": _raw("U1", (_row(),))})
    monkeypatch.setattr(subject, "read_etabs_unit_snapshot", lambda _sap: _snapshot(length_unit=999))

    with pytest.raises(EtabsConcreteColumnDesignResultProviderError, match="outside reviewed scope"):
        capture_concrete_column_design_results(
            sap,
            topology=topology,
            design_sections=sections,
            session_provenance_ref="session:fixture",
        )


def test_design_section_must_bind_to_same_canonical_assigned_section(monkeypatch):
    column = _column("U1", "C1", section="SEC_A")
    topology = _topology(column)
    sections = _design_sections(topology, assigned_override={"U1": "OTHER_SEC"})
    sap = _Sap({"U1": _raw("U1", (_row(),))})
    monkeypatch.setattr(subject, "read_etabs_unit_snapshot", lambda _sap: _snapshot())

    with pytest.raises(EtabsConcreteColumnDesignResultProviderError, match="same canonical topology identity"):
        capture_concrete_column_design_results(
            sap,
            topology=topology,
            design_sections=sections,
            session_provenance_ref="session:fixture",
        )


def test_provider_is_deterministic_under_canonical_topology_input_order(monkeypatch):
    c1 = _column("U1", "C1", x=0.0)
    c2 = _column("U2", "C2", x=2.0)
    raw_by_name = {
        "U1": _raw("U1", (_row(Location=1.0, PMMArea=0.004, PMMCombo="A"),)),
        "U2": _raw("U2", (_row(Location=2.0, PMMArea=0.005, PMMCombo="B"),)),
    }
    snapshot = _snapshot()
    monkeypatch.setattr(subject, "read_etabs_unit_snapshot", lambda _sap: snapshot)

    topology_a = _topology(c1, c2)
    topology_b = _topology(c2, c1)
    first = capture_concrete_column_design_results(
        _Sap(raw_by_name),
        topology=topology_a,
        design_sections=_design_sections(topology_a),
        session_provenance_ref="session:fixture",
    )
    second = capture_concrete_column_design_results(
        _Sap(raw_by_name),
        topology=topology_b,
        design_sections=_design_sections(topology_b),
        session_provenance_ref="session:fixture",
    )
    assert first == second


def test_provider_boundary_contains_no_analysis_design_or_selection_mutation():
    source = inspect.getsource(subject)
    for forbidden in (
        "StartDesign",
        "RunAnalysis",
        "SetPresentUnits",
        "SetLoadCasesSelectedForDisplay",
        "SetLoadCombinationsSelectedForDisplay",
        "ENGINE_SELECTED_REBAR",
    ):
        assert forbidden not in source
