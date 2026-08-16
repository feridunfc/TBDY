from __future__ import annotations

import inspect
from collections.abc import Mapping

import pytest

from tbdy_engine.checks.ndm_selection import (
    EngineeringQuantityRequest,
    NdmAvailability,
    ReviewedNdmLoadBinding,
    ReviewedNdmPolicy,
    select_ndm_demand,
)
from tbdy_engine.checks.result import CheckStatus
from tbdy_engine.checks.wall_applicability import derive_ndm_n
from tbdy_engine.checks.wall_contract import WALL_NET_SECTION_AXIAL_CAPACITY
from tbdy_engine.checks.wall_pipeline import WallExecutionEvidence, run_wall_checks
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus
from tbdy_engine.features.result_evidence import (
    PIER_FORCE_IDENTITY_FIELDS,
    PIER_FORCE_PAYLOAD_FIELDS,
    ResultRowEvidenceBundle,
    RuntimeCaptureStatus,
)
from tbdy_engine.features.snapshot import FeatureSnapshot
from tbdy_engine.features.value import FeatureValue, FeatureValueStatus


AUTHORITY_IDS = (
    "TBDY2018_RG_20180318_M1-2-1",
    "TBDY2018_7.6.1.1",
    "TBDY2018_4.4.2.1_EQ4.9",
    "TBDY2018_4.4.4.1_EQ4.11",
    "TS498_1997_13_REVIEWED_DECISION",
)


def _row(case, p, *, case_type="Combination", step="Max", location="Bottom", story="L1", pier="P1", step_number=None):
    row = {field: 0.0 for field in PIER_FORCE_PAYLOAD_FIELDS}
    row.update({field: None for field in PIER_FORCE_IDENTITY_FIELDS})
    row.update({
        "Story": story, "Pier": pier, "OutputCase": case, "CaseType": case_type,
        "StepType": step, "StepNumber": step_number, "Location": location, "P": p,
    })
    return row


def _static(case, p, *, location="Bottom", story="L1", pier="P1"):
    return _row(case, p, case_type="LinStatic", step=None, step_number=None,
                location=location, story=story, pier=pier)


def _bundle(rows, *, unit="N", capture=RuntimeCaptureStatus.FULL, reported=None):
    rows = tuple(rows)
    return ResultRowEvidenceBundle(
        table_key="pier_forces", actual_table_name="Pier Forces",
        identity_fields=PIER_FORCE_IDENTITY_FIELDS, payload_fields=PIER_FORCE_PAYLOAD_FIELDS,
        rows=rows, source_contract_status="VERIFIED_LIVE", units={"force_unit": unit},
        runtime_capture_status=capture,
        reported_row_count=len(rows) if reported is None else reported,
    )


def _binding(*, q_ids=("Q_CASE",), baseline_override=None, fixed_override=None):
    final_ids = ("FINAL_X", "FINAL_Y")
    g = ("G_CASE",); q = tuple(q_ids); s = ("S_CASE",); h = ("E_X", "E_Y"); v = ("E_Z",)
    x = {"G_CASE": 1.0, **{item: 1.0 for item in q}, "S_CASE": 1.0,
         "E_X": 1.0, "E_Y": 0.3, "E_Z": 0.3}
    y = {"G_CASE": 1.0, **{item: 1.0 for item in q}, "S_CASE": 1.0,
         "E_X": 0.3, "E_Y": 1.0, "E_Z": 0.3}
    baseline = {"FINAL_X": x, "FINAL_Y": y}
    if baseline_override:
        for combo, values in baseline_override.items(): baseline[combo] = {**baseline[combo], **values}
    fixed = {
        "FINAL_X": {"G_CASE": 1.0, "E_X": 1.0, "E_Y": 0.3, "E_Z": 0.3},
        "FINAL_Y": {"G_CASE": 1.0, "E_X": 0.3, "E_Y": 1.0, "E_Z": 0.3},
    }
    if fixed_override:
        for combo, values in fixed_override.items(): fixed[combo] = {**fixed[combo], **values}
    return ReviewedNdmLoadBinding(
        binding_id="BINDING-1", version="v1", final_combination_ids=final_ids,
        g_case_ids=g, q_case_ids=q, s_case_ids=s, horizontal_e_case_ids=h, vertical_e_case_ids=v,
        baseline_coefficients_by_combination=baseline,
        required_fixed_coefficients_by_combination=fixed,
        review_refs=("supervisor-reviewed-live-inventory",),
    )


