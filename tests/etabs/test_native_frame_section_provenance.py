"""R1B native acquisition tests. All ETABS/session surfaces are offline fixtures."""
from dataclasses import replace
import json
from types import SimpleNamespace as NS

import pytest

from test_oapi_material_properties import _FakeSession, _Model, _PropMaterial
from test_native_material_provenance import owned_context
import tbdy_engine.etabs.oapi.frame_section_mechanics as subject
import tbdy_engine.application.column_a18_end_restraint as a18
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
from tbdy_engine.etabs.safety import read_session_identity


class _PropFrame:
    def __init__(self, model):
        self.model = model
        self.calls = []
        self.raw = (.4, .3, .3, .006, .0083, .0213, 1., 2., 3., 4., 5., 6., 0)
        self.after_getter = lambda: None

    def GetSectProps(self, name):
        self.calls.append(name)
        self.model.events.append("GetSectProps")
        self.after_getter()
        return self.raw


@pytest.fixture
def runtime(monkeypatch):
    session = _FakeSession()
    model = _Model(_PropMaterial())
    prop = model.PropFrame = _PropFrame(model)
    application = NS(GetOAPIVersionNumber=lambda: 2.014)
    session.identity = read_session_identity(application, model, process_id=16664,
                                             attach_strategy="OFFLINE_FIXTURE")
    session._gateway_session = object()
    model.events.clear()
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)

    def verified_read(actual, callback, *, operation, timeout_seconds):
        assert actual is session
        assert operation == "oapi_prop_frame_get_sect_props"
        assert timeout_seconds > 0
        return callback(application, model)

    monkeypatch.setattr(subject, "_execute_verified_read", verified_read)
    return session, prop


def acquire(runtime, **kwargs):
    return subject.get_frame_section_mechanics_from_session(runtime[0], section_name="S", **kwargs)


@pytest.mark.parametrize("present,triplet,unit,factor", [
    (10, (3,6,2,0), "m4", 1.), (5, (4,4,2,0), "mm4", 1.e-12),
])
def test_native_qualifies_exact_independent_outputs_with_fresh_units(runtime, monkeypatch, present, triplet, unit, factor):
    session, prop = runtime
    prop.model.present, prop.model.triplet = present, triplet
    if unit == "mm4":
        # Exercise the getter with independently verified synthetic mm state.
        # Current canonical observer's live enum allowlist remains m-only.
        def verified_mm(*args, **kwargs):
            current = read_session_identity(*args, **kwargs)
            return replace(current, units=replace(current.units, present_observation_status="OBSERVED_CONSISTENT"))
        monkeypatch.setattr(subject, "read_session_identity", verified_mm)
    original = prop.raw
    fact = acquire(runtime)
    assert prop.calls == ["S"]
    assert fact.raw_response == original
    assert (fact.inertia_22, fact.inertia_33) == original[4:6]
    assert [p.output_key for p in fact.unit_provenance] == ["I22", "I33"]
    assert len({p.evidence_ref for p in fact.unit_provenance}) == 2
    events = prop.model.events
    call = events.index("GetSectProps")
    for side in (events[:call], events[call+1:]):
        assert side.count("GetPresentUnits_2") == side.count("GetModelFilename") == 1
    for key, axis, index in (("I22","M2",4), ("I33","M3",5)):
        p = fact.source_unit_for(key, "L4")
        assert p.source_unit == unit
        assert p.authority_ref == "COLUMN_R1_GETSECTPROPS_PRESENT_L4_POLICY_V1"
        assert p.authority_kind == "REVIEWED_PROPERTY_SOURCE_SEMANTICS"
        assert p.source_call == "SapModel.PropFrame.GetSectProps"
        assert p.subject_key == "S"
        assert p.source_model_ref == fact.source_model_ref == session.identity.model_full_path
        assert p.session_ref == fact.session_ref == "etabs-session:pid:16664"
        assert p.capture_ref == fact.capture_ref and p.raw_response_ref == fact.raw_response_ref
        assert p.unit_state_before == p.unit_state_after
        assert json.loads(p.unit_state_before)["active_identity"]["units"]["present_units"] == present
        member = NS(base_fact=NS(source_model_ref=fact.source_model_ref,
                                session_provenance_ref=fact.session_ref), section_mechanics=fact)
        assert a18._inertia_m4(member, "F1", axis)[0] == pytest.approx(original[index]*factor, abs=1.e-25)
    assert not prop.model.PropMaterial.calls  # E/G cannot authorize inertia.


