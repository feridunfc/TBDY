from tbdy_engine.design.columns.slenderness import SWAY_PREVENTED
from tbdy_engine.design.columns.slenderness_basis import (
    MOMENT_RATIO_AUTHORITY,
    REGULATORY_FREE_LENGTH_AUTHORITY,
    SWAY_CLASSIFICATION_AUTHORITY,
)
from tbdy_engine.regulatory.contracts import (
    AvailabilityState,
    DependencyKey,
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
    REGISTRY,
    RULE_ID,
    SLENDERNESS_EVIDENCE_KEY,
    STIFFNESS_EVIDENCE_KEY,
    WIDTH_MM_KEY,
    ColumnDesignReadinessApplicabilityInput,
)
from tbdy_engine.regulatory.kernel import (
    AnalysisBasisStatus,
    ExternalDependencyAuthority,
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


def _authorities(*, slenderness_value=None, stiffness=()):
    combo = (
        {
            "name": "ULS",
            "combo_type": "LINEAR_ADD",
            "constituents": ({"name": "G", "scale_factor": 1.0, "cname_type": "LOAD_CASE"},),
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
    if slenderness_value is None:
        slenderness_value = _slenderness()
    return (
        _authority("width", WIDTH_MM_KEY, DependencySourceKind.FACT, SemanticType.COLUMN_WIDTH, PhysicalDimension.LENGTH, UNIT_MM, 500.0, refs=("fact:width",)),
        _authority("depth", DEPTH_MM_KEY, DependencySourceKind.FACT, SemanticType.COLUMN_DEPTH, PhysicalDimension.LENGTH, UNIT_MM, 800.0, refs=("fact:depth",)),
        _authority("combos", COMBO_DEFINITIONS_KEY, DependencySourceKind.CONTEXT, SemanticType.CHECK_EVIDENCE_TRACE, PhysicalDimension.DIMENSIONLESS, UNIT_DIMENSIONLESS, combo, refs=("evidence:combo-definitions",)),
        _authority("demands", CASE_DEMANDS_KEY, DependencySourceKind.SOURCE_POPULATION, SemanticType.CHECK_EVIDENCE_TRACE, PhysicalDimension.DIMENSIONLESS, UNIT_DIMENSIONLESS, demands, refs=("evidence:concurrent-pmm-population",)),
        _authority("slenderness", SLENDERNESS_EVIDENCE_KEY, DependencySourceKind.CONTEXT, SemanticType.CHECK_EVIDENCE_TRACE, PhysicalDimension.DIMENSIONLESS, UNIT_DIMENSIONLESS, slenderness_value, refs=("evidence:slenderness",)),
        _authority("stiffness", STIFFNESS_EVIDENCE_KEY, DependencySourceKind.CONTEXT, SemanticType.CHECK_EVIDENCE_TRACE, PhysicalDimension.DIMENSIONLESS, UNIT_DIMENSIONLESS, stiffness, refs=("evidence:stiffness",)),
    )


def _compile(authorities, *, analysis_basis_status=AnalysisBasisStatus.MATCH):
    return RegulatoryCompiler.compile(
        REGISTRY,
        RegulatoryCompileInputs(
            rule_targets=(
                RuleScopeTarget(
                    rule_id=RULE_ID,
                    grain=Grain.COMPONENT,
                    scope_ref=COMP,
                    applicability_input=ColumnDesignReadinessApplicabilityInput(True),
                    analysis_basis_status=analysis_basis_status,
                ),
            ),
            external_authorities=authorities,
        ),
    )


def test_f0_derivation_emits_ready_canonical_concurrent_demand_state():
    snapshot = RegulatoryEngine.execute(_compile(_authorities()))
    assert len(snapshot.regulatory_quantities) == 1
    quantity = snapshot.regulatory_quantities[0]
    assert quantity.quantity_key == READINESS_KEY
    assert quantity.value["status"] == "READY"
    assert quantity.value["analysis_basis_status"] == "MATCH"
    states = quantity.value["demand_states"]
    assert len(states) == 2
    assert states[0]["source_identity"].startswith("raw:G:")
    assert states[1]["source_identity"].startswith("raw:G:")
    assert {(s["nd_compression_n"], s["m2_nmm"], s["m3_nmm"]) for s in states} == {
        (1_000_000.0, -100_000_000.0, 80_000_000.0),
        (900_000.0, 70_000_000.0, -60_000_000.0),
    }


def test_caller_created_resolved_flag_is_not_a_declared_dependency_and_cannot_authorize():
    bogus = _authority(
        "bogus-resolved",
        DependencyKey("minimum_eccentricity_status"),
        DependencySourceKind.CONTEXT,
        SemanticType.CHECK_EVIDENCE_TRACE,
        PhysicalDimension.DIMENSIONLESS,
        UNIT_DIMENSIONLESS,
        "RESOLVED",
        refs=("caller:bogus",),
    )
    authorities = _authorities(slenderness_value=None) + (bogus,)
    # Replace canonical slenderness authority value with factual absence.
    authorities = tuple(
        _authority(
            item.authority_id,
            item.key,
            item.source_kind,
            item.semantic_type,
            item.physical_dimension,
            item.unit,
            None if item.key == SLENDERNESS_EVIDENCE_KEY else item.value,
            refs=item.provenance_refs,
        )
        for item in authorities
    )
    snapshot = RegulatoryEngine.execute(_compile(authorities))
    quantity = snapshot.regulatory_quantities[0]
    assert quantity.value["status"] != "READY"
    assert "minimum_eccentricity_status" not in {dep.value for dep in quantity.dependency_refs}


def test_factual_nonunit_stiffness_is_derived_into_reanalysis_required():
    stiffness = (
        {
            "section_name": "C80",
            "member_kind": "COLUMN",
            "i2_modifier": 0.70,
            "i3_modifier": 0.70,
            "source_refs": ("ETABS:C80",),
        },
    )
    slenderness = _slenderness()
    for axis in ("m2", "m3"):
        slenderness[axis]["sway_classification"] = None
        slenderness[axis]["sway_source_ref"] = None
        slenderness[axis]["sway_authority"] = None
        slenderness[axis]["moment_ratio_m1_over_m2"] = None
        slenderness[axis]["moment_ratio_source_ref"] = None
        slenderness[axis]["moment_ratio_authority"] = None
    snapshot = RegulatoryEngine.execute(_compile(_authorities(slenderness_value=slenderness, stiffness=stiffness)))
    quantity = snapshot.regulatory_quantities[0]
    assert quantity.value["status"] == "REANALYSIS_REQUIRED"
    assert quantity.value["analysis_basis_status"] == "REANALYSIS_REQUIRED"


def test_existing_analysis_basis_gate_blocks_execution_before_domain_derivation():
    snapshot = RegulatoryEngine.execute(
        _compile(_authorities(), analysis_basis_status=AnalysisBasisStatus.REANALYSIS_REQUIRED)
    )
    assert snapshot.regulatory_quantities == ()
    assert snapshot.closure_outcomes[0].execution_status.value == "BLOCKED"
    assert "REANALYSIS_REQUIRED" in snapshot.closure_outcomes[0].diagnostic_refs[0]


def test_f0_output_is_deterministic_and_never_emits_engine_selected_rebar():
    first = RegulatoryEngine.execute(_compile(_authorities()))
    second = RegulatoryEngine.execute(_compile(_authorities()))
    assert first == second
    assert "ENGINE_SELECTED_REBAR" not in repr(first)