def _policy(*, q=None, s=0.2, ts498="RESOLVED", unequal=True, linear=True):
    q = {"Q_CASE": 0.5} if q is None else q
    return ReviewedNdmPolicy(
        policy_id="NDM-POLICY-1", version="v1", ts498_decision=ts498,
        q_target_coefficients=q, s_target_coefficients={"S_CASE": s},
        unequal_q_interpretation_reviewed=unequal,
        linear_superposition_reviewed=linear,
        regulatory_authority_ids=AUTHORITY_IDS,
        review_refs=("reviewed-ts498-decision", "reviewed-linear-superposition"),
    )


def _request(): return EngineeringQuantityRequest("REQ-1", "W1", "L1", "P1")


def _correction_rows(*, q_p=-20_000.0, s_p=-10_000.0, locations=("Top", "Bottom")):
    rows = []
    for location in locations:
        rows.extend((_static("Q_CASE", q_p, location=location), _static("S_CASE", s_p, location=location)))
    return rows


def _resolved_rows():
    return [
        _row("FINAL_X", -100_000.0, step="Max", location="Top"),
        _row("FINAL_X", -120_000.0, step="Min", location="Bottom"),
        _row("FINAL_Y", -90_000.0, step="Max", location="Top"),
        _row("FINAL_Y", -110_000.0, step="Min", location="Bottom"),
        *_correction_rows(),
    ]


def test_selector_uses_exact_binding_only_and_has_no_runtime_name_heuristics():
    demand = select_ndm_demand(_request(), _bundle([*_resolved_rows(), _row("FINAL_X_EXTRA", -9_000_000.0)]), _binding(), _policy())
    assert demand.availability == NdmAvailability.RESOLVED
    assert all(item.final_combination_id in {"FINAL_X", "FINAL_Y"} for item in demand.trace.candidate_rows)
    source = inspect.getsource(select_ndm_demand)
    for forbidden in ("Duct_SeisX", "Duct_SeisY", "LC_DL", "LC_LL", "RSX", "RSY"):
        assert forbidden not in source


def test_raw_row_reordering_is_deterministic():
    rows = _resolved_rows()
    a = select_ndm_demand(_request(), _bundle(rows), _binding(), _policy())
    b = select_ndm_demand(_request(), _bundle(reversed(rows)), _binding(), _policy())
    assert a.ndm_n == b.ndm_n
    assert a.trace.as_dict() == b.trace.as_dict()


def test_negative_p_is_compression_and_abs_is_not_used():
    rows = [_row("FINAL_X", 900_000.0, step="Max", location="Top"), _row("FINAL_X", -100_000.0, step="Min", location="Bottom"), *_correction_rows()]
    demand = select_ndm_demand(_request(), _bundle(rows), _binding(), _policy())
    compressions = [item.canonical_compression_n for item in demand.trace.candidate_rows]
    assert min(compressions) == 0.0
    assert 0.0 < demand.ndm_n < 900_000.0


def test_standalone_response_spectrum_rows_are_not_direct_ndm_candidates():
    rows = [*_resolved_rows(), _row("E_X", -8_000_000.0, case_type="LinRespSpec", step="Max")]
    demand = select_ndm_demand(_request(), _bundle(rows), _binding(), _policy())
    assert demand.availability == NdmAvailability.RESOLVED
    assert all(item.final_combination_id != "E_X" for item in demand.trace.candidate_rows)
    assert demand.ndm_n < 8_000_000.0


def test_max_and_min_and_top_and_bottom_are_all_evaluated_without_step_shortcut():
    demand = select_ndm_demand(_request(), _bundle(_resolved_rows()), _binding(), _policy())
    seen = {(item.step_type, item.location) for item in demand.trace.candidate_rows}
    assert ("Max", "Top") in seen and ("Min", "Bottom") in seen
    assert len(demand.trace.candidate_rows) == 4
    governing = dict(demand.trace.governing_row_identities[0])
    assert governing["StepType"] == "Min" and governing["Location"] == "Bottom"


