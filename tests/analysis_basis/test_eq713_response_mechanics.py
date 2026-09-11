from __future__ import annotations

from tbdy_engine.analysis_basis.eq713_response_mechanics import _response_truth


def test_response_truth_zero_is_unknown_never_false() -> None:
    participates, _reason = _response_truth(values=(0.0, 0.0), effective_modifier=1.0)
    assert participates is None


def test_response_truth_nonzero_requires_positive_modifier() -> None:
    participates, _reason = _response_truth(values=(1.0,), effective_modifier=0.0)
    assert participates is None


def test_response_truth_nonzero_with_positive_modifier_is_true() -> None:
    participates, _reason = _response_truth(values=(1.0,), effective_modifier=1.0)
    assert participates is True
