"""Focused FND-COL-1 longitudinal reinforcement authority proofs."""
from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
import subprocess
import sys

import pytest

from tbdy_engine.design.columns.rebar_catalog import build_rebar_catalog_from_rows
from tbdy_engine.design.columns.rebar_layout import (
    ColumnRebarGeometryInputs,
    build_rectangular_column_rebar_geometry_candidate,
    ts500_min_clear_spacing_mm,
)
from tbdy_engine.regulatory.authority import (
    ApprovedImplementationBinding,
    RegulatoryAuthorityCatalog,
    RegulatoryAuthorityError,
    implementation_fingerprint,
    regulatory_claim_fingerprint,
    validate_rule_authority,
)
from tbdy_engine.regulatory.column_longitudinal_rebar import (
    ColumnLongitudinalAuthorityError,
    ColumnLongitudinalLayoutInputs,
    ColumnLongitudinalRequirementInputs,
    ColumnLongitudinalRuleProbe,
    FND_COL_1_CHECK_SPEC,
    FND_COL_1_RULE_ID,
    TBDYMinRequiredRebar,
    TBDY_CIRCULAR_COLUMN_MIN_LONGITUDINAL_BAR_COUNT,
    TBDY_COLUMN_LONGITUDINAL_LAP_SPLICE_TOTAL_RHO_MAX,
    derive_tbdy_min_required_rebar,
    evaluate_column_longitudinal_layout_candidate,
    evaluate_column_longitudinal_layouts,
)
from tbdy_engine.regulatory.contracts import Grain
from tbdy_engine.regulatory.kernel import (
    RegulatoryCompileInputs,
    RegulatoryCompiler,
    RuleScopeTarget,
)
from tbdy_engine.regulatory.registry import RegulatoryRegistry
from tbdy_engine.regulatory.sources.fnd_col_1_longitudinal import (
    APPROVED_IMPLEMENTATION_FINGERPRINT,
    CLAIM_DATA,
    CLAIMS_FOR_RULE,
    FND_COL_1_AUTHORITY_CATALOG,
    IMPLEMENTATION_MODULES,
)


def _requirement() -> ColumnLongitudinalRequirementInputs:
    return ColumnLongitudinalRequirementInputs(
        component_id="C1",
        section_id="COL300X300",
        width_mm=300.0,
        depth_mm=300.0,
        model_identity="model:abc",
        evidence_epoch_id="epoch:1",
        geometry_source_ref="Frame Assignments - Summary|C1",
    )


def _catalog(*diameters: float):
    rows = tuple({"Name": f"D{diameter:g}", "Diameter": diameter} for diameter in diameters)
    return build_rebar_catalog_from_rows(
        rows,
        name_field="Name",
        diameter_field="Diameter",
        diameter_unit="mm",
        source_name="ETABS Rebar Sizes",
    )


def _layout_inputs(*diameters: float, aggregate: float = 20.0) -> ColumnLongitudinalLayoutInputs:
    return ColumnLongitudinalLayoutInputs(
        requirement_inputs=_requirement(),
        clear_cover_mm=20.0,
        tie_diameter_mm=8.0,
        aggregate_max_mm=aggregate,
        rebar_catalog=_catalog(*diameters),
        cover_source_ref="project:cover",
        tie_source_ref="project:tie",
        aggregate_source_ref="project:aggregate",
    )


def _copy_catalog(
    catalog: RegulatoryAuthorityCatalog,
    *,
    claims=None,
    reviews=None,
    bindings=None,
) -> RegulatoryAuthorityCatalog:
    return RegulatoryAuthorityCatalog(
        source_documents=catalog.source_documents,
        anchors=catalog.anchors,
        claims=catalog.claims if claims is None else claims,
        review_records=catalog.review_records if reviews is None else reviews,
        implementation_bindings=catalog.implementation_bindings if bindings is None else bindings,
    )


