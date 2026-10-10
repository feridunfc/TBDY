from copy import deepcopy
from dataclasses import asdict, replace
import json
import math
import os
from pathlib import Path

import pytest

from tbdy_engine.features.column_shear_topology import (
    PointTopologyEvidence, resolve_column_physical_endpoints,
    ColumnShearTopologyError,
)
from tbdy_engine.etabs.oapi.eq713_response_results import FrameForceResponseFact, FrameForceResponseRow
from tbdy_engine.providers.etabs_story_stability_result_provider import (
    qualify_native_modal_physical_bottom_rows as select,
    NativeModalBottomBindingError,
)
from tbdy_engine.analysis_basis.eq713_response_mechanics import (
    qualify_ts500_eq713_axis_to_axis_length as li,
    NativeModalColumnAxial, aggregate_native_modal_column_axial,
)
from tools import column_r1_r3f_physical_modal_aggregate_offline as review
from tools import column_r1_r3e_modal_normalization_offline as normalization
from test_column_r1_r3e_native_normalization import synthetic_receipt, amplitude


def geometry(reverse=False, length=3.):
    points = {n: PointTopologyEvidence(n, '+0.00', 1., 2., z, {})
              for n, z in (('lo', 0.), ('hi', length))}
    row = dict(UniqueName='C1', Story='+0.00', UniquePtI='hi' if reverse else 'lo',
               UniquePtJ='lo' if reverse else 'hi', Length=length)
    return resolve_column_physical_endpoints(row, points=points,
        source_refs=('column:raw', 'points:raw'), reviewed_length_unit='m')


def row(n, station=0., element='mesh1', element_station=0., **changes):
    r = FrameForceResponseRow('C1', station, element, element_station, 'Modal', 'Mode', n,
                              -30., 0., 0., 0., 0., 0.)
    return replace(r, **changes)


def select_rows(rows, g=None, **changes):
    options = dict(modal_case='Modal', expected_modes=(1, 2), raw_response_ref='native:raw',
                   force_unit='kN', length_unit='m')
    options.update(changes)
    return select(g or geometry(), FrameForceResponseFact('C1', 'Modal', tuple(rows), 0), **options)


@pytest.mark.parametrize('reverse', [False, True])
def test_physical_bottom_at_i_or_j_selects_exact_native_mesh_grain(reverse):
    g = geometry(reverse)
    target = 3. if reverse else 0.
    rows = [row(n, s, element=e, element_station=es)
            for n in (2, 1) for s, e, es in ((target, 'end', 3.), (1.5, 'internal', 1.5))]
    result = select_rows(rows, g)
    assert [r.step_number for r in result] == [1, 2]
    assert all((r.object_station, r.element_name, r.element_station, r.p) == (target, 'end', 3., -30.) for r in result)
    assert g.bottom.unique_name == 'lo' and li(g, source_length_unit='m') == 3.


@pytest.mark.parametrize('defect,code', [
    ('missing', 'MODE_POPULATION'), ('extra', 'MODE_POPULATION'),
    ('duplicate', 'DUPLICATE_MODE'), ('fraction', 'MODE_POPULATION'),
    ('nearest', 'ENDPOINT_NOT_EXACT'), ('truncated', 'ENDPOINT_NOT_EXACT'),
    ('ambiguous', 'AMBIGUOUS_STATION'), ('nonfinite', 'ROW_VALUES'),
    ('object', 'ROW_IDENTITY'), ('case', 'ROW_IDENTITY'), ('extremum', 'ROW_IDENTITY'),
    ('blank_element', 'ROW_VALUES'), ('negative_station', 'ROW_VALUES'),
    ('element_drift', 'MODE_POPULATION'),
])
def test_native_bottom_failures_are_typed_source_specific_and_never_fallback(defect, code):
    rows = [row(1), row(2)]
    if defect == 'missing': rows.pop()
    elif defect == 'extra': rows.append(row(3))
    elif defect == 'duplicate': rows.append(row(1))
    elif defect == 'fraction': rows[0] = replace(rows[0], step_number=1.1)
    elif defect == 'nearest': rows = [replace(r, object_station=1e-12) for r in rows]
    elif defect == 'truncated': rows = [replace(r, object_station=1.5) for r in rows]
    elif defect == 'ambiguous': rows += [row(n, element='other') for n in (1, 2)]
    elif defect == 'nonfinite': rows[0] = replace(rows[0], p=float('nan'))
    elif defect == 'object': rows[0] = replace(rows[0], object_name='C2')
    elif defect == 'case': rows[0] = replace(rows[0], load_case='RSX')
    elif defect == 'extremum': rows[0] = replace(rows[0], step_type='Max')
    elif defect == 'blank_element': rows[0] = replace(rows[0], element_name=' ')
    elif defect == 'negative_station': rows[0] = replace(rows[0], element_station=-1.)
    elif defect == 'element_drift': rows[0] = replace(rows[0], element_name='other')
    with pytest.raises(NativeModalBottomBindingError, match=code) as err:
        select_rows(rows)
    assert err.value.column == 'C1' and err.value.raw_response_ref == 'native:raw'


