from __future__ import annotations

from types import SimpleNamespace
import pytest
import tbdy_engine.etabs.oapi.analysis_execution as subject
from tbdy_engine.etabs.oapi.contracts import EtabsOAPIError

class _FakeSession:
    pass

def _runtime(monkeypatch, raw):
    session = _FakeSession()
    model = SimpleNamespace(
        LoadCases=SimpleNamespace(
            ResponseSpectrum=SimpleNamespace(GetModalCase=lambda _name: raw),
        )
    )
    monkeypatch.setattr(subject, "EtabsVerifiedSession", _FakeSession)
    def fake_read(_session, function, *, operation, timeout_seconds=30.0):
        assert _session is session
        assert operation == "oapi_load_cases_response_spectrum_get_modal_case"
        return function(object(), model)
    monkeypatch.setattr(subject, "_execute_verified_read", fake_read)
    return session

def test_get_response_spectrum_modal_case_preserves_exact_live_projection(monkeypatch):
    session = _runtime(monkeypatch, ["Modal", 0])
    fact = subject.get_response_spectrum_modal_case_from_session(
        session, response_spectrum_case_name="RSX"
    )
    assert fact.success is True
    assert fact.response_spectrum_case_name == "RSX"
    assert fact.modal_case_name == "Modal"
    assert fact.return_code == 0
    assert fact.evidence_ref.startswith(subject.ANALYSIS_EXECUTION_EVIDENCE_PREFIX)

def test_get_response_spectrum_modal_case_preserves_nonzero_return(monkeypatch):
    session = _runtime(monkeypatch, ["Modal", 9])
    fact = subject.get_response_spectrum_modal_case_from_session(
        session, response_spectrum_case_name="RSX"
    )
    assert fact.success is False
    assert fact.return_code == 9

@pytest.mark.parametrize("raw", [
    None, "Modal", [], ["Modal"], ["Modal", 0, 99], ["", 0], [" Modal ", 0],
    [1, 0], ["Modal", "0"], ["Modal", True],
])
def test_get_response_spectrum_modal_case_rejects_bad_python_projection(monkeypatch, raw):
    session = _runtime(monkeypatch, raw)
    with pytest.raises(EtabsOAPIError):
        subject.get_response_spectrum_modal_case_from_session(
            session, response_spectrum_case_name="RSX"
        )
