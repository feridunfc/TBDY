from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.integration.etabs_controlled_design_execution as subject
from tbdy_engine.etabs.oapi.concrete_design import (
    ConcreteDesignResultsAvailabilityFact,
    ConcreteDesignStartFact,
)


class _FakeContext:
    def __init__(self) -> None:
        self.source_model_identity = SimpleNamespace(
            source_model_ref="source-model:test",
        )
        self.verified_session = object()
        self.acquisition_context_ref = "acquisition-context:test"
        self.session_provenance_ref = "session-provenance:test"


class _FakeOwnedScratch:
    def __init__(self) -> None:
        self.scratch_path = r"C:\\tmp\\model.tbdy-b4s-test.edb"
        self.ownership_proof_ref = "owned-scratch:test"


class _FakeAnalysisLineage:
    def __init__(self) -> None:
        self.qualification_ref = "analysis-lineage:test"
        self.capture_provenance_refs = (
            "acquisition-context:test",
            "session-provenance:test",
            "owned-scratch:test",
        )
        self.result = SimpleNamespace(identity_ref="analysis-result:test")

    def require_qualified_result(self):
        return self.result


class _FakeTopology:
    def __init__(self) -> None:
        self.model_fingerprint = "model-fingerprint:test"
        self.evidence_epoch_id = "epoch:test"
        self.topology = SimpleNamespace(
            columns=(
                SimpleNamespace(component_id="Story1:C1:10"),
                SimpleNamespace(component_id="Story1:C2:20"),
            )
        )


class _FakeDesignState:
    def __init__(self, *, selected_ref: str) -> None:
        expected_scopes = tuple(
            sorted(
                (
                    subject.design_component_scope_ref("Story1:C1:10"),
                    subject.design_component_scope_ref("Story1:C2:20"),
                )
            )
        )
        self.source_model_ref = "source-model:test"
        self.parent_analysis_result_ref = "analysis-result:test"
        self.analysis_lineage_qualification_ref = "analysis-lineage:test"
        self.model_fingerprint = "model-fingerprint:test"
        self.evidence_epoch_id = "epoch:test"
        self.selected_design_combo_population_ref = selected_ref
        self.design_component_population_refs = expected_scopes
        self.combo_grain_binding_refs = ("combo-grain:test",)
        self.identity_ref = "design-state:test"


class _FakeExecutionProof:
    def __init__(self, **values) -> None:
        self.values = values


@pytest.fixture
def harness(monkeypatch):
    context = _FakeContext()
    owned = _FakeOwnedScratch()
    analysis = _FakeAnalysisLineage()
    topology = _FakeTopology()
    selected_ref = "selected-design-combo-population:sha256:test"
    design_state = _FakeDesignState(selected_ref=selected_ref)

    monkeypatch.setattr(subject, "TrustedLiveAcquisitionContext", _FakeContext)
    monkeypatch.setattr(subject, "OwnedScratchContext", _FakeOwnedScratch)
    monkeypatch.setattr(subject, "AnalysisLineageQualification", _FakeAnalysisLineage)
    monkeypatch.setattr(subject, "ColumnTopologyEvidenceEnvelope", _FakeTopology)
    monkeypatch.setattr(subject, "DesignStateIdentity", _FakeDesignState)
    monkeypatch.setattr(subject, "_VerifiedDesignExecutionProof", _FakeExecutionProof)

    state = {
        "preflight_status": subject.DesignPreflightStatus.ABSENT,
        "active_paths": [owned.scratch_path, owned.scratch_path],
        "selected_refs": [selected_ref, selected_ref],
        "start_return_code": 0,
        "results_available": True,
        "capture_complete": True,
        "captured_component_ids": ("Story1:C1:10", "Story1:C2:20"),
        "calls": [],
    }

    def capture_preflight(**kwargs):
        state["calls"].append("preflight")
        return SimpleNamespace(
            status=state["preflight_status"],
            preflight_ref="design-preflight:test",
        )

    def acquire_selection(*, context):
        state["calls"].append("selection")
        ref = state["selected_refs"].pop(0)
        return SimpleNamespace(source_refs=(ref, "selection-source:test"))

    def reread_identity(_session, *, timeout_seconds=30.0):
        state["calls"].append("identity")
        return SimpleNamespace(model_full_path=state["active_paths"].pop(0))

    def start_design(_session, *, timeout_seconds=300.0):
        state["calls"].append("start_design")
        return ConcreteDesignStartFact(return_code=state["start_return_code"])

    def results_available(_session, *, timeout_seconds=30.0):
        state["calls"].append("results_available")
        value = state["results_available"]
        return ConcreteDesignResultsAvailabilityFact(value, value)

    def capture_sections(*, context, topology):
        state["calls"].append("design_sections")
        return SimpleNamespace(source_refs=("design-sections:test",))

    def capture_results(*, context, topology, design_sections):
        state["calls"].append("design_results")
        return SimpleNamespace(
            capture_complete=state["capture_complete"],
            expected_component_ids=state["captured_component_ids"],
            source_refs=("design-results:test",),
            reported_result_row_count=4,
        )

    def build_result_identity(**kwargs):
        state["calls"].append("build_result_identity")
        return SimpleNamespace(identity_ref="design-result:test")

    def build_lineage(**kwargs):
        state["calls"].append("build_lineage")
        return SimpleNamespace(
            qualified=True,
            qualification_ref="design-lineage:test",
        )

    monkeypatch.setattr(subject, "capture_design_preflight", capture_preflight)
    monkeypatch.setattr(
        subject,
        "acquire_actual_concrete_design_combo_selection_from_context",
        acquire_selection,
    )
    monkeypatch.setattr(subject, "reread_verified_session_identity", reread_identity)
    monkeypatch.setattr(subject, "start_concrete_design_from_session", start_design)
    monkeypatch.setattr(subject, "read_results_available_from_session", results_available)
    monkeypatch.setattr(
        subject,
        "capture_concrete_column_design_sections_from_context",
        capture_sections,
    )
    monkeypatch.setattr(
        subject,
        "capture_concrete_column_design_results_from_context",
        capture_results,
    )
    monkeypatch.setattr(subject, "build_design_result_identity", build_result_identity)
    monkeypatch.setattr(subject, "_design_execution_proof_ref", lambda **kwargs: "design-proof:test")
    monkeypatch.setattr(subject, "_build_qualified_design_lineage", build_lineage)

    return context, owned, analysis, topology, design_state, state