@pytest.mark.parametrize('changes', [dict(force_unit='N'), dict(length_unit='mm'),
    dict(raw_response_ref=''), dict(raw_response_ref=' raw '), dict(expected_modes=(1, 1)),
    dict(expected_modes=(True, 2)), dict(expected_modes=())])
def test_exact_native_selection_requires_units_refs_and_mode_authority(changes):
    with pytest.raises(NativeModalBottomBindingError): select_rows([row(1), row(2)], **changes)


@pytest.mark.parametrize('defect', ['return_code', 'source_api', 'frame_name', 'case_name'])
def test_unsuccessful_or_wrong_native_fact_cannot_qualify(defect):
    f = FrameForceResponseFact('C1', 'Modal', (row(1), row(2)), 0)
    f = replace(f, **{defect: 1 if defect == 'return_code' else 'Other'})
    with pytest.raises(NativeModalBottomBindingError, match='SOURCE_IDENTITY'):
        select(geometry(), f, modal_case='Modal', expected_modes=(1, 2), raw_response_ref='raw', force_unit='kN', length_unit='m')


@pytest.mark.parametrize('defect', ['zero', 'negative', 'nan', 'coordinate', 'orientation',
    'inclined', 'authority', 'clear_length', 'offset_corrected', 'unit', 'raw'])
def test_axis_to_axis_length_rejects_unqualified_candidates(defect):
    g = geometry()
    options = dict(source_length_unit='m')
    with pytest.raises((ValueError, ColumnShearTopologyError)):
        if defect in ('zero', 'negative', 'nan', 'coordinate'):
            g = replace(g, object_length_m={'zero': 0., 'negative': -1., 'nan': float('nan'), 'coordinate': 3.001}[defect])
        elif defect == 'orientation': g = replace(g, bottom=g.top, top=g.bottom)
        elif defect == 'inclined':
            top = replace(g.top, x_m=2.)
            g = replace(g, point_j=top, top=top, coordinate_length_m=math.sqrt(10), object_length_m=math.sqrt(10))
        elif defect == 'authority': options['authority_ref'] = 'inferred'
        elif defect == 'clear_length': options['length_basis'] = 'ANALYSIS_CLEAR_LENGTH'
        elif defect == 'offset_corrected': options['length_basis'] = 'END_OFFSET_CORRECTED'
        elif defect == 'unit': options['source_length_unit'] = 'mm'
        elif defect == 'raw': g = replace(g, source_refs=())
        li(g, **options)


def test_signed_sum_uses_individual_axis_lengths_and_preserves_tension_cancellation():
    a = amplitude(.5)
    rows = (NativeModalColumnAxial('C1', 2, -30., li(geometry(), source_length_unit='m'), a.binding,
        'kN', 'm', 'Mode', 'PHYSICAL_BOTTOM', 'force1', 'axis1'),
        NativeModalColumnAxial('C2', 2, 40., li(geometry(length=4.), source_length_unit='m'), a.binding,
        'kN', 'm', 'Mode', 'PHYSICAL_BOTTOM', 'force2', 'axis2'))
    r = aggregate_native_modal_column_axial(amplitude=a, columns=rows, expected_complete_story_columns=('C1', 'C2'))
    assert r.column_contributions == (('C1', 5.), ('C2', -5.))
    assert r.r_force_per_length == 0. and r.qualified_for_stability is False


def factual_receipt():
    r = synthetic_receipt()
    def fact(key, payload):
        r['facts'][key] = dict(payload=payload, capture_payload_ref=normalization._payload_ref(payload))
    def table(key, rows, fields):
        names = list(fields)
        fact(key, dict(parsed=dict(fetch_status='FETCHED', return_code=0, rows=rows)))
        fact(key + ':metadata', dict(raw_response=[1, len(names), names, names,
            ['native geometry']*len(names), list(fields.values()), [False]*len(names), 0]))
    columns, points = [], []
    for i in range(86):
        uid = str(i)
        columns.append(dict(UniqueName=uid, Story='+0.00', UniquePtI=uid+'I', UniquePtJ=uid+'J', Length=3.))
        points.extend([dict(UniqueName=uid+end, Story='+0.00', X=i, Y=0., Z=z) for end,z in (('I', 0.), ('J', 3.))])
        rows = [asdict(row(n, object_name=uid)) for n in range(1, 101)]
        fact('Modal:FrameForce:'+uid, dict(frame_name=uid, case_name='Modal', rows=rows,
             return_code=0, source_api='Results.FrameForce', state_diagnostics=[]))
    table('Column Object Connectivity', columns, {'Length':'m'})
    table('Point Object Connectivity', points, {'X':'m', 'Y':'m', 'Z':'m'})
    r['representative_story'] = '+0.00'
    return r


