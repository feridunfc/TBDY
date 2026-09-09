from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_execution as subject


class _FakeTransverseInput:
    def __init__(
        self,
        *,
        component_id="Story1:C1:10",
        model_fingerprint="model:test",
        evidence_epoch_id="epoch:test",
    ) -> None:
        self.component_id = component_id
        self.model_fingerprint = model_fingerprint
        self.evidence_epoch_id = evidence_epoch_id


class _FakeLineage:
    pass


class _FakeResult:
    def __init__(self, *, component_id="Story1:C1:10", blockers=()) -> None:
        self.component_id = component_id
        self.blockers = tuple(blockers)


def _column(*, status=None, selected_rebar=object()):
    return subject.ColumnDomainArtifact(
        component_id="Story1:C1:10",
        model_fingerprint="model:test",
        evidence_epoch_id="epoch:test",
        status=subject.STATUS_SELECTED if status is None else status,
        blockers=(),
        longitudinal_selection=SimpleNamespace(selected_rebar=selected_rebar),
    )


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setattr(subject, "ColumnTransverseConfinementInput", _FakeTransverseInput)
    monkeypatch.setattr(subject, "DesignLineageQualification", _FakeLineage)
    monkeypatch.setattr(subject, "ColumnTransverseConfinementResult", _FakeResult)
    calls = []
    state = {"result": _FakeResult()}

    def evaluate(request, *, selected_rebar, design_lineage):
        calls.append((request, selected_rebar, design_lineage))
        return state["result"]

    monkeypatch.setattr(subject, "evaluate_column_transverse_confinement_bound", evaluate)
    return calls, state


def test_lane_c_join_uses_bound_evaluator_and_preserves_selected_state(harness) -> None:
    calls, state = harness
    column = _column()
    request = _FakeTransverseInput()
    lineage = _FakeLineage()

    result = subject._compose_lane_c_after_qualified_design(
        column,
        transverse_input=request,
        design_lineage=lineage,
    )

    assert calls == [(request, column.selected_rebar, lineage)]
    assert result.transverse_confinement is state["result"]
    assert result.status == subject.STATUS_SELECTED
    assert result.blockers == ()


def test_lane_c_blockers_fail_closed_without_reinterpreting_authority(harness) -> None:
    _calls, state = harness
    state["result"] = _FakeResult(
        blockers=(
            "TS500_COLUMN_BW_D_ASW_DIRECTION_MAPPING_NOT_PROVEN:DIR2",
            "LIMITED_DUCTILITY_APPLICABILITY_NOT_PROVEN",
        )
    )

    result = subject._compose_lane_c_after_qualified_design(
        _column(),
        transverse_input=_FakeTransverseInput(),
        design_lineage=_FakeLineage(),
    )

    assert result.status == subject.STATUS_APPLICATION_BLOCKED
    assert result.blockers == (
        "TRANSVERSE_CONFINEMENT:TS500_COLUMN_BW_D_ASW_DIRECTION_MAPPING_NOT_PROVEN:DIR2",
        "TRANSVERSE_CONFINEMENT:LIMITED_DUCTILITY_APPLICABILITY_NOT_PROVEN",
    )


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("component_id", "Story1:C2:20", "component identity mismatch"),
        ("model_fingerprint", "model:other", "model identity mismatch"),
        ("evidence_epoch_id", "epoch:other", "EvidenceEpoch identity mismatch"),
    ],
)
def test_lane_c_join_rejects_identity_drift_before_authority_call(
    harness,
    field,
    value,
    match,
) -> None:
    calls, _state = harness
    kwargs = {
        "component_id": "Story1:C1:10",
        "model_fingerprint": "model:test",
        "evidence_epoch_id": "epoch:test",
    }
    kwargs[field] = value

    with pytest.raises(subject.ColumnExecutionContractError, match=match):
        subject._compose_lane_c_after_qualified_design(
            _column(),
            transverse_input=_FakeTransverseInput(**kwargs),
            design_lineage=_FakeLineage(),
        )

    assert calls == []


def test_lane_c_join_requires_selected_longitudinal_authority(harness) -> None:
    calls, _state = harness

    with pytest.raises(
        subject.ColumnExecutionContractError,
        match="ENGINE_SELECTED_REBAR",
    ):
        subject._compose_lane_c_after_qualified_design(
            _column(status=subject.STATUS_APPLICATION_BLOCKED),
            transverse_input=_FakeTransverseInput(),
            design_lineage=_FakeLineage(),
        )

    with pytest.raises(
        subject.ColumnExecutionContractError,
        match="ENGINE_SELECTED_REBAR",
    ):
        subject._compose_lane_c_after_qualified_design(
            _column(selected_rebar=None),
            transverse_input=_FakeTransverseInput(),
            design_lineage=_FakeLineage(),
        )

    assert calls == []


def test_lane_c_join_rejects_foreign_result_identity(harness) -> None:
    _calls, state = harness
    state["result"] = _FakeResult(component_id="Story1:C2:20")

    with pytest.raises(subject.ColumnExecutionContractError, match="result component"):
        subject._compose_lane_c_after_qualified_design(
            _column(),
            transverse_input=_FakeTransverseInput(),
            design_lineage=_FakeLineage(),
        )


def test_lane_c_join_does_not_reintroduce_authority_into_request_dto() -> None:
    from dataclasses import fields
    from tbdy_engine.application.contracts import ColumnExecutionRequest

    assert tuple(item.name for item in fields(ColumnExecutionRequest)) == ("component_id",)