def execute(harness):
    context, owned, analysis, topology, design_state, _state = harness
    return subject.execute_controlled_concrete_design(
        context=context,
        owned_scratch=owned,
        analysis_lineage=analysis,
        topology=topology,
        design_state=design_state,
        timeout_seconds=60.0,
    )


def test_controlled_design_happy_path_causes_exactly_one_start_and_qualified_lineage(
    harness,
) -> None:
    result = execute(harness)
    state = harness[-1]

    assert state["calls"].count("start_design") == 1
    assert result.start_fact.success is True
    assert result.design_lineage.qualified is True
    assert result.factual_design_results.capture_complete is True
    assert result.selected_combo_population_ref == (
        "selected-design-combo-population:sha256:test"
    )
    assert result.design_attempt_ref.startswith(subject.DESIGN_ATTEMPT_REF_PREFIX)
    assert result.design_generation_ref.startswith(subject.DESIGN_GENERATION_REF_PREFIX)
    assert state["calls"] == [
        "preflight",
        "selection",
        "identity",
        "start_design",
        "identity",
        "results_available",
        "selection",
        "design_sections",
        "design_results",
        "build_result_identity",
        "build_lineage",
    ]


@pytest.mark.parametrize(
    "status",
    [subject.DesignPreflightStatus.PRESENT, subject.DesignPreflightStatus.AMBIGUOUS],
)
def test_preflight_not_absent_blocks_before_start_design(harness, status) -> None:
    harness[-1]["preflight_status"] = status

    with pytest.raises(subject.ControlledDesignExecutionError) as exc_info:
        execute(harness)

    assert exc_info.value.stage == "preflight"
    assert "start_design" not in harness[-1]["calls"]


def test_nonzero_start_design_is_not_promoted_to_success(harness) -> None:
    harness[-1]["start_return_code"] = 7

    with pytest.raises(subject.ControlledDesignExecutionError) as exc_info:
        execute(harness)

    assert exc_info.value.stage == "start_design_nonzero"
    assert harness[-1]["calls"].count("start_design") == 1
    assert "results_available" not in harness[-1]["calls"]
    assert "design_results" not in harness[-1]["calls"]


def test_start_success_without_results_available_fails_closed(harness) -> None:
    harness[-1]["results_available"] = False

    with pytest.raises(subject.ControlledDesignExecutionError) as exc_info:
        execute(harness)

    assert exc_info.value.stage == "post_design_results_unavailable"
    assert harness[-1]["calls"].count("start_design") == 1
    assert "design_results" not in harness[-1]["calls"]


def test_active_scratch_change_after_start_blocks_result_capture(harness) -> None:
    harness[-1]["active_paths"] = [
        harness[1].scratch_path,
        r"C:\\tmp\\other.edb",
    ]

    with pytest.raises(subject.ControlledDesignExecutionError) as exc_info:
        execute(harness)

    assert exc_info.value.stage == "design_state_revalidation"
    assert harness[-1]["calls"].count("start_design") == 1
    assert "results_available" not in harness[-1]["calls"]
    assert "design_results" not in harness[-1]["calls"]


def test_selected_combo_population_change_after_start_blocks_result_capture(
    harness,
) -> None:
    harness[-1]["selected_refs"] = [
        "selected-design-combo-population:sha256:test",
        "selected-design-combo-population:sha256:changed",
    ]

    with pytest.raises(subject.ControlledDesignExecutionError) as exc_info:
        execute(harness)

    assert exc_info.value.stage == "design_state_revalidation"
    assert harness[-1]["calls"].count("start_design") == 1
    assert "design_results" not in harness[-1]["calls"]


def test_incomplete_post_design_population_does_not_issue_lineage(harness) -> None:
    harness[-1]["capture_complete"] = False

    with pytest.raises(subject.ControlledDesignExecutionError) as exc_info:
        execute(harness)

    assert exc_info.value.stage == "result_population"
    assert "build_result_identity" not in harness[-1]["calls"]
    assert "build_lineage" not in harness[-1]["calls"]


def test_post_design_component_scope_must_equal_design_state_scope(harness) -> None:
    harness[-1]["captured_component_ids"] = ("Story1:C1:10",)

    with pytest.raises(subject.ControlledDesignExecutionError) as exc_info:
        execute(harness)

    assert exc_info.value.stage == "result_population"
    assert "build_result_identity" not in harness[-1]["calls"]
    assert "build_lineage" not in harness[-1]["calls"]
