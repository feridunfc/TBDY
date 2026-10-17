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


def _reviewed_detailing(selected, facts):
    from tbdy_engine.application.column_longitudinal_detailing import ReviewedColumnDetailingEvidence, detailing_facts_digest
    from tbdy_engine.regulatory.column_detailing_checks import SOURCE_HASHES
    return ReviewedColumnDetailingEvidence(
        selected.component_id,selected.selected_rebar_ref,selected.model_fingerprint,selected.evidence_epoch_id,
        selected.material_context_ref,
        next(r for r in selected.provenance_refs if r.startswith(DESIGN_RESULT_REF_PREFIX)),
        next(r for r in selected.provenance_refs if r.startswith(DESIGN_LINEAGE_REF_PREFIX)),
        SOURCE_HASHES,'TBDY_HIGH_DUCTILITY_RECTANGULAR_SINGLE_DEFORMED_BARS',
        'OFFLINE SYNTHETIC REVIEW','2026-10-17T08:00:00+03:00',('TEST_DETAIL_DRAWING_AND_REPORT',),facts,
        detailing_facts_digest(facts),FIX._composition_fixture()['material_context'])


def _complete_detailing(selected):
    from tests.regulatory.test_column_detailing_checks import complete_facts
    c=selected.selected_candidate
    f=complete_facts(c,area=float(c.as_total_mm2)/float(c.rho))
    # This binding test uses the original selection fixture material, not a
    # substitute strength. Numerical boundary tests live in regulatory tests.
    fyd=FIX._composition_fixture()['material_context'].material.fyd_mpa
    return replace(f,lap=replace(f.lap,bond=replace(f.lap.bond,fyd_mpa=fyd)),anchorage=replace(f.anchorage,bond=replace(f.anchorage.bond,fyd_mpa=fyd)))


def _supported_selected_for_detailing(monkeypatch):
    # Reuse the existing selection fixture and existing geometry owners; this
    # binding-only fixture's PMM proof patch is not an engineering acceptance.
    from tbdy_engine.regulatory.column_detailing_checks import maximum_perimeter_bar_gap_mm
    FIX._patch_all_pmm_rows_proven(monkeypatch)
    values=FIX._composition_fixture();layout=values['layout_authority']
    candidates=tuple(c for c in layout.eligible_candidates if maximum_perimeter_bar_gap_mm(c.bars)<=300.)
    assert candidates
    values['layout_authority']=replace(layout,eligible_candidates=candidates)
    result=FIX._run(values)
    assert result.selected
    return result.selected_rebar


def test_a35_evidence_materializes_six_actual_decisions_and_keeps_exact_selection(monkeypatch):
    from tbdy_engine.application.column_longitudinal_detailing import DETAILING_PROVEN
    selected=_supported_selected_for_detailing(monkeypatch);facts=_complete_detailing(selected)
    result=materialize_selected_column_longitudinal_detailing(selected,reviewed_evidence=_reviewed_detailing(selected,facts))
    assert result.status==DETAILING_PROVEN and result.complete and result.unresolved_items==()
    assert result.engine_selected_rebar is selected and all(x.status=='PROVEN' for x in result.outcomes)
    assert all(x.values_json!='{}' for x in result.outcomes)
    assert all('TEST_DETAIL_DRAWING_AND_REPORT' in x.source_refs for x in result.outcomes)


def test_a35_failed_detail_is_resolved_but_never_complete(monkeypatch):
    from tbdy_engine.application.column_longitudinal_detailing import DETAILING_FAILED
    selected=_supported_selected_for_detailing(monkeypatch);facts=_complete_detailing(selected)
    facts=replace(facts,continuity=replace(facts.continuity,max_tie_spacing_mm=400.))
    result=materialize_selected_column_longitudinal_detailing(selected,reviewed_evidence=_reviewed_detailing(selected,facts))
    assert result.status==DETAILING_FAILED and not result.complete
    assert result.outcomes[-1].status=='FAIL' and result.outcomes[-1].resolved


@pytest.mark.parametrize('field,value',[('component_id','wrong'),('selected_rebar_ref','wrong'),('model_fingerprint','wrong'),('evidence_epoch_id','wrong'),('material_context_ref','wrong'),('design_result_ref','wrong'),('design_lineage_ref','wrong'),('source_hashes',()),('reviewed_facts_sha256','wrong'),('applicability','UNKNOWN'),('reviewed_at','2026-10-17T08:00:00')])
def test_a35_rejects_detached_review_source_epoch_lineage_and_facts(monkeypatch,field,value):
    selected=_selected_rebar(monkeypatch);facts=_complete_detailing(selected)
    evidence=replace(_reviewed_detailing(selected,facts),**{field:value})
    with pytest.raises(ValueError):materialize_selected_column_longitudinal_detailing(selected,reviewed_evidence=evidence)


def test_a35_cannot_substitute_anchorage_strength_under_same_material_reference(monkeypatch):
    selected=_selected_rebar(monkeypatch);f=_complete_detailing(selected)
    f=replace(f,anchorage=replace(f.anchorage,bond=replace(f.anchorage.bond,fyd_mpa=100.)))
    with pytest.raises(ValueError):materialize_selected_column_longitudinal_detailing(selected,reviewed_evidence=_reviewed_detailing(selected,f))