def test_more_compressive_max_can_govern_over_min():
    rows = [_row("FINAL_X", -200_000.0, step="Max", location="Top"), _row("FINAL_X", -100_000.0, step="Min", location="Bottom"), *_correction_rows()]
    demand = select_ndm_demand(_request(), _bundle(rows), _binding(), _policy())
    assert dict(demand.trace.governing_row_identities[0])["StepType"] == "Max"


def test_step_number_none_is_preserved_not_fabricated():
    demand = select_ndm_demand(_request(), _bundle(_resolved_rows()), _binding(), _policy())
    assert demand.availability == NdmAvailability.RESOLVED
    assert all(item.step_number is None for item in demand.trace.candidate_rows)
    assert all(dict(identity)["StepNumber"] is None for identity in demand.trace.governing_row_identities)


def test_explicit_kn_to_n_conversion():
    rows = [_row("FINAL_X", -100.0, step="Max", location="Top"), _row("FINAL_Y", -90.0, step="Max", location="Top"), *_correction_rows(q_p=-20.0, s_p=-10.0, locations=("Top",))]
    demand = select_ndm_demand(_request(), _bundle(rows, unit="kN"), _binding(), _policy())
    assert demand.availability == NdmAvailability.RESOLVED
    assert demand.ndm_n == pytest.approx(82_000.0)
    assert demand.unit == "N" and demand.trace.source_unit == "kN"


@pytest.mark.parametrize("capture", [RuntimeCaptureStatus.PARTIAL, RuntimeCaptureStatus.SAMPLED, RuntimeCaptureStatus.TRUNCATED, RuntimeCaptureStatus.UNKNOWN])
def test_incomplete_capture_is_blocked(capture):
    rows = _resolved_rows(); reported = len(rows) + 1 if capture == RuntimeCaptureStatus.TRUNCATED else len(rows)
    demand = select_ndm_demand(_request(), _bundle(rows, capture=capture, reported=reported), _binding(), _policy())
    assert demand.availability == NdmAvailability.BLOCKED and demand.ndm_n is None


def test_missing_and_unsupported_units_block():
    bundle = _bundle(_resolved_rows())
    def with_units(units):
        return ResultRowEvidenceBundle(table_key="pier_forces", actual_table_name="Pier Forces",
            identity_fields=PIER_FORCE_IDENTITY_FIELDS, payload_fields=PIER_FORCE_PAYLOAD_FIELDS,
            rows=bundle.rows, source_contract_status="VERIFIED_LIVE", units=units,
            runtime_capture_status=RuntimeCaptureStatus.FULL, reported_row_count=len(bundle.rows))
    assert select_ndm_demand(_request(), with_units({}), _binding(), _policy()).availability == NdmAvailability.BLOCKED
    assert select_ndm_demand(_request(), with_units({"force_unit": "kgf"}), _binding(), _policy()).availability == NdmAvailability.BLOCKED


def test_missing_binding_and_unresolved_ts498_block():
    bundle = _bundle(_resolved_rows())
    assert select_ndm_demand(_request(), bundle, None, _policy()).availability == NdmAvailability.BLOCKED
    demand = select_ndm_demand(_request(), bundle, _binding(), _policy(ts498="UNRESOLVED"))
    assert demand.availability == NdmAvailability.BLOCKED and "TS498" in str(demand.trace.reason)


def test_unequal_q_requires_reviewed_interpretation():
    binding = _binding(q_ids=("Q1", "Q2"))
    demand = select_ndm_demand(_request(), _bundle([]), binding, _policy(q={"Q1": 0.5, "Q2": 0.3}, unequal=False))
    assert demand.availability == NdmAvailability.BLOCKED and "Unequal Q" in str(demand.trace.reason)