def test_exact_claim_fingerprints_match_reviewed_literals() -> None:
    catalog = FND_COL_1_AUTHORITY_CATALOG
    assert set(CLAIMS_FOR_RULE) == set(CLAIM_DATA)
    assert len(CLAIMS_FOR_RULE) == 5
    for claim_id, (_anchor_refs, _version, _statement, expected) in CLAIM_DATA.items():
        claim = catalog.claim(claim_id)
        anchors = tuple(catalog.anchor(ref) for ref in claim.anchor_refs)
        source_ids = sorted({anchor.source_id for anchor in anchors})
        actual = regulatory_claim_fingerprint(
            claim=claim,
            anchors=anchors,
            source_documents=tuple(catalog.source(source_id) for source_id in source_ids),
        )
        assert actual == expected
        review = catalog.review(f"FND_COL_1_REVIEW:{claim_id}:r1")
        assert review.reviewed_claim_fingerprint == expected


def test_exact_implementation_fingerprint_matches_approved_literal() -> None:
    actual = implementation_fingerprint(
        rule_id=FND_COL_1_CHECK_SPEC.rule_id,
        rule_version=FND_COL_1_CHECK_SPEC.rule_version,
        evaluator_binding_id=FND_COL_1_CHECK_SPEC.evaluator.binding_id,
        implementation_modules=IMPLEMENTATION_MODULES,
    )
    assert actual == APPROVED_IMPLEMENTATION_FINGERPRINT


def test_strict_compiler_accepts_actual_fnd_col_1_catalog() -> None:
    registry = RegulatoryRegistry(checks=(FND_COL_1_CHECK_SPEC,))
    program = RegulatoryCompiler.compile(
        registry,
        RegulatoryCompileInputs(
            rule_targets=(
                RuleScopeTarget(
                    rule_id=FND_COL_1_RULE_ID,
                    grain=Grain.COMPONENT,
                    scope_ref="C1",
                    applicability_input=ColumnLongitudinalRuleProbe(
                        component_id="C1",
                        section_id="COL300X300",
                        rho=0.02,
                        bar_diameter_mm=16.0,
                        clear_spacing_mm=50.0,
                        aggregate_max_mm=20.0,
                    ),
                ),
            ),
            regulatory_authority_catalog=FND_COL_1_AUTHORITY_CATALOG,
        ),
    )
    assert "F0.9_SOURCE_AUTHORITY_OK" in program.plan.compile_diagnostics
    assert program.plan.regulatory_authority_catalog_version == FND_COL_1_AUTHORITY_CATALOG.catalog_version
    assert program.plan.compiled_authority_fingerprints


def test_stale_implementation_binding_fails_closed() -> None:
    binding = FND_COL_1_AUTHORITY_CATALOG.implementation_bindings[0]
    stale_binding = ApprovedImplementationBinding(
        binding_id=binding.binding_id,
        rule_id=binding.rule_id,
        claim_refs=binding.claim_refs,
        review_refs=binding.review_refs,
        evaluator_binding_id=binding.evaluator_binding_id,
        rule_version=binding.rule_version,
        implementation_modules=binding.implementation_modules,
        approved_implementation_fingerprint="sha256:" + "0" * 64,
        binding_version=binding.binding_version,
    )
    stale = _copy_catalog(FND_COL_1_AUTHORITY_CATALOG, bindings=(stale_binding,))
    with pytest.raises(RegulatoryAuthorityError, match="STALE_REGULATORY_IMPLEMENTATION_BINDING"):
        validate_rule_authority(FND_COL_1_CHECK_SPEC, stale)


def test_stale_claim_review_fails_closed() -> None:
    claims = list(FND_COL_1_AUTHORITY_CATALOG.claims)
    target = claims[0]
    claims[0] = replace(target, normalized_statement=target.normalized_statement + " Reviewed drift.")
    stale = _copy_catalog(FND_COL_1_AUTHORITY_CATALOG, claims=tuple(claims))
    with pytest.raises(RegulatoryAuthorityError, match="STALE_REGULATORY_CLAIM_REVIEW"):
        validate_rule_authority(FND_COL_1_CHECK_SPEC, stale)


