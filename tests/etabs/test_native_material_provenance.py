"""Q1N acquisition wiring and fail-closed tests; all native surfaces are fixtures."""
from dataclasses import replace
from decimal import Decimal
import json

import pytest

from test_oapi_material_properties import runtime
import tbdy_engine.etabs.oapi.material_properties as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.providers.etabs_frame_flexural_base_provider import (
    _property_stress_to_mpa, FrameFlexuralBaseFactError,
)


def acquire(runtime, **kwargs):
    session, prop = runtime
    return subject.get_isotropic_material_properties_from_session(session, material_name="C30", **kwargs)


def test_fresh_native_getters_keep_capture_proofs_and_share_a4_semantics(runtime):
    from tbdy_engine.application.column_public_a5 import _isotropic_material_continuity_key

    pre, post = acquire(runtime), acquire(runtime)
    assert runtime[1].calls == [("C30", 0.), ("C30", 0.)]
    assert pre.capture_ref != post.capture_ref
    assert pre.evidence_ref != post.evidence_ref
    assert all(p.evidence_ref != q.evidence_ref for p, q in zip(pre.unit_provenance, post.unit_provenance))
    assert _isotropic_material_continuity_key(pre) == _isotropic_material_continuity_key(post)


@pytest.mark.parametrize("key", ["E", "G"])
def test_missing_binding_reproduces_the_A3_failure(runtime, key):
    fact = replace(acquire(runtime), unit_provenance=())
    with pytest.raises(FrameFlexuralBaseFactError, match="UNIT_UNQUALIFIED:UNIT_UNQUALIFIED:MISSING_OR_DUPLICATE_OUTPUT_BINDING"):
        _property_stress_to_mpa(fact, key, source_model_ref=fact.source_model_ref,
                               session_ref=fact.session_ref)


@pytest.mark.parametrize("present,triplet,unit", [(10,(3,6,2,0),"N/m2"),(6,(4,6,2,0),"kN/m2")])
def test_real_acquisition_seam_qualifies_independent_E_G_with_raw_unchanged(runtime, present, triplet, unit):
    session, prop = runtime
    prop.model.present, prop.model.triplet = present, triplet
    # Cached units still contain N/m; qualification must use fresh observations.
    original = prop.raw
    fact = acquire(runtime)
    assert prop.calls == [("C30",0.)]
    events = prop.model.events
    call = events.index("GetMPIsotropic")
    assert events[:call].count("GetPresentUnits_2") == 1
    assert events[call+1:].count("GetPresentUnits_2") == 1
    assert events[:call].count("GetModelFilename") == 1
    assert events[call+1:].count("GetModelFilename") == 1
    assert fact.raw_response == original
    assert fact.modulus_of_elasticity == original[0] and fact.shear_modulus == original[3]
    assert [p.output_key for p in fact.unit_provenance] == ["E","G"]
    assert len({p.evidence_ref for p in fact.unit_provenance}) == 2
    for key in ("E","G"):
        p = fact.source_unit_for(key,"F/L2")
        assert p.qualification == "QUALIFIED" and p.source_unit == unit
        assert p.capture_ref == fact.capture_ref and p.raw_response_ref == fact.raw_response_ref
        assert p.authority_ref == subject.ISOTROPIC_SOURCE_AUTHORITY_REF
        assert "PROJECT_REVIEWED" in p.authority_version
        assert json.loads(p.unit_state_before)["active_identity"]["units"]["present_units"] == present
    # Unit-specific conversion is downstream only; no table property involved.
    expected = Decimal("30") if unit == "N/m2" else Decimal("30000")
    assert _property_stress_to_mpa(fact,"E",source_model_ref=fact.source_model_ref,
                                 session_ref=fact.session_ref) == expected


@pytest.mark.parametrize("after", [False,True])
def test_missing_observations_fail_closed_at_the_required_side(runtime, after):
    _, prop = runtime
    def missing():
        prop.model.present = None
        prop.model.triplet = None
    if after:
        prop.after_getter = missing
    else:
        missing()
    with pytest.raises(EtabsOAPIError, match="UNIT_UNQUALIFIED"):
        acquire(runtime)
    assert len(prop.calls) == int(after)


@pytest.mark.parametrize("change,reason", [
    ("units","CAPTURE_STATE_DRIFT"), ("model","ACTIVE_MODEL_MISMATCH"),
    ("session","SESSION_MISMATCH"), ("gateway","SESSION_MISMATCH"),
])
def test_after_getter_drift_never_issues_provenance(runtime, change, reason):
    session, prop = runtime
    def drift():
        if change == "units":
            prop.model.present, prop.model.triplet = 6,(4,6,2,0)
        elif change == "model":
            prop.model.filename = "foreign.edb"
        elif change == "session":
            session.identity = replace(session.identity,process_id=20000)
        else:
            session._gateway_session = object()
    prop.after_getter = drift
    with pytest.raises(EtabsOAPIError, match=reason):
        acquire(runtime)
    assert len(prop.calls) == 1


def test_foreign_active_source_blocks_before_getter(runtime):
    _, prop = runtime
    prop.model.filename = "foreign.edb"
    with pytest.raises(EtabsOAPIError, match="ACTIVE_MODEL_MISMATCH"):
        acquire(runtime)
    assert not prop.calls


@pytest.mark.parametrize("change",[{"program_version":"24.0.0"},{"program_api_version":3.0}])
def test_reviewed_project_policy_is_not_a_generic_version_default(runtime,change):
    session,prop = runtime
    session.identity = replace(session.identity,**change)
    with pytest.raises(EtabsOAPIError,match="UNREVIEWED_COMPATIBILITY_SCOPE"):
        acquire(runtime)
    assert not prop.calls


