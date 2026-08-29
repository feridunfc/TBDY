"""P8A-B provider-neutral production composition proofs."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import ast
import importlib.util
from pathlib import Path
import sys

import pytest

import tbdy_engine.design.columns.column_pmm_assessment as pmm_subject
from tbdy_engine.design.columns.column_combo_eligibility_projection import (
    ComboAnalysisBasisBinding,
)
from tbdy_engine.design.columns.column_concrete_design_evidence_authority import (
    AnalysisBasisEligibilityEvidence,
    ConcreteDesignComboReconciliation,
)
from tbdy_engine.design.columns.column_longitudinal_production_composition import (
    compose_canonical_column_longitudinal_selection,
)
from tbdy_engine.design.columns.column_longitudinal_selection import (
    CanonicalEngineSelectedRebar,
    ENGINE_SELECTED_REBAR_AUTHORITY,
    STATUS_SELECTED,
)
from tbdy_engine.design.columns.section_capacity import (
    ColumnInteractionEnvelope,
    RadialMomentCapacity,
)
from tbdy_engine.features.column_design_rebar_evidence import (
    ColumnDesignRebarEvidenceError,
    FactualColumnDesignResultPopulation,
    FactualColumnDesignResultRow,
)
from tbdy_engine.regulatory.column_candidate_adequacy_authority import (
    authorize_candidate_adequacy_policy,
)
from tbdy_engine.regulatory.sources.fnd_col_4_candidate_adequacy import (
    FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG,
)


def _load_module(name: str, path: Path):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load fixture module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FIX = _load_module(
    "_p8ab_fnd_col_4_fixture",
    Path(__file__).with_name("test_fnd_col_4_pmm_assessment.py"),
)


def _adequacy_policy():
    return authorize_candidate_adequacy_policy(
        authority_catalog=FND_COL_4_CANDIDATE_ADEQUACY_AUTHORITY_CATALOG,
    )


def _patch_all_pmm_rows_proven(monkeypatch):
    def envelope(
        *,
        width_mm,
        depth_mm,
        bars,
        material,
        target_n_compression_n,
        angle_count,
        axial_tolerance_n,
    ):
        return ColumnInteractionEnvelope(
            target_n_compression_n=target_n_compression_n,
            states=(),
            status="PROVEN",
            angle_step_deg=360.0 / float(angle_count),
        )

    def radial(
        envelope,
        *,
        demand_m2_nmm,
        demand_m3_nmm,
    ):
        return RadialMomentCapacity(
            demand_angle_deg=0.0,
            capacity_nmm=1_000_000_000.0,
            boundary_m2_nmm=1_000_000_000.0,
            boundary_m3_nmm=0.0,
            status="PROVEN",
        )

    monkeypatch.setattr(
        pmm_subject,
        "build_interaction_envelope_at_axial_force",
        envelope,
    )
    monkeypatch.setattr(
        pmm_subject,
        "radial_moment_capacity",
        radial,
    )


def _composition_fixture():
    selection_inputs, _ = FIX._selection_context()
    projection = selection_inputs.combo_eligibility_projections[0]
    identity = projection.design_combo_identity
    definition_fingerprint = projection.normalized_definition_fingerprint
    assert definition_fingerprint is not None

    reconciliation = ConcreteDesignComboReconciliation(
        model_fingerprint=FIX.MODEL,
        evidence_epoch_id=FIX.EPOCH,
        expected=(identity,),
        actual_selected=(identity,),
        matched=(identity,),
        missing_expected=(),
        unexpected_selected=(),
        definition_mismatch=(),
        actual_definition_drift=(),
        unsupported_definition=(),
        analysis_basis_blocked=(),
        reviewed_definition_fingerprints=(
            (identity[0], identity[1], definition_fingerprint),
        ),
        actual_capture_definition_fingerprints=(
            (identity[0], identity[1], definition_fingerprint),
        ),
        definition_fingerprints=(
            (identity[0], identity[1], definition_fingerprint),
        ),
        source_refs=("reconciliation:p8ab",),
    )

    analysis_binding = ComboAnalysisBasisBinding(
        design_combo_identity=identity,
        evidence=AnalysisBasisEligibilityEvidence(
            status_value="MATCH",
            compatibility_ref="analysis-basis:p8ab:ULS",
            provenance_refs=("analysis-basis:p8ab:provenance",),
        ),
        normalized_definition_fingerprint=definition_fingerprint,
        model_fingerprint=FIX.MODEL,
        evidence_epoch_id=FIX.EPOCH,
        provenance_refs=("analysis-binding:p8ab:ULS",),
    )

    component_id = selection_inputs.component_id
    section_id = selection_inputs.layout_authority.requirement.section_id
    factual = FactualColumnDesignResultPopulation(
        model_fingerprint=FIX.MODEL,
        evidence_epoch_id=FIX.EPOCH,
        expected_component_ids=(component_id,),
        attempted_component_ids=(component_id,),
        captured_component_ids=(component_id,),
        reported_result_row_count=1,
        rows=(
            FactualColumnDesignResultRow(
                source_row_id="p8ab:row:1",
                component_id=component_id,
                unique_name="U1",
                story="Story1",
                label="C1",
                assigned_section=section_id,
                design_section=section_id,
                my_option=2,
                pmm_combo=identity[1],
                location_mm=Decimal("500"),
                pmm_area_mm2=Decimal("0"),
                error_summary="",
                warning_summary="",
                model_fingerprint=FIX.MODEL,
                evidence_epoch_id=FIX.EPOCH,
                source_refs=("source:p8ab:row:1",),
            ),
        ),
        source_refs=("capture:p8ab",),
    )

    return {
        "component_id": component_id,
        "layout_authority": selection_inputs.layout_authority,
        "readiness_binding": selection_inputs.readiness_binding,
        "combo_reconciliation": reconciliation,
        "combo_analysis_basis_bindings": {identity: analysis_binding},
        "factual_design_results": factual,
        "selection_policy": selection_inputs.policy,
        "numerical_policy": FIX._policy(),
        "material_context": FIX._material(),
        "adequacy_policy": _adequacy_policy(),
    }


def _run(values):
    return compose_canonical_column_longitudinal_selection(**values)


def test_factual_rows_to_exact_combo_to_canonical_selected_rebar(monkeypatch):
    _patch_all_pmm_rows_proven(monkeypatch)
    values = _composition_fixture()

    result = _run(values)

    assert result.status == STATUS_SELECTED
    assert result.selected
    assert isinstance(result.selected_rebar, CanonicalEngineSelectedRebar)
    selected = result.selected_rebar
    assert selected is not None
    assert selected.authority == ENGINE_SELECTED_REBAR_AUTHORITY
    assert selected.rank == 1
    assert selected.required_area_decision_ids
    assert selected.pmm_decision_ids
    assert result.adequacy_population is not None
    assert result.ranking_policy is not None
    assert result.selection_contract is not None
    expected_area_rows = (
        len(values["layout_authority"].eligible_candidates)
        * len(result.adequacy_population.requirement_ids)
    )
    expected_pmm_rows = (
        len(values["layout_authority"].eligible_candidates)
        * len(values["readiness_binding"].readiness.demand_states)
    )
    assert result.adequacy_population.expected_required_area_decision_count == expected_area_rows
    assert len(result.adequacy_population.required_area_rows) == expected_area_rows
    assert result.adequacy_population.expected_pmm_decision_count == expected_pmm_rows
    assert len(result.adequacy_population.pmm_rows) == expected_pmm_rows
    assert selected.requirement_ids == result.adequacy_population.requirement_ids
    assert selected.demand_state_ids == result.adequacy_population.demand_state_ids
    assert selected.ranking_policy_fingerprint == result.ranking_policy.policy_fingerprint
    assert selected.adequacy_policy_fingerprint == result.adequacy_population.adequacy_policy_fingerprint
    assert selected.numerical_policy_fingerprint == result.adequacy_population.numerical_policy_fingerprint
    assert result.selection_contract.etabs_requirement_ids == selected.requirement_ids
    assert result.selection_contract.combo_projection_ids


def test_non_ready_component_cannot_produce_selected_rebar(monkeypatch):
    values = _composition_fixture()
    readiness = replace(
        values["readiness_binding"].readiness,
        status="BLOCKED",
        second_order_treatment="MOMENT_MAGNIFICATION_REQUIRED",
    )
    values["readiness_binding"] = replace(
        values["readiness_binding"],
        readiness=readiness,
    )

    result = _run(values)

    assert not result.selected
    assert result.selected_rebar is None


def test_incomplete_p8a_promotion_cannot_fall_back_to_selection(monkeypatch):
    values = _composition_fixture()
    factual = values["factual_design_results"]
    values["factual_design_results"] = replace(
        factual,
        rows=(replace(factual.rows[0], warning_summary="fixture warning"),),
    )

    result = _run(values)

    assert not result.selected
    assert result.selected_rebar is None


@pytest.mark.parametrize(
    ("field", "replacement"),
    (("model_fingerprint", "model:other"), ("evidence_epoch_id", "epoch:other")),
)
def test_cross_context_factual_population_fails_closed(field, replacement):
    values = _composition_fixture()
    factual = values["factual_design_results"]
    changed_row = replace(factual.rows[0], **{field: replacement})
    values["factual_design_results"] = replace(
        factual,
        rows=(changed_row,),
        **{field: replacement},
    )

    with pytest.raises(ColumnDesignRebarEvidenceError):
        _run(values)


def test_unbindable_exact_combo_cannot_fall_back_to_etabs_required_rebar(monkeypatch):
    values = _composition_fixture()
    factual = values["factual_design_results"]
    values["factual_design_results"] = replace(
        factual,
        rows=(replace(factual.rows[0], pmm_combo="UNBOUND_COMBO"),),
    )

    result = _run(values)

    assert not result.selected
    assert result.selected_rebar is None


def test_identical_typed_inputs_are_deterministic(monkeypatch):
    _patch_all_pmm_rows_proven(monkeypatch)
    values = _composition_fixture()

    first = _run(values)
    second = _run(values)

    assert first == second
    assert first.selected_rebar is not None
    assert second.selected_rebar is not None
    assert first.selected_rebar.selected_rebar_ref == second.selected_rebar.selected_rebar_ref


def test_existing_p8a_provider_to_required_rebar_integration_remains_green(monkeypatch):
    integration = _load_module(
        "_p8ab_existing_p8a_integration",
        Path(__file__).resolve().parents[2]
        / "integration"
        / "test_p8a_design_result_to_required_rebar_chain.py",
    )
    integration.test_provider_to_exact_combo_projection_to_etabs_required_rebar_preserves_all_design_rows(
        monkeypatch
    )


def test_composition_is_orchestration_only_and_no_second_emitter():
    import tbdy_engine.design.columns.column_longitudinal_production_composition as subject

    source = Path(subject.__file__).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)

    forbidden = {
        "tbdy_engine.design.columns.rebar_selection",
        "tbdy_engine.design.columns.column_rebar_design_engine",
        "tbdy_engine.design.columns.column_design_engine",
    }
    assert imports.isdisjoint(forbidden)
    assert "CanonicalEngineSelectedRebar(" not in source
    assert '"ENGINE_SELECTED_REBAR"' not in source
    assert "SELECTED_ENGINE_REBAR" not in source


def test_canonical_selected_rebar_constructor_has_one_production_owner():
    root = Path(__file__).resolve().parents[3] / "tbdy_engine"
    owner = (
        root
        / "design"
        / "columns"
        / "column_longitudinal_selection.py"
    ).resolve()
    constructor_sites = []

    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name == "CanonicalEngineSelectedRebar":
                constructor_sites.append(path.resolve())

    assert constructor_sites
    assert set(constructor_sites) == {owner}
