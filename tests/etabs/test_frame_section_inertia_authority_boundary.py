"""R1 authority boundary: raw native seam stays unqualified pending review.

Qualified DTOs below have independent OFFLINE_SYNTHETIC_1 authority only.
They test existing contracts/A18, not installed CSI source-unit semantics.
"""
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

import tbdy_engine.etabs.oapi.frame_section_mechanics as subject
import tbdy_engine.application.column_a18_end_restraint as a18
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from unit_contract_fixtures import binding, MODEL, SESSION


RAW = (.4, .3, .3, .006, .008333333333333333, .021333333333333336,
       1., 1., 1., 1., 1., 1., 0)


def synthetic_fact():
    fact = subject.FrameSectionMechanicsFact(
        "S", *RAW[:6], 0, raw_response=RAW, source_model_ref=MODEL,
        session_ref=SESSION, capture_ref="synthetic:inertia-capture",
    )
    return replace(fact, unit_provenance=tuple(
        binding(fact.source_call, fact.section_name, key, "L4", "m4",
                fact.raw_response_ref, model=MODEL, session=SESSION,
                capture=fact.capture_ref) for key in ("I22", "I33")
    ))


@pytest.mark.parametrize("present_length", [4, 6])
def test_current_native_seam_keeps_both_outputs_raw_without_source_authority(monkeypatch, present_length):
    calls = []

    class FakeSession:
        identity = NS(model_full_path="synthetic:active-scratch", process_id=123,
                      units=NS(as_dict=lambda: {"present_length_unit": present_length,
                                               "database_length_unit": 6}))

    class PropFrame:
        def GetSectProps(self, name):
            calls.append(name)
            return RAW

        def __getattr__(self, name):
            raise AssertionError(f"forbidden native call: {name}")

    session = FakeSession()
    monkeypatch.setattr(subject, "EtabsVerifiedSession", FakeSession)

    def verified_read(actual_session, callback, **kwargs):
        assert actual_session is session
        assert kwargs["operation"] == "oapi_prop_frame_get_sect_props"
        return callback(object(), NS(PropFrame=PropFrame()))

    monkeypatch.setattr(subject, "_execute_verified_read", verified_read)
    fact = subject.get_frame_section_mechanics_from_session(session, section_name="S")
    assert calls == ["S"]
    assert fact.raw_response == RAW
    assert fact.inertia_22 == RAW[4] and fact.inertia_33 == RAW[5]
    assert fact.unit_provenance == ()
    assert fact.unit_observation is not None  # Cached context cannot issue authority.
    for key in ("I22", "I33"):
        with pytest.raises(EtabsOAPIError, match="MISSING_OR_DUPLICATE_OUTPUT_BINDING"):
            fact.source_unit_for(key, "L4")


def test_synthetic_bindings_are_independent_and_raw_is_unchanged():
    fact = synthetic_fact()
    i22 = fact.source_unit_for("I22", "L4")
    i33 = fact.source_unit_for("I33", "L4")
    assert i22.evidence_ref != i33.evidence_ref
    assert (i22.output_key, i33.output_key) == ("I22", "I33")
    assert i22.authority_version == i33.authority_version == "OFFLINE_SYNTHETIC_1"
    assert fact.raw_response == RAW
    reordered = replace(fact, unit_provenance=tuple(reversed(fact.unit_provenance)))
    assert reordered.source_unit_for("I22", "L4") == i22
    assert reordered.source_unit_for("I33", "L4") == i33


@pytest.mark.parametrize("key,axis,index", [("I22", "M2", 4), ("I33", "M3", 5)])
def test_A18_consumes_each_exact_own_synthetic_binding(key, axis, index):
    fact = synthetic_fact()
    member = NS(base_fact=NS(source_model_ref=MODEL, session_provenance_ref=SESSION,
                            present_length_unit=4), section_mechanics=fact)
    assert a18._inertia_m4(member, "F1", axis)[0] == pytest.approx(RAW[index])
    # Valid base enums and the opposite output cannot replace a missing binding.
    member.section_mechanics = replace(fact, unit_provenance=tuple(
        p for p in fact.unit_provenance if p.output_key != key))
    with pytest.raises(a18._Unresolved, match="MISSING_OR_DUPLICATE_OUTPUT_BINDING"):
        a18._inertia_m4(member, "F1", axis)


@pytest.mark.parametrize("key", ["I22", "I33"])
@pytest.mark.parametrize("change", [
    {"source_call": "SapModel.PropMaterial.GetMPIsotropic"},
    {"source_call": "SapModel.DatabaseTables.GetAllFieldsInTable"},
    {"subject_key": "OTHER_SECTION"}, {"output_key": "Torsion"},
    {"dimension": "L"}, {"source_model_ref": "foreign:model"},
    {"session_ref": "foreign:session"}, {"capture_ref": "foreign:capture"},
    {"raw_response_ref": "foreign:raw"}, {"unit_state_before": None},
    {"unit_state_after": None}, {"unit_state_after": "changed-unit-state"},
    {"return_code": 1}, {"authority_kind": "REPORT_DEFAULT"},
    {"qualification": "UNIT_UNQUALIFIED"},
])
def test_each_synthetic_binding_fails_closed_for_wrong_identity_or_state(key, change):
    fact = synthetic_fact()
    changed = replace(fact, unit_provenance=tuple(
        replace(p, **change) if p.output_key == key else p for p in fact.unit_provenance))
    with pytest.raises(EtabsOAPIError, match="UNIT_UNQUALIFIED"):
        changed.source_unit_for(key, "L4")


@pytest.mark.parametrize("key,axis", [("I22", "M2"), ("I33", "M3")])
def test_duplicate_binding_is_rejected_by_fact_and_A18(key, axis):
    fact = synthetic_fact()
    own = fact.source_unit_for(key, "L4")
    duplicated = replace(fact, unit_provenance=(*fact.unit_provenance, own))
    with pytest.raises(EtabsOAPIError, match="MISSING_OR_DUPLICATE_OUTPUT_BINDING"):
        duplicated.source_unit_for(key, "L4")
    member = NS(base_fact=NS(source_model_ref=MODEL, session_provenance_ref=SESSION),
                section_mechanics=duplicated)
    with pytest.raises(a18._Unresolved, match="MISSING_OR_DUPLICATE_OUTPUT_BINDING"):
        a18._inertia_m4(member, "F1", axis)


@pytest.mark.parametrize("axis", ["M2", "M3"])
@pytest.mark.parametrize("bad_unit", ["mm", "N/m2", "", "unknown"])
def test_A18_cannot_take_another_property_dimension_or_default(axis, bad_unit):
    fact = synthetic_fact()
    changed = replace(fact, unit_provenance=tuple(
        replace(p, source_unit=bad_unit) for p in fact.unit_provenance))
    member = NS(base_fact=NS(source_model_ref=MODEL, session_provenance_ref=SESSION,
                            present_length_unit=6), section_mechanics=changed)
    with pytest.raises(a18._Unresolved, match="UNIT_UNQUALIFIED"):
        a18._inertia_m4(member, "F1", axis)


def test_provenance_changes_identity_without_changing_raw_tuple():
    original = synthetic_fact()
    changed = replace(original, unit_provenance=tuple(
        replace(p, authority_ref="fixture:independent-review-2") for p in original.unit_provenance))
    assert changed.raw_response == original.raw_response == RAW
    assert changed.raw_response_ref == original.raw_response_ref
    assert changed.evidence_ref != original.evidence_ref