def test_reviewed_q_and_s_linear_corrections_are_reconstructable():
    rows = [_row("FINAL_X", -100_000.0, step="Max", location="Top"), *_correction_rows(locations=("Top",))]
    demand = select_ndm_demand(_request(), _bundle(rows), _binding(), _policy())
    assert demand.ndm_n == pytest.approx(82_000.0)
    candidate = demand.trace.candidate_rows[0]; q = candidate.q_corrections[0]; s = candidate.s_corrections[0]
    assert q.baseline_coefficient == 1.0 and q.target_coefficient == 0.5 and q.delta_p_n == pytest.approx(10_000.0)
    assert s.baseline_coefficient == 1.0 and s.target_coefficient == 0.2 and s.delta_p_n == pytest.approx(8_000.0)
    assert candidate.adjusted_p_n == pytest.approx(-82_000.0)


def test_zero_s_force_has_zero_numeric_correction_but_remains_traced():
    rows = [_row("FINAL_X", -100_000.0, location="Top"), _static("Q_CASE", -20_000.0, location="Top"), _static("S_CASE", 0.0, location="Top")]
    s = select_ndm_demand(_request(), _bundle(rows), _binding(), _policy()).trace.candidate_rows[0].s_corrections[0]
    assert s.delta_coefficient == pytest.approx(-0.8) and s.delta_p_n == 0.0


def test_correction_requires_reviewed_linear_superposition_authority():
    demand = select_ndm_demand(_request(), _bundle(_resolved_rows()), _binding(), _policy(linear=False))
    assert demand.availability == NdmAvailability.BLOCKED and "linear-superposition" in str(demand.trace.reason)


def test_missing_exact_correction_row_after_full_lookup_is_no_data():
    rows = [_row("FINAL_X", -100_000.0, location="Top"), _static("Q_CASE", -20_000.0, location="Top")]
    demand = select_ndm_demand(_request(), _bundle(rows), _binding(), _policy())
    assert demand.availability == NdmAvailability.NO_DATA and "S correction row" in str(demand.trace.reason)


def test_g_or_e_coefficient_mismatch_is_blocked():
    binding = _binding(fixed_override={"FINAL_X": {"E_Y": 0.4}})
    demand = select_ndm_demand(_request(), _bundle(_resolved_rows()), binding, _policy())
    assert demand.availability == NdmAvailability.BLOCKED and "G/E coefficient mismatch" in str(demand.trace.reason)


def test_conflicting_duplicate_source_identity_blocks():
    first = _row("FINAL_X", -100_000.0, location="Top"); second = dict(first); second["P"] = -120_000.0
    demand = select_ndm_demand(_request(), _bundle([first, second, *_correction_rows(locations=("Top",))]), _binding(), _policy())
    assert demand.availability == NdmAvailability.BLOCKED and "Conflicting duplicate" in str(demand.trace.reason)


def test_all_exact_co_governing_ties_are_retained():
    rows = [_row("FINAL_X", -100_000.0, step="Max", location="Top"), _row("FINAL_Y", -100_000.0, step="Min", location="Top"), *_correction_rows(locations=("Top",))]
    demand = select_ndm_demand(_request(), _bundle(rows), _binding(), _policy())
    assert demand.availability == NdmAvailability.RESOLVED and len(demand.trace.governing_row_identities) == 2


def test_full_resolved_lookup_with_no_matching_final_row_is_no_data():
    demand = select_ndm_demand(_request(), _bundle([_static("Q_CASE", -20_000.0), _static("S_CASE", -10_000.0)]), _binding(), _policy())
    assert demand.availability == NdmAvailability.NO_DATA


def test_selection_result_has_availability_not_regulatory_verdict_or_ratio():
    trace = select_ndm_demand(_request(), _bundle(_resolved_rows()), _binding(), _policy()).trace.as_dict()
    assert trace["availability"] == "RESOLVED" and "status" not in trace and "ratio" not in trace
    assert not any(isinstance(value, str) and value in {"PASS", "FAIL", "WARNING", "OUT_OF_SCOPE"} for value in trace.values())


def test_derive_ndm_n_is_the_single_adapter_and_preserves_selection_trace():
    q = derive_ndm_n(component_id="W1", story_name="L1", pier_name="P1", pier_forces=_bundle(_resolved_rows()), load_binding=_binding(), policy=_policy())
    assert q.status == "RESOLVED" and q.value is not None
    assert q.evidence and q.evidence[0]["selection_trace"]["governing_value_n"] == q.value


