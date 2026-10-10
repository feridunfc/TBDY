from dataclasses import replace
import math
import pytest
from tbdy_engine.analysis_basis.eq713_response_mechanics import (
    NativeModalNormalizationBinding as Binding, NativeModalAmplitude as Amp,
    NativeModalColumnAxial as Col, aggregate_native_modal_column_axial as aggregate,
    srss_native_modal_aggregates as srss,
)

B = Binding("FC09", "session:1", "capture:1", "Modal", "RSX", "U1", "tonf", "m", "db-normalization:raw:1")
def amplitude(mode=1, multiplier=2.): return Amp(mode, 1./mode, multiplier, B, "U1Amp", f"amplitude:raw:{mode}")
def column(name="C1", p=-30., length=3., mode=1):
    return Col(name,mode,p,length,B,"tonf","m","Mode","PHYSICAL_BOTTOM",f"force:raw:{name}:{mode}",f"length:raw:{name}")
def result(mode=1, ps=(-30.,12.), multiplier=2.):
    return aggregate(amplitude=amplitude(mode,multiplier), columns=(column("C1",ps[0],3.,mode),column("C2",ps[1],4.,mode)),expected_complete_story_columns=("C1","C2"))

def test_exact_weighted_signed_aggregate_precedes_modal_combination():
    a,b = result(1),result(2,(-9.,-8.),3.)
    assert a.r_force_per_length == 14.  # 2*(30/3-12/4), tension retained.
    assert b.r_force_per_length == 15.
    assert srss((a,b),source_modal_method="SRSS") == pytest.approx(math.hypot(14,15))
    independent = sum(math.hypot(a.column_contributions[i][1],b.column_contributions[i][1]) for i in range(2))
    assert independent != pytest.approx(math.hypot(14,15))
    assert not a.qualified_for_stability
    assert a.source_refs[1] == "amplitude:raw:1"

def test_cancellation_zero_and_negative_modes_are_valid_facts():
    a = aggregate(amplitude=amplitude(),columns=(column("C1",-30.,3.),column("C2",30.,3.)),expected_complete_story_columns=("C1","C2"))
    assert a.r_force_per_length == 0.
    assert result(ps=(30.,12.)).r_force_per_length == -26.
    assert result(multiplier=-2.).r_force_per_length == -14.

@pytest.mark.parametrize("field,value", [
    ("source_model_ref","5AA"),("session_ref","other"),("acquisition_ref","other"),
    ("modal_case","other"),("spectrum_case","RSY"),("source_direction","U2"),
    ("normalization_ref","other"),
])
def test_normalization_case_source_session_capture_drift_rejected(field,value):
    row = replace(column(),binding=replace(B,**{field:value}))
    with pytest.raises(ValueError,match="mismatch"):
        aggregate(amplitude=amplitude(),columns=(row,),expected_complete_story_columns=("C1",))

@pytest.mark.parametrize("rows,denominator", [
    ((column(),), ("C1","C2")), ((column(),column()),("C1",)),
    ((column(),column("C2")),("C1",)), ((column(),),("C1","C1")), ((),()),
])
def test_complete_physical_denominator_required(rows,denominator):
    with pytest.raises(ValueError): aggregate(amplitude=amplitude(),columns=rows,expected_complete_story_columns=denominator)

@pytest.mark.parametrize("field,value", [("step_type","Min"),("step_type","Max"),("physical_location","TOP"),
    ("physical_length",0.),("force_unit","kN"),("length_unit","mm"),("signed_p",float("nan")),("mode",True)])
def test_inferred_extrema_station_units_or_nonfinite_force_rejected(field,value):
    with pytest.raises(ValueError): replace(column(),**{field:value})

@pytest.mark.parametrize("field,value", [("source_field","U1Acc"),("source_field","U2Amp"),("period_s",0.),("multiplier",float("nan")),("mode",True)])
def test_amplitude_semantics_exact(field,value):
    with pytest.raises(ValueError): replace(amplitude(),**{field:value})

def test_mode_mismatch_is_not_tolerated():
    with pytest.raises(ValueError,match="mismatch"):
        aggregate(amplitude=amplitude(),columns=(column(mode=2),),expected_complete_story_columns=("C1",))

@pytest.mark.parametrize("method", ["CQC","ABS","GMC","SRSS_FROM_OLD_EXAMPLE"])
def test_actual_native_method_required_no_implicit_srss_or_joint_statistic(method):
    with pytest.raises(ValueError,match="not SRSS"): srss((result(),),source_modal_method=method)

def test_duplicate_modes_and_fabricated_stability_qualification_rejected():
    with pytest.raises(ValueError,match="duplicate"): srss((result(),result()),source_modal_method="SRSS")
    with pytest.raises(ValueError,match="cannot qualify"): replace(result(),qualified_for_stability=True)

from tbdy_engine.analysis_basis.eq713_response_mechanics import NativeModalScalarResponse as Scalar, native_modal_scalar_contribution as scale

@pytest.mark.parametrize("quantity,unit,value,refs", [
    ("PHYSICAL_TOP_MINUS_BOTTOM_TRANSLATION","m",-.002,("top:raw","bottom:raw")),
    ("STORY_BOTTOM_SHEAR","tonf",-75.,("bottom-cut:raw",)),
])
def test_signed_delta_and_shear_share_native_amplitude_basis(quantity,unit,value,refs):
    response = Scalar(1,value,B,quantity,unit,"physical-grain:1",refs)
    assert scale(amplitude=amplitude(),response=response) == 2*value

@pytest.mark.parametrize("kwargs", [
    {"source_unit":"mm"},{"quantity":"INDEPENDENT_MAX_DRIFT"},{"step_type":"Max"},
    {"raw_response_refs":("same","same")},{"mode":True},{"value":float("inf")},
])
def test_invalid_modal_translation_not_promoted(kwargs):
    with pytest.raises(ValueError):
        Scalar(**dict({"mode":1,"value":.002,"binding":B,"quantity":"PHYSICAL_TOP_MINUS_BOTTOM_TRANSLATION",
            "source_unit":"m","physical_grain_ref":"physical:1","raw_response_refs":("top","bottom")},**kwargs))

def test_modal_shear_different_epoch_and_mode_fail():
    for response in (Scalar(2,10.,B,"STORY_BOTTOM_SHEAR","tonf","cut",("raw",)),
                     Scalar(1,10.,replace(B,acquisition_ref="other"),"STORY_BOTTOM_SHEAR","tonf","cut",("raw",))):
        with pytest.raises(ValueError,match="mismatch"): scale(amplitude=amplitude(),response=response)
