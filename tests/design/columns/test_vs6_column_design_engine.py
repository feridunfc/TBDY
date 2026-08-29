from tbdy_engine.design.columns.column_design_demand_engine import ColumnComboDefinition
from tbdy_engine.design.columns.column_design_engine import evaluate_column_design
from tbdy_engine.design.columns.column_rebar_design_engine import ColumnRebarDesignInputs
from tbdy_engine.design.columns.combo_pattern_engine import ComboPatternConstituent
from tbdy_engine.design.columns.rebar_catalog import build_rebar_catalog_from_rows
from tbdy_engine.design.columns.rebar_selection import (
    ColumnDemandBasis,
    ColumnDemandState,
    ColumnRebarSelectionPolicy,
)
from tbdy_engine.design.columns.section_capacity import ColumnSectionMaterial
from tbdy_engine.design.columns.slenderness import (
    ColumnSlendernessAxisBasis,
    ColumnSlendernessBasis,
    SWAY_PREVENTED,
)
from tbdy_engine.design.columns.slenderness_basis import (
    ColumnSlendernessAxisEvidence,
    ColumnSlendernessEvidence,
    FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
    REGULATORY_FREE_LENGTH_AUTHORITY,
)
from tbdy_engine.design.columns.stability_stiffness_basis import (
    AssignedFrameBendingModifierEvidence,
    STATUS_REANALYSIS_REQUIRED,
    assess_ts500_eq713_stiffness_basis,
)


COMP = "+0.00:C2:236"


def _state(case, case_type, end, station, n=1_000.0, m2=10.0, m3=20.0, step=None):
    return ColumnDemandState(
        state_id=f"{case}:{end}:{step}",
        component_id=COMP,
        output_case=case,
        case_type=case_type,
        step_type=step,
        step_number=None,
        station_m=station,
        end_tag=end,
        nd_compression_n=n,
        m2_nmm=m2,
        m3_nmm=m3,
        source_identity=f"src:{case}:{end}:{step}",
    )


def _catalog():
    return build_rebar_catalog_from_rows(
        (
            {"Name": "14", "Diameter": 14.0},
            {"Name": "20", "Diameter": 20.0},
            {"Name": "25", "Diameter": 25.0},
        ),
        name_field="Name",
        diameter_field="Diameter",
        diameter_unit="mm",
        source_name="fixture",
    )


def _rebar_inputs(*, combo_scope="RESOLVED", min_ecc="BLOCKED", slenderness="BLOCKED"):
    return ColumnRebarDesignInputs(
        component_id=COMP,
        width_mm=800.0,
        depth_mm=800.0,
        clear_cover_mm=40.0,
        tie_diameter_mm=10.0,
        aggregate_max_mm=25.0,
        material=ColumnSectionMaterial(fck_mpa=35.0, fcd_mpa=35.0 / 1.5, fyd_mpa=500.0 / 1.15),
        demand_basis=ColumnDemandBasis(
            analysis_order_status="RESOLVED",
            minimum_eccentricity_status=min_ecc,
            slenderness_status=slenderness,
            combination_scope_status=combo_scope,
            review_refs=("fixture-review",),
        ),
        selection_policy=ColumnRebarSelectionPolicy(angle_count=36, axial_tolerance_n=1_000.0),
    )


def _slenderness_basis():
    def axis(name):
        return ColumnSlendernessAxisBasis(
            axis=name,
            section_dimension_mm=800.0,
            free_length_ln_mm=3000.0,
            effective_length_factor_k=1.0,
            sway_classification=SWAY_PREVENTED,
            moment_ratio_m1_over_m2=0.0,
            source_refs=(f"fixture:{name}",),
        )

    return ColumnSlendernessBasis(
        component_id=COMP,
        m2=axis("M2"),
        m3=axis("M3"),
        source_refs=("fixture:slenderness",),
    )


