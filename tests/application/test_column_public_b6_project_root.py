from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import tbdy_engine.application.column_execution as column_execution
import tbdy_engine.application.column_public_a5 as a5
import tbdy_engine.application.project_execution as project_execution


SELECTED_POPULATION = "selected-design-combo-population:sha256:" + "9" * 64
DEFINITION_REF = "combo-definition:sha256:" + "a" * 64


def _load_existing_public_a5_harness_module():
    path = Path(__file__).with_name("test_column_public_a5_product_path.py")
    spec = importlib.util.spec_from_file_location("_column_public_a5_product_harness", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _invoke_fixture_factory(fixture_function, monkeypatch):
    wrapped = getattr(fixture_function, "__pytest_wrapped__", None)
    if wrapped is not None:
        return wrapped.obj(monkeypatch)
    wrapped = getattr(fixture_function, "__wrapped__", None)
    if wrapped is not None:
        return wrapped(monkeypatch)
    return fixture_function(monkeypatch)


def test_execute_project_reaches_qualified_fnd2_designstate_and_existing_controlled_b6(
    monkeypatch,
) -> None:
    """Public proof starts at execute_project; no private READY authority is injected."""
    harness_module = _load_existing_public_a5_harness_module()
    harness = _invoke_fixture_factory(harness_module.product_harness, monkeypatch)

    selected = SimpleNamespace(
        capture_complete=True,
        model_fingerprint="model-fingerprint:public-a5",
        evidence_epoch_id="evidence-epoch:public-a5",
        rows=(
            SimpleNamespace(
                combo_type="Strength",
                combo_name="ULS",
                source_row_ref="selected-combo-row:ULS",
            ),
        ),
        names=("ULS",),
        source_refs=(
            "session-provenance:public-a5",
            SELECTED_POPULATION,
        ),
    )
    combo = SimpleNamespace(
        name="ULS",
        combo_type="LINEAR_ADD",
        constituents=(
            SimpleNamespace(
                cname_type="LOAD_CASE",
                name="EX",
                scale_factor=1.0,
            ),
        ),
        nested_combos=(),
    )
    monkeypatch.setattr(
        a5,
        "acquire_actual_concrete_design_combo_selection_from_session",
        lambda *_args, **_kwargs: selected,
    )
    monkeypatch.setattr(
        a5,
        "capture_etabs_combo_definitions_from_session",
        lambda *_args, **_kwargs: (combo,),
    )

    topology_envelopes = []

    def envelope(**kwargs):
        value = SimpleNamespace(
            topology=kwargs["topology"],
            model_fingerprint=kwargs["model_fingerprint"],
            evidence_epoch_id=kwargs["evidence_epoch_id"],
            source_refs=tuple(kwargs["source_refs"]),
        )
        topology_envelopes.append(value)
        return value

    monkeypatch.setattr(column_execution, "ColumnTopologyEvidenceEnvelope", envelope)
    monkeypatch.setattr(
        column_execution,
        "read_design_code_from_session",
        lambda _session: SimpleNamespace(
            design_code_ref="etabs-concrete-design-code:sha256:" + "b" * 64
        ),
    )
    procedure = SimpleNamespace(
        capture_complete=True,
        design_procedure_ref="design-procedure-population:sha256:" + "c" * 64,
        source_refs=("design-procedure-row:public-b6",),
    )
    monkeypatch.setattr(
        column_execution,
        "capture_column_design_procedure_population_from_session",
        lambda _session, *, topology: procedure,
    )
    monkeypatch.setattr(
        column_execution,
        "normalized_combo_definition_fingerprint",
        lambda definition: DEFINITION_REF,
    )

    b6_calls = []
    factual_results = SimpleNamespace(capture_complete=True, rows=("design-row",))
    design_sections = SimpleNamespace(rows=("design-section",))

    def controlled_b6(**kwargs):
        b6_calls.append(kwargs)
        design_state = kwargs["design_state"]
        return SimpleNamespace(
            design_state=design_state,
            design_result_identity=SimpleNamespace(
                identity_ref="design-result:sha256:" + "d" * 64,
                parent_design_state_ref=design_state.identity_ref,
            ),
            design_lineage=SimpleNamespace(qualified=True),
            factual_design_results=factual_results,
            design_sections=design_sections,
        )

    monkeypatch.setattr(
        column_execution,
        "execute_controlled_concrete_design",
        controlled_b6,
    )

    result = project_execution.execute_project(
        harness.request,
        verified_session=harness_module._FakeSession(),
    )

    assert result.column.fnd_col_2_execution is not None
    assert result.column.status == column_execution.STATUS_READY
    assert result.column.design_state is not None
    assert result.column.design_result_identity is not None
    assert result.column.design_lineage.qualified
    assert result.column.factual_design_results is factual_results
    assert result.column.design_sections is design_sections

    assert len(b6_calls) == 1
    assert b6_calls[0]["design_state"] is result.column.design_state
    assert b6_calls[0]["analysis_lineage"].qualified
    assert (
        b6_calls[0]["analysis_lineage"].require_qualified_result().identity_ref
        == result.column.design_state.parent_analysis_result_ref
    )
    assert result.column.design_result_identity.parent_design_state_ref == result.column.design_state.identity_ref
    assert result.column.design_state.selected_design_combo_population_ref == SELECTED_POPULATION
    assert result.column.design_state.combo_definition_population_refs == (DEFINITION_REF,)
    assert len(result.column.design_state.combo_grain_binding_refs) == 1
    assert result.column.design_state.combo_grain_binding_refs[0].startswith(
        "combo-analysis-basis-binding:sha256:"
    )
    assert topology_envelopes and b6_calls[0]["topology"] is topology_envelopes[0]
    assert harness.runtime["run_calls"] == 1