class _Bundle:
    def __init__(self):
        feature = lambda unit="", role="GEOMETRY": {"element_type": "wall", "unit": unit, "semantic_role": role, "source": {"table_key": None, "field_aliases": []}, "evidence_fields": []}
        self.data = {
            "check_catalog.yaml": {"checks": {}},
            "feature_catalog.yaml": {"features": {"wall_thickness_mm": feature("mm"), "wall_length_mm": feature("mm"), "story_height_mm": feature("mm"), "concrete_fck_mpa": feature("MPa", "DESIGN_BASIS")}},
            "table_registry.yaml": {"tables": {}}, "element_registry.yaml": {"element_types": {"wall": {}}},
            "high_ductility_check_scope.yaml": {"scope_items": []}, "check_scope_alignment.yaml": {}, "design_combo_matrix.yaml": {"design_mappings": []},
        }
    def catalog(self, name): return self.data[name]


def _fv(name, value, unit="", role="GEOMETRY"):
    ev = FeatureEvidence(evidence_status=FeatureEvidenceStatus.FULL, source_table="b2_fixture", actual_table_name="b2_fixture", source_column=name, source_row={"name": name}, raw_value=value, normalized_value=value, unit=unit, resolver="b2_fixture")
    return FeatureValue(feature_name=name, value=value, unit=unit, semantic_role=role, status=FeatureValueStatus.RESOLVED, evidence=[ev])


def _snapshot():
    return FeatureSnapshot(component_type="wall", component_id="W1", identity={"story": "L1", "assigned_wall_property": "WALL-P1"}, features={
        "wall_thickness_mm": _fv("wall_thickness_mm", 300.0, "mm"), "story_height_mm": _fv("story_height_mm", 3200.0, "mm"),
        "wall_body_classification": _fv("wall_body_classification", "RECTANGULAR_BODY", role="GEOMETRY_CLASSIFICATION"),
        "wall_is_basement": _fv("wall_is_basement", False, role="REGULATORY_LOCATION"), "concrete_fck_mpa": _fv("concrete_fck_mpa", 35.0, "MPa", "DESIGN_BASIS"),
    })


def _execution(rows):
    return WallExecutionEvidence(result_bundles={"pier_forces": _bundle(rows)}, wall_to_pier={"W1": "P1"}, ndm_load_binding=_binding(), ndm_policy=_policy(), net_section_topology_by_component={"W1": {"topology_verified": True, "section_semantics_verified": True, "gross_cross_section_area_mm2": 300_000.0, "openings": []}})


def test_pack_b_pipeline_materializes_ndm_before_engine_and_existing_formula_executes():
    run = run_wall_checks(_Bundle(), [_snapshot()], [WALL_NET_SECTION_AXIAL_CAPACITY], execution_evidence=_execution(_resolved_rows()))
    readiness = {item.context_name: item for item in run.coverage_rows[0].execution_context_readiness}
    assert readiness["ndm_demand"].status.value == "READY"
    demand = run.check_inputs[0].execution_context.values["ndm_demand"]
    assert demand.status == "RESOLVED"
    result = run.check_results[0]
    assert result.status == CheckStatus.OK
    assert result.limit == pytest.approx(demand.value / (0.35 * 35.0))
    assert any("selection_trace" in evidence for evidence in result.evidence if isinstance(evidence, Mapping))


def test_pack_b_pipeline_propagates_authoritative_no_data_not_blocked():
    run = run_wall_checks(_Bundle(), [_snapshot()], [WALL_NET_SECTION_AXIAL_CAPACITY], execution_evidence=_execution([_static("Q_CASE", -20_000.0), _static("S_CASE", -10_000.0)]))
    readiness = {item.context_name: item for item in run.coverage_rows[0].execution_context_readiness}
    assert readiness["ndm_demand"].status.value == "READY"
    assert run.check_results[0].status == CheckStatus.NO_DATA


def test_ndm_selector_does_not_duplicate_wall_capacity_formula():
    source = inspect.getsource(select_ndm_demand)
    assert "0.35" not in source and "net_section_area" not in source and "concrete_fck" not in source
