from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import tbdy_engine.providers.etabs_concrete_column_design_result_provider as provider_module
from tbdy_engine.design.columns.column_combo_eligibility_projection import (
    ComboAnalysisBasisBinding,
    ComponentReadinessBinding,
    project_column_combo_eligibility,
)
from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    AnalysisBasisEligibilityEvidence,
    ConcreteDesignComboReconciliation,
)
from tbdy_engine.design.columns.column_design_demand_engine import ColumnComboDefinition
from tbdy_engine.design.columns.column_design_readiness import resolve_column_design_demand_readiness
from tbdy_engine.design.columns.combo_pattern_engine import ComboPatternConstituent
from tbdy_engine.design.columns.rebar_selection import ColumnDemandState
from tbdy_engine.design.columns.slenderness import (
    ColumnSlendernessAxisBasis,
    ColumnSlendernessBasis,
    SWAY_PREVENTED,
)
from tbdy_engine.features.column_concrete_design_evidence import (
    ColumnDesignSectionEvidence,
    ColumnTopologyEvidenceEnvelope,
)
from tbdy_engine.design.columns.column_design_rebar_promotion import (
    ETABS_REQUIRED_REBAR,
    promote_etabs_required_rebar,
)
from tbdy_engine.features.column_shear_topology import (
    ColumnTopologyEvidence,
    StrictColumnTopologyBundle,
)
from tbdy_engine.providers.etabs_concrete_column_design_result_provider import (
    capture_concrete_column_design_results,
)
from tbdy_engine.providers.etabs_concrete_design_section_provider import (
    CapturedConcreteColumnDesignSection,
    ConcreteColumnDesignSectionPopulation,
)

MODEL = "model:p8a-integration"
EPOCH = "epoch:p8a-integration"


class _DesignConcrete:
    def __init__(self, raw_by_name):
        self.raw_by_name = dict(raw_by_name)
        self.calls: list[str] = []

    def GetSummaryResultsColumn(self, frame_name):
        self.calls.append(frame_name)
        return self.raw_by_name[frame_name]


class _Sap:
    def __init__(self, raw_by_name):
        self.DesignConcrete = _DesignConcrete(raw_by_name)


def _snapshot():
    return SimpleNamespace(
        present_units_api="GetPresentUnits_2",
        database_units_api="GetDatabaseUnits_2",
        present_units=6,
        database_units=6,
        present_force_unit=4,
        present_length_unit=6,
        present_temperature_unit=2,
        database_force_unit=4,
        database_length_unit=6,
        database_temperature_unit=2,
    )


def _column():
    return ColumnTopologyEvidence(
        unique_name="U1",
        column_label="C1",
        story="Story1",
        section="SEC_A",
        width_t2_m=0.4,
        depth_t3_m=0.5,
        object_length_m=3.0,
        coordinate_length_m=3.0,
        joint_bottom="J:U1:B",
        joint_top="J:U1:T",
        bottom_coord_m=(0.0, 0.0, 0.0),
        top_coord_m=(0.0, 0.0, 3.0),
        offset_bottom_m=0.0,
        offset_top_m=0.0,
        analysis_clear_length_candidate_m=3.0,
        local_axis_angle_deg=0.0,
        local_axis_explicit=True,
        beams_at_bottom=(),
        beams_at_top=(),
        connectivity_row={"UniqueName": "U1"},
        assignment_row={"UniqueName": "U1", "SectProp": "SEC_A"},
        end_offset_row={"UniqueName": "U1"},
        section_row={"Name": "SEC_A"},
        local_axis_row={"UniqueName": "U1"},
    )


def _topology(column):
    return ColumnTopologyEvidenceEnvelope(
        topology=StrictColumnTopologyBundle(
            columns=(column,),
            point_count=2,
            beam_count=0,
            supported_rc_beam_count=0,
            unsupported_beam_count=0,
            reviewed_length_unit="m",
        ),
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        source_refs=("topology:p8a-integration",),
    )


def _design_sections(column, topology):
    evidence = ColumnDesignSectionEvidence(
        frame_name=column.unique_name,
        design_section="DESIGN_SEC_A",
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        source_api="DesignConcrete.GetDesignSection",
        source_ref="section:U1",
    )
    row = CapturedConcreteColumnDesignSection(
        component_id=column.component_id,
        unique_name=column.unique_name,
        story=column.story,
        label=column.column_label,
        assigned_section=column.section,
        design_section_evidence=evidence,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        source_refs=("section-row:U1",),
    )
    return ConcreteColumnDesignSectionPopulation(
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        expected_component_ids=(column.component_id,),
        expected_frame_names=(column.unique_name,),
        rows=(row,),
        topology_source_refs=topology.source_refs,
    )


