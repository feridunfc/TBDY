from __future__ import annotations

import inspect
from collections.abc import Mapping

import pytest

from tbdy_engine.checks import ndm_selection as ndm_module
from tbdy_engine.checks.ndm_selection import (
    EngineeringQuantityRequest,
    NdmAvailability,
    ReviewedNdmLoadBinding,
    ReviewedNdmPolicy,
    Ts498StoreyQState,
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


def _binding(*, q_ids=("Q_CASE",), baseline_override=None, fixed_override=None,
             final_ids=("FINAL_X", "FINAL_Y"), allowed_steps=("Max", "Min"),
             allowed_locations=("Top", "Bottom")):
    final_ids = tuple(final_ids)
    g = ("G_CASE",); q = tuple(q_ids); s = ("S_CASE",); h = ("E_X", "E_Y"); v = ("E_Z",)
    all_baseline = {
        "FINAL_X": {"G_CASE": 1.0, **{item: 1.0 for item in q}, "S_CASE": 1.0,
                    "E_X": 1.0, "E_Y": 0.3, "E_Z": 0.3},
        "FINAL_Y": {"G_CASE": 1.0, **{item: 1.0 for item in q}, "S_CASE": 1.0,
                    "E_X": 0.3, "E_Y": 1.0, "E_Z": 0.3},
    }
    all_fixed = {
        "FINAL_X": {"G_CASE": 1.0, "E_X": 1.0, "E_Y": 0.3, "E_Z": 0.3},
        "FINAL_Y": {"G_CASE": 1.0, "E_X": 0.3, "E_Y": 1.0, "E_Z": 0.3},
    }
    baseline = {combo: dict(all_baseline[combo]) for combo in final_ids}
    fixed = {combo: dict(all_fixed[combo]) for combo in final_ids}
    if baseline_override:
        for combo, values in baseline_override.items(): baseline[combo] = {**baseline[combo], **values}
    if fixed_override:
        for combo, values in fixed_override.items(): fixed[combo] = {**fixed[combo], **values}
    return ReviewedNdmLoadBinding(
        binding_id="BINDING-1", version="v1", final_combination_ids=final_ids,
        g_case_ids=g, q_case_ids=q, s_case_ids=s, horizontal_e_case_ids=h, vertical_e_case_ids=v,
        baseline_coefficients_by_combination=baseline,
        required_fixed_coefficients_by_combination=fixed,
        allowed_final_step_types=tuple(allowed_steps), allowed_locations=tuple(allowed_locations),
        review_refs=("supervisor-reviewed-live-inventory",),
    )


def _policy(*, q=None, s=0.2, q_state=Ts498StoreyQState.EQUAL_STOREY_Q_REVIEWED,
            target_component_id="W1", target_story="L1", target_pier="P1",
            unequal_interpretation="reviewed supported-storey Q_i interpretation", linear=True):
    q = {"Q_CASE": 0.5} if q is None else q
    return ReviewedNdmPolicy(
        policy_id=f"NDM-POLICY-{target_component_id}", version="v1",
        target_component_id=target_component_id, target_story=target_story, target_pier=target_pier,
        ts498_storey_q_state=q_state,
        q_target_coefficients=q, s_target_coefficients={"S_CASE": s},
        unequal_storey_q_interpretation=unequal_interpretation,
        linear_superposition_reviewed=linear,
        regulatory_authority_ids=AUTHORITY_IDS,
        review_refs=("reviewed-ts498-decision", "reviewed-linear-superposition"),
    )


def _request(): return EngineeringQuantityRequest("REQ-1", "W1", "L1", "P1")


def _correction_rows(*, q_p=-20_000.0, s_p=-10_000.0, locations=("Top", "Bottom"), story="L1", pier="P1", q_ids=("Q_CASE",)):
    rows = []
    for location in locations:
        for q_id in q_ids:
            rows.append(_static(q_id, q_p, location=location, story=story, pier=pier))
        rows.append(_static("S_CASE", s_p, location=location, story=story, pier=pier))
    return rows


def _resolved_rows():
    return [
        _row("FINAL_X", -100_000.0, step="Max", location="Top"),
        _row("FINAL_X", -105_000.0, step="Max", location="Bottom"),
        _row("FINAL_X", -115_000.0, step="Min", location="Top"),
        _row("FINAL_X", -120_000.0, step="Min", location="Bottom"),
        _row("FINAL_Y", -90_000.0, step="Max", location="Top"),
        _row("FINAL_Y", -95_000.0, step="Max", location="Bottom"),
        _row("FINAL_Y", -105_000.0, step="Min", location="Top"),
        _row("FINAL_Y", -110_000.0, step="Min", location="Bottom"),
        *_correction_rows(),
    ]


def _single_cell_rows(*, final_p=-100_000.0, q_p=-20_000.0, s_p=-10_000.0, story="L1", pier="P1", q_ids=("Q_CASE",)):
    return [
        _row("FINAL_X", final_p, step="Max", location="Top", story=story, pier=pier),
        *_correction_rows(q_p=q_p, s_p=s_p, locations=("Top",), story=story, pier=pier, q_ids=q_ids),
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
    rows = [
        _row("FINAL_X", 900_000.0, step="Max", location="Top"),
        _row("FINAL_X", 800_000.0, step="Max", location="Bottom"),
        _row("FINAL_X", -90_000.0, step="Min", location="Top"),
        _row("FINAL_X", -100_000.0, step="Min", location="Bottom"),
        *_correction_rows(),
    ]
    demand = select_ndm_demand(_request(), _bundle(rows), _binding(final_ids=("FINAL_X",)), _policy())
    assert demand.availability == NdmAvailability.RESOLVED
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
    seen = {(item.final_combination_id, item.step_type, item.location) for item in demand.trace.candidate_rows}
    assert len(seen) == 8
    assert ("FINAL_X", "Max", "Top") in seen and ("FINAL_Y", "Min", "Bottom") in seen
    governing = dict(demand.trace.governing_row_identities[0])
    assert governing["StepType"] == "Min" and governing["Location"] == "Bottom"


def test_more_compressive_max_can_govern_over_min():
    rows = [
        _row("FINAL_X", -200_000.0, step="Max", location="Top"),
        _row("FINAL_X", -190_000.0, step="Max", location="Bottom"),
        _row("FINAL_X", -100_000.0, step="Min", location="Top"),
        _row("FINAL_X", -90_000.0, step="Min", location="Bottom"),
        *_correction_rows(),
    ]
    demand = select_ndm_demand(_request(), _bundle(rows), _binding(final_ids=("FINAL_X",)), _policy())
    assert demand.availability == NdmAvailability.RESOLVED
    assert dict(demand.trace.governing_row_identities[0])["StepType"] == "Max"


def test_step_number_none_is_preserved_not_fabricated():
    demand = select_ndm_demand(_request(), _bundle(_resolved_rows()), _binding(), _policy())
    assert demand.availability == NdmAvailability.RESOLVED
    assert all(item.step_number is None for item in demand.trace.candidate_rows)
    assert all(dict(identity)["StepNumber"] is None for identity in demand.trace.governing_row_identities)


def test_explicit_kn_to_n_conversion():
    rows = [_row("FINAL_X", -100.0, step="Max", location="Top"), _row("FINAL_Y", -90.0, step="Max", location="Top"), *_correction_rows(q_p=-20.0, s_p=-10.0, locations=("Top",))]
    demand = select_ndm_demand(_request(), _bundle(rows, unit="kN"), _binding(allowed_steps=("Max",), allowed_locations=("Top",)), _policy())
    assert demand.availability == NdmAvailability.RESOLVED
    assert demand.ndm_n == pytest.approx(82_000.0)
    assert demand.unit == "N" and demand.trace.source_unit == "kN"


def test_live_shaped_decimal_string_p_values_decode_without_mutating_raw_evidence():
    rows = [
        _row("FINAL_X", "-446.9878", step="Max", location="Top"),
        _row("FINAL_X", "-430.1250", step="Max", location="Bottom"),
        _row("FINAL_X", "-440.5000", step="Min", location="Top"),
        _row("FINAL_X", "-445.2500", step="Min", location="Bottom"),
        *_correction_rows(q_p="-20.0000", s_p="-10.0000"),
    ]
    bundle = _bundle(rows, unit="kN")
    demand = select_ndm_demand(_request(), bundle, _binding(final_ids=("FINAL_X",)), _policy())
    assert demand.availability == NdmAvailability.RESOLVED
    live = next(item for item in demand.trace.candidate_rows if item.step_type == "Max" and item.location == "Top")
    assert live.raw_p == "-446.9878"
    assert live.canonical_p_n == pytest.approx(-446_987.8)
    assert isinstance(bundle.rows[0]["P"], str)
    assert all(isinstance(trace.raw_p, str) for trace in live.q_corrections + live.s_corrections)


@pytest.mark.parametrize("bad_p", ["", "abc", "NaN", "Infinity", "+Inf", "-Inf", "1,23", True])
def test_invalid_live_p_scalars_are_rejected(bad_p):
    rows = _single_cell_rows(final_p=bad_p)
    demand = select_ndm_demand(
        _request(), _bundle(rows),
        _binding(final_ids=("FINAL_X",), allowed_steps=("Max",), allowed_locations=("Top",)),
        _policy(),
    )
    assert demand.availability == NdmAvailability.BLOCKED
    assert demand.ndm_n is None


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


def test_missing_binding_blocks():
    bundle = _bundle(_resolved_rows())
    assert select_ndm_demand(_request(), bundle, None, _policy()).availability == NdmAvailability.BLOCKED


def test_one_q_case_with_unequal_storey_q_unresolved_is_blocked():
    demand = select_ndm_demand(
        _request(), _bundle(_single_cell_rows()),
        _binding(final_ids=("FINAL_X",), allowed_steps=("Max",), allowed_locations=("Top",)),
        _policy(q_state=Ts498StoreyQState.UNEQUAL_STOREY_Q_UNRESOLVED),
    )
    assert demand.availability == NdmAvailability.BLOCKED
    assert "storey Q" in str(demand.trace.reason)


def test_multiple_q_cases_with_equal_coefficients_do_not_imply_equal_storey_q():
    binding = _binding(q_ids=("Q1", "Q2"), final_ids=("FINAL_X",), allowed_steps=("Max",), allowed_locations=("Top",))
    policy = _policy(q={"Q1": 0.5, "Q2": 0.5}, q_state=Ts498StoreyQState.UNEQUAL_STOREY_Q_UNRESOLVED)
    demand = select_ndm_demand(_request(), _bundle([]), binding, policy)
    assert demand.availability == NdmAvailability.BLOCKED


def test_explicit_equal_storey_q_reviewed_state_may_execute():
    binding = _binding(final_ids=("FINAL_X",), allowed_steps=("Max",), allowed_locations=("Top",))
    demand = select_ndm_demand(_request(), _bundle(_single_cell_rows()), binding, _policy(q_state=Ts498StoreyQState.EQUAL_STOREY_Q_REVIEWED))
    assert demand.availability == NdmAvailability.RESOLVED


def test_explicit_unequal_storey_q_reviewed_state_may_execute_with_interpretation():
    binding = _binding(final_ids=("FINAL_X",), allowed_steps=("Max",), allowed_locations=("Top",))
    policy = _policy(
        q_state=Ts498StoreyQState.UNEQUAL_STOREY_Q_REVIEWED,
        unequal_interpretation="reviewed unequal supported-storey Q_i distribution",
    )
    demand = select_ndm_demand(_request(), _bundle(_single_cell_rows()), binding, policy)
    assert demand.availability == NdmAvailability.RESOLVED


def test_unequal_storey_q_reviewed_requires_explicit_interpretation():
    binding = _binding(final_ids=("FINAL_X",), allowed_steps=("Max",), allowed_locations=("Top",))
    policy = _policy(q_state=Ts498StoreyQState.UNEQUAL_STOREY_Q_REVIEWED, unequal_interpretation=None)
    demand = select_ndm_demand(_request(), _bundle(_single_cell_rows()), binding, policy)
    assert demand.availability == NdmAvailability.BLOCKED


def test_mass_source_is_not_part_of_ts498_storey_q_contract_and_old_proxy_is_deleted():
    assert not any("mass" in name.casefold() for name in ReviewedNdmPolicy.__dataclass_fields__)
    source = inspect.getsource(ndm_module._binding_policy_reason)
    assert "q_target_coefficients.values" not in source
    assert "Mass Source" not in inspect.getsource(ReviewedNdmPolicy)


def test_w1_policy_cannot_execute_w2_request():
    request = EngineeringQuantityRequest("REQ-W2", "W2", "L1", "P1")
    demand = select_ndm_demand(request, _bundle(_resolved_rows()), _binding(), _policy())
    assert demand.availability == NdmAvailability.BLOCKED
    assert "target_component_id" in str(demand.trace.reason)


def test_policy_correct_component_wrong_story_is_blocked():
    request = EngineeringQuantityRequest("REQ-L2", "W1", "L2", "P1")
    demand = select_ndm_demand(request, _bundle(_resolved_rows()), _binding(), _policy())
    assert demand.availability == NdmAvailability.BLOCKED
    assert "target_story" in str(demand.trace.reason)


def test_policy_correct_component_story_wrong_pier_is_blocked():
    request = EngineeringQuantityRequest("REQ-P2", "W1", "L1", "P2")
    demand = select_ndm_demand(request, _bundle(_resolved_rows()), _binding(), _policy())
    assert demand.availability == NdmAvailability.BLOCKED
    assert "target_pier" in str(demand.trace.reason)


def test_reviewed_q_and_s_linear_corrections_are_reconstructable():
    rows = [_row("FINAL_X", -100_000.0, step="Max", location="Top"), *_correction_rows(locations=("Top",))]
    demand = select_ndm_demand(_request(), _bundle(rows), _binding(final_ids=("FINAL_X",), allowed_steps=("Max",), allowed_locations=("Top",)), _policy())
    assert demand.ndm_n == pytest.approx(82_000.0)
    candidate = demand.trace.candidate_rows[0]; q = candidate.q_corrections[0]; s = candidate.s_corrections[0]
    assert q.baseline_coefficient == 1.0 and q.target_coefficient == 0.5 and q.delta_p_n == pytest.approx(10_000.0)
    assert s.baseline_coefficient == 1.0 and s.target_coefficient == 0.2 and s.delta_p_n == pytest.approx(8_000.0)
    assert candidate.adjusted_p_n == pytest.approx(-82_000.0)


def test_zero_s_force_has_zero_numeric_correction_but_remains_traced():
    rows = [_row("FINAL_X", -100_000.0, location="Top"), _static("Q_CASE", -20_000.0, location="Top"), _static("S_CASE", 0.0, location="Top")]
    binding = _binding(final_ids=("FINAL_X",), allowed_steps=("Max",), allowed_locations=("Top",))
    demand = select_ndm_demand(_request(), _bundle(rows), binding, _policy())
    assert demand.availability == NdmAvailability.RESOLVED
    s = demand.trace.candidate_rows[0].s_corrections[0]
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
    rows = [
        _row("FINAL_X", -100_000.0, step="Max", location="Top"),
        _row("FINAL_X", -90_000.0, step="Min", location="Top"),
        _row("FINAL_Y", -80_000.0, step="Max", location="Top"),
        _row("FINAL_Y", -100_000.0, step="Min", location="Top"),
        *_correction_rows(locations=("Top",)),
    ]
    demand = select_ndm_demand(_request(), _bundle(rows), _binding(allowed_locations=("Top",)), _policy())
    assert demand.availability == NdmAvailability.RESOLVED and len(demand.trace.governing_row_identities) == 2


def test_full_resolved_lookup_with_no_matching_final_row_is_no_data():
    demand = select_ndm_demand(_request(), _bundle([_static("Q_CASE", -20_000.0), _static("S_CASE", -10_000.0)]), _binding(), _policy())
    assert demand.availability == NdmAvailability.NO_DATA


def test_complete_cartesian_candidate_population_resolves():
    demand = select_ndm_demand(_request(), _bundle(_resolved_rows()), _binding(), _policy())
    expected = {
        (combo, step, location)
        for combo in ("FINAL_X", "FINAL_Y")
        for step in ("Max", "Min")
        for location in ("Top", "Bottom")
    }
    actual = {(item.final_combination_id, item.step_type, item.location) for item in demand.trace.candidate_rows}
    assert demand.availability == NdmAvailability.RESOLVED
    assert actual == expected


def test_cartesian_population_missing_exactly_one_cell_is_no_data_even_when_unions_are_complete():
    rows = [
        row for row in _resolved_rows()
        if not (row.get("OutputCase") == "FINAL_Y" and row.get("StepType") == "Min" and row.get("Location") == "Bottom")
    ]
    demand = select_ndm_demand(_request(), _bundle(rows), _binding(), _policy())
    assert demand.availability == NdmAvailability.NO_DATA
    assert "FINAL_Y/Min/Bottom" in str(demand.trace.reason)


def test_full_lookup_missing_one_reviewed_final_combination_is_no_data():
    rows = [row for row in _resolved_rows() if row.get("OutputCase") != "FINAL_Y"]
    demand = select_ndm_demand(_request(), _bundle(rows), _binding(), _policy())
    assert demand.availability == NdmAvailability.NO_DATA
    assert "FINAL_Y/Max/Top" in str(demand.trace.reason)


def test_full_lookup_missing_reviewed_step_or_location_cells_is_no_data():
    no_min = [row for row in _resolved_rows() if row.get("StepType") != "Min"]
    min_demand = select_ndm_demand(_request(), _bundle(no_min), _binding(), _policy())
    assert min_demand.availability == NdmAvailability.NO_DATA
    assert "/Min/" in str(min_demand.trace.reason)
    no_bottom = [row for row in _resolved_rows() if row.get("Location") != "Bottom"]
    bottom_demand = select_ndm_demand(_request(), _bundle(no_bottom), _binding(), _policy())
    assert bottom_demand.availability == NdmAvailability.NO_DATA
    assert "/Bottom" in str(bottom_demand.trace.reason)


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


def _snapshot(component_id="W1", story="L1"):
    return FeatureSnapshot(component_type="wall", component_id=component_id, identity={"story": story, "assigned_wall_property": "WALL-P1"}, features={
        "wall_thickness_mm": _fv("wall_thickness_mm", 300.0, "mm"), "story_height_mm": _fv("story_height_mm", 3200.0, "mm"),
        "wall_body_classification": _fv("wall_body_classification", "RECTANGULAR_BODY", role="GEOMETRY_CLASSIFICATION"),
        "wall_is_basement": _fv("wall_is_basement", False, role="REGULATORY_LOCATION"), "concrete_fck_mpa": _fv("concrete_fck_mpa", 35.0, "MPa", "DESIGN_BASIS"),
    })


def _execution(rows):
    return WallExecutionEvidence(
        result_bundles={"pier_forces": _bundle(rows)},
        wall_to_pier={"W1": "P1"},
        ndm_load_binding=_binding(),
        ndm_policies_by_component_id={"W1": _policy()},
        net_section_topology_by_component={"W1": {"topology_verified": True, "section_semantics_verified": True, "gross_cross_section_area_mm2": 300_000.0, "openings": []}},
    )


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


def test_two_walls_receive_only_their_exact_component_scoped_ndm_policy():
    binding = _binding(final_ids=("FINAL_X",), allowed_steps=("Max",), allowed_locations=("Top",))
    rows = [
        *_single_cell_rows(story="L1", pier="P1"),
        *_single_cell_rows(story="L2", pier="P2"),
    ]
    execution = WallExecutionEvidence(
        result_bundles={"pier_forces": _bundle(rows)},
        wall_to_pier={"W1": "P1", "W2": "P2"},
        ndm_load_binding=binding,
        ndm_policies_by_component_id={
            "W1": _policy(q={"Q_CASE": 0.5}, target_component_id="W1", target_story="L1", target_pier="P1"),
            "W2": _policy(q={"Q_CASE": 0.25}, target_component_id="W2", target_story="L2", target_pier="P2"),
        },
        net_section_topology_by_component={
            "W1": {"topology_verified": True, "section_semantics_verified": True, "gross_cross_section_area_mm2": 300_000.0, "openings": []},
            "W2": {"topology_verified": True, "section_semantics_verified": True, "gross_cross_section_area_mm2": 300_000.0, "openings": []},
        },
    )
    run = run_wall_checks(
        _Bundle(), [_snapshot("W1", "L1"), _snapshot("W2", "L2")],
        [WALL_NET_SECTION_AXIAL_CAPACITY], execution_evidence=execution,
    )
    demands = {item.component_id: item.execution_context.values["ndm_demand"].value for item in run.check_inputs}
    assert demands["W1"] == pytest.approx(82_000.0)
    assert demands["W2"] == pytest.approx(77_000.0)
    with pytest.raises(TypeError):
        execution.ndm_policies_by_component_id["W3"] = _policy(target_component_id="W3")


def test_missing_per_component_policy_blocks_wall_execution():
    binding = _binding(final_ids=("FINAL_X",), allowed_steps=("Max",), allowed_locations=("Top",))
    execution = WallExecutionEvidence(
        result_bundles={"pier_forces": _bundle(_single_cell_rows())},
        wall_to_pier={"W1": "P1"},
        ndm_load_binding=binding,
        ndm_policies_by_component_id={},
        net_section_topology_by_component={"W1": {"topology_verified": True, "section_semantics_verified": True, "gross_cross_section_area_mm2": 300_000.0, "openings": []}},
    )
    run = run_wall_checks(_Bundle(), [_snapshot()], [WALL_NET_SECTION_AXIAL_CAPACITY], execution_evidence=execution)
    readiness = {item.context_name: item for item in run.coverage_rows[0].execution_context_readiness}
    assert readiness["ndm_demand"].status.value == "BLOCKED"
    assert run.check_results[0].status == CheckStatus.BLOCKED
    assert "Reviewed Ndm policy is missing" in run.check_results[0].messages[0]


def test_policy_mapping_key_must_equal_policy_target_component_id():
    with pytest.raises(ValueError, match="mapping key"):
        WallExecutionEvidence(ndm_policies_by_component_id={"W2": _policy(target_component_id="W1")})


def test_ndm_selector_does_not_duplicate_wall_capacity_formula():
    source = inspect.getsource(select_ndm_demand)
    assert "0.35" not in source and "net_section_area" not in source and "concrete_fck" not in source