def test_nonzero_getter_remains_raw_but_cannot_qualify(runtime):
    _, prop = runtime
    prop.raw = (*prop.raw[:4],4)
    fact = acquire(runtime)
    assert fact.raw_response == prop.raw and fact.return_code == 4
    assert not fact.unit_provenance
    for key in ("E","G"):
        with pytest.raises(EtabsOAPIError,match="MISSING_SUCCESSFUL_RAW_RESPONSE"):
            fact.source_unit_for(key,"F/L2")


@pytest.mark.parametrize("field,value", [
    ("source_model_ref","foreign:model"),("session_ref","foreign:session"),
    ("capture_ref","foreign:capture"),("raw_response_ref","foreign:raw"),
])
@pytest.mark.parametrize("key",["E","G"])
def test_each_binding_rejects_foreign_context(runtime, field, value, key):
    fact = acquire(runtime)
    bindings = tuple(replace(p,**{field:value}) if p.output_key==key else p for p in fact.unit_provenance)
    fact = replace(fact,unit_provenance=bindings)
    with pytest.raises(EtabsOAPIError,match="MISMATCH"):
        fact.source_unit_for(key,"F/L2")


@pytest.mark.parametrize("key",["E","G"])
def test_missing_one_binding_does_not_borrow_the_other(runtime,key):
    fact = acquire(runtime)
    fact = replace(fact,unit_provenance=tuple(p for p in fact.unit_provenance if p.output_key!=key))
    with pytest.raises(EtabsOAPIError,match="MISSING_OR_DUPLICATE_OUTPUT_BINDING"):
        fact.source_unit_for(key,"F/L2")


def test_unsupported_present_context_never_uses_database_or_report_default(runtime):
    _, prop = runtime
    prop.model.present, prop.model.triplet = 8,(5,6,2,0)
    with pytest.raises(EtabsOAPIError,match="UNIT_UNQUALIFIED"):
        acquire(runtime)
    assert not prop.calls  # Database remains the valid kN/m fixture.


@pytest.mark.parametrize("key",["E","G"])
def test_unsupported_stress_converter_stays_fail_closed(runtime,key):
    fact = acquire(runtime)
    fact = replace(fact,unit_provenance=tuple(replace(p,source_unit="kN/mm2") for p in fact.unit_provenance))
    with pytest.raises(FrameFlexuralBaseFactError,match="UNKNOWN_OR_WRONG_DIMENSION_UNIT"):
        _property_stress_to_mpa(fact,key,source_model_ref=fact.source_model_ref,session_ref=fact.session_ref)


def owned_context(runtime):
    """Synthetic factory-type fixtures; no ownership lifecycle or COM executes."""
    from tbdy_engine.integration.live_etabs_acquisition_context import TrustedLiveAcquisitionContext, SourceModelIdentity
    from tbdy_engine.integration.etabs_scratch_lifecycle import OwnedScratchContext
    session, prop = runtime
    source = SourceModelIdentity("synthetic:source","synthetic:fingerprint",r"c:\synthetic\source.edb")
    context = object.__new__(TrustedLiveAcquisitionContext)
    for k,v in dict(verified_session=session,source_model_identity=source,
                    session_provenance_ref="synthetic:trusted-session",acquisition_context_ref="synthetic:acquisition").items():
        object.__setattr__(context,k,v)
    scratch = object.__new__(OwnedScratchContext)
    for k,v in dict(source_model_identity=source,scratch_path=r"C:\synthetic\scratch.edb",
                    ownership_proof_ref="synthetic:ownership").items():
        object.__setattr__(scratch,k,v)
    prop.model.filename = "scratch.edb"
    return context,scratch


def test_owned_scratch_origin_bridges_to_the_existing_A3_consumer(runtime):
    context,scratch = owned_context(runtime)
    fact = acquire(runtime,context=context,owned_scratch=scratch)
    assert fact.source_model_ref == context.source_model_identity.source_model_ref
    assert fact.session_ref == context.session_provenance_ref
    for key in ("E","G"):
        p = fact.source_unit_for(key,"F/L2")
        state = json.loads(p.unit_state_before)
        assert state["active_identity"]["model_full_path"] == scratch.scratch_path
        assert state["same_capture_bridge"]["ownership_proof_ref"] == scratch.ownership_proof_ref
        assert state["same_capture_bridge"]["acquisition_context_ref"] == context.acquisition_context_ref
        assert _property_stress_to_mpa(fact,key,source_model_ref=fact.source_model_ref,
                                       session_ref=fact.session_ref) > 0


@pytest.mark.parametrize("change,reason",[("source","SOURCE_MODEL_MISMATCH"),("session","SESSION_MISMATCH"),("scratch","ACTIVE_MODEL_MISMATCH"),("missing","MISSING_OWNED_CAPTURE_CONTEXT")])
def test_owned_context_rejects_foreign_or_incomplete_origin(runtime,change,reason):
    context,scratch = owned_context(runtime)
    if change=="source":
        object.__setattr__(scratch,"source_model_identity",replace(scratch.source_model_identity,source_model_ref="foreign:source"))
    elif change=="session":
        object.__setattr__(context,"verified_session",object())
    elif change=="scratch":
        object.__setattr__(scratch,"scratch_path",r"C:\foreign.edb")
    else:
        scratch=None
    with pytest.raises(EtabsOAPIError,match=reason):
        acquire(runtime,context=context,owned_scratch=scratch)
    assert not runtime[1].calls
