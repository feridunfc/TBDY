from types import SimpleNamespace as NS

import pytest

import tbdy_engine.providers.etabs_column_axial_b5_provider as subject


def _setup(monkeypatch):
    analysis = NS(qualification=NS(qualified=True), manifest=NS(scope=NS(case_names=("EX", "G", "Q"))))
    monkeypatch.setattr(subject, "AnalysisExecutionResult", type(analysis))
    calls = []
    def capture(session, *, case_name, expectation):
        calls.append((session, case_name, expectation.expected_unique_names))
        return NS(case_name=case_name, evidence_ref="factual:combo-response")
    monkeypatch.setattr(subject, "capture_column_force_result_population_from_session", capture)
    kwargs = dict(session=object(), analysis_execution=analysis,
                  topology=NS(columns=(NS(unique_name="1"), NS(unique_name="2"))),
                  required_combo_names=("GQE",), flattened_combos=(("GQE", (("G", 1.), ("Q", 1.), ("EX", 1.))),))
    return kwargs, calls


def test_combo_read_reuses_qualified_generation_and_full_factual_population(monkeypatch):
    kwargs, calls = _setup(monkeypatch)
    facts = subject.capture_b5_bound_column_combo_force_populations(**kwargs)
    assert tuple(item.case_name for item in facts) == ("GQE",)
    assert calls == [(kwargs["session"], "GQE", ("1", "2"))]


@pytest.mark.parametrize("defect", ["unqualified", "missing", "outside", "duplicate", "duplicate_definition"])
def test_invalid_combo_scope_is_rejected_before_any_factual_read(monkeypatch, defect):
    kwargs, calls = _setup(monkeypatch)
    if defect == "unqualified":
        kwargs["analysis_execution"].qualification.qualified = False
    elif defect == "missing":
        kwargs["required_combo_names"] = ("UNKNOWN",)
    elif defect == "outside":
        kwargs["flattened_combos"] = (("GQE", (("NOT_RUN", 1.),)),)
    elif defect == "duplicate":
        kwargs["required_combo_names"] = ("GQE", "GQE")
    else:
        kwargs["flattened_combos"] *= 2
    with pytest.raises(subject.ColumnAxialB5EvidenceError):
        subject.capture_b5_bound_column_combo_force_populations(**kwargs)
    assert calls == []
