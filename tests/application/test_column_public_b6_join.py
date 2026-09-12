from __future__ import annotations

from dataclasses import fields
from types import SimpleNamespace

import pytest

import tbdy_engine.application.column_execution as subject
import tbdy_engine.application.column_public_a5 as public_a5
from tbdy_engine.application.contracts import ColumnExecutionRequest, ProjectExecutionRequest


COMPONENT = "Story1:C1:1"
MODEL = "model:fingerprint:public-b6"
EPOCH = "epoch:public-b6"
SELECTED_POPULATION = "selected-design-combo-population:sha256:" + "1" * 64
DEFINITION_REF = "combo-definition:sha256:" + "2" * 64


class _FakeContext:
    def __init__(self) -> None:
        self.verified_session = object()
        self.acquisition_context_ref = "acquisition-context:public-b6"
        self.session_provenance_ref = "session-provenance:public-b6"


class _QualifiedLineage:
    qualified = True
    qualification_ref = "analysis-lineage:qualified:public-b6"

    def __init__(self, parent) -> None:
        self._parent = parent

    def require_qualified_result(self):
        return self._parent


def _ready_column() -> subject.ColumnDomainArtifact:
    return subject.ColumnDomainArtifact(
        component_id=COMPONENT,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        status=subject.STATUS_READY,
        blockers=(),
        fnd_col_2_program=object(),
        fnd_col_2_execution=object(),
        readiness_binding=SimpleNamespace(readiness_ref="fnd-col-2:ready:public-b6"),
    )


def test_execute_column_domain_wires_public_a5_to_b6_completion(monkeypatch) -> None:
    context = _FakeContext()
    sentinel = _ready_column()
    captured = {}

    monkeypatch.setattr(subject, "TrustedLiveAcquisitionContext", _FakeContext)

    def fake_public_a5(
        request,
        *,
        acquisition_context,
        execute_fnd2,
        complete_after_fnd2=None,
    ):
        captured["request"] = request
        captured["context"] = acquisition_context
        captured["execute_fnd2"] = execute_fnd2
        captured["complete_after_fnd2"] = complete_after_fnd2
        return sentinel

    monkeypatch.setattr(public_a5, "execute_public_a5_column", fake_public_a5)

    request = ColumnExecutionRequest(COMPONENT)
    result = subject.execute_column_domain(request, acquisition_context=context)

    assert result is sentinel
    assert captured["request"] is request
    assert captured["context"] is context
    assert captured["execute_fnd2"] is subject._execute_fnd2
    assert captured["complete_after_fnd2"] is subject._complete_public_b6_after_fnd2