@pytest.mark.parametrize("after", [False, True])
def test_missing_fresh_observation_fails_at_each_side(runtime, after):
    def missing():
        runtime[1].model.present = None
        runtime[1].model.triplet = None
    if after:
        runtime[1].after_getter = missing
    else:
        missing()
    with pytest.raises(EtabsOAPIError, match="UNIT_UNQUALIFIED"):
        acquire(runtime)
    assert len(runtime[1].calls) == int(after)


@pytest.mark.parametrize("change,reason", [
    ("unit", "CAPTURE_STATE_DRIFT"), ("source", "ACTIVE_MODEL_MISMATCH"),
    ("session", "SESSION_MISMATCH"), ("gateway", "SESSION_MISMATCH"),
    ("version", "SESSION_MISMATCH"), ("lock", "CAPTURE_STATE_DRIFT"),
])
def test_state_drift_rejects_after_exactly_one_getter(runtime, change, reason):
    session, prop = runtime
    def drift():
        if change == "unit":
            prop.model.present, prop.model.triplet = 6, (4,6,2,0)
        elif change == "source":
            prop.model.filename = "foreign.edb"
        elif change == "session":
            session.identity = replace(session.identity, process_id=20000)
        elif change == "gateway":
            session._gateway_session = object()
        elif change == "version":
            prop.model.GetVersion = lambda: ("24.0.0", 0., 0)
        else:
            prop.model.GetModelIsLocked = lambda: False
    prop.after_getter = drift
    with pytest.raises(EtabsOAPIError, match=reason):
        acquire(runtime)
    assert prop.calls == ["S"]


@pytest.mark.parametrize("change", [{"program_version":"24.0.0"}, {"program_api_version":3.0}])
def test_unsupported_version_rejects_before_getter(runtime, change):
    runtime[0].identity = replace(runtime[0].identity, **change)
    with pytest.raises(EtabsOAPIError, match="UNREVIEWED_COMPATIBILITY_SCOPE"):
        acquire(runtime)
    assert not runtime[1].calls


def test_nonzero_raw_result_has_no_provenance(runtime):
    runtime[1].raw = (*runtime[1].raw[:-1], 4)
    fact = acquire(runtime)
    assert fact.raw_response == runtime[1].raw and fact.return_code == 4
    assert not fact.unit_provenance
    for key in ("I22", "I33"):
        with pytest.raises(EtabsOAPIError, match="MISSING_SUCCESSFUL_RAW_RESPONSE"):
            fact.source_unit_for(key, "L4")


@pytest.mark.parametrize("key", ["I22", "I33"])
@pytest.mark.parametrize("change", [
    "missing", "duplicate", {"output_key":"Torsion"}, {"dimension":"L"},
    {"source_call":"SapModel.PropMaterial.GetMPIsotropic"},
    {"source_call":"SapModel.DatabaseTables.GetTableForDisplayArray"},
    {"source_model_ref":"foreign:source"}, {"session_ref":"foreign:session"},
    {"capture_ref":"foreign:capture"}, {"raw_response_ref":"foreign:raw"},
])
def test_native_bindings_fail_closed_independently(runtime, key, change):
    fact = acquire(runtime)
    own = fact.source_unit_for(key, "L4")
    if change == "missing":
        bindings = tuple(p for p in fact.unit_provenance if p.output_key != key)
    elif change == "duplicate":
        bindings = (*fact.unit_provenance, own)
    else:
        bindings = tuple(replace(p, **change) if p.output_key == key else p for p in fact.unit_provenance)
    broken = replace(fact, unit_provenance=bindings)
    with pytest.raises(EtabsOAPIError, match="UNIT_UNQUALIFIED"):
        broken.source_unit_for(key, "L4")
    opposite = "I33" if key == "I22" else "I22"
    assert broken.source_unit_for(opposite, "L4") == fact.source_unit_for(opposite, "L4")


