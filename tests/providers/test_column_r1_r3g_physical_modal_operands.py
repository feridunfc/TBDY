from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path

import pytest

from tbdy_engine.analysis_basis.eq713_response_mechanics import (
    NativeModalAmplitude, NativeModalNormalizationBinding,
    CSI_DATABASE_NORMALIZED_MODAL_AMPLITUDE_CONTRACT as NORMALIZATION,
    native_modal_scalar_contribution,
)
from tbdy_engine.etabs.oapi.database_tables import decode_table_field_metadata
from tbdy_engine.etabs.oapi.joint_displacement_results import JointDisplacementResultFact, JointDisplacementResultRow
from tbdy_engine.providers.etabs_story_stability_result_provider import (
    qualify_native_modal_endpoint_rows as endpoints, qualify_native_modal_story_shear as shear,
    StoryStabilityResultProviderError,
)
from tools import column_r1_r3g_modal_operands_offline as review
from tools.column_r1_r3e_modal_normalization_offline import _payload_ref, ACCEPTED_RECEIPT_SHA256


def amplitudes(direction='U1'):
    b = NativeModalNormalizationBinding('source','session','capture','Modal','RSX' if direction=='U1' else 'RSY',
                                       direction,'kN','m',NORMALIZATION)
    return tuple(NativeModalAmplitude(n, 1/n, factor, b, direction+'Amp', f'fixture:amp:{n}')
                 for n, factor in ((1,2.),(2,-3.)))


def metadata(unit='kN', direction='X'):
    return decode_table_field_metadata((1,2,['VX','VY'],['VX','VY'],
        [f'The shear force in the global {direction}-direction.','The shear force in the global Y-direction.'],
        [unit,unit],[False,False],0), table_name='Story Forces')


def rows():
    return [dict(Story='+0.00',OutputCase='Modal',Location='Bottom',CaseType='LinModRitz',
                 StepType='Mode',StepNumber=str(n),VX=str(v),VY=str(-v)) for n,v in ((1,-10.),(2,20.))]


def select(data=None, **changes):
    options=dict(story='+0.00',amplitudes=amplitudes(),expected_modes=(1,2),metadata=metadata(),raw_response_ref='fixture:shear')
    options.update(changes)
    return shear(rows() if data is None else data, **options)


def test_signed_global_bottom_shear_is_scaled_by_native_amplitude_exactly_once():
    selected=select()
    assert [r.value for r in selected] == [-10.,20.]
    assert [native_modal_scalar_contribution(amplitude=a,response=r) for a,r in zip(amplitudes(),selected)] == [-20.,-60.]
    assert all('Bottom|Modal|Mode:' in r.physical_grain_ref and r.source_unit=='kN' for r in selected)
    assert [r.value for r in select(amplitudes=amplitudes('U2'))] == [10.,-20.]


def test_unrelated_combinations_stories_and_top_cuts_never_enter_modal_population():
    data=rows()
    data += [dict(data[0],OutputCase='Crack_SeisX',StepType='Max',VX='99999'),
             dict(data[0],Story='+14.5',VX='99999'), dict(data[0],Location='Top',VX='99999')]
    assert select(data) == select()


@pytest.mark.parametrize('defect', ['missing','duplicate','extra','fraction','extremum','case_type','nan','boolean_mode','boolean_shear','blank'])
def test_modal_cut_ambiguity_truncation_and_invalid_values_fail(defect):
    data=rows()
    if defect=='missing': data.pop()
    elif defect=='duplicate': data.append(data[0].copy())
    elif defect=='extra': data.append(dict(data[0],StepNumber='3'))
    elif defect=='fraction': data[0]['StepNumber']='1.5'
    elif defect=='extremum': data[0]['StepType']='Max'
    elif defect=='case_type': data[0]['CaseType']='Combination'
    elif defect=='nan': data[0]['VX']='nan'
    elif defect=='boolean_mode': data[0]['StepNumber']=True
    elif defect=='boolean_shear': data[0]['VX']=True
    else: data[0]['VX']=''
    with pytest.raises(StoryStabilityResultProviderError): select(data)