def _slenderness_evidence_without_sway():
    def axis(name):
        return ColumnSlendernessAxisEvidence(
            axis=name,
            section_dimension_mm=800.0,
            factual_clear_length_candidate_mm=3000.0,
            factual_clear_length_source_ref=f"fixture:{name}:clear-candidate",
            factual_clear_length_authority=FACTUAL_CLEAR_LENGTH_CANDIDATE_AUTHORITY,
            regulatory_free_length_ln_mm=3000.0,
            regulatory_free_length_source_ref=f"fixture:{name}:ln",
            regulatory_free_length_authority=REGULATORY_FREE_LENGTH_AUTHORITY,
        )

    return ColumnSlendernessEvidence(
        component_id=COMP,
        m2=axis("M2"),
        m3=axis("M3"),
        source_refs=("fixture:slenderness-evidence",),
    )


def _reanalysis_stiffness_resolution():
    return assess_ts500_eq713_stiffness_basis(
        (
            AssignedFrameBendingModifierEvidence(
                section_name="Column_80x80",
                member_kind="COLUMN",
                i2_modifier=0.7,
                i3_modifier=0.7,
                source_refs=("fixture:Column_80x80:I2Mod/I3Mod",),
            ),
        )
    )


def test_unsupported_combo_overrides_caller_claim_of_resolved_combo_scope():
    result = evaluate_column_design(
        component_id=COMP,
        combo_definitions=(
            ColumnComboDefinition(
                name="BAD",
                combo_type="LINEAR_ADD",
                constituents=(ComboPatternConstituent("NL", 1.0),),
            ),
        ),
        constituent_case_demands=(
            _state("NL", "NonlinearStatic", "I_END", 0.0),
            _state("NL", "NonlinearStatic", "J_END", 4.0),
        ),
        rebar_catalog=_catalog(),
        rebar_inputs=_rebar_inputs(combo_scope="RESOLVED"),
    )
    assert result.status == "BLOCKED_COMBINATION_SCOPE"
    assert not result.design_demands.combination_scope_resolved
    assert not result.minimum_eccentricity.resolved
    assert not result.slenderness.resolved
    assert result.rebar_design.authority == "NOT_SELECTED"
    assert result.rebar_design.selection is not None
    assert result.rebar_design.selection.basis.combination_scope_status == "BLOCKED"
    assert result.rebar_design.selection.basis.minimum_eccentricity_status == "BLOCKED"
    assert result.rebar_design.selection.basis.slenderness_status == "BLOCKED"


def test_supported_combo_derives_combo_and_minimum_eccentricity_but_missing_slenderness_basis_blocks():
    result = evaluate_column_design(
        component_id=COMP,
        combo_definitions=(
            ColumnComboDefinition(
                name="ANY",
                combo_type="LINEAR_ADD",
                constituents=(ComboPatternConstituent("D", 1.4),),
            ),
        ),
        constituent_case_demands=(
            _state("D", "LinStatic", "I_END", 0.0),
            _state("D", "LinStatic", "J_END", 4.0),
        ),
        rebar_catalog=_catalog(),
        # Caller even claims slenderness is RESOLVED; engine must not trust it.
        rebar_inputs=_rebar_inputs(combo_scope="BLOCKED", min_ecc="BLOCKED", slenderness="RESOLVED"),
    )
    assert result.design_demands.combination_scope_resolved
    assert result.minimum_eccentricity.resolved
    assert result.slenderness.status == "BLOCKED_SLENDERNESS_BASIS"
    assert result.status == "BLOCKED_SLENDERNESS_BASIS"
    assert result.rebar_design.selection is not None
    assert result.rebar_design.selection.basis.combination_scope_status == "RESOLVED"
    assert result.rebar_design.selection.basis.minimum_eccentricity_status == "RESOLVED"
    assert result.rebar_design.selection.basis.slenderness_status == "BLOCKED"
    assert result.rebar_design.selection.status == "BLOCKED_DEMAND_BASIS"
    assert set(result.rebar_design.selection.basis.blocked_items) == {"slenderness_status"}


