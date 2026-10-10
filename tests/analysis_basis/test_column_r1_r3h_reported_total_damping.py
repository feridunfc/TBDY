from dataclasses import replace
import math

import pytest

from tbdy_engine.analysis_basis.eq713_response_mechanics import (
    CSI_DATABASE_NORMALIZED_MODAL_AMPLITUDE_CONTRACT as NORMALIZATION,
    CsiReportedTotalModalDamping, CqcModalQuantity, ModalDampingComponents,
    NativeModalNormalizationBinding, PeriodicCqcMode, PeriodicCqcOperator,
)


def binding():
    return NativeModalNormalizationBinding('source', 'session', 'capture', 'Modal', 'RSX', 'U1', 'kN', 'm', NORMALIZATION)


def total(mode=1, ratio=.05):
    return CsiReportedTotalModalDamping(mode, ratio, str(ratio), binding(), 'DampRatio', 'fixture:metadata', 'fixture:raw')


def operator(damping=None):
    values = damping or (total(1), total(2))
    return PeriodicCqcOperator(tuple(PeriodicCqcMode(n, f, d, binding(), ('fixture:frequency',))
        for n, f, d in zip((1, 2), (1., 1.005), values)), (1, 2), 'CQC', 0.)


def test_reported_total_is_alternative_to_components_and_is_not_added_twice():
    component = ModalDampingComponents(.02, .01, .02, 'fixture:case', 'fixture:material', 'fixture:link')
    assert total().total_ratio == component.total_ratio == .05
    assert operator().correlation_matrix == operator((component, component)).correlation_matrix
    assert not hasattr(total(), 'case_ratio') and not hasattr(total(), 'material_ratio')
    with pytest.raises(TypeError):
        operator((total().total_ratio + component.total_ratio, total(2)))


@pytest.mark.parametrize('changes', [dict(mode=0),dict(mode=True),dict(reported_total_ratio=-.1),
    dict(reported_total_ratio=1.),dict(reported_total_ratio=5.),dict(reported_total_ratio=float('nan')),
    dict(reported_total_ratio=float('inf')),dict(reported_total_ratio=True),dict(native_value_text=''),
    dict(native_value_text='nan'),dict(native_value_text='bad'),dict(native_value_text='.06'),
    dict(native_field='CaseDamping'),dict(authority_ref='caller-approved'),dict(dimension='ANGLE'),
    dict(unit='percent'),dict(native_field_unit='%'),dict(metadata_ref=''),dict(raw_payload_ref=''),
    dict(binding='source-string'),dict(qualified_for_stability=True)])
def test_invalid_or_unbound_reported_total_cannot_qualify(changes):
    with pytest.raises((ValueError,TypeError)):
        replace(total(), **changes)


@pytest.mark.parametrize('field', ['source_model_ref','session_ref','acquisition_ref','modal_case','spectrum_case','source_direction'])
def test_source_session_capture_case_direction_drift_fails(field):
    drift = 'U2' if field == 'source_direction' else 'different'
    d = replace(total(), binding=replace(binding(), **{field: drift}))
    with pytest.raises(ValueError,match='mismatch'):
        PeriodicCqcMode(1,1.,d,binding(),('fixture:frequency',))


def test_mode_binding_and_unequal_reported_totals_fail_without_average_or_srss():
    with pytest.raises(ValueError,match='mismatch'):
        PeriodicCqcMode(2,1.,total(1),binding(),('fixture:frequency',))
    with pytest.raises(ValueError,match='unequal total'):
        operator((total(1), total(2,.06)))


def test_reported_total_retains_native_text_and_cannot_issue_b5_or_concurrency():
    d = replace(total(), native_value_text='5.000E-2')
    assert d.native_value_text=='5.000E-2' and d.total_ratio==.05
    assert d.binding.acquisition_ref=='capture' and d.native_field=='DampRatio'
    assert d.qualified_for_stability is False
    assert not hasattr(d,'analysis_result_identity')
    q = tuple(CqcModalQuantity(n,v,binding(),'R','kN/m',('fixture:R',)) for n,v in ((1,3.),(2,-3.)))
    magnitude = operator().combine(q)
    assert isinstance(magnitude,float) and 0<magnitude<math.sqrt(18)
    assert not hasattr(magnitude,'analysis_result_identity')


def test_total_damping_preserves_signed_close_mode_cancellation():
    op=operator()
    q=lambda vals: tuple(CqcModalQuantity(n,v,binding(),'R','kN/m',('fixture:R',)) for n,v in enumerate(vals,1))
    assert op.combine(q((1.,-1.))) < .1
    assert op.combine(q((1.,1.))) > 1.99
