from dataclasses import replace

import pytest

from tbdy_engine.design.columns.slenderness import SWAY_PREVENTED
from tbdy_engine.design.columns.slenderness_basis import (
    MOMENT_RATIO_AUTHORITY,
    REGULATORY_FREE_LENGTH_AUTHORITY,
    SWAY_CLASSIFICATION_AUTHORITY,
)
from tbdy_engine.regulatory.authority import (
    RegulatoryAuthorityCatalog,
    implementation_fingerprint,
    regulatory_claim_fingerprint,
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
    REGISTRY,
    RULE_ID,
    RULE_VERSION,
    SLENDERNESS_EVIDENCE_KEY,
    SPEC,
    STIFFNESS_EVIDENCE_KEY,
    WIDTH_MM_KEY,
    ColumnDesignReadinessApplicabilityInput,
)
from tbdy_engine.regulatory.fnd_col_2_authority import (
    APPROVED_IMPLEMENTATION_FINGERPRINT,
    APPROVED_IMPLEMENTATION_MODULES,
    CLAIMS,
    FND_COL_2_AUTHORITY_CATALOG,
    IMPLEMENTATION_BINDING,
    REVIEWED_CLAIM_FINGERPRINTS,
)
from tbdy_engine.regulatory.fnd_col_2_program import (
    compile_fnd_col_2_program,
    compile_source_bound_fnd_col_2_program,
    execute_source_bound_fnd_col_2,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    ExternalDependencyAuthority,
    KernelCompileError,
    PopulationCompleteness,
    RegulatoryCompileInputs,
    RegulatoryCompiler,
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


def _slenderness():
    def axis(name, h):
        return {
            "axis": name,
            "section_dimension_mm": h,
            "factual_clear_length_candidate_mm": 3000.0,
            "factual_clear_length_source_ref": f"ETABS:{name}:clear-length",
            "factual_clear_length_authority": "FACTUAL_ANALYSIS_CLEAR_LENGTH_CANDIDATE",
            "regulatory_free_length_ln_mm": 3000.0,
            "regulatory_free_length_source_ref": f"reviewed:{name}:ln",
            "regulatory_free_length_authority": REGULATORY_FREE_LENGTH_AUTHORITY,
            "sway_classification": SWAY_PREVENTED,
            "sway_source_ref": f"reviewed:{name}:sway",
            "sway_authority": SWAY_CLASSIFICATION_AUTHORITY,
            "effective_length_factor_k": None,
            "effective_length_source_ref": None,
            "effective_length_authority": None,
            "moment_ratio_m1_over_m2": 0.0,
            "moment_ratio_source_ref": f"reviewed:{name}:ratio",
            "moment_ratio_authority": MOMENT_RATIO_AUTHORITY,
            "allow_conservative_braced_ratio": False,
        }

    return {
        "component_id": COMP,
        "m2": axis("M2", 800.0),
        "m3": axis("M3", 500.0),
        "source_refs": ("fixture:slenderness",),
    }


def _external_authorities():
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
    return (
        _authority(
            "width",
            WIDTH_MM_KEY,
            DependencySourceKind.FACT,
            SemanticType.COLUMN_WIDTH,
            PhysicalDimension.LENGTH,
            UNIT_MM,
            500.0,
            refs=("fact:width",),
        ),
        _authority(
            "depth",
            DEPTH_MM_KEY,
            DependencySourceKind.FACT,
            SemanticType.COLUMN_DEPTH,
            PhysicalDimension.LENGTH,
            UNIT_MM,
            800.0,
            refs=("fact:depth",),
        ),
        _authority(
            "combos",
            COMBO_DEFINITIONS_KEY,
            DependencySourceKind.CONTEXT,
            SemanticType.CHECK_EVIDENCE_TRACE,
            PhysicalDimension.DIMENSIONLESS,
            UNIT_DIMENSIONLESS,
            combo,
            refs=("evidence:combo-definitions",),
        ),
        _authority(
            "demands",
            CASE_DEMANDS_KEY,
            DependencySourceKind.SOURCE_POPULATION,
            SemanticType.CHECK_EVIDENCE_TRACE,
            PhysicalDimension.DIMENSIONLESS,
            UNIT_DIMENSIONLESS,
            demands,
            refs=("evidence:concurrent-pmm-population",),
        ),
        _authority(
            "slenderness",
            SLENDERNESS_EVIDENCE_KEY,
            DependencySourceKind.CONTEXT,
            SemanticType.CHECK_EVIDENCE_TRACE,
            PhysicalDimension.DIMENSIONLESS,
            UNIT_DIMENSIONLESS,
            _slenderness(),
            refs=("evidence:slenderness",),
        ),
        _authority(
            "stiffness",
            STIFFNESS_EVIDENCE_KEY,
            DependencySourceKind.CONTEXT,
            SemanticType.CHECK_EVIDENCE_TRACE,
            PhysicalDimension.DIMENSIONLESS,
            UNIT_DIMENSIONLESS,
            (),
            refs=("evidence:stiffness",),
        ),
    )


def _inputs(*, catalog=None):
    return RegulatoryCompileInputs(
        rule_targets=(
            RuleScopeTarget(
                rule_id=RULE_ID,
                grain=Grain.COMPONENT,
                scope_ref=COMP,
                applicability_input=ColumnDesignReadinessApplicabilityInput(True),
                analysis_basis_status=AnalysisBasisStatus.MATCH,
            ),
        ),
        external_authorities=_external_authorities(),
        regulatory_authority_catalog=catalog,
    )


def _catalog(*, reviews=None, bindings=None):
    return RegulatoryAuthorityCatalog(
        source_documents=FND_COL_2_AUTHORITY_CATALOG.source_documents,
        anchors=FND_COL_2_AUTHORITY_CATALOG.anchors,
        claims=FND_COL_2_AUTHORITY_CATALOG.claims,
        review_records=(
            FND_COL_2_AUTHORITY_CATALOG.review_records if reviews is None else reviews
        ),
        implementation_bindings=(
            FND_COL_2_AUTHORITY_CATALOG.implementation_bindings if bindings is None else bindings
        ),
    )


def test_every_reviewed_claim_fingerprint_matches_exact_fnd_col_2_source_chain():
    reviews_by_claim = {
        review.claim_id: review for review in FND_COL_2_AUTHORITY_CATALOG.review_records
    }
    assert {claim.claim_id for claim in CLAIMS} == set(REVIEWED_CLAIM_FINGERPRINTS)
    assert {claim.claim_id for claim in CLAIMS} == set(reviews_by_claim)

    for claim in CLAIMS:
        anchors = tuple(
            FND_COL_2_AUTHORITY_CATALOG.anchor(ref) for ref in claim.anchor_refs
        )
        sources_by_id = {
            anchor.source_id: FND_COL_2_AUTHORITY_CATALOG.source(anchor.source_id)
            for anchor in anchors
        }
        actual = regulatory_claim_fingerprint(
            claim=claim,
            anchors=anchors,
            source_documents=tuple(
                sources_by_id[source_id] for source_id in sorted(sources_by_id)
            ),
        )
        approved = REVIEWED_CLAIM_FINGERPRINTS[claim.claim_id]
        assert actual == approved
        assert reviews_by_claim[claim.claim_id].reviewed_claim_fingerprint == approved


def test_approved_implementation_fingerprint_matches_exact_reviewed_modules():
    actual = implementation_fingerprint(
        rule_id=RULE_ID,
        rule_version=RULE_VERSION,
        evaluator_binding_id=SPEC.evaluator.binding_id,
        implementation_modules=APPROVED_IMPLEMENTATION_MODULES,
    )
    assert actual == APPROVED_IMPLEMENTATION_FINGERPRINT
    assert IMPLEMENTATION_BINDING.approved_implementation_fingerprint == actual


def test_strict_regulatory_compiler_accepts_concrete_fnd_col_2_catalog():
    program = RegulatoryCompiler.compile(
        REGISTRY,
        _inputs(catalog=FND_COL_2_AUTHORITY_CATALOG),
    )
    assert (
        program.plan.regulatory_authority_catalog_version
        == FND_COL_2_AUTHORITY_CATALOG.catalog_version
    )
    assert len(program.plan.compiled_authority_binding_refs) == 1
    assert IMPLEMENTATION_BINDING.binding_id in program.plan.compiled_authority_binding_refs[0]
    assert APPROVED_IMPLEMENTATION_FINGERPRINT in program.plan.compiled_authority_fingerprints[0]


def test_stale_implementation_fingerprint_fails_closed_at_compile():
    stale_binding = replace(
        IMPLEMENTATION_BINDING,
        approved_implementation_fingerprint="sha256:" + "0" * 64,
    )
    stale_catalog = _catalog(bindings=(stale_binding,))
    with pytest.raises(KernelCompileError, match="STALE_REGULATORY_IMPLEMENTATION_BINDING"):
        compile_fnd_col_2_program(_inputs(), authority_catalog=stale_catalog)


def test_stale_reviewed_claim_fingerprint_fails_closed_at_compile():
    first, *rest = FND_COL_2_AUTHORITY_CATALOG.review_records
    stale_review = replace(
        first,
        reviewed_claim_fingerprint="sha256:" + "0" * 64,
    )
    stale_catalog = _catalog(reviews=(stale_review, *rest))
    with pytest.raises(KernelCompileError, match="STALE_REGULATORY_CLAIM_REVIEW"):
        compile_fnd_col_2_program(_inputs(), authority_catalog=stale_catalog)


def test_missing_empty_and_unbound_authority_catalogs_fail_closed():
    with pytest.raises(KernelCompileError, match="requires a bound regulatory authority catalog"):
        compile_fnd_col_2_program(_inputs(), authority_catalog=None)

    empty = RegulatoryAuthorityCatalog()
    with pytest.raises(KernelCompileError, match="MISSING_REGULATORY_AUTHORITY_BINDING"):
        compile_fnd_col_2_program(_inputs(), authority_catalog=empty)

    unbound = _catalog(bindings=())
    with pytest.raises(KernelCompileError, match="MISSING_REGULATORY_AUTHORITY_BINDING"):
        compile_fnd_col_2_program(_inputs(), authority_catalog=unbound)


def test_executable_source_bound_path_consumes_concrete_authority_catalog():
    program = compile_source_bound_fnd_col_2_program(_inputs())
    assert (
        program.plan.regulatory_authority_catalog_version
        == FND_COL_2_AUTHORITY_CATALOG.catalog_version
    )
    assert IMPLEMENTATION_BINDING.binding_id in program.plan.compiled_authority_binding_refs[0]

    expected = RegulatoryEngine.execute(program)
    actual = execute_source_bound_fnd_col_2(_inputs())
    assert actual == expected
    assert len(actual.regulatory_quantities) == 1
    assert actual.regulatory_quantities[0].value["status"] == "READY"


def test_source_bound_compile_and_execution_are_deterministic():
    first_program = compile_source_bound_fnd_col_2_program(_inputs())
    second_program = compile_source_bound_fnd_col_2_program(_inputs())
    assert first_program.plan == second_program.plan
    assert execute_source_bound_fnd_col_2(_inputs()) == execute_source_bound_fnd_col_2(_inputs())