@pytest.mark.parametrize('changes', [dict(metadata=metadata('N')),dict(metadata=metadata(direction='Y')),
    dict(expected_modes=(1,1)),dict(expected_modes=(True,2)),dict(raw_response_ref=''),dict(amplitudes=())])
def test_exact_mode_direction_unit_and_raw_authority_required(changes):
    with pytest.raises(StoryStabilityResultProviderError): select(**changes)


def test_amplitude_source_session_case_drift_fails():
    a=amplitudes()
    with pytest.raises(StoryStabilityResultProviderError):
        select(amplitudes=(a[0],replace(a[1],binding=replace(a[1].binding,session_ref='other'))))


def endpoint_fact():
    return JointDisplacementResultFact('P1','Modal','case',tuple(
        JointDisplacementResultRow('P1','elm','Modal','Mode',n,n*.001,-n*.002,n*.003,0.,0.,0.) for n in (1,2)),0)


def endpoint_select(fact=None, **changes):
    options=dict(modal_case='Modal',expected_modes=(1,2),length_unit='m',raw_response_ref='fixture:endpoint')
    options.update(changes)
    return endpoints('P1',endpoint_fact() if fact is None else fact,**options)


def test_physical_endpoint_selector_preserves_point_local_values_and_signs():
    fact=endpoint_fact()
    assert endpoint_select()==fact.rows
    assert [(r.u1,r.u2,r.u3) for r in endpoint_select()]==[(.001,-.002,.003),(.002,-.004,.006)]


@pytest.mark.parametrize('defect', ['missing','duplicate','extra','element','point','case','extremum','nan','boolean','fraction'])
def test_exact_endpoint_grain_population_and_basis_remain_factual(defect):
    f=endpoint_fact();r=list(f.rows)
    if defect=='missing': r.pop()
    elif defect=='duplicate': r.append(r[0])
    elif defect=='extra': r.append(replace(r[0],step_number=3))
    elif defect=='element': r[0]=replace(r[0],element_name='other')
    elif defect=='point': r[0]=replace(r[0],point_object='other')
    elif defect=='case': r[0]=replace(r[0],load_case='other')
    elif defect=='extremum': r[0]=replace(r[0],step_type='Max')
    elif defect=='nan': r[0]=replace(r[0],u1=float('nan'))
    elif defect=='boolean': r[0]=replace(r[0],step_number=True)
    else: r[0]=replace(r[0],step_number=1.5)
    with pytest.raises(StoryStabilityResultProviderError): endpoint_select(replace(f,rows=tuple(r)))


@pytest.mark.parametrize('changes', [dict(return_code=1),dict(source_api='other'),dict(item_type_elm=1),
    dict(point_object='other'),dict(output_name='other'),dict(output_kind='combo')])
def test_wrong_native_endpoint_source_fails(changes):
    with pytest.raises(StoryStabilityResultProviderError): endpoint_select(replace(endpoint_fact(),**changes))


@pytest.mark.parametrize('changes', [dict(length_unit='mm'),dict(raw_response_ref=''),dict(expected_modes=()),dict(expected_modes=(1,1))])
def test_endpoint_units_and_applicable_population_fail_closed(changes):
    with pytest.raises(StoryStabilityResultProviderError): endpoint_select(**changes)


@pytest.fixture(scope='module')
def accepted_receipt():
    path=os.environ.get('COLUMN_R1_R3E_CAPTURE_TEST_PATH')
    if not path: pytest.skip('exact external accepted R3D source receipt required')
    data=Path(path).read_bytes()
    assert hashlib.sha256(data).hexdigest()==ACCEPTED_RECEIPT_SHA256
    return json.loads(data)


