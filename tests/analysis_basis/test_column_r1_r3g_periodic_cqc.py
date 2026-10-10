"""Primary published CQC benchmark and fail-closed source contracts."""
from dataclasses import replace
import math

import pytest

from tbdy_engine.analysis_basis.eq713_response_mechanics import (
    CSI_DATABASE_NORMALIZED_MODAL_AMPLITUDE_CONTRACT as NORMALIZATION,
    CqcModalQuantity, ModalDampingComponents, NativeModalNormalizationBinding,
    PeriodicCqcMode, PeriodicCqcOperator, _cqc_quadratic_magnitude,
)


def binding():
    return NativeModalNormalizationBinding('source', 'session', 'capture', 'Modal', 'RSX', 'U1', 'kN', 'm', NORMALIZATION)


def damping(z=.05):
    # Synthetic fixtures, explicitly not an authority for FC09 factual zeros.
    return ModalDampingComponents(z, 0., 0., 'fixture:case', 'fixture:material-zero', 'fixture:link-zero')


def operator(frequencies=(1., 1.005), z=.05, **changes):
    modes = tuple(PeriodicCqcMode(n, f, damping(z), binding(), (f'fixture:frequency:{n}',))
                  for n, f in enumerate(frequencies, 1))
    options = dict(modes=modes, expected_modes=tuple(m.mode for m in modes), source_modal_method='CQC', rigid_response_f2=0.)
    options.update(changes)
    return PeriodicCqcOperator(**options)


def quantities(values):
    return tuple(CqcModalQuantity(n, v, binding(), 'COLUMN_ONLY_R', 'kN/m', (f'fixture:physical-R:{n}',))
                 for n, v in enumerate(values, 1))


def test_independent_wilson_published_table_15_1():
    # Primary author Chapter 15 revision 2014, printed p.15-11. Both the
    # frequencies and published coefficients are rounded. Coefficient
    # tolerance is half one published 0.001 unit, not a native comparison.
    w = (13.87, 13.93, 43.99, 44.19, 54.41)
    expected = ((1,.998,.006,.006,.004), (.998,1,.006,.006,.004),
                (.006,.006,1,.998,.180), (.006,.006,.998,1,.186), (.004,.004,.180,.186,1))
    matrix = operator(tuple(v / (2 * math.pi) for v in w)).correlation_matrix
    for i in range(5):
        for j in range(5):
            assert matrix[i][j] == pytest.approx(expected[i][j], abs=.0005)


def test_close_modes_retain_sign_cancellation_and_differ_from_srss():
    op = operator()
    positive = op.combine(quantities((1., 1.)))
    cancellation = op.combine(quantities((1., -1.)))
    assert positive > 1.99 and cancellation < .1
    assert positive != pytest.approx(math.sqrt(2))
    assert cancellation != pytest.approx(math.sqrt(2))


def test_equal_frequency_signed_quantity_cancels_exactly():
    op = operator((1., 1.))
    assert op.combine(quantities((3., -3.))) == 0.
    assert op.combine(quantities((3., 3.))) == 6.


def test_well_separated_modes_approach_but_do_not_fallback_to_srss():
    actual = operator((1., 100.)).combine(quantities((1., 2.)))
    assert math.sqrt(5) < actual < math.sqrt(5) + .001


def test_zero_response_modes_and_single_mode_keep_physical_units():
    assert operator((1., 2., 3.)).combine(quantities((0., -3., 0.))) == 3.
    assert operator((1.,)).combine(quantities((-4.,))) == 4.
    assert operator().combine(quantities((0., 0.))) == 0.


def test_source_explicit_all_zero_damping_limit_is_srss():
    op = operator((1., 1.), z=0.)
    assert op.correlation_matrix == ((1., 0.), (0., 1.))
    assert op.combine(quantities((1., -1.))) == math.sqrt(2)


def test_complete_100_by_100_matrix_is_symmetric_unit_diagonal_and_stable():
    op = operator(tuple(1 + n / 100 for n in range(100)))
    matrix = op.correlation_matrix
    assert len(matrix) == 100 and all(len(r) == 100 for r in matrix)
    for i in range(100):
        assert matrix[i][i] == 1.
        assert all(0 <= matrix[i][j] <= 1 and matrix[i][j] == matrix[j][i] for j in range(100))
    signed = tuple((-1.)**n * (n + 1) for n in range(100))
    actual = op.combine(quantities(signed))
    # Independent full matrix product, not sum of member magnitudes.
    expected = math.sqrt(math.fsum(signed[i] * matrix[i][j] * signed[j] for i in range(100) for j in range(100)))
    assert actual == pytest.approx(expected, rel=2e-13)


