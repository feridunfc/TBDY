from __future__ import annotations

from types import SimpleNamespace
import pytest
import tbdy_engine.integration.etabs_analysis_execution as subject
from tbdy_engine.etabs.oapi.analysis_execution import (
    DefinedAnalysisCasePopulationFact,
    EtabsRuntimeVersionFact,
    LoadCaseTypeRuntimeFact,
    ResponseSpectrumModalCaseFact,
)

def _resolve(monkeypatch, *, requested, defined, case_types, slots, modal_bindings, modal_return_codes=None):
    session = object()
    context = SimpleNamespace(verified_session=session)
    modal_calls = []
    modal_return_codes = dict(modal_return_codes or {})
    monkeypatch.setattr(
        subject, "get_etabs_runtime_version_fact_from_session",
        lambda _session, timeout_seconds=30.0: EtabsRuntimeVersionFact(
            program_version="23.2.0", internal_version_number=0.0, return_code=0,
        )
    )
    def type_fact(_session, *, case_name, timeout_seconds=30.0):
        return LoadCaseTypeRuntimeFact(
            case_name=case_name,
            case_type=case_types.get(case_name, 1),
            sub_type=0,
            design_type=8 if case_name == "Modal" else 1,
            design_type_option=0,
            runtime_auto_slot_value=slots.get(case_name, 0),
            return_code=0,
        )
    monkeypatch.setattr(subject, "get_load_case_type_runtime_fact_from_session", type_fact)
    def modal_fact(_session, *, response_spectrum_case_name, timeout_seconds=30.0):
        modal_calls.append(response_spectrum_case_name)
        return ResponseSpectrumModalCaseFact(
            response_spectrum_case_name=response_spectrum_case_name,
            modal_case_name=modal_bindings[response_spectrum_case_name],
            return_code=modal_return_codes.get(response_spectrum_case_name, 0),
        )
    monkeypatch.setattr(subject, "get_response_spectrum_modal_case_from_session", modal_fact)
    attempt = subject.AnalysisExecutionAttempt(
        attempt_ref="analysis-execution-attempt:test",
        generation_ref="analysis-generation:test",
    )
    resolution = subject._resolve_runtime_execution_scope(
        context=context,
        requested_case_names=requested,
        defined_cases=DefinedAnalysisCasePopulationFact(case_names=tuple(defined), return_code=0),
        timeout_seconds=30.0,
        attempt=attempt,
    )
    return resolution, modal_calls

def _full_runtime():
    defined = (
        "EX", "Modal", "RSX", "RSY", "~ChineseX", "~ChineseY", "~LLRF",
        "~Static+EccRSX", "~StaticRSX", "~TorsionRSX",
    )
    case_types = {"RSX": 4, "RSY": 4, "Modal": 3}
    slots = {
        "~ChineseX": 6, "~ChineseY": 7, "~LLRF": 5,
        "~Static+EccRSX": 10, "~StaticRSX": 10, "~TorsionRSX": 3,
    }
    modal_bindings = {"RSX": "Modal", "RSY": "Modal"}
    return defined, case_types, slots, modal_bindings

def test_complete_response_spectrum_scope_promotes_runtime_closure_to_dependencies(monkeypatch):
    defined, case_types, slots, modal_bindings = _full_runtime()
    resolution, modal_calls = _resolve(
        monkeypatch, requested=("EX", "RSX", "RSY"), defined=defined,
        case_types=case_types, slots=slots, modal_bindings=modal_bindings,
    )
    assert resolution.scope.case_names == ("EX", "RSX", "RSY")
    assert resolution.scope.execution_dependency_case_names == (
        "Modal", "~LLRF", "~Static+EccRSX", "~StaticRSX", "~TorsionRSX",
    )
    assert resolution.scope.permitted_runtime_retired_case_names == ()
    assert modal_calls == ["RSX", "RSY"]
    assert tuple((f.response_spectrum_case_name, f.modal_case_name) for f in resolution.response_spectrum_modal_case_facts) == (
        ("RSX", "Modal"), ("RSY", "Modal"),
    )
    assert "~ChineseX" not in resolution.scope.execution_case_names
    assert "~ChineseY" not in resolution.scope.execution_case_names

