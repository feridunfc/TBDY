import pytest

from tbdy_engine.application.column_design_basis import (
    ColumnDesignBasisError,
    ReviewedAggregateBasis,
    ReviewedColumnDesignBasis,
    ReviewedConcreteDesignStrength,
    ReviewedLongitudinalSteelDesignStrength,
    bind_reviewed_column_design_basis,
)
from tbdy_engine.features.used_rc_material_population import (
    ConcreteStrengthFactStatus,
    MaterialUsageReference,
    MaterialUsageStatus,
    UsedMaterialDefinition,
)
from tbdy_engine.providers.etabs_column_rebar_intent_provider import (
    EtabsColumnRebarIntentEvidence,
)


def _basis(*, concrete="C30", steel="B420C"):
    return ReviewedColumnDesignBasis(
        concrete_strengths=(
            ReviewedConcreteDesignStrength(
                material_name=concrete,
                fcd_mpa=20.0,
                review_refs=(f"review:fcd:{concrete}",),
            ),
        ),
        longitudinal_steel_strengths=(
            ReviewedLongitudinalSteelDesignStrength(
                material_name=steel,
                fyd_mpa=365.2173913043478,
                review_refs=(f"review:fyd:{steel}",),
            ),
        ),
        aggregate=ReviewedAggregateBasis(
            aggregate_max_mm=22.0,
            review_refs=("review:aggregate:22mm",),
        ),
        basis_refs=("project-design-basis:rev-7",),
    )


def _usage(*, concrete="C30"):
    return MaterialUsageReference(
        usage_id="frame:column:U1",
        component_type="Column",
        component_identity="U1",
        story="S1",
        label="C1",
        assigned_property="COL50x70",
        material_name=concrete,
        material_type_code=2,
        status=MaterialUsageStatus.RESOLVED_CONCRETE_USAGE,
        source_references=({"table": "Frame Section Property Definitions - Summary", "UniqueName": "U1"},),
    )


def _definition(*, concrete="C30", model="model:abc"):
    return UsedMaterialDefinition(
        material_id=f"material:{concrete}",
        model_fingerprint=model,
        material_name=concrete,
        material_type_code=2,
        is_concrete=True,
        raw_fc=30.0,
        canonical_fck_mpa=30.0,
        concrete_strength_status=ConcreteStrengthFactStatus.RESOLVED,
        unit_context=None,
        usage_references=(_usage(concrete=concrete),),
    )


def _intent(*, section="COL50x70", steel="B420C"):
    return EtabsColumnRebarIntentEvidence(
        section_name=section,
        mat_prop_long=steel,
        mat_prop_confine=steel,
        pattern=1,
        confine_type=1,
        cover=0.04,
        number_c_bars=0,
        number_r3_bars=0,
        number_r2_bars=0,
        rebar_size_name="20",
        tie_size_name="10",
        tie_spacing_longit=0.15,
        number_2_dir_tie_bars=2,
        number_3_dir_tie_bars=2,
        to_be_designed=True,
        reviewed_length_unit="m",
        raw_api="GetRebarColumn(...)",
    )


def test_basis_binds_exact_factual_concrete_and_longitudinal_materials():
    result = bind_reviewed_column_design_basis(
        _basis(),
        component_id="S1:C1:U1",
        section_id="COL50x70",
        factual_concrete_usage=_usage(),
        factual_concrete_definition=_definition(),
        factual_rebar_intent=_intent(),
        model_fingerprint="model:abc",
        evidence_epoch_id="epoch:1",
    )
    assert result.concrete_material_name == "C30"
    assert result.longitudinal_material_name == "B420C"
    assert result.material_context.material.fck_mpa == pytest.approx(30.0)
    assert result.material_context.material.fcd_mpa == pytest.approx(20.0)
    assert result.material_context.material.fyd_mpa == pytest.approx(365.2173913043478)
    assert result.material_context.model_fingerprint == "model:abc"
    assert result.material_context.evidence_epoch_id == "epoch:1"
    assert "MatPropLong=B420C" in "|".join(result.material_context.steel_design_strength_review_refs)
    assert result.aggregate_max_mm == pytest.approx(22.0)
    assert result.aggregate_source_ref.startswith("column-aggregate-basis:sha256:")
    assert result.binding_ref.startswith("column-design-basis-binding:sha256:")


def test_basis_rejects_unrelated_reviewed_concrete_strength():
    with pytest.raises(ColumnDesignBasisError, match="reviewed fcd applicability"):
        bind_reviewed_column_design_basis(
            _basis(concrete="C35"),
            component_id="S1:C1:U1",
            section_id="COL50x70",
            factual_concrete_usage=_usage(concrete="C30"),
            factual_concrete_definition=_definition(concrete="C30"),
            factual_rebar_intent=_intent(),
            model_fingerprint="model:abc",
            evidence_epoch_id="epoch:1",
        )


def test_basis_rejects_unrelated_reviewed_longitudinal_strength():
    with pytest.raises(ColumnDesignBasisError, match="reviewed fyd applicability"):
        bind_reviewed_column_design_basis(
            _basis(steel="B500C"),
            component_id="S1:C1:U1",
            section_id="COL50x70",
            factual_concrete_usage=_usage(),
            factual_concrete_definition=_definition(),
            factual_rebar_intent=_intent(steel="B420C"),
            model_fingerprint="model:abc",
            evidence_epoch_id="epoch:1",
        )


def test_basis_rejects_model_identity_mismatch():
    with pytest.raises(ColumnDesignBasisError, match="model_fingerprint"):
        bind_reviewed_column_design_basis(
            _basis(),
            component_id="S1:C1:U1",
            section_id="COL50x70",
            factual_concrete_usage=_usage(),
            factual_concrete_definition=_definition(model="model:other"),
            factual_rebar_intent=_intent(),
            model_fingerprint="model:abc",
            evidence_epoch_id="epoch:1",
        )


def test_basis_rejects_section_identity_mismatch():
    with pytest.raises(ColumnDesignBasisError, match="section differs"):
        bind_reviewed_column_design_basis(
            _basis(),
            component_id="S1:C1:U1",
            section_id="COL50x70",
            factual_concrete_usage=_usage(),
            factual_concrete_definition=_definition(),
            factual_rebar_intent=_intent(section="COL60x80"),
            model_fingerprint="model:abc",
            evidence_epoch_id="epoch:1",
        )


def test_basis_rejects_nonpositive_aggregate_without_default():
    with pytest.raises(ColumnDesignBasisError, match="> 0"):
        ReviewedAggregateBasis(
            aggregate_max_mm=0.0,
            review_refs=("review:aggregate",),
        )