def test_empty_or_unbound_catalog_fails_closed() -> None:
    empty = RegulatoryAuthorityCatalog()
    with pytest.raises(RegulatoryAuthorityError, match="MISSING_REGULATORY_AUTHORITY_BINDING"):
        validate_rule_authority(FND_COL_1_CHECK_SPEC, empty)
    unbound = _copy_catalog(FND_COL_1_AUTHORITY_CATALOG, bindings=())
    with pytest.raises(RegulatoryAuthorityError, match="MISSING_REGULATORY_AUTHORITY_BINDING"):
        derive_tbdy_min_required_rebar(_requirement(), authority_catalog=unbound)


def test_tbdy_min_required_rebar_is_factory_only_and_derives_one_and_four_percent() -> None:
    with pytest.raises(TypeError, match="authority-created only"):
        TBDYMinRequiredRebar()
    result = derive_tbdy_min_required_rebar(
        _requirement(), authority_catalog=FND_COL_1_AUTHORITY_CATALOG
    )
    assert result.authority == "TBDY_MIN_REQUIRED_REBAR"
    assert result.minimum_ratio == pytest.approx(0.01)
    assert result.maximum_ratio == pytest.approx(0.04)
    assert result.minimum_area_mm2 == pytest.approx(900.0)
    assert result.maximum_area_mm2 == pytest.approx(3600.0)
    assert result.minimum_bar_diameter_mm == pytest.approx(14.0)
    assert set(result.source_claim_refs) == set(CLAIMS_FOR_RULE)


def test_phi14_is_regulatory_eligibility_not_geometry_filter() -> None:
    candidate = build_rectangular_column_rebar_geometry_candidate(
        ColumnRebarGeometryInputs(300.0, 300.0, 20.0, 8.0),
        diameter_mm=12.0,
        n_bars_dir2=2,
        n_bars_dir3=2,
    )
    assert candidate.bar_count == 4
    eligibility = evaluate_column_longitudinal_layout_candidate(candidate, aggregate_max_mm=20.0)
    assert not eligibility.eligible
    assert "BELOW_TBDY_MIN_LONGITUDINAL_BAR_DIAMETER" in eligibility.reason_codes


def test_circular_six_bar_rule_is_not_applied_to_rectangular_layouts() -> None:
    assert TBDY_CIRCULAR_COLUMN_MIN_LONGITUDINAL_BAR_COUNT == 6
    candidate = build_rectangular_column_rebar_geometry_candidate(
        ColumnRebarGeometryInputs(300.0, 300.0, 20.0, 8.0),
        diameter_mm=18.0,
        n_bars_dir2=2,
        n_bars_dir3=2,
    )
    assert candidate.bar_count == 4
    eligibility = evaluate_column_longitudinal_layout_candidate(candidate, aggregate_max_mm=20.0)
    assert eligibility.eligible
    assert all("BAR_COUNT" not in code for code in eligibility.reason_codes)


def test_six_percent_splice_ceiling_is_separate_not_ordinary_layout_permission() -> None:
    assert TBDY_COLUMN_LONGITUDINAL_LAP_SPLICE_TOTAL_RHO_MAX == pytest.approx(0.06)
    candidate = build_rectangular_column_rebar_geometry_candidate(
        ColumnRebarGeometryInputs(250.0, 250.0, 20.0, 8.0),
        diameter_mm=22.0,
        n_bars_dir2=3,
        n_bars_dir3=3,
    )
    assert 0.04 < candidate.rho < 0.06
    eligibility = evaluate_column_longitudinal_layout_candidate(candidate, aggregate_max_mm=20.0)
    assert not eligibility.eligible
    assert "ABOVE_TBDY_MAX_LONGITUDINAL_RATIO" in eligibility.reason_codes


