from __future__ import annotations

import pytest

from tbdy_engine.design.columns.column_concrete_design_evidence_authority import ConcreteDesignComboReconciliation
from tbdy_engine.features.column_concrete_design_evidence import ColumnTopologyEvidenceEnvelope
from tbdy_engine.features.column_design_rebar_evidence import (
    ColumnDesignRebarEvidenceError,
    promote_etabs_required_rebar,
)
from tbdy_engine.features.column_shear_topology import ColumnTopologyEvidence, StrictColumnTopologyBundle
from tbdy_engine.features.evidence_epoch import EvidenceEpoch, EvidenceEpochOrigin
from tbdy_engine.providers.etabs_concrete_design_section_provider import capture_concrete_column_design_sections
from tbdy_engine.providers.etabs_concrete_column_design_result_provider import capture_concrete_column_design_results


def _column():
    return ColumnTopologyEvidence(
        unique_name="U1",
        column_label="C1",
        story="Story1",
        section="ASSIGNED",
        width_t2_m=0.8,
        depth_t3_m=0.8,
        object_length_m=3.0,
        coordinate_length_m=3.0,
        joint_bottom="P1",
        joint_top="P2",
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
        assignment_row={"UniqueName": "U1", "Section": "ASSIGNED"},
        end_offset_row={"UniqueName": "U1"},
        section_row={"Name": "ASSIGNED"},
        local_axis_row={"UniqueName": "U1"},
    )


def _topology():
    strict = StrictColumnTopologyBundle((_column(),), 2, 0, 0, 0, "m")
    epoch = EvidenceEpoch("epoch:1", "model:1", EvidenceEpochOrigin.FIXTURE_REPLAY)
    return ColumnTopologyEvidenceEnvelope.bind(
        topology=strict,
        epoch=epoch,
        source_refs=("strict-topology:fixture",),
    )


class _Sections:
    def GetDesignSection(self, name):
        assert name == "U1"
        return "DESIGN", 0


class _Results:
    def __init__(self, raw):
        self.raw = raw

    def GetSummaryResultsColumn(self, name):
        assert name == "U1"
        return self.raw


class _Sap:
    def __init__(self, raw):
        self.DesignConcrete = _Results(raw)

    def GetPresentUnits_2(self):
        return 4, 6, 2, 0


def _raw(*, options=(2, 2), combos=("ULS1", "ULS2"), areas=(0.004, 0.005), errors=("", "")):
    return (
        2,
        ["U1", "U1"],
        list(options),
        [0.0, 3.0],
        list(combos),
        list(areas),
        [8.8, 0.0],
        ["", ""],
        [0.0, 0.0],
        ["", ""],
        [0.0, 0.0],
        list(errors),
        ["", ""],
        0,
    )


def _results(raw=None):
    topology = _topology()
    sections = capture_concrete_column_design_sections(_Sections(), topology=topology)
    return capture_concrete_column_design_results(
        _Sap(raw or _raw()),
        topology=topology,
        design_sections=sections,
        session_provenance_ref="session:fixture",
    )


def _reconciliation(*identities, model="model:1", epoch="epoch:1"):
    values = tuple(sorted(identities or (("Strength", "ULS1"), ("Strength", "ULS2"))))
    return ConcreteDesignComboReconciliation(
        model_fingerprint=model,
        evidence_epoch_id=epoch,
        expected=values,
        actual_selected=values,
        matched=values,
        missing_expected=(),
        unexpected_selected=(),
        definition_mismatch=(),
        actual_definition_drift=(),
        unsupported_definition=(),
        analysis_basis_blocked=(),
        reviewed_definition_fingerprints=(),
        actual_capture_definition_fingerprints=(),
        definition_fingerprints=(),
        source_refs=("F0:reconciliation:fixture",),
    )


def test_all_exact_design_rows_promote_without_max_or_envelope_collapse():
    population = promote_etabs_required_rebar(
        _results(),
        combo_reconciliation=_reconciliation(),
    )
    component = population.components[0]
    assert population.source_result_row_count == 2
    assert population.source_design_row_count == 2
    assert population.promoted_requirement_count == 2
    assert len(component.requirements) == 2
    assert sorted(item.required_as_mm2 for item in component.requirements) == [4000, 5000]
    assert {item.design_combo_identity for item in component.requirements} == {
        ("Strength", "ULS1"),
        ("Strength", "ULS2"),
    }
    assert all(item.authority == "ETABS_REQUIRED_REBAR" for item in component.requirements)


def test_check_mode_row_and_pmm_ratio_do_not_become_required_rebar():
    raw = _raw(options=(1, 2), combos=(None, "ULS2"), areas=(999.0, 0.005))
    population = promote_etabs_required_rebar(
        _results(raw),
        combo_reconciliation=_reconciliation(),
    )
    component = population.components[0]
    assert population.source_result_row_count == 2
    assert population.source_design_row_count == 1
    assert component.promoted_requirement_count == 1
    assert component.requirements[0].required_as_mm2 == 5000
    assert component.requirements[0].design_combo_identity == ("Strength", "ULS2")


def test_exact_combo_identity_is_required_and_special_suffix_is_not_stripped():
    raw = _raw(combos=("ULS1 (Sp)", "ULS2"))
    with pytest.raises(ColumnDesignRebarEvidenceError, match="exactly one F0 matched combo"):
        promote_etabs_required_rebar(
            _results(raw),
            combo_reconciliation=_reconciliation(),
        )


def test_nonclosed_f0_combo_reconciliation_blocks_promotion():
    base = _reconciliation()
    blocked = ConcreteDesignComboReconciliation(
        model_fingerprint=base.model_fingerprint,
        evidence_epoch_id=base.evidence_epoch_id,
        expected=base.expected,
        actual_selected=base.actual_selected,
        matched=(("Strength", "ULS1"),),
        missing_expected=(),
        unexpected_selected=(),
        definition_mismatch=(("Strength", "ULS2"),),
        actual_definition_drift=(),
        unsupported_definition=(),
        analysis_basis_blocked=(),
        reviewed_definition_fingerprints=(),
        actual_capture_definition_fingerprints=(),
        definition_fingerprints=(),
        source_refs=("F0:reconciliation:blocked",),
    )
    with pytest.raises(ColumnDesignRebarEvidenceError, match="not closed"):
        promote_etabs_required_rebar(_results(), combo_reconciliation=blocked)


def test_model_or_epoch_mismatch_blocks_before_promotion():
    with pytest.raises(ColumnDesignRebarEvidenceError, match="model/evidence epoch"):
        promote_etabs_required_rebar(
            _results(),
            combo_reconciliation=_reconciliation(model="other-model"),
        )


def test_etabs_error_summary_blocks_factual_required_rebar_promotion():
    raw = _raw(errors=("DESIGN ERROR", ""))
    with pytest.raises(ColumnDesignRebarEvidenceError, match="ErrorSummary"):
        promote_etabs_required_rebar(
            _results(raw),
            combo_reconciliation=_reconciliation(),
        )
