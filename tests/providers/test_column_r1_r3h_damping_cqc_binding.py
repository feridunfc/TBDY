from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext
import hashlib
import json
import math
import os
from pathlib import Path

import pytest

from tbdy_engine.analysis_basis.eq713_response_mechanics import (
    NativeModalAmplitude, NativeModalNormalizationBinding,
    CSI_DATABASE_NORMALIZED_MODAL_AMPLITUDE_CONTRACT as NORMALIZATION,
)
from tbdy_engine.etabs.oapi.database_tables import decode_table_field_metadata
from tbdy_engine.providers.etabs_story_stability_result_provider import qualify_native_reported_total_modal_damping
from tools import column_r1_r3h_reported_damping_offline as review
from tools.column_r1_r3e_modal_normalization_offline import ACCEPTED_RECEIPT_SHA256, _payload_ref


def amplitudes():
    b=NativeModalNormalizationBinding('source','session','capture','Modal','RSX','U1','kN','m',NORMALIZATION)
    return tuple(NativeModalAmplitude(n,1./n,1.,b,'U1Amp',f'fixture:amp:{n}') for n in (1,2))


def metadata():
    keys=['SpecCase','ModalCase','Mode','Period','DampRatio']
    descriptions=['The name of a response spectrum load case.','The name of a modal load case.',
                  'The mode number.','The period of the mode.','The damping ratio.']
    return decode_table_field_metadata((1,5,keys,keys,descriptions,['','','','sec',''],[False]*5,0),
                                       table_name='Response Spectrum Modal Info')


def rows():
    return [dict(SpecCase='RSX',ModalCase='Modal',Mode=str(n),Period=str(1./n),DampRatio='0.05') for n in (1,2)]


def select(data=None, **changes):
    options=dict(amplitudes=amplitudes(),expected_modes=(1,2),metadata=metadata(),raw_response_ref='fixture:raw')
    options.update(changes)
    return qualify_native_reported_total_modal_damping(rows() if data is None else data, **options)


def test_native_table_total_has_exact_independent_mode_case_and_metadata_binding():
    bound=select()
    assert [d.mode for d in bound]==[1,2] and all(d.total_ratio==.05 for d in bound)
    assert all(d.binding==amplitudes()[0].binding and d.metadata_ref==metadata().raw_response_ref
               and d.raw_payload_ref=='fixture:raw' and not d.qualified_for_stability for d in bound)


@pytest.mark.parametrize('defect',['missing','duplicate','extra','fraction','boolean_mode','nonfinite_mode',
    'wrong_case','wrong_modal','wrong_period','boolean_ratio','numeric_ratio','nan','inf','negative','unity'])
def test_missing_duplicate_or_unrelated_native_damping_cannot_enter_cqc(defect):
    data=rows()
    if defect=='missing':data.pop()
    elif defect=='duplicate':data.append(data[0].copy())
    elif defect=='extra':data.append(dict(data[0],Mode='3'))
    else:
        field,value={'fraction':('Mode','1.5'),'boolean_mode':('Mode',True),'nonfinite_mode':('Mode','nan'),
            'wrong_case':('SpecCase','RSY'),'wrong_modal':('ModalCase','Other'),'wrong_period':('Period','3'),
            'boolean_ratio':('DampRatio',True),'numeric_ratio':('DampRatio',.05),'nan':('DampRatio','nan'),
            'inf':('DampRatio','inf'),'negative':('DampRatio','-.1'),'unity':('DampRatio','1')}[defect]
        data[0][field]=value
    with pytest.raises((ValueError,RuntimeError)):select(data)


@pytest.mark.parametrize('changes',[dict(table_name='Load Case Definitions - Response Spectrum'),
    dict(return_code=1),dict(units_strings=('','','','sec','%')),
    dict(descriptions=('The name of a response spectrum load case.','The name of a modal load case.',
        'The mode number.','The period of the mode.','The load case damping only.')),
    dict(field_keys=('SpecCase','ModalCase','Mode','Period','Mode'))])
def test_case_only_damping_and_inconsistent_metadata_fail(changes):
    with pytest.raises((ValueError,RuntimeError)):select(metadata=replace(metadata(),**changes))


@pytest.mark.parametrize('changes',[dict(expected_modes=(1,1)),dict(expected_modes=(True,2)),
    dict(amplitudes=()),dict(raw_response_ref='')])
def test_complete_authority_and_raw_binding_required(changes):
    with pytest.raises((ValueError,RuntimeError)):select(**changes)


def test_native_amplitude_source_drift_fails():
    a=amplitudes()
    with pytest.raises(RuntimeError):
        select(amplitudes=(a[0],replace(a[1],binding=replace(a[1].binding,session_ref='other'))))


def frequency_row():
    return {'Period':'0.56','Frequency':'1.787','CircFreq':'11.2297','Eigenvalue':'126.1067'}


def test_native_rounded_period_frequency_correspondence_preserves_frequency():
    assert review.validate_native_frequency_correspondence(frequency_row())==1.787


@pytest.mark.parametrize('field,value',[('Frequency','17.87'),('Period','5.60'),('CircFreq','112.297'),
    ('Eigenvalue','1261.067'),('Frequency','nan'),('CircFreq','inf'),('Period','-1'),('Frequency',True),('Frequency','bad')])
def test_wrong_frequency_or_correlation_interpretation_fails(field,value):
    with pytest.raises(ValueError):review.validate_native_frequency_correspondence(dict(frequency_row(),**{field:value}))