@pytest.mark.parametrize('defect', ['missing_column', 'extra_column', 'duplicate_column', 'missing_point',
    'duplicate_point', 'length_unit', 'force_unit', 'raw', 'session', 'epoch', 'b5'])
def test_factual_adapter_preserves_exact_denominator_units_payloads_and_false_b5(defect):
    r = factual_receipt()
    key = 'Column Object Connectivity'
    rows = r['facts'][key]['payload']['parsed']['rows']
    if defect == 'missing_column': rows.pop()
    elif defect == 'extra_column': rows.append(dict(rows[0], UniqueName='extra'))
    elif defect == 'duplicate_column': rows.append(deepcopy(rows[0]))
    elif defect in ('missing_point', 'duplicate_point'):
        key = 'Point Object Connectivity'
        rows = r['facts'][key]['payload']['parsed']['rows']
        if defect == 'missing_point': rows.pop()
        else: rows.append(deepcopy(rows[0]))
    elif defect == 'length_unit':
        key += ':metadata'
        r['facts'][key]['payload']['raw_response'][5] = ['mm']
    elif defect == 'force_unit': r['native_result_units']['FrameForce'] = 'N'
    elif defect == 'raw': rows.pop()
    elif defect == 'session': r['identity_after']['process_id'] = 9
    elif defect == 'epoch': r['factual_capture_binding']['is_analysis_result_epoch'] = True
    elif defect == 'b5': r['current_b5_qualified'] = True
    if defect != 'raw': r['facts'][key]['capture_payload_ref'] = normalization._payload_ref(r['facts'][key]['payload'])
    with pytest.raises(ValueError): review.reconcile_receipt_modal_axial(r)


def test_synthetic_complete_factual_scope_keeps_native_amplitude_and_all_closed_gates():
    r = review.reconcile_receipt_modal_axial(factual_receipt())
    assert r['native_physical_bottom_rows'] == 8600
    for case in ('RSX', 'RSY'):
        assert len(r['signed_modal_r'][case]) == 100
        assert r['signed_modal_r'][case][0]['r_force_per_length'] == pytest.approx(86*10*-.353072)
    assert not r['additional_scale_factor_applied']
    assert not r['current_b5_qualified'] and not r['stability_promotion'] and not r['R2_RERUN_READY']
    assert r['CQC'] == 'NOT_PERFORMED'


def test_changed_receipt_bytes_fail_before_factual_interpretation(tmp_path):
    p = tmp_path/'changed.json'
    p.write_text('{}')
    with pytest.raises(ValueError, match='SHA256'): review.reconcile_exact_receipt(p)


def test_actual_receipt_8600_native_bottoms_200_signed_vectors_and_exact_lineage():
    p = os.getenv('COLUMN_R1_R3E_CAPTURE_TEST_PATH')
    if not p: pytest.skip('complete raw FC09 source receipt is external evidence')
    report = review.reconcile_exact_receipt(Path(p))
    raw = json.loads(Path(p).read_bytes())
    amps = normalization.bind_receipt_amplitudes(raw)
    assert report['column_denominator'] == 86 and report['mode_denominator'] == 100
    assert report['native_physical_bottom_rows'] == 8600 and set(report['lengths_m'].values()) == {5.15}
    assert not report['factual_capture_binding']['is_analysis_result_epoch']
    for uid, physical in report['physical_columns'].items():
        assert physical['object_station'] == 0. and physical['element_station'] == 0.
        assert physical['joint_bottom'] != physical['joint_top']
        assert raw['facts']['Modal:FrameForce:'+uid]['capture_payload_ref'] in physical['source_refs']
    for case, modes in report['signed_modal_r'].items():
        assert [m['mode'] for m in modes] == list(range(1, 101))
        for m, a in zip(modes, amps[case]):
            expected = []
            for uid, length in report['lengths_m'].items():
                rows = raw['facts']['Modal:FrameForce:'+uid]['payload']['rows']
                native = [x for x in rows if x['step_number'] == m['mode'] and x['object_station'] == 0.]
                assert len(native) == 1
                expected.append(-native[0]['p']*a.multiplier/length)
            assert m['r_force_per_length'] == pytest.approx(math.fsum(expected), rel=1e-13, abs=1e-13)
            assert len(m['column_contributions']) == 86 and not m['qualified_for_stability']
            assert m['binding']['source_direction'] == ('U1' if case == 'RSX' else 'U2')
    assert report['current_b5_qualified'] is report['stability_promotion'] is report['R2_RERUN_READY'] is False