def test_owned_scratch_preserves_trusted_engineering_source_and_A18(runtime):
    context, scratch = owned_context(runtime)
    fact = acquire(runtime, context=context, owned_scratch=scratch)
    assert fact.source_model_ref == context.source_model_identity.source_model_ref
    assert fact.session_ref == context.session_provenance_ref
    member = NS(base_fact=NS(source_model_ref=fact.source_model_ref,
                            session_provenance_ref=fact.session_ref), section_mechanics=fact)
    for key, axis in (("I22","M2"), ("I33","M3")):
        state = json.loads(fact.source_unit_for(key, "L4").unit_state_before)
        assert state["active_identity"]["model_full_path"] == scratch.scratch_path
        assert state["same_capture_bridge"]["ownership_proof_ref"] == scratch.ownership_proof_ref
        assert state["same_capture_bridge"]["acquisition_context_ref"] == context.acquisition_context_ref
        assert a18._inertia_m4(member, "F1", axis)[0] > 0


@pytest.mark.parametrize("field", ["source", "session", "scratch", "ownership", "capture"])
def test_owned_source_session_scratch_bridge_drift_fails(runtime, field):
    context, scratch = owned_context(runtime)
    def drift():
        if field == "source":
            object.__setattr__(scratch, "source_model_identity", replace(scratch.source_model_identity, source_model_ref="foreign:source"))
        elif field == "session":
            object.__setattr__(context, "session_provenance_ref", "foreign:session")
        elif field == "scratch":
            object.__setattr__(scratch, "scratch_path", r"C:\foreign.edb")
        elif field == "ownership":
            object.__setattr__(scratch, "ownership_proof_ref", "foreign:ownership")
        else:
            object.__setattr__(context, "acquisition_context_ref", "foreign:capture")
    runtime[1].after_getter = drift
    with pytest.raises(EtabsOAPIError, match="OWNED_CAPTURE_CONTEXT_DRIFT"):
        acquire(runtime, context=context, owned_scratch=scratch)
    assert runtime[1].calls == ["S"]


@pytest.mark.parametrize("raw", [0, (1.,)*12, (1.,)*14, (1.,)*12+(False,), (1.,)*4+(float("nan"),)+(1.,)*7+(0,)])
def test_unsupported_raw_ABI_fails_without_provenance(runtime, raw):
    runtime[1].raw = raw
    with pytest.raises(EtabsOAPIError, match="ABI shape"):
        acquire(runtime)


def test_actual_observer_rejects_mm_outside_current_verified_enum_allowlist(runtime):
    runtime[1].model.present, runtime[1].model.triplet = 5, (4,4,2,0)
    with pytest.raises(EtabsOAPIError, match="MISSING_PRESENT_UNIT_OBSERVATION"):
        acquire(runtime)
    assert not runtime[1].calls


def test_each_call_has_fresh_capture_and_exact_same_raw_reference(runtime):
    first, second = acquire(runtime), acquire(runtime)
    assert runtime[1].calls == ["S", "S"]
    assert first.capture_ref != second.capture_ref
    assert first.raw_response_ref == second.raw_response_ref
    assert first.evidence_ref != second.evidence_ref


@pytest.mark.parametrize("change,reason", [
    ("source", "SOURCE_MODEL_MISMATCH"), ("session", "SESSION_MISMATCH"),
    ("scratch", "ACTIVE_MODEL_MISMATCH"), ("missing", "MISSING_OWNED_CAPTURE_CONTEXT"),
])
def test_foreign_or_incomplete_owned_bridge_blocks_before_getter(runtime, change, reason):
    context, scratch = owned_context(runtime)
    if change == "source":
        object.__setattr__(scratch,"source_model_identity",replace(scratch.source_model_identity,source_model_ref="foreign:source"))
    elif change == "session":
        object.__setattr__(context,"verified_session",object())
    elif change == "scratch":
        object.__setattr__(scratch,"scratch_path",r"C:\foreign.edb")
    else:
        scratch = None
    with pytest.raises(EtabsOAPIError,match=reason):
        acquire(runtime,context=context,owned_scratch=scratch)
    assert not runtime[1].calls


@pytest.mark.parametrize("pid", [None, 0, -1, True])
def test_missing_exact_native_session_identity_prevents_getter(runtime, pid):
    runtime[0].identity = replace(runtime[0].identity, process_id=pid)
    with pytest.raises(EtabsOAPIError, match="MISSING_SESSION_IDENTITY"):
        acquire(runtime)
    assert not runtime[1].calls