@pytest.fixture(scope='module')
def accepted_receipt():
    path=os.environ.get('COLUMN_R1_R3E_CAPTURE_TEST_PATH')
    if not path:pytest.skip('exact external R3D receipt not supplied')
    data=Path(path).read_bytes()
    assert hashlib.sha256(data).hexdigest()==ACCEPTED_RECEIPT_SHA256
    return json.loads(data)


@pytest.fixture(scope='module')
def actual_result(accepted_receipt):
    return review.reconcile_reported_total_damping(accepted_receipt)


def decimal_cqc(values,frequencies,z):
    # Independent decimal implementation of Wilson's quadratic, with ordered
    # full double sum and reciprocal ratio; no use of production coefficients.
    with localcontext() as ctx:
        ctx.prec=50
        q=list(map(lambda v:Decimal(str(v)),values));f=list(map(lambda v:Decimal(str(v)),frequencies));d=Decimal(str(z));s=Decimal(0)
        for i in range(len(q)):
            for j in range(len(q)):
                if i==j:rho=Decimal(1)
                else:
                    r=f[i]/f[j]
                    rho=8*d*d*(1+r)*r*r.sqrt()/((1-r*r)**2+4*d*d*r*(1+r)**2)
                s+=q[i]*rho*q[j]
        return float(s.sqrt())


def test_real_fc09_200_total_bindings_and_separate_cqc_pass_independent_decimal(actual_result,accepted_receipt):
    result=actual_result
    for case in ('RSX','RSY'):
        damping=result['reported_total_damping'][case]
        assert len(damping)==100 and [d['mode'] for d in damping]==list(range(1,101))
        assert all(d['reported_total_ratio']==.05 and d['native_value_text']=='0.05' for d in damping)
        assert result['total_damping_checks'][case]['additional_case_material_link_contribution_added'] is False
        matrix=result['CQC_correlation_matrices'][case]
        assert len(matrix)==100 and all(len(row)==100 for row in matrix)
        assert all(matrix[i][i]==1 and all(matrix[i][j]==matrix[j][i] for j in range(100)) for i in range(100))
        rows_=result['modal_operands'][case];freq=[r['frequency_hz'] for r in rows_]
        for key,field in (('_R_CQC','R_kN_per_m'),('_V_CQC','V_kN')):
            values=[r[field] for r in rows_]
            assert result[case+key]==pytest.approx(decimal_cqc(values,freq,.05),rel=2e-13)
        assert damping[0]['binding']['spectrum_case']==case
        assert damping[0]['binding']['source_model_ref']==accepted_receipt['factual_capture_binding']['source_model_ref']
        assert damping[0]['binding']['session_ref']==accepted_receipt['factual_capture_binding']['session_ref']
        assert damping[0]['binding']['acquisition_ref']==accepted_receipt['factual_capture_binding']['capture_ref']
    assert result['CQC_matrix_issued'] is True
    assert result['GLOBAL_DELTA']=='BLOCKED_POINT_LOCAL_TO_GLOBAL_AXES_NOT_CAPTURED'
    assert result['CURRENT_UNCRACKED_B5']=='NOT_PROVIDED' and result['M6_B']=='OPEN'
    assert all(r['Delta_global_m'] is None for rows_ in result['modal_operands'].values() for r in rows_)
    assert not result['current_b5_qualified'] and not result['stability_promotion'] and not result['R2_RERUN_READY']
    assert result['joint_delta_r_v_statistic']=='PROJECT_DECISION_REQUIRED'
    assert not result['factual_capture_binding']['is_analysis_result_epoch']


@pytest.mark.parametrize('key', ['current_b5_qualified','stability_promotion','R2_RERUN_READY'])
def test_strings_or_damping_cannot_self_issue_missing_b5_or_concurrent_state(accepted_receipt,key):
    r=dict(accepted_receipt);r[key]=True
    with pytest.raises(ValueError,match='B5/stability'):review.reconcile_reported_total_damping(r)


@pytest.mark.parametrize('defect',['missing','duplicate','case','unequal','case_only_metadata','double_count'])
def test_actual_100_mode_total_contract_fails_closed_for_source_defects(accepted_receipt,defect):
    r=deepcopy(accepted_receipt);key='Response Spectrum Modal Info@RSX'
    rows_=r['facts'][key]['payload']['parsed']['rows']
    if defect=='missing':rows_.pop()
    elif defect=='duplicate':rows_.append(rows_[0].copy())
    elif defect=='case':rows_[0]['SpecCase']='RSY'
    elif defect=='unequal':rows_[0]['DampRatio']='0.06'
    elif defect=='case_only_metadata':
        key='Response Spectrum Modal Info:metadata'
        r['facts'][key]['payload']['raw_response'][4][4]='The load case damping only.'
    else:
        # A changed native text with stale raw identity cannot masquerade as
        # adding another .05 case/material/link component to the reported total.
        for row in rows_:row['DampRatio']='0.10'
    if defect!='double_count':
        r['facts'][key]['capture_payload_ref']=_payload_ref(r['facts'][key]['payload'])
    with pytest.raises((ValueError,RuntimeError)):
        review.reconcile_reported_total_damping(r)


def test_current_record_keeps_historical_r3g_projection_immutable(actual_result):
    assert actual_result['input_receipt_sha256']==ACCEPTED_RECEIPT_SHA256
    assert actual_result['CQC_result_semantics'].endswith('NOT_CONCURRENT')
    assert actual_result['additional_spectrum_scale_factor_applied'] is False


def test_exact_byte_cli_rejects_replaced_receipt(tmp_path):
    p=tmp_path/'changed.json';p.write_text('{}\n')
    with pytest.raises(ValueError,match='SHA256'):review.reconcile_exact_receipt(p)