def test_complete_response_spectrum_scope_deduplicates_shared_modal_dependency(monkeypatch):
    defined, case_types, slots, modal_bindings = _full_runtime()
    resolution, _ = _resolve(
        monkeypatch, requested=("RSX", "RSY"), defined=defined,
        case_types=case_types, slots=slots, modal_bindings=modal_bindings,
    )
    assert resolution.scope.execution_dependency_case_names.count("Modal") == 1

def test_partial_defined_response_spectrum_scope_fails_closed_before_run(monkeypatch):
    defined, case_types, slots, modal_bindings = _full_runtime()
    with pytest.raises(subject.AnalysisExecutionError) as exc:
        _resolve(
            monkeypatch, requested=("EX", "RSX"), defined=defined,
            case_types=case_types, slots=slots, modal_bindings=modal_bindings,
        )
    assert exc.value.stage == "runtime_scope_resolution"
    assert exc.value.details["defined_response_spectrum_cases"] == ("RSX", "RSY")
    assert exc.value.details["requested_response_spectrum_cases"] == ("RSX",)

def test_response_spectrum_modal_target_must_exist_in_defined_universe(monkeypatch):
    defined, case_types, slots, modal_bindings = _full_runtime()
    defined = tuple(name for name in defined if name != "Modal")
    with pytest.raises(subject.AnalysisExecutionError) as exc:
        _resolve(
            monkeypatch, requested=("RSX", "RSY"), defined=defined,
            case_types=case_types, slots=slots, modal_bindings=modal_bindings,
        )
    assert exc.value.stage == "runtime_scope_resolution"
    assert exc.value.details["modal_case_name"] == "Modal"

def test_response_spectrum_modal_getter_nonzero_fails_closed(monkeypatch):
    defined, case_types, slots, modal_bindings = _full_runtime()
    with pytest.raises(subject.AnalysisExecutionError) as exc:
        _resolve(
            monkeypatch, requested=("RSX", "RSY"), defined=defined,
            case_types=case_types, slots=slots, modal_bindings=modal_bindings,
            modal_return_codes={"RSX": 7},
        )
    assert exc.value.stage == "runtime_scope_resolution"
    assert exc.value.details["return_code"] == 7

def test_no_requested_response_spectrum_preserves_historical_retirement_semantics(monkeypatch):
    defined, case_types, slots, modal_bindings = _full_runtime()
    resolution, modal_calls = _resolve(
        monkeypatch, requested=("EX",), defined=defined,
        case_types=case_types, slots=slots, modal_bindings=modal_bindings,
    )
    assert resolution.scope.case_names == ("EX",)
    assert resolution.scope.execution_dependency_case_names == ("~LLRF",)
    assert resolution.scope.permitted_runtime_retired_case_names == (
        "~Static+EccRSX", "~StaticRSX", "~TorsionRSX",
    )
    assert resolution.response_spectrum_modal_case_facts == ()
    assert modal_calls == []

def test_modal_evidence_is_bound_into_runtime_resolution_identity(monkeypatch):
    defined, case_types, slots, modal_bindings = _full_runtime()
    resolution, _ = _resolve(
        monkeypatch, requested=("RSX", "RSY"), defined=defined,
        case_types=case_types, slots=slots, modal_bindings=modal_bindings,
    )
    assert resolution.evidence_ref.startswith(subject.ANALYSIS_RUNTIME_SCOPE_RESOLUTION_REF_PREFIX)
    assert all(f.evidence_ref for f in resolution.response_spectrum_modal_case_facts)
    assert resolution.scope.case_names == ("RSX", "RSY")
    assert "Modal" not in resolution.scope.case_names
    assert "Modal" in resolution.scope.execution_dependency_case_names
