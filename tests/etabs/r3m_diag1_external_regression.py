"""Explicit offline DIAG-1 tests; synthetic wrappers never attach to ETABS."""
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from etabs_gateway.errors import ETABSCallError, ETABSTimeoutError
from r3m_external_probe_regression import native_owner
from r3m_candidate_source_regression import census_model

SCRIPT_SHA = "8a55a6d3792066f5acfd68b4c7226c3482b846586f4d4f8d832058a8bdc63df5"
CANDIDATE_SHA = "61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621"

@pytest.fixture(scope="module")
def diag():
    path=Path(os.environ["COLUMN_R1_R3M_DIAG1_PROBE_PATH"]).resolve()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==SCRIPT_SHA
    spec=importlib.util.spec_from_file_location("r3m_diag1_external",path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value

def phases(d):
    return [p['phase'] for p in d['phase_markers']]

def test_gateway_original_details_and_chained_cause_survive_outer_record(diag):
    try:
        try: raise ValueError('generated native parameter flags unavailable')
        except ValueError as inner:
            raise ETABSCallError('Worker operation failed.',operation='r3m_candidate_fact_reconciliation',
                details={'exception_type':'ValueError','exception_message':str(inner)}) from inner
    except ETABSCallError as exc:
        result=diag.exception_record(exc)
        assert result['code']==exc.code=='ETABS_CALL_FAILED'
        assert result['operation']==exc.operation=='r3m_candidate_fact_reconciliation'
        assert result['details']==exc.details
        assert result['message']=='Worker operation failed.'
        assert result['chain'][0]['relation']=='cause'
        assert result['chain'][0]['type']=='ValueError'
        assert result['chain'][0]['message']=='generated native parameter flags unavailable'
        assert json.loads(json.dumps(result))==result

@pytest.mark.parametrize('prefix',['','final guards: ','gateway close: ','final file guards: '])
def test_all_error_exits_preserve_metadata_without_prefixing_original_message(diag,prefix):
    exc=ETABSCallError('Original exact message.',operation='bounded_read',
        details={'exception_type':'RuntimeError','exception_message':'inner exact message'})
    evidence={'errors':[]};diag.record_failure(evidence,exc,prefix=prefix)
    result=evidence['errors'][0]
    assert result['message']==prefix+'Original exact message.'
    assert result['original_exception_message']=='Original exact message.'
    assert result['details']==exc.details and result['code']==exc.code and result['operation']==exc.operation

def test_timeout_details_are_preserved_as_timeout_not_native_return_code(diag):
    exc=ETABSTimeoutError('Timed out.',operation='r3m_candidate_fact_reconciliation',
        details={'timeout_seconds':300.,'cancelled_before_start':False})
    result=diag.exception_record(exc)
    assert result['code']=='ETABS_TIMEOUT' and result['details']==exc.details
    assert 'return_code' not in result

def test_implicit_context_and_suppressed_context_are_distinguished(diag):
    inner=ValueError('underlying')
    outer=RuntimeError('wrapper');outer.__context__=inner
    assert diag.exception_record(outer)['chain'][0]['relation']=='context'
    outer.__suppress_context__=True
    assert diag.exception_record(outer)['chain']==[]
    outer.__cause__=inner
    assert diag.exception_record(outer)['chain'][0]['relation']=='cause'

def test_exception_chain_cycles_and_depth_are_bounded(diag):
    a=RuntimeError('a');b=ValueError('b');a.__cause__=b;b.__cause__=a
    assert diag.exception_record(a)['chain_status']=='CYCLE_STOPPED'
    outer=RuntimeError('top');current=outer
    for i in range(12): current.__cause__=ValueError(str(i));current=current.__cause__
    value=diag.exception_record(outer)
    assert len(value['chain'])==8 and value['chain_status']=='DEPTH_LIMIT_STOPPED'

def test_com_hresult_args_and_original_strings_are_retained(diag):
    exc=RuntimeError(-2147352567,'native COM message');exc.hresult=-2147352567
    value=diag.exception_record(exc)
    assert value['args']==[-2147352567,'native COM message'] and value['hresult']==-2147352567

def test_non_json_details_cannot_mask_original_gateway_failure(diag):
    details={'exception_type':'ValueError','exception_message':'exact','odd':b'bytes'}
    exc=ETABSCallError('Worker operation failed.',details=details)
    value=diag.exception_record(exc)
    assert value['details']['exception_message']=='exact'
    assert value['details']['odd']['metadata_status']=='NON_JSON_PYTHON_VALUE'
    json.dumps(value,allow_nan=False)

@pytest.mark.parametrize('failure',['abi','native','return','names','owner'])
def test_first_getter_failure_stops_without_other_getters_and_records_exact_last_stage(diag,failure):
    m,baseline,original,plan=census_model(diag);calls=[]
    if failure=='owner': m=SimpleNamespace()
    elif failure=='abi': type(m.FrameObj)._methods_=[]
    else:
        def first():
            calls.append('FrameObj.GetNameList')
            if failure=='native': raise RuntimeError('Original native failure')
            if failure=='return': return [0,[],7]
            return [2,['duplicate','duplicate'],0]
        m.FrameObj.GetNameList=first
    diagnostics=diag.new_diagnostics();records=[];comparisons=[]
    with pytest.raises((ValueError,RuntimeError,AttributeError)):
        diag.reconcile_native(m,baseline,original,plan,records,comparisons,lambda:None,diagnostics=diagnostics)
    first=diagnostics['first_getter'];assert first['getter']=='FrameObj.GetNameList' and first['failure'] is not None
    assert comparisons==[] and calls in ([],['FrameObj.GetNameList'])
    expected={'owner':1,'abi':2,'native':3,'return':4,'names':4}[failure]
    assert phases(diagnostics)==list(diag.DIAGNOSTIC_PHASES[:expected])
    if failure=='abi': assert first['ABI_validation']=='FAIL' and first['return_code_status']=='NOT_OBSERVED'
    if failure=='return': assert first['return_code']==7 and first['return_code_status']=='OBSERVED'
    if failure=='names': assert first['return_code']==0 and 'FIRST_GETTER_VALIDATED' not in phases(diagnostics)

def test_successful_first_getter_records_all_five_markers_without_changing_comparisons(diag):
    m,baseline,original,plan=census_model(diag);records=[];comparisons=[];d=diag.new_diagnostics()
    endpoints=diag.reconcile_native(m,baseline,original,plan,records,comparisons,lambda:None,diagnostics=d)
    assert phases(d)==list(diag.DIAGNOSTIC_PHASES) and len(endpoints)==172
    assert d['first_getter']['ABI_validation']=='PASS' and d['first_getter']['return_code']==0
    m2,b2,o2,p2=census_model(diag);r2=[];c2=[]
    assert diag.reconcile_native(m2,b2,o2,p2,r2,c2,lambda:None)==endpoints
    assert records==r2 and comparisons==c2

@pytest.mark.parametrize('raw',[[0,[],True],[0,[]],[0,[],0,0],None])
def test_malformed_first_response_does_not_invent_return_code_or_validation(diag,raw):
    m,b,o,p=census_model(diag);m.FrameObj.GetNameList=lambda:raw;d=diag.new_diagnostics()
    with pytest.raises(ValueError):diag.reconcile_native(m,b,o,p,[],[],lambda:None,diagnostics=d)
    assert d['first_getter']['return_code_status']=='NOT_OBSERVED'
    assert phases(d)[-1]=='FIRST_GETTER_RETURNED'

def test_phase_sequence_cannot_retry_or_expand(diag):
    d=diag.new_diagnostics()
    for phase in diag.DIAGNOSTIC_PHASES:diag.mark_phase(d,phase)
    with pytest.raises(ValueError):diag.mark_phase(d,'FIRST_GETTER_ABI_CHECK')
    assert len(d['phase_markers'])==5

@pytest.mark.parametrize('failure',['abi','native','return','before_callback'])
def test_run_outer_wrapper_writes_immutable_original_error_details_and_stops(diag,monkeypatch,tmp_path,failure):
    from tbdy_engine.etabs import safety
    from tools import column_r1_r3l_route_offline as accepted
    m,baseline,original,plan=census_model(diag);calls=[]
    if failure=='abi':type(m.FrameObj)._methods_=[]
    else:
        def first():
            calls.append('FrameObj.GetNameList')
            if failure=='native':raise RuntimeError('Original synthetic native exception')
            return [0,[],9]
        m.FrameObj.GetNameList=first
    identity=SimpleNamespace(as_dict=lambda:{'synthetic':'OFFLINE_ONLY'})
    session=SimpleNamespace(identity=identity,capabilities=SimpleNamespace(pid_attach=safety.CapabilityState.SUPPORTED),close=lambda:True)
    anchor={'HEAD':'a'*40,'TREE':'b'*40,'worktree_status':''}
    repo=tmp_path/'repo';repo.mkdir();pre=tmp_path/'pre.json';rd=tmp_path/'rd.json';manual=tmp_path/'manual.json'
    pre.write_text(json.dumps(baseline));rd.write_text(json.dumps(original));manual.write_text('{}')
    original_sha=diag.file_sha
    def fake_sha(path):
        if str(path)==diag.SOURCE:return CANDIDATE_SHA
        if Path(path)==pre:return '79a7bca0dd50f42b6d9852d2ed56dfc03d0a1cdb40a1c534ea7071f6e8c4ce00'
        if Path(path)==rd:return plan['R3D_original_sha256']
        if Path(path)==manual:return diag.MANUAL_SHA
        return original_sha(path)
    def execute(s,callback,*,operation,timeout_seconds=30.):
        calls.append(operation)
        if operation.startswith('r3m_selection_getters_'):return {'synthetic_selection':'UNCHANGED_OFFLINE_ONLY'}
        assert operation=='r3m_candidate_fact_reconciliation'
        try:
            if failure=='before_callback':raise RuntimeError('Before callback entry')
            return callback(None,m)
        except Exception as inner:
            raise ETABSCallError('Worker operation failed.',operation=operation,
                details={'exception_type':type(inner).__name__,'exception_message':str(inner)}) from inner
    monkeypatch.setattr(diag,'os',SimpleNamespace(name='nt'))
    monkeypatch.setattr(diag,'file_sha',fake_sha);monkeypatch.setattr(diag,'git_anchor',lambda _:anchor)
    monkeypatch.setattr(diag,'validate_identity',lambda *_:None)
    monkeypatch.setattr(safety,'attach_verified_to_running_etabs',lambda *a,**k:session)
    monkeypatch.setattr(safety,'reread_verified_session_identity',lambda _:identity)
    monkeypatch.setattr(safety,'_execute_verified_read',execute)
    monkeypatch.setattr(accepted,'derive_physical_plan',lambda _:plan)
    receipt=tmp_path/'diag.json'
    args=SimpleNamespace(repo=str(repo),receipt=str(receipt),pid=2072,expected_head='a'*40,expected_tree='b'*40,
        candidate_sha256=CANDIDATE_SHA,gui_decimal_places=6,preflight_receipt=str(pre),r3d_receipt=str(rd),manual_receipt=str(manual))
    result=diag.run(args);persisted=json.loads(receipt.read_text())
    assert result==persisted and len(result['errors'])==1
    error=result['errors'][0]
    assert error['code']=='ETABS_CALL_FAILED' and error['operation']=='r3m_candidate_fact_reconciliation'
    assert error['details']['exception_type']==error['chain'][0]['type']
    assert error['details']['exception_message']==error['chain'][0]['message']
    assert result['candidate_stage']=='NOT_STARTED' and result['observations']==[] and result['fact_comparisons']==[]
    assert result['native_fact_getters']==[]
    assert calls.count('r3m_candidate_fact_reconciliation')==1
    assert not any(c.startswith('r3m_matrix:') or c.startswith('r3m_static_') for c in calls)
    assert result['source_sha_before']==result['source_sha_after']==CANDIDATE_SHA
    assert result['identity_before']==result['identity_after'] and result['selection_before']==result['selection_after']
    assert receipt.with_name(receipt.name+'.sha256').read_text().split()[0]==original_sha(receipt)
    assert receipt.stat().st_mode & 0o222==0
    expected={'abi':2,'native':3,'return':4,'before_callback':0}[failure]
    assert phases(result['diagnostics'])==list(diag.DIAGNOSTIC_PHASES[:expected])

def test_engineering_and_native_contract_functions_are_ast_identical_to_accepted_artifact(diag):
    old=Path(os.environ['COLUMN_R1_R3M_CANDIDATE_PROBE_PATH']);assert hashlib.sha256(old.read_bytes()).hexdigest()=='27362d2fd9c5cbb1d5a9800f4b207d4e6832f057f1cff2982f06500f2089248b'
    def functions(path):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef)}
    before,after=functions(old),functions(Path(diag.__file__))
    for name in ['generated_abi','decode_names','decode_flag','snapshot_selection','require_lc_dl_only','decode_matrix','compare_hypotheses',
                 'decode_static','flatten_plan','scan_matrices','acquire_static_candidates','scan_disposition','choose_operator_point',
                 'validate_identity','candidate_pin','compare_fact','engineering_disposition','write_immutable']:
        assert before[name]==after[name],name
    calls={n.func.attr for n in ast.walk(ast.parse(Path(diag.__file__).read_text())) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
    assert not calls & {'RunAnalysis','StartDesign','Save','SetPresentUnits','SetCaseSelectedForOutput','SetComboSelectedForOutput','GetTableForDisplayArray'}
