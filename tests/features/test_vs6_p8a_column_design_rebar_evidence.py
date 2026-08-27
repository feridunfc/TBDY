from __future__ import annotations

import pytest

from tbdy_engine.design.columns.column_concrete_design_evidence_authority import ConcreteDesignComboReconciliation
from tbdy_engine.features.column_concrete_design_evidence import ColumnTopologyEvidenceEnvelope
from tbdy_engine.features.column_design_rebar_evidence import (
    BLOCKED_ETABS_ERROR_SUMMARY,
    BLOCKED_ETABS_WARNING_SUMMARY,
    BLOCKED_MISSING_PMM_COMBO,
    BLOCKED_UNBINDABLE_PMM_COMBO,
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


def _raw(
    *,
    options=(2, 2),
    combos=("ULS1", "ULS2"),
    areas=(0.004, 0.005),
    errors=("", ""),
    warnings=("", ""),
):
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
        list(warnings),
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
    assert population.blocked_requirement_count == 0
    assert population.promotion_complete
    assert len(component.requirements) == 2
    assert component.blocked_rows == ()
    assert sorted(item.required_as_mm2 for item in component.requirements) == [4000, 5000]
    assert {item.design_combo_identity for item in component.requirements} == {
        ("Strength", "ULS1"),
        ("Strength", "ULS2"),
    }
    assert all(item.authority == "ETABS_REQUIRED_REBAR" for item in component.requirements)
    assert not hasattr(population, "governing_required_as_mm2")


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
    assert component.blocked_requirement_count == 0
    assert component.requirements[0].required_as_mm2 == 5000
    assert component.requirements[0].design_combo_identity == ("Strength", "ULS2")


def test_exact_combo_identity_is_required_and_special_suffix_is_not_stripped():
    raw = _raw(combos=("ULS1 (Sp)", "ULS2"))
    population = promote_etabs_required_rebar(
        _results(raw),
        combo_reconciliation=_reconciliation(),
    )
    assert population.promoted_requirement_count == 1
    assert population.blocked_requirement_count == 1
    assert not population.promotion_complete
    blocked = population.blocked_rows[0]
    assert blocked.pmm_combo == "ULS1 (Sp)"
    assert blocked.reason_code == BLOCKED_UNBINDABLE_PMM_COMBO
    assert "ULS1 (Sp)" in blocked.reason_detail
    assert population.requirements[0].design_combo_identity == ("Strength", "ULS2")


def test_missing_pmm_combo_is_retained_as_explicit_blocker():
    raw = _raw(combos=(None, "ULS2"))
    population = promote_etabs_required_rebar(
        _results(raw),
        combo_reconciliation=_reconciliation(),
    )
    assert population.promoted_requirement_count == 1
    assert population.blocked_requirement_count == 1
    assert population.blocked_rows[0].reason_code == BLOCKED_MISSING_PMM_COMBO
    assert population.blocked_rows[0].pmm_combo is None


def test_nonclosed_f0_combo_reconciliation_blocks_population_promotion():
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


def test_model_or_epoch_mismatch_blocks_before_population_promotion():
    with pytest.raises(ColumnDesignRebarEvidenceError, match="model/evidence epoch"):
        promote_etabs_required_rebar(
            _results(),
            combo_reconciliation=_reconciliation(model="other-model"),
        )


def test_etabs_error_summary_is_preserved_and_blocks_only_that_required_rebar_row():
    raw = _raw(errors=("DESIGN ERROR", ""))
    population = promote_etabs_required_rebar(
        _results(raw),
        combo_reconciliation=_reconciliation(),
    )
    assert population.promoted_requirement_count == 1
    assert population.blocked_requirement_count == 1
    blocked = population.blocked_rows[0]
    assert blocked.reason_code == BLOCKED_ETABS_ERROR_SUMMARY
    assert blocked.error_summary == "DESIGN ERROR"
    assert blocked.warning_summary == ""
    assert blocked.required_as_mm2 == 4000


def test_nonempty_warning_summary_is_preserved_and_fails_closed_for_that_row():
    raw = _raw(warnings=("DESIGN WARNING: REVIEW REQUIRED", ""))
    population = promote_etabs_required_rebar(
        _results(raw),
        combo_reconciliation=_reconciliation(),
    )
    assert population.promoted_requirement_count == 1
    assert population.blocked_requirement_count == 1
    assert not population.promotion_complete
    blocked = population.blocked_rows[0]
    assert blocked.reason_code == BLOCKED_ETABS_WARNING_SUMMARY
    assert blocked.warning_summary == "DESIGN WARNING: REVIEW REQUIRED"
    assert blocked.error_summary == ""
    assert population.requirements[0].design_combo_identity == ("Strength", "ULS2")
