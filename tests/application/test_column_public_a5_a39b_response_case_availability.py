from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_public_a5 as a5


def _context():
    return SimpleNamespace(verified_session=object(), session_provenance_ref="session:a39b")


def _defined(*names, success=True):
    return SimpleNamespace(success=success, case_names=tuple(names), evidence_ref="defined:a39b")


def _population(name):
    return SimpleNamespace(case_name=name, evidence_ref=f"population:{name}", rows=())


def _execution(*names):
    return SimpleNamespace(manifest=SimpleNamespace(result_populations=tuple(_population(n) for n in names)))


def test_full_model_response_discovery_is_independent_of_design_leaves(monkeypatch):
    seen = {}
    monkeypatch.setattr(a5, "get_defined_analysis_cases_from_session", lambda _s: _defined("DL", "EQX", "EQY", "RSX"))
    def qualify(_context, candidates):
        seen["candidates"] = tuple(candidates)
        return ("EQX", "EQY"), ("qualified:xy",)
    monkeypatch.setattr(a5, "_qualified_linear_static_response_scope", qualify)
    result = a5._discover_qualified_response_case_availability(_context(), ("DL", "RSX"))
    assert seen["candidates"] == ("DL", "EQX", "EQY", "RSX")
    assert result.design_required_case_names == ("DL", "RSX")
    assert result.qualified_linear_static_case_names == ("EQX", "EQY")
    assert result.response_evidence_only_case_names == ("EQX", "EQY")
    assert result.b5_requested_case_names == ("DL", "EQX", "EQY", "RSX")
    assert result.direction_rank == 2
    assert "defined:a39b" in result.source_refs
    assert "qualified:xy" in result.source_refs


def test_response_discovery_never_uses_case_name_for_direction(monkeypatch):
    monkeypatch.setattr(a5, "get_defined_analysis_cases_from_session", lambda _s: _defined("gravity", "banana", "left"))
    monkeypatch.setattr(a5, "_qualified_linear_static_response_scope", lambda *_a: (("banana", "left"), ("source-bound-direction",)))
    result = a5._discover_qualified_response_case_availability(_context(), ("gravity",))
    assert result.qualified_linear_static_case_names == ("banana", "left")


def test_b5_union_is_exact_and_duplicate_free(monkeypatch):
    monkeypatch.setattr(a5, "get_defined_analysis_cases_from_session", lambda _s: _defined("DL", "EQX", "EQY"))
    monkeypatch.setattr(a5, "_qualified_linear_static_response_scope", lambda *_a: (("EQX", "EQY"), ("qualified:xy",)))
    result = a5._discover_qualified_response_case_availability(_context(), ("DL", "EQX"))
    assert result.response_evidence_only_case_names == ("EQY",)
    assert result.b5_requested_case_names == ("DL", "EQX", "EQY")
    assert len(result.b5_requested_case_names) == len(set(result.b5_requested_case_names))


def test_duplicate_design_case_identity_fails_closed():
    with pytest.raises(a5.PublicA5CompositionError, match="duplicate-free"):
        a5._discover_qualified_response_case_availability(_context(), ("DL", "DL"))


def test_failed_full_case_population_fails_closed(monkeypatch):
    monkeypatch.setattr(a5, "get_defined_analysis_cases_from_session", lambda _s: _defined(success=False))
    with pytest.raises(a5.PublicA5CompositionError, match="full factual LoadCases population"):
        a5._discover_qualified_response_case_availability(_context(), ("DL",))


def test_design_leaf_missing_from_model_fails_closed(monkeypatch):
    monkeypatch.setattr(a5, "get_defined_analysis_cases_from_session", lambda _s: _defined("EQX", "EQY"))
    with pytest.raises(a5.PublicA5CompositionError, match="design-required case"):
        a5._discover_qualified_response_case_availability(_context(), ("DL",))


def test_existing_xy_qualification_failure_is_not_weakened(monkeypatch):
    monkeypatch.setattr(a5, "get_defined_analysis_cases_from_session", lambda _s: _defined("DL", "EQX", "EQY"))
    def fail(*_args):
        raise a5.PublicA5CompositionError(a5.BLOCKER_A3_MEMBER_RESPONSE, "qualified LINEAR_STATIC Eq713 response scope does not span independent global X/Y directions")
    monkeypatch.setattr(a5, "_qualified_linear_static_response_scope", fail)
    with pytest.raises(a5.PublicA5CompositionError, match="independent global X/Y") as caught:
        a5._discover_qualified_response_case_availability(_context(), ("DL",))
    assert caught.value.blocker == a5.BLOCKER_A3_MEMBER_RESPONSE


def test_design_case_projection_remains_flattened_combo_authority():
    flattened = (("ULS", (("DL", 1.4), ("RSX", 1.0))), ("SERVICE", (("DL", 1.0),)))
    assert a5._design_required_case_names(flattened) == ("DL", "RSX")
    assert "EQX" not in repr(flattened)
    assert "EQY" not in repr(flattened)


def test_response_only_result_populations_do_not_enter_design_demands():
    flattened = (("ULS", (("DL", 1.0), ("RSX", 1.0))),)
    selected = a5._design_result_populations(_execution("DL", "EQX", "EQY", "RSX"), flattened)
    assert tuple(item.case_name for item in selected) == ("DL", "RSX")


def test_missing_design_result_population_fails_closed():
    flattened = (("ULS", (("DL", 1.0), ("RSX", 1.0))),)
    with pytest.raises(a5.PublicA5CompositionError, match="missing design-required case"):
        a5._design_result_populations(_execution("DL", "EQX", "EQY"), flattened)


def test_duplicate_b5_result_population_fails_closed():
    flattened = (("ULS", (("DL", 1.0),)),)
    with pytest.raises(a5.PublicA5CompositionError, match="duplicate case"):
        a5._design_result_populations(_execution("DL", "DL", "EQX"), flattened)


def test_existing_b5_owner_and_no_case_creation_path_remain_frozen():
    run_source = inspect.getsource(a5._run_a3_generation)
    module_source = inspect.getsource(a5)
    assert "execute_controlled_analysis(" in run_source
    assert "RunAnalysis" not in run_source
    assert "run_analysis_from_session" not in module_source
    assert "StaticLinear.SetCase" not in module_source
    assert "StaticLinear.SetLoads" not in module_source