def test_real_fc09_complete_operand_binding_without_cqc_or_global_delta_fabrication(accepted_receipt):
    result=review.reconcile_receipt_modal_operands(accepted_receipt)
    assert result['physical_endpoint_rows']==17200 and result['physical_column_mode_pairs']==8600
    assert len(result['native_endpoint_pairs'])==86
    assert all(len(v)==100 for v in result['native_endpoint_pairs'].values())
    assert result['V_modes_per_case']==100 and result['Delta_modes_formed']==0
    assert result['CQC_matrix_issued'] is False
    assert result['RSX_R_CQC'] is None and result['RSY_R_CQC'] is None
    assert result['joint_delta_r_v_statistic']=='PROJECT_DECISION_REQUIRED'
    assert not result['current_b5_qualified'] and not result['R2_RERUN_READY']
    assert not result['factual_capture_binding']['is_analysis_result_epoch']
    assert result['modal_operands']['RSX'][0]['V_kN']==pytest.approx(8838.7923282192)
    assert result['modal_operands']['RSY'][0]['V_kN']==pytest.approx(1982.0907851472)
    assert result['modal_operands']['RSX'][1]['native_amplitude']['multiplier']<0
    for case in ('RSX','RSY'):
        assert [r['mode'] for r in result['modal_operands'][case]]==list(range(1,101))
        assert all(r['Delta_global_m'] is None and r['total_damping_ratio'] is None for r in result['modal_operands'][case])
        assert result['case_signatures'][case]['native_case_row']['ModalCombo']=='CQC'
        assert result['case_signatures'][case]['native_case_row']['RigidResp']=='No'


@pytest.mark.parametrize('defect', ['period_missing','period_duplicate','period_unit','shear_missing','shear_duplicate',
    'global_angle','csys','cqc_label','rigid','getter_rigid','endpoint_missing','endpoint_mode_missing','raw_changed'])
def test_real_native_source_negative_bindings(accepted_receipt,defect):
    r=deepcopy(accepted_receipt);f=r['facts']
    if defect.startswith('period_'):
        key='Modal Periods And Frequencies@Modal';p=f[key]['payload']['parsed']['rows']
        if defect=='period_missing': p.pop()
        elif defect=='period_duplicate': p.append(p[0].copy())
        else:
            key='Modal Periods And Frequencies:metadata';f[key]['payload']['raw_response'][5][2]='ms'
    elif defect.startswith('shear_'):
        key='Story Forces@Modal';p=f[key]['payload']['parsed']['rows'];i=next(i for i,v in enumerate(p) if v['Story']=='+0.00')
        if defect=='shear_missing': p.pop(i)
        else: p.append(p[i].copy())
    elif defect in ('global_angle','csys','cqc_label','rigid'):
        key='Load Case Definitions - Response Spectrum';p=f[key]['payload']['parsed']['rows'][0]
        name,value={'global_angle':('Angle','1'),'csys':('CoordSys','Other'),'cqc_label':('ModalCombo','SRSS'),'rigid':('RigidResp','Yes')}[defect]
        p[name]=value
    elif defect=='getter_rigid':
        key='RSX:settings';p=next(s for s in f[key]['payload']['settings'] if s['method']=='GetModalComb_1');p['outputs'][2][1]=1.
    elif defect=='endpoint_missing':
        del f[next(k for k in f if k.startswith('Modal:JointDispl:'))];key=None
    else:
        key=next(k for k in f if k.startswith('Modal:JointDispl:'))
        if defect=='endpoint_mode_missing': f[key]['payload']['rows'].pop()
        else: f[key]['payload']['rows'][0]['u1']+=1
    # Rehash deliberate synthetic altered payload to exercise its semantic
    # contract; the exact-byte CLI still rejects every altered receipt.
    if key and defect!='raw_changed': f[key]['capture_payload_ref']=_payload_ref(f[key]['payload'])
    with pytest.raises((ValueError,StoryStabilityResultProviderError)):
        review.reconcile_receipt_modal_operands(r)


def test_exact_cli_bytes_cannot_be_replaced_by_another_receipt(tmp_path):
    p=tmp_path/'changed.json';p.write_text('{}\n')
    with pytest.raises(ValueError,match='SHA256'): review.reconcile_exact_receipt(p)