def _result_row(**overrides):
    row = {
        "FrameName": "U1",
        "MyOption": 2,
        "Location": 0.5,
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


def _raw(rows):
    rows = tuple(rows)
    names = (
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
    )
    return [len(rows), *(tuple(row[name] for row in rows) for name in names), 0]


def _state(component_id, case, end, station, n, m2, m3):
    return ColumnDemandState(
        state_id=f"{case}:{end}",
        component_id=component_id,
        output_case=case,
        case_type="LinStatic",
        step_type=None,
        step_number=None,
        station_m=station,
        end_tag=end,
        nd_compression_n=n,
        m2_nmm=m2,
        m3_nmm=m3,
        source_identity=f"src:{case}:{end}",
    )


def _axis_basis(axis):
    return ColumnSlendernessAxisBasis(
        axis=axis,
        section_dimension_mm=500.0 if axis == "M2" else 400.0,
        free_length_ln_mm=3000.0,
        effective_length_factor_k=1.0,
        sway_classification=SWAY_PREVENTED,
        moment_ratio_m1_over_m2=0.0,
        source_refs=(f"reviewed:{axis}",),
    )


def _readiness(component_id):
    return resolve_column_design_demand_readiness(
        component_id=component_id,
        combo_definitions=(
            ColumnComboDefinition(
                name="ULS",
                combo_type="LINEAR_ADD",
                constituents=(ComboPatternConstituent("G", 1.0),),
            ),
        ),
        constituent_case_demands=(
            _state(component_id, "G", "I_END", 0.0, 1_000_000.0, -100_000_000.0, 80_000_000.0),
            _state(component_id, "G", "J_END", 3.0, 900_000.0, 70_000_000.0, -60_000_000.0),
        ),
        width_mm=400.0,
        depth_mm=500.0,
        slenderness_basis=ColumnSlendernessBasis(
            component_id=component_id,
            m2=_axis_basis("M2"),
            m3=_axis_basis("M3"),
            source_refs=("reviewed:slenderness-basis",),
        ),
    )


def _projection(component_id):
    identity = ("Strength", "ULS")
    fingerprint = "combo-definition:fixture:Strength:ULS"
    reconciliation = ConcreteDesignComboReconciliation(
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        expected=(identity,),
        actual_selected=(identity,),
        matched=(identity,),
        missing_expected=(),
        unexpected_selected=(),
        definition_mismatch=(),
        actual_definition_drift=(),
        unsupported_definition=(),
        analysis_basis_blocked=(),
        reviewed_definition_fingerprints=(("Strength", "ULS", fingerprint),),
        actual_capture_definition_fingerprints=(("Strength", "ULS", fingerprint),),
        definition_fingerprints=(("Strength", "ULS", fingerprint),),
        source_refs=("reconciliation:p8a-integration",),
    )
    readiness = _readiness(component_id)
    readiness_binding = ComponentReadinessBinding(
        readiness=readiness,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        readiness_ref=f"fnd-col-2-readiness:{component_id}",
        provenance_refs=("fnd-col-2:p8a-integration",),
    )
    analysis_binding = ComboAnalysisBasisBinding(
        design_combo_identity=identity,
        evidence=AnalysisBasisEligibilityEvidence(
            status_value="MATCH",
            compatibility_ref="analysis-basis:Strength:ULS",
            provenance_refs=("analysis-basis-provenance:Strength:ULS",),
        ),
        normalized_definition_fingerprint=fingerprint,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        provenance_refs=("combo-analysis-binding:Strength:ULS",),
    )
    projections = project_column_combo_eligibility(
        readiness_binding=readiness_binding,
        reconciliation=reconciliation,
        analysis_basis_bindings={identity: analysis_binding},
    )
    assert len(projections) == 1
    assert projections[0].eligible
    return projections


def test_provider_to_exact_combo_projection_to_etabs_required_rebar_preserves_all_design_rows(monkeypatch):
    column = _column()
    topology = _topology(column)
    sections = _design_sections(column, topology)
    sap = _Sap(
        {
            "U1": _raw(
                (
                    _result_row(Location=0.50, PMMArea=0.0064),
                    _result_row(Location=2.50, PMMArea=0.0070),
                    _result_row(MyOption=1, Location=1.50, PMMCombo="SERVICE", PMMArea=0.0080),
                )
            )
        }
    )
    snapshot = _snapshot()
    monkeypatch.setattr(provider_module, "read_etabs_unit_snapshot", lambda _sap: snapshot)

    factual = capture_concrete_column_design_results(
        sap,
        topology=topology,
        design_sections=sections,
        session_provenance_ref="session:p8a-integration",
    )

    projections = _projection(column.component_id)
    promoted = promote_etabs_required_rebar(
        factual,
        combo_eligibility_projections=projections,
    )

    assert factual.capture_complete
    assert factual.reported_result_row_count == 3
    assert len(factual.rows) == 3
    assert len(factual.design_rows) == 2
    assert sap.DesignConcrete.calls == ["U1"]

    assert promoted.promotion_complete
    assert promoted.source_result_row_count == 3
    assert promoted.source_design_row_count == 2
    assert promoted.promoted_requirement_count == 2
    assert promoted.blocked_requirement_count == 0
    assert len(promoted.requirements) == 2
    assert promoted.blocked_rows == ()

    assert {item.authority for item in promoted.requirements} == {ETABS_REQUIRED_REBAR}
    assert {item.design_combo_identity for item in promoted.requirements} == {("Strength", "ULS")}
    assert {item.location_mm for item in promoted.requirements} == {Decimal("500"), Decimal("2500")}
    assert {item.required_as_mm2 for item in promoted.requirements} == {Decimal("6400"), Decimal("7000")}
    assert {item.source_row_id for item in promoted.requirements} == {
        item.source_row_id for item in factual.design_rows
    }
    assert all(item.combo_eligibility_projection_id == projections[0].projection_id for item in promoted.requirements)