def test_total_damping_includes_material_and_link_support_contributions():
    d = ModalDampingComponents(.02, .01, .02, 'case', 'material', 'link')
    assert d.total_ratio == .05
    modes = tuple(replace(m, damping=d) for m in operator().modes)
    assert operator(modes=modes).correlation_matrix == operator().correlation_matrix


@pytest.mark.parametrize('changes', [dict(case_ratio=-.01), dict(case_ratio=1.), dict(case_ratio=5.),
    dict(material_ratio=-.01), dict(link_support_ratio=-.01), dict(case_ratio=float('nan')),
    dict(material_ratio=None), dict(link_support_ratio=None), dict(case_source_ref=''),
    dict(material_source_ref=''), dict(link_support_source_ref=''), dict(case_ratio=True),
    dict(material_ratio=.96)])
def test_missing_or_invalid_damping_never_defaults_to_zero(changes):
    with pytest.raises((ValueError, TypeError)):
        replace(damping(), **changes)


@pytest.mark.parametrize('method', ['SRSS', 'GMC', 'ABS', 'CQC3', 1, None])
def test_no_enum_inference_or_other_method_fallback(method):
    with pytest.raises(ValueError, match='named CQC'): operator(source_modal_method=method)


@pytest.mark.parametrize('f2', [.1, 1., -1., float('nan'), True])
def test_rigid_or_unqualified_response_branch_is_unsupported(f2):
    with pytest.raises(ValueError): operator(rigid_response_f2=f2)


@pytest.mark.parametrize('bad', [0., -1., float('inf'), float('nan'), True])
def test_invalid_frequency_is_rejected(bad):
    with pytest.raises(ValueError): operator((1., bad))


@pytest.mark.parametrize('defect', ['missing', 'duplicate', 'extra', 'order', 'authority', 'zero', 'boolean'])
def test_operator_requires_exact_complete_applicable_modes(defect):
    modes = operator().modes; expected=(1,2)
    if defect == 'missing': modes = modes[:1]
    elif defect == 'duplicate': modes = (modes[0], modes[0])
    elif defect == 'extra': modes += (replace(modes[0], mode=3),)
    elif defect == 'order': modes = modes[::-1]
    elif defect == 'authority': expected=(1,1)
    elif defect == 'zero': expected=(0,2)
    else: expected=(True,2)
    with pytest.raises(ValueError): operator(modes=modes, expected_modes=expected)


def test_unequal_total_damping_is_not_silently_treated_as_constant():
    modes = operator().modes
    with pytest.raises(ValueError, match='unequal total'):
        operator(modes=(modes[0], replace(modes[1], damping=damping(.04))))


@pytest.mark.parametrize('field,value', [('source_model_ref','other'),('session_ref','other'),('acquisition_ref','other'),
    ('spectrum_case','RSY'),('modal_case','OtherModal'),('source_direction','U2')])
def test_modal_binding_drift_is_rejected(field, value):
    modes = operator().modes
    b = replace(binding(), **{field:value})
    with pytest.raises(ValueError, match='drift'):
        operator(modes=(modes[0],replace(modes[1],binding=b)))
    q = quantities((1.,2.))
    with pytest.raises(ValueError, match='drift'):
        operator().combine((q[0],replace(q[1],binding=b)))


@pytest.mark.parametrize('defect', ['missing','duplicate','order','quantity','unit'])
def test_quantity_population_units_and_physical_grain_are_separate(defect):
    q = quantities((1.,2.))
    if defect == 'missing': q=q[:1]
    elif defect == 'duplicate': q=(q[0],q[0])
    elif defect == 'order': q=q[::-1]
    elif defect == 'quantity': q=(q[0],replace(q[1],quantity='STORY_SHEAR'))
    else: q=(q[0],replace(q[1],unit='N/m'))
    with pytest.raises(ValueError): operator().combine(q)


def test_invalid_negative_quadratic_is_rejected_without_absolute_or_clipping():
    with pytest.raises(ValueError, match='negative'):
        _cqc_quadratic_magnitude((1.,-1.), ((1.,2.),(2.,1.)))


def test_scaled_quadratic_avoids_intermediate_response_square_overflow():
    result = operator((1.,)).combine(quantities((1e200,)))
    assert result == 1e200
