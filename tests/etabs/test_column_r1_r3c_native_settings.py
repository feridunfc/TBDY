"""Exact factual getter acquisition, no native ETABS runtime."""
from dataclasses import replace
from types import SimpleNamespace as NS
import pytest
from test_oapi_material_properties import _FakeSession, _Model, _PropMaterial
from tbdy_engine.etabs.safety import read_session_identity
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError
import tbdy_engine.etabs.oapi.analysis_execution as owner

RAW = {
    "GetModalCase": ("Modal", 0),
    "GetLoads": (1, ["U2"], ["actual-function"], [9810.], ["GLOBAL"], [27.], 0),
    "GetModalComb_1": (1, 0., 0., 2, 0., 0),
    "GetDirComb": (3, .3, 0),
    "GetDampType": (1, 0), "GetDampConstant": (.05, 0),
    "GetDampInterpolated": (0, 0, [], [], 1),
    "GetDampProportional": (0, 0., 0., 0., 0., 0., 0., 1),
    "GetDampOverrides": (1, [2], [.07], 0),
    "GetEccentricity": (.05, 0),
    "GetDiaphragmEccentricityOverride": (1, ["D1"], [.08], 0),
}

@pytest.fixture
def native(monkeypatch):
    session = _FakeSession()
    model = _Model(_PropMaterial())
    app = NS(GetOAPIVersionNumber=lambda: 2.014)
    session.identity = read_session_identity(app, model, process_id=16664, attach_strategy="OFFLINE_FIXTURE")
    session._gateway_session = object()
    calls = []
    hook = {"after": lambda: None}
    def getter(method):
        def read(case):
            calls.append((method, case))
            if method == "GetLoads": hook["after"]()
            return RAW[method]
        return read
    model.LoadCases = NS(ResponseSpectrum=NS(**{m:getter(m) for m in RAW}))
    monkeypatch.setattr(owner, "EtabsVerifiedSession", _FakeSession)
    monkeypatch.setattr(owner, "_execute_verified_read", lambda s,f,**kw: f(app, model))
    model.events.clear()
    return session, model, calls, hook

def test_real_factual_settings_preserve_direction_codes_units_raw_and_fresh_observations(native):
    session, model, calls, _ = native
    fact = owner.get_response_spectrum_settings_from_session(session, case_name="RSX")
    assert calls == [(m,"RSX") for m in RAW]
    assert fact.source_model_ref == session.identity.model_full_path
    assert fact.session_ref == "etabs-session:pid:16664"
    assert fact.observation_before == fact.observation_after
    assert model.events.count("GetModelFilename") == model.events.count("GetPresentUnits_2") == 2
    assert [f.raw_response for f in fact.settings] == list(RAW.values())
    loads = dict(next(x.outputs for x in fact.settings if x.method == "GetLoads"))
    assert loads["LoadName"] == ["U2"] and loads["Ang"] == [27.]  # RSX doesn't infer U1/X.
    assert loads["SF"] == [9810.]
    assert not fact.analysis_result_qualified
    assert fact.evidence_ref.startswith("etabs-analysis-execution:sha256:")
    failed = next(x for x in fact.settings if x.method == "GetDampInterpolated")
    assert not failed.success and failed.outputs == () and failed.raw_response == RAW[failed.method]
    second = owner.get_response_spectrum_settings_from_session(session, case_name="RSX")
    assert second.capture_ref != fact.capture_ref and second.evidence_ref != fact.evidence_ref

@pytest.mark.parametrize("drift", ["source", "session", "unit", "gateway", "version"])
def test_drift_fails_closed(native, drift):
    session, model, _, hook = native
    def change():
        if drift == "source": model.filename = "different.edb"
        elif drift == "unit": model.present, model.triplet = 6, (4,6,2,0)
        elif drift == "session": session.identity = replace(session.identity, process_id=17777)
        elif drift == "gateway": session._gateway_session = object()
        else: session.identity = replace(session.identity, program_version="24.0.0")
    hook["after"] = change
    with pytest.raises(EtabsOAPIError, match="drift"):
        owner.get_response_spectrum_settings_from_session(session, case_name="RSX")

@pytest.mark.parametrize("kwargs", [{"program_version":"22.0.0"},{"program_api_version":2.013}])
def test_unsupported_version_does_not_get_settings(native, kwargs):
    session, _, calls, _ = native
    session.identity = replace(session.identity, **kwargs)
    with pytest.raises(EtabsOAPIError, match="unsupported"):
        owner.get_response_spectrum_settings_from_session(session, case_name="RSY")
    assert calls == []

@pytest.mark.parametrize("method,raw", [
    ("GetLoads", (2,["U1"],["F"],[1.],["GLOBAL"],[0.],0)),
    ("GetLoads", (1,["U1"],["F"],[True],["GLOBAL"],[0.],0)),
    ("GetLoads", (True,[],[],[],[],[],0)),
    ("GetModalComb_1", (1,0.,0.,True,0.,0)),
    ("GetDirComb", (3,float("nan"),0)),
    ("GetDampConstant", (.05,)),
    ("GetDampOverrides", (1,[0],[.05],0)),
])
def test_invalid_exact_abi_is_not_qualified(method, raw):
    with pytest.raises(EtabsOAPIError): owner._decode_response_spectrum_setting(method,raw)


def test_zero_authoritative_count_retains_null_safearrays():
    raw=(0,None,None,0)
    fact=owner._decode_response_spectrum_setting("GetDampOverrides",raw)
    assert fact.success and fact.raw_response == raw and dict(fact.outputs)["Mode"] is None

def test_unavailable_exact_getter_has_specific_diagnostic(native):
    session,model,_,_=native
    model.LoadCases.ResponseSpectrum.GetModalComb_1=None
    with pytest.raises(EtabsOAPIError,match="GetModalComb_1: getter unavailable"):
        owner.get_response_spectrum_settings_from_session(session,case_name="RSX")