def test_ready_fnd2_materializes_exact_design_state_and_reaches_existing_b6(
    monkeypatch,
) -> None:
    column = _ready_column()
    context = _FakeContext()
    scratch = SimpleNamespace(ownership_proof_ref="owned-scratch:public-b6")
    parent = SimpleNamespace(identity_ref="analysis-result:sha256:" + "3" * 64)
    lineage = _QualifiedLineage(parent)
    analysis_execution = SimpleNamespace(
        qualification=lineage,
        analysis_result_identity=parent,
        execution_proof_ref="analysis-execution-proof:public-b6",
        manifest=SimpleNamespace(scope=SimpleNamespace(case_names=("EX", "EY"))),
    )
    selected = SimpleNamespace(
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        rows=(
            SimpleNamespace(
                combo_type="Strength",
                combo_name="ULS",
                source_row_ref="selected-combo-row:ULS",
            ),
        ),
        source_refs=(context.session_provenance_ref, SELECTED_POPULATION),
    )
    definition = SimpleNamespace(name="ULS")
    flattened = (("ULS", (("EX", 1.0), ("EY", 0.3))),)
    topology = SimpleNamespace(
        columns=(SimpleNamespace(component_id=COMPONENT),),
    )
    topology_envelope = SimpleNamespace(
        topology=topology,
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        source_refs=(
            context.session_provenance_ref,
            scratch.ownership_proof_ref,
            lineage.qualification_ref,
            parent.identity_ref,
            analysis_execution.execution_proof_ref,
        ),
    )

    monkeypatch.setattr(
        subject,
        "ColumnTopologyEvidenceEnvelope",
        lambda **kwargs: topology_envelope,
    )
    monkeypatch.setattr(
        subject,
        "read_design_code_from_session",
        lambda _session: SimpleNamespace(
            design_code_ref="etabs-concrete-design-code:sha256:" + "4" * 64
        ),
    )
    procedure = SimpleNamespace(
        capture_complete=True,
        design_procedure_ref="design-procedure-population:sha256:" + "5" * 64,
        source_refs=("procedure:row:1",),
    )
    monkeypatch.setattr(
        subject,
        "capture_column_design_procedure_population_from_session",
        lambda _session, *, topology: procedure,
    )
    monkeypatch.setattr(
        subject,
        "normalized_combo_definition_fingerprint",
        lambda item: DEFINITION_REF if item is definition else None,
    )
    monkeypatch.setattr(
        subject,
        "design_component_scope_ref",
        lambda component_id: f"column-design-result-scope:{component_id}",
    )

    builder_call = {}

    def fake_build_design_state_identity(**kwargs):
        builder_call.update(kwargs)
        return SimpleNamespace(identity_ref="design-state:sha256:" + "6" * 64)

    monkeypatch.setattr(subject, "build_design_state_identity", fake_build_design_state_identity)

    b6_call = {}
    design_result = SimpleNamespace(
        identity_ref="design-result:sha256:" + "7" * 64,
        parent_design_state_ref="design-state:sha256:" + "6" * 64,
    )
    factual = SimpleNamespace(capture_complete=True, rows=("row",))
    sections = SimpleNamespace(rows=("section",))
    design_lineage = SimpleNamespace(qualified=True)

    def fake_controlled_b6(**kwargs):
        b6_call.update(kwargs)
        return SimpleNamespace(
            design_state=kwargs["design_state"],
            design_result_identity=design_result,
            design_lineage=design_lineage,
            factual_design_results=factual,
            design_sections=sections,
        )

    monkeypatch.setattr(subject, "execute_controlled_concrete_design", fake_controlled_b6)

    result = subject._complete_public_b6_after_fnd2(
        column,
        acquisition_context=context,
        owned_scratch=scratch,
        analysis_execution=analysis_execution,
        topology=topology,
        selected_combo_population=selected,
        combo_definitions=(definition,),
        flattened_combos=flattened,
    )

    assert result.status == subject.STATUS_READY
    assert result.blockers == ()
    assert result.design_state is b6_call["design_state"]
    assert result.design_result_identity is design_result
    assert result.design_lineage is design_lineage
    assert result.factual_design_results is factual
    assert result.design_sections is sections

    assert builder_call["analysis_lineage"] is lineage
    assert builder_call["model_fingerprint"] == MODEL
    assert builder_call["evidence_epoch_id"] == EPOCH
    assert builder_call["selected_design_combo_population_ref"] == SELECTED_POPULATION
    assert builder_call["combo_definition_population_refs"] == (DEFINITION_REF,)
    assert builder_call["design_component_population_refs"] == (
        f"column-design-result-scope:{COMPONENT}",
    )
    assert len(builder_call["combo_grain_binding_refs"]) == 1
    assert builder_call["combo_grain_binding_refs"][0].startswith(
        "combo-analysis-basis-binding:sha256:"
    )

    assert b6_call["context"] is context
    assert b6_call["owned_scratch"] is scratch
    assert b6_call["analysis_lineage"] is lineage
    assert b6_call["topology"] is topology_envelope
    assert b6_call["design_state"] is result.design_state
    assert design_result.parent_design_state_ref == result.design_state.identity_ref


def test_exact_combo_binding_rejects_leaf_outside_qualified_b5_scope() -> None:
    column = _ready_column()
    parent = SimpleNamespace(identity_ref="analysis-result:sha256:" + "8" * 64)
    lineage = _QualifiedLineage(parent)
    analysis_execution = SimpleNamespace(
        qualification=lineage,
        analysis_result_identity=parent,
        execution_proof_ref="analysis-execution-proof:public-b6",
        manifest=SimpleNamespace(scope=SimpleNamespace(case_names=("EX",))),
    )
    selected = SimpleNamespace(
        model_fingerprint=MODEL,
        evidence_epoch_id=EPOCH,
        rows=(
            SimpleNamespace(
                combo_type="Strength",
                combo_name="ULS",
                source_row_ref="selected-combo-row:ULS",
            ),
        ),
        source_refs=(SELECTED_POPULATION,),
    )

    with pytest.raises(
        subject.ColumnExecutionContractError,
        match="not covered by exact B5 result scope",
    ):
        subject._build_exact_combo_basis_bindings(
            column=column,
            analysis_execution=analysis_execution,
            selected_combo_population=selected,
            combo_definitions=(SimpleNamespace(name="ULS"),),
            flattened_combos=(("ULS", (("NOT_RUN", 1.0),)),),
        )


def test_production_request_dtos_do_not_gain_caller_authority_injection_fields() -> None:
    forbidden = {
        "design_state",
        "design_result_identity",
        "factual_design_results",
        "combo_analysis_basis_bindings",
        "combo_reconciliation",
        "ready_fixture_inputs",
        "layout_authority",
        "selection_authority",
        "reviewed_pmm_context",
    }
    assert forbidden.isdisjoint({item.name for item in fields(ColumnExecutionRequest)})
    assert forbidden.isdisjoint({item.name for item in fields(ProjectExecutionRequest)})