def test_ts500_spacing_is_aggregate_dependent() -> None:
    assert ts500_min_clear_spacing_mm(bar_diameter_mm=18.0, aggregate_max_mm=20.0) == pytest.approx(40.0)
    assert ts500_min_clear_spacing_mm(bar_diameter_mm=18.0, aggregate_max_mm=50.0) == pytest.approx(200.0 / 3.0)
    candidate = build_rectangular_column_rebar_geometry_candidate(
        ColumnRebarGeometryInputs(300.0, 300.0, 20.0, 8.0),
        diameter_mm=18.0,
        n_bars_dir2=4,
        n_bars_dir3=4,
    )
    assert evaluate_column_longitudinal_layout_candidate(candidate, aggregate_max_mm=20.0).eligible
    blocked = evaluate_column_longitudinal_layout_candidate(candidate, aggregate_max_mm=50.0)
    assert not blocked.eligible
    assert "BELOW_TS500_COLUMN_LONGITUDINAL_CLEAR_SPACING" in blocked.reason_codes


def test_missing_cover_tie_aggregate_or_catalog_fails_closed() -> None:
    common = dict(
        requirement_inputs=_requirement(),
        clear_cover_mm=20.0,
        tie_diameter_mm=8.0,
        aggregate_max_mm=20.0,
        rebar_catalog=_catalog(14.0, 18.0),
        cover_source_ref="project:cover",
        tie_source_ref="project:tie",
        aggregate_source_ref="project:aggregate",
    )
    for field in ("clear_cover_mm", "tie_diameter_mm", "aggregate_max_mm"):
        values = dict(common)
        values[field] = None
        with pytest.raises(ColumnLongitudinalAuthorityError, match="required"):
            ColumnLongitudinalLayoutInputs(**values)
    values = dict(common)
    values["rebar_catalog"] = None
    with pytest.raises(TypeError, match="rebar_catalog"):
        ColumnLongitudinalLayoutInputs(**values)


def test_geometrically_valid_candidate_can_be_regulatorily_ineligible() -> None:
    candidate = build_rectangular_column_rebar_geometry_candidate(
        ColumnRebarGeometryInputs(300.0, 300.0, 20.0, 8.0),
        diameter_mm=12.0,
        n_bars_dir2=2,
        n_bars_dir3=2,
    )
    assert candidate.authority == "CANDIDATE_GEOMETRY_ONLY"
    eligibility = evaluate_column_longitudinal_layout_candidate(candidate, aggregate_max_mm=20.0)
    assert not eligibility.eligible
    assert set(eligibility.reason_codes) >= {
        "BELOW_TBDY_MIN_LONGITUDINAL_RATIO",
        "BELOW_TBDY_MIN_LONGITUDINAL_BAR_DIAMETER",
    }


def test_no_nearest_bar_substitution_and_no_engine_selected_rebar() -> None:
    result = evaluate_column_longitudinal_layouts(
        _layout_inputs(14.0, 20.0),
        authority_catalog=FND_COL_1_AUTHORITY_CATALOG,
    )
    produced_diameters = {item.bar_diameter_mm for item in result.eligible_candidates}
    assert produced_diameters <= {14.0, 20.0}
    assert 16.0 not in produced_diameters
    assert 18.0 not in produced_diameters
    assert result.requirement.authority == "TBDY_MIN_REQUIRED_REBAR"
    assert result.authority == "TBDY_COLUMN_LAYOUT_ELIGIBILITY"
    assert not hasattr(result, "engine_selected_rebar")
    assert all(candidate.authority == "CANDIDATE_GEOMETRY_ONLY" for candidate in result.eligible_candidates)


def test_fresh_interpreter_import_without_shared_checks_init_patch() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import tbdy_engine.regulatory.column_longitudinal_rebar; "
            "import tbdy_engine.regulatory.sources.fnd_col_1_longitudinal",
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_layout_population_is_deterministic() -> None:
    first = evaluate_column_longitudinal_layouts(
        _layout_inputs(14.0, 18.0, 20.0),
        authority_catalog=FND_COL_1_AUTHORITY_CATALOG,
    )
    second = evaluate_column_longitudinal_layouts(
        _layout_inputs(14.0, 18.0, 20.0),
        authority_catalog=FND_COL_1_AUTHORITY_CATALOG,
    )
    assert first == second
    assert math.isfinite(first.requirement.minimum_area_mm2)