def test_source_bound_slenderness_basis_closes_slenderness_without_caller_authority():
    result = evaluate_column_design(
        component_id=COMP,
        combo_definitions=(
            ColumnComboDefinition(
                name="ANY",
                combo_type="LINEAR_ADD",
                constituents=(ComboPatternConstituent("D", 1.0),),
            ),
        ),
        constituent_case_demands=(
            _state("D", "LinStatic", "I_END", 0.0),
            _state("D", "LinStatic", "J_END", 4.0),
        ),
        rebar_catalog=_catalog(),
        rebar_inputs=_rebar_inputs(slenderness="BLOCKED"),
        slenderness_basis=_slenderness_basis(),
    )
    assert result.slenderness.status == "PROVEN_SLENDERNESS_EFFECTS_NEGLIGIBLE"
    assert result.slenderness.resolved
    assert result.rebar_design.selection is not None
    assert result.rebar_design.selection.basis.slenderness_status == "RESOLVED"
    assert "slenderness_status" not in result.rebar_design.selection.basis.blocked_items


def test_eq713_nonunit_stiffness_promotes_reanalysis_required_while_sway_is_unpromoted():
    stiffness = _reanalysis_stiffness_resolution()
    result = evaluate_column_design(
        component_id=COMP,
        combo_definitions=(
            ColumnComboDefinition(
                name="ANY",
                combo_type="LINEAR_ADD",
                constituents=(ComboPatternConstituent("D", 1.0),),
            ),
        ),
        constituent_case_demands=(
            _state("D", "LinStatic", "I_END", 0.0),
            _state("D", "LinStatic", "J_END", 4.0),
        ),
        rebar_catalog=_catalog(),
        rebar_inputs=_rebar_inputs(),
        slenderness_evidence=_slenderness_evidence_without_sway(),
        stability_stiffness_basis=stiffness,
    )

    assert stiffness.status == STATUS_REANALYSIS_REQUIRED
    assert result.status == "REANALYSIS_REQUIRED"
    assert result.stability_stiffness_basis is stiffness
    assert result.slenderness_basis.status == "BLOCKED_TS500_SLENDERNESS_BASIS"
    assert any(
        item.endswith(":SWAY_CLASSIFICATION_NOT_PROMOTED")
        for item in result.slenderness_basis.blocked_items
    )
    assert result.rebar_design.selection is not None
    assert result.rebar_design.selection.status == "BLOCKED_DEMAND_BASIS"
    assert result.rebar_design.selection.basis.slenderness_status == "BLOCKED"
    assert result.rebar_design.authority == "NOT_SELECTED"
    assert "TS500_7.6.2.1_STIFFNESS_BASIS:REANALYSIS_REQUIRED" in result.rebar_design.selection.basis.review_refs


def test_eq713_specific_reanalysis_does_not_override_a_complete_alternative_slenderness_basis():
    result = evaluate_column_design(
        component_id=COMP,
        combo_definitions=(
            ColumnComboDefinition(
                name="ANY",
                combo_type="LINEAR_ADD",
                constituents=(ComboPatternConstituent("D", 1.0),),
            ),
        ),
        constituent_case_demands=(
            _state("D", "LinStatic", "I_END", 0.0),
            _state("D", "LinStatic", "J_END", 4.0),
        ),
        rebar_catalog=_catalog(),
        rebar_inputs=_rebar_inputs(),
        slenderness_basis=_slenderness_basis(),
        stability_stiffness_basis=_reanalysis_stiffness_resolution(),
    )

    assert result.slenderness.resolved
    assert result.status == "SELECTED_DESIGN_CANDIDATE_ONLY"
    assert result.rebar_design.authority == "DESIGN_CANDIDATE_ONLY"
    assert result.rebar_design.authority != "ENGINE_SELECTED_REBAR"
