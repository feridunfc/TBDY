from dataclasses import replace
import inspect

import pytest

import tbdy_engine.regulatory.fnd_col_2 as fnd_col_2
import tbdy_engine.regulatory.fnd_col_2_program as fnd_col_2_program
from tbdy_engine.design.columns.column_combo_eligibility_projection import ComponentReadinessBinding
from tbdy_engine.design.columns.column_design_readiness import (
    BLOCKED,
    READY,
    REANALYSIS_REQUIRED,
    SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED,
    UNRESOLVED,
)
from tbdy_engine.design.columns.slenderness import SWAY_PREVENTED
from tbdy_engine.design.columns.slenderness_basis import (
    MOMENT_RATIO_AUTHORITY,
    REGULATORY_FREE_LENGTH_AUTHORITY,
    SWAY_CLASSIFICATION_AUTHORITY,
)
from tbdy_engine.regulatory.contracts import (
    AvailabilityState,
    DependencySourceKind,
    Grain,
    PhysicalDimension,
    SemanticType,
)
from tbdy_engine.regulatory.fnd_col_2 import (
    CASE_DEMANDS_KEY,
    COMBO_DEFINITIONS_KEY,
    DEPTH_MM_KEY,
    READINESS_KEY,
    RULE_ID,
    SLENDERNESS_EVIDENCE_KEY,
    STIFFNESS_EVIDENCE_KEY,
    WIDTH_MM_KEY,
    ColumnDesignReadinessApplicabilityInput,
)
from tbdy_engine.regulatory.fnd_col_2_program import (
    compile_source_bound_fnd_col_2_program,
    execute_source_bound_fnd_col_2,
    execute_source_bound_fnd_col_2_with_artifact,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    ExternalDependencyAuthority,
    PopulationCompleteness,
    RegulatoryCompileInputs,
    RegulatoryEngine,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.units import UNIT_DIMENSIONLESS, UNIT_MM

COMP = "+0.00:C2:236"


def _authority(authority_id, key, source_kind, semantic, dimension, unit, value, *, refs):
    return ExternalDependencyAuthority(
        authority_id=authority_id,
        key=key,
        source_kind=source_kind,
        semantic_type=semantic,
        physical_dimension=dimension,
        grain=Grain.COMPONENT,
        scope_ref=COMP,
        direction=None,
        unit=unit,
        availability=AvailabilityState.RESOLVED,
        population_completeness=PopulationCompleteness.FULL,
        value=value,
        provenance_refs=refs,
    )


def _axis(name, h, *, ln=3000.0, ratio=0.0, promote_sway=True, promote_ratio=True):
    return {
        "axis": name,
        "section_dimension_mm": h,
        "factual_clear_length_candidate_mm": ln,
        "factual_clear_length_source_ref": f"ETABS:{name}:clear-length",
        "factual_clear_length_authority": "FACTUAL_ANALYSIS_CLEAR_LENGTH_CANDIDATE",
        "regulatory_free_length_ln_mm": ln,
        "regulatory_free_length_source_ref": f"reviewed:{name}:ln",
        "regulatory_free_length_authority": REGULATORY_FREE_LENGTH_AUTHORITY,
        "sway_classification": SWAY_PREVENTED if promote_sway else None,
        "sway_source_ref": f"reviewed:{name}:sway" if promote_sway else None,
        "sway_authority": SWAY_CLASSIFICATION_AUTHORITY if promote_sway else None,
        "effective_length_factor_k": None,
        "effective_length_source_ref": None,
        "effective_length_authority": None,
        "moment_ratio_m1_over_m2": ratio if promote_ratio else None,
        "moment_ratio_source_ref": f"reviewed:{name}:ratio" if promote_ratio else None,
        "moment_ratio_authority": MOMENT_RATIO_AUTHORITY if promote_ratio else None,
        "allow_conservative_braced_ratio": False,
    }


def _slenderness(*, m2=None, m3=None):
    return {
        "component_id": COMP,
        "m2": m2 or _axis("M2", 800.0),
        "m3": m3 or _axis("M3", 500.0),
        "source_refs": ("fixture:slenderness",),
    }


def _authorities(*, slenderness=None, stiffness=()):
    combo = (
        {
            "name": "ULS",
            "combo_type": "LINEAR_ADD",
            "constituents": (
                {"name": "G", "scale_factor": 1.0, "cname_type": "LOAD_CASE"},
            ),
        },
    )
    demands = (
        {
            "state_id": "G:I",
            "component_id": COMP,
            "output_case": "G",
            "case_type": "LinStatic",
            "step_type": None,
            "step_number": None,
            "station_m": 0.0,
            "end_tag": "I_END",
            "nd_compression_n": 1_000_000.0,
            "m2_nmm": -100_000_000.0,
            "m3_nmm": 80_000_000.0,
            "source_identity": "raw:G:I",
        },
        {
            "state_id": "G:J",
            "component_id": COMP,
            "output_case": "G",
            "case_type": "LinStatic",
            "step_type": None,
            "step_number": None,
            "station_m": 3.0,
            "end_tag": "J_END",
            "nd_compression_n": 900_000.0,
            "m2_nmm": 70_000_000.0,
            "m3_nmm": -60_000_000.0,
            "source_identity": "raw:G:J",
        },
    )
    if slenderness is None:
        slenderness = _slenderness()
    return (
        _authority("width", WIDTH_MM_KEY, DependencySourceKind.FACT, SemanticType.COLUMN_WIDTH, PhysicalDimension.LENGTH, UNIT_MM, 500.0, refs=("fact:width",)),
        _authority("depth", DEPTH_MM_KEY, DependencySourceKind.FACT, SemanticType.COLUMN_DEPTH, PhysicalDimension.LENGTH, UNIT_MM, 800.0, refs=("fact:depth",)),
        _authority("combos", COMBO_DEFINITIONS_KEY, DependencySourceKind.CONTEXT, SemanticType.CHECK_EVIDENCE_TRACE, PhysicalDimension.DIMENSIONLESS, UNIT_DIMENSIONLESS, combo, refs=("evidence:combo-definitions",)),
        _authority("demands", CASE_DEMANDS_KEY, DependencySourceKind.SOURCE_POPULATION, SemanticType.CHECK_EVIDENCE_TRACE, PhysicalDimension.DIMENSIONLESS, UNIT_DIMENSIONLESS, demands, refs=("evidence:concurrent-pmm-population",)),
        _authority("slenderness", SLENDERNESS_EVIDENCE_KEY, DependencySourceKind.CONTEXT, SemanticType.CHECK_EVIDENCE_TRACE, PhysicalDimension.DIMENSIONLESS, UNIT_DIMENSIONLESS, slenderness, refs=("evidence:slenderness",)),
        _authority("stiffness", STIFFNESS_EVIDENCE_KEY, DependencySourceKind.CONTEXT, SemanticType.CHECK_EVIDENCE_TRACE, PhysicalDimension.DIMENSIONLESS, UNIT_DIMENSIONLESS, stiffness, refs=("evidence:stiffness",)),
    )


def _inputs(*, slenderness=None, stiffness=(), analysis_basis_status=AnalysisBasisStatus.MATCH):
    return RegulatoryCompileInputs(
        rule_targets=(
            RuleScopeTarget(
                rule_id=RULE_ID,
                grain=Grain.COMPONENT,
                scope_ref=COMP,
                applicability_input=ColumnDesignReadinessApplicabilityInput(True),
                analysis_basis_status=analysis_basis_status,
            ),
        ),
        external_authorities=_authorities(slenderness=slenderness, stiffness=stiffness),
    )


def test_exact_typed_readiness_is_retained_and_serialized_from_same_instance(monkeypatch):
    resolved = []
    serialized = []
    original_resolver = fnd_col_2.resolve_column_design_demand_readiness
    original_serializer = fnd_col_2._regulatory_quantity_from_readiness

    def resolver_spy(**kwargs):
        result = original_resolver(**kwargs)
        resolved.append(result)
        return result

    def serializer_spy(inp, readiness):
        serialized.append(readiness)
        return original_serializer(inp, readiness)

    monkeypatch.setattr(fnd_col_2, "resolve_column_design_demand_readiness", resolver_spy)
    monkeypatch.setattr(fnd_col_2, "_regulatory_quantity_from_readiness", serializer_spy)

    artifact = execute_source_bound_fnd_col_2_with_artifact(_inputs())

    assert len(resolved) == 1
    assert len(serialized) == 1
    assert artifact.readiness is resolved[0]
    assert serialized[0] is resolved[0]
    assert artifact.readiness.status == READY
    record = artifact.readiness_records[0]
    assert record.readiness is artifact.readiness
    assert record.readiness_instance_ref.scope_ref == COMP
    assert record.plan_identity == artifact.snapshot.plan_identity
    quantity = artifact.snapshot.regulatory_quantities[0]
    assert quantity.quantity_key == READINESS_KEY
    assert quantity.producer_instance_id == record.readiness_instance_ref
    assert quantity.value["status"] == artifact.readiness.status
    assert quantity.evidence_refs == record.evidence_refs
    assert quantity.dependency_refs == record.dependency_refs


def test_snapshot_only_public_contract_delegates_without_changing_snapshot_behavior():
    inputs = _inputs()
    expected = RegulatoryEngine.execute(compile_source_bound_fnd_col_2_program(inputs))
    artifact = execute_source_bound_fnd_col_2_with_artifact(inputs)
    assert artifact.snapshot == expected
    assert execute_source_bound_fnd_col_2(inputs) == expected


def test_reanalysis_required_typed_result_is_preserved_exactly():
    stiffness = (
        {
            "section_name": "C80",
            "member_kind": "COLUMN",
            "i2_modifier": 0.70,
            "i3_modifier": 0.70,
            "source_refs": ("ETABS:C80",),
        },
    )
    unresolved_sway = _slenderness(
        m2=_axis("M2", 800.0, promote_sway=False, promote_ratio=False),
        m3=_axis("M3", 500.0, promote_sway=False, promote_ratio=False),
    )
    artifact = execute_source_bound_fnd_col_2_with_artifact(
        _inputs(slenderness=unresolved_sway, stiffness=stiffness)
    )
    assert artifact.readiness.status == REANALYSIS_REQUIRED
    assert artifact.readiness.second_order_treatment == SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED
    assert artifact.snapshot.regulatory_quantities[0].value["status"] == REANALYSIS_REQUIRED


def test_blocked_and_unresolved_typed_semantics_are_preserved():
    blocked = _slenderness(
        m2=_axis("M2", 500.0, ln=6000.0, ratio=1.0),
        m3=_axis("M3", 800.0),
    )
    blocked_artifact = execute_source_bound_fnd_col_2_with_artifact(_inputs(slenderness=blocked))
    assert blocked_artifact.readiness.status == BLOCKED

    unresolved = _slenderness(
        m2=_axis("M2", 800.0, promote_ratio=False),
        m3=_axis("M3", 500.0),
    )
    unresolved_artifact = execute_source_bound_fnd_col_2_with_artifact(_inputs(slenderness=unresolved))
    assert unresolved_artifact.readiness.status == UNRESOLVED


def test_general_second_order_requirement_survives_typed_artifact():
    general = _slenderness(
        m2=_axis("M2", 500.0, ln=16000.0, ratio=0.0),
        m3=_axis("M3", 800.0),
    )
    artifact = execute_source_bound_fnd_col_2_with_artifact(_inputs(slenderness=general))
    assert artifact.readiness.status == REANALYSIS_REQUIRED
    assert artifact.readiness.second_order_treatment == SECOND_ORDER_GENERAL_ANALYSIS_REQUIRED


def test_nonexecuted_analysis_basis_gate_retains_no_fabricated_typed_readiness():
    artifact = execute_source_bound_fnd_col_2_with_artifact(
        _inputs(analysis_basis_status=AnalysisBasisStatus.REANALYSIS_REQUIRED)
    )
    assert artifact.readiness is None
    assert artifact.readiness_records == ()
    assert artifact.snapshot.regulatory_quantities == ()
    assert artifact.snapshot.closure_outcomes[0].execution_status.value == "BLOCKED"


def test_typed_execution_is_deterministic():
    assert execute_source_bound_fnd_col_2_with_artifact(_inputs()) == execute_source_bound_fnd_col_2_with_artifact(_inputs())


def test_fnd_col_2x_adds_no_p8a_dependency_or_binding_construction():
    source = inspect.getsource(fnd_col_2) + inspect.getsource(fnd_col_2_program)
    assert "column_combo_eligibility_projection" not in source
    assert "ComponentReadinessBinding" not in source
    assert "ENGINE_SELECTED_REBAR" not in source


def test_retained_readiness_can_enter_existing_component_readiness_binding_with_valid_context():
    artifact = execute_source_bound_fnd_col_2_with_artifact(_inputs())
    binding = ComponentReadinessBinding(
        readiness=artifact.readiness,
        model_fingerprint="model:fixture",
        evidence_epoch_id="epoch:fixture",
        readiness_ref=f"fnd-col-2:{artifact.readiness_records[0].readiness_instance_ref.value}",
        provenance_refs=("runtime-context:fixture",),
    )
    assert binding.readiness is artifact.readiness
    assert binding.component_id == COMP
