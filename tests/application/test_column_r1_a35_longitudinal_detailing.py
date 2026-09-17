"""Focused A35 selected-cage -> longitudinal-detailing proofs."""
from __future__ import annotations

from dataclasses import replace
import importlib.util
from pathlib import Path
import sys

import pytest

from tbdy_engine.application.column_longitudinal_detailing import (
    ANCHORAGE,
    CONTINUITY_CORNER_REQUIREMENTS,
    FINAL_DETAILING_REQUIRED,
    LAP_RHO_CLAIM,
    LAP_SECTION_RHO,
    LAP_SPLICE_LOCATION_REGION,
    MECHANICAL_WELDED_SPLICE_APPLICABILITY,
    OUTCOME_UNRESOLVED,
    SECTION_TRANSITION,
    ColumnLongitudinalDetailingError,
    materialize_selected_column_longitudinal_detailing,
)
from tbdy_engine.design.columns.column_longitudinal_selection import (
    ENGINE_SELECTED_REBAR_AUTHORITY,
)
from tbdy_engine.integration.etabs_design_lineage import (
    DESIGN_LINEAGE_REF_PREFIX,
    DESIGN_RESULT_REF_PREFIX,
)


def _load_selection_fixture():
    name = "_a35_existing_selected_rebar_fixture"
    if name in sys.modules:
        return sys.modules[name]
    path = (
        Path(__file__).resolve().parents[1]
        / "design"
        / "columns"
        / "test_p8a_b_column_longitudinal_production_composition.py"
    )
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load selected-rebar fixture: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


FIX = _load_selection_fixture()


def _selected_rebar(monkeypatch):
    FIX._patch_all_pmm_rows_proven(monkeypatch)
    result = FIX._run(FIX._composition_fixture())
    assert result.selected
    assert result.selected_rebar is not None
    assert result.selected_rebar.authority == ENGINE_SELECTED_REBAR_AUTHORITY
    return result.selected_rebar


def test_selected_cage_materializes_complete_a35_outcome_population_without_false_completion(
    monkeypatch,
):
    selected = _selected_rebar(monkeypatch)

    result = materialize_selected_column_longitudinal_detailing(selected)

    assert result.status == FINAL_DETAILING_REQUIRED
    assert not result.complete
    assert result.component_id == selected.component_id
    assert result.selected_rebar_ref == selected.selected_rebar_ref
    assert result.engine_selected_rebar is selected
    assert result.model_fingerprint == selected.model_fingerprint
    assert result.evidence_epoch_id == selected.evidence_epoch_id
    assert tuple(item.item for item in result.outcomes) == (
        LAP_SPLICE_LOCATION_REGION,
        LAP_SECTION_RHO,
        ANCHORAGE,
        SECTION_TRANSITION,
        MECHANICAL_WELDED_SPLICE_APPLICABILITY,
        CONTINUITY_CORNER_REQUIREMENTS,
    )
    assert all(item.status == OUTCOME_UNRESOLVED for item in result.outcomes)


def test_a35_retains_exact_selected_candidate_geometry_area_and_adequacy_identity(
    monkeypatch,
):
    selected = _selected_rebar(monkeypatch)

    result = materialize_selected_column_longitudinal_detailing(selected)

    assert result.selected_candidate_identity == selected.candidate_id
    assert result.selected_candidate is selected.selected_candidate
    assert result.selected_bar_diameter_mm == selected.selected_candidate.bar_diameter_mm
    assert result.selected_bar_count == selected.selected_candidate.bar_count
    assert result.selected_total_area_mm2 == selected.as_total_mm2
    assert result.candidate_adequacy_ref == selected.candidate_adequacy_ref
    assert selected.candidate_adequacy_ref in result.source_refs
    assert set(selected.required_area_decision_ids).issubset(result.source_refs)
    assert set(selected.pmm_decision_ids).issubset(result.source_refs)
    assert selected.material_context_ref in result.source_refs


def test_a35_retains_exact_b6_design_result_and_lineage_parentage(monkeypatch):
    selected = _selected_rebar(monkeypatch)

    result = materialize_selected_column_longitudinal_detailing(selected)

    assert result.design_result_parent_ref.startswith(DESIGN_RESULT_REF_PREFIX)
    assert result.design_lineage_qualification_ref.startswith(DESIGN_LINEAGE_REF_PREFIX)
    assert result.design_result_parent_ref in selected.provenance_refs
    assert result.design_lineage_qualification_ref in selected.provenance_refs
    assert result.design_result_parent_ref in result.source_refs
    assert result.design_lineage_qualification_ref in result.source_refs


def test_lap_section_outcome_retains_reviewed_source_authority_without_inventing_lap_population(
    monkeypatch,
):
    selected = _selected_rebar(monkeypatch)

    result = materialize_selected_column_longitudinal_detailing(selected)
    lap = next(item for item in result.outcomes if item.item == LAP_SECTION_RHO)

    assert LAP_RHO_CLAIM in lap.source_refs
    assert "SOURCE_BOUND_LAP_SECTION_REINFORCEMENT_POPULATION_NOT_MATERIALIZED" == lap.reason
    assert selected.selected_rebar_ref in lap.source_refs


def test_a35_rejects_noncanonical_selected_rebar():
    with pytest.raises(TypeError):
        materialize_selected_column_longitudinal_detailing(object())


def test_a35_fails_closed_if_selected_identity_is_detached(monkeypatch):
    selected = _selected_rebar(monkeypatch)
    result = materialize_selected_column_longitudinal_detailing(selected)

    with pytest.raises(ColumnLongitudinalDetailingError, match="selected-rebar reference"):
        replace(result, selected_rebar_ref="engine-selected-rebar:sha256:" + "0" * 64)
    with pytest.raises(ColumnLongitudinalDetailingError, match="component identity"):
        replace(result, component_id="COLUMN-DETACHED")
    with pytest.raises(ColumnLongitudinalDetailingError, match="model fingerprint"):
        replace(result, model_fingerprint="model-fingerprint:detached")
    with pytest.raises(ColumnLongitudinalDetailingError, match="EvidenceEpoch"):
        replace(result, evidence_epoch_id="evidence-epoch:detached")


def test_a35_owner_contains_no_second_selector_pmm_startdesign_or_etabs_path():
    import tbdy_engine.application.column_longitudinal_detailing as detailing

    source = Path(detailing.__file__).read_text(encoding="utf-8-sig")
    forbidden = (
        "select_canonical_column_longitudinal_rebar(",
        "evaluate_column_candidate_adequacy_population(",
        "execute_controlled_concrete_design(",
        "StartDesign(",
        "SapModel",
        "win32com",
        "comtypes",
    )
    assert all(token not in source for token in forbidden)


def test_production_runtime_contains_real_a35_consumer_after_selection():
    import tbdy_engine.application.column_longitudinal_runtime as runtime

    source = Path(runtime.__file__).read_text(encoding="utf-8-sig")
    assert "materialize_selected_column_longitudinal_detailing(" in source
    assert "selection.selected_rebar" in source
    assert "detailing=detailing" in source
