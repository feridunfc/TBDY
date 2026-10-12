"""Explicit ABI-2 offline tests: native responses are synthetic; no ETABS attach."""
import ast
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import NamedTuple
import pytest
from etabs_gateway.errors import ETABSCallError

SCRIPT_SHA='3c2ec29d660e6c354ebd7ae534370b24e5c941c35a887821ea5128d8f7e826a3'

class _ComMemberSpec(NamedTuple):
    restype:object
    name:str
    argtypes:tuple
    paramflags:tuple
    idlflags:tuple
    doc:object
class FakeBSTR(ctypes.c_wchar_p):pass
class FakeSafeArray(ctypes.Structure):_fields_=[]
ArrayPtr=ctypes.POINTER(FakeSafeArray)
ArrayPtr._itemtype_=FakeBSTR
ArrayPtr.__ctypes_from_outparam__=lambda self:self.synthetic_values

@pytest.fixture(scope='module')
def abi():
    path=Path(os.environ['COLUMN_R1_R3M_ABI2_PROBE_PATH']);assert hashlib.sha256(path.read_bytes()).hexdigest()==SCRIPT_SHA
    s=importlib.util.spec_from_file_location('abi2_external',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

@pytest.fixture(scope='module')
def memberspec(tmp_path_factory):
    source=Path(os.environ['COLUMN_R1_COMTYPES_SOURCE_PATH'])
    assert hashlib.sha256(source.read_bytes()).hexdigest()=='bc85a42d1daf6d84b2697c7ab0f56f70689db4e97122e06bee40af15e583ada2'
    text=source.read_text();tree=ast.parse(text)
    body='from __future__ import annotations\nimport ctypes\nfrom typing import Any,Callable\nPARAMFLAG_FIN=1\nPARAMFLAG_FOUT=2\n_PyCSimpleType=type(ctypes.c_int)\n_CArgObject=type(ctypes.byref(ctypes.c_int()))\n'
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name in ('_prepare_parameter','_fix_inout_args'):body+='\n'+ast.get_source_segment(text,node)+'\n'
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ComMemberGenerator')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_fix_args')
    body+='\nclass OfflineGenerator:\n'+ '\n'.join('    '+line for line in ast.get_source_segment(text,method).splitlines())+'\n'
    p=tmp_path_factory.mktemp('actual_comtypes_source')/'memberspec_offline.py';p.write_text(body)
    spec=importlib.util.spec_from_file_location('memberspec_offline',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def model(abi,memberspec,*,ret=0,raw_names=('F1','F2'),count=None):
    calls=[]
    declaration=_ComMemberSpec(ctypes.c_int32,'GetNameList',
        (ctypes.POINTER(ctypes.c_int32),ctypes.POINTER(ArrayPtr),ctypes.POINTER(ctypes.c_int32)),
        ((3,'NumberNames'),(3,'MyName'),(10,'pRetVal')),(),None)
    def backend(self,*args,**kw):
        calls.append({'args':args,'kw_names':list(kw)})
        assert args==() and kw['NumberNames'].value==0 and not bool(kw['MyName'])
        kw['NumberNames'].value=len(raw_names) if count is None else count
        kw['MyName'].synthetic_values=raw_names
        return [-999,['SYNTHETIC_STALE_PRE_CONVERSION'],ret]
    wrapper=memberspec.OfflineGenerator()._fix_args(declaration,backend)
    interface=type('cFrameObj',(),{'_iid_':abi.OBSERVED_IID,'_methods_':[declaration],'GetNameList':wrapper})
    base=type('ComPointerBase',(ctypes.c_void_p,),{})
    pointer=type(base)('POINTER(cFrameObj)',(interface,base),{'__com_interface__':interface})
    owner=pointer();return SimpleNamespace(FrameObj=owner),declaration,calls

def evidence():return {'invocation_attempts':0,'phases':[],'native_return_code_status':'NOT_OBSERVED'}

@pytest.mark.parametrize('flags,expected',[((1,),'IN'),((2,),'OUT'),((3,),'INOUT'),((10,),'OUT')])
def test_explicit_IN_OUT_INOUT_RETVAL_classification(abi,flags,expected):
    d=_ComMemberSpec(ctypes.c_int32,'Synthetic',(ctypes.POINTER(ctypes.c_int32),),((flags[0],'value'),),(),None)
    r=abi.classify_parameters(d);p=r['parameters'][0]
    assert p['direction']==expected and p['numeric_flags']==flags[0] and p['RETVAL']==(flags[0]==10)
    if flags[0]==3:assert r['native_inputs_including_INOUT']==r['native_outputs_including_INOUT_RETVAL']==['value']

@pytest.mark.parametrize('flag',[0,4,8,9,11,-1,True,32,64,19])
def test_malformed_direction_flags_rejected(abi,flag):
    d=_ComMemberSpec(ctypes.c_int32,'Synthetic',(ctypes.POINTER(ctypes.c_int32),),((flag,'x'),),(),None)
    # Optional INOUT (19) is outside the observed contract and is rejected by GetNameList exact binding below.
    if flag==19:
        r=abi.classify_parameters(d);assert r['parameters'][0]['numeric_flags']==19
    else:
        with pytest.raises(ValueError):abi.classify_parameters(d)


def test_exact_observed_contract_and_actual_dependency_wrapper_return_sequence(abi,memberspec):
    m,d,calls=model(abi,memberspec);observed=abi.metadata_snapshot(m.FrameObj)
    contract,_=abi.qualify_getnamelist(m.FrameObj,bstr_type=FakeBSTR,hresult_type=ctypes.c_int32,observed_metadata=observed)
    r=contract['raw_COM_directions'];assert r['native_inputs_including_INOUT']==['NumberNames','MyName']
    assert r['python_omittable_named_INOUT']==['NumberNames','MyName'] and r['python_required_input_names']==[]
    assert r['python_return_sequence']==['NumberNames','MyName','pRetVal']
    p=abi.qualify_python_wrapper(m.FrameObj.GetNameList,d,memberspec)
    assert p['factory_AST_sha256']==abi.EXPECTED_INOUT_FACTORY_AST_SHA
    raw=m.FrameObj.GetNameList();assert raw==[2,('F1','F2'),0]
    assert calls==[{'args':(),'kw_names':['NumberNames','MyName']}]
    assert abi.decode_names(raw)==('F1','F2')
    from tbdy_engine.etabs.oapi.object_model import _read_name_list
    # A distinct offline owner proves the unchanged repository decoder contract.
    other,_,_=model(abi,memberspec);assert _read_name_list(other.FrameObj,'FrameObj')==(('F1','F2'),[2,('F1','F2'),0])

@pytest.mark.parametrize('fault',['ambiguous','wrong_iid','wrong_output_order','wrong_type','wrong_BSTR','wrong_return_type','wrong_numeric_flags','type_count'])
def test_exact_method_and_type_binding_fail_closed_without_call(abi,memberspec,fault):
    m,d,calls=model(abi,memberspec);observed=abi.metadata_snapshot(m.FrameObj);i=type(m.FrameObj).__com_interface__
    if fault=='ambiguous':i._methods_=[d,d]
    if fault=='wrong_iid':i._iid_='{00000000-0000-0000-0000-000000000000}'
    if fault=='wrong_output_order':d=d._replace(paramflags=((3,'MyName'),(3,'NumberNames'),(10,'pRetVal')))
    if fault=='wrong_type':d=d._replace(argtypes=(ctypes.POINTER(ctypes.c_double),*d.argtypes[1:]))
    if fault=='wrong_BSTR':d=d._replace(argtypes=(d.argtypes[0],ctypes.POINTER(ctypes.POINTER(ctypes.c_double)),d.argtypes[2]))
    if fault=='wrong_return_type':d=d._replace(restype=ctypes.c_double)
    if fault=='wrong_numeric_flags':d=d._replace(paramflags=((19,'NumberNames'),(3,'MyName'),(10,'pRetVal')))
    if fault=='type_count':d=d._replace(argtypes=d.argtypes[:-1])
    if fault not in ('ambiguous','wrong_iid'):i._methods_=[d];observed=abi.metadata_snapshot(m.FrameObj)
    with pytest.raises(ValueError):abi.qualify_getnamelist(m.FrameObj,bstr_type=FakeBSTR,hresult_type=ctypes.c_int32,observed_metadata=observed)
    assert calls==[]

@pytest.mark.parametrize('fault',['other_callable','wrong_closure','wrong_dependency_source'])
def test_python_wrapper_verification_rejects_uncontrolled_callable(abi,memberspec,fault):
    m,d,calls=model(abi,memberspec);bound=m.FrameObj.GetNameList
    if fault=='other_callable':type(m.FrameObj).__com_interface__.GetNameList=lambda _:None;bound=m.FrameObj.GetNameList
    if fault=='wrong_closure':d=d._replace(paramflags=((2,'NumberNames'),(2,'MyName'),(10,'pRetVal')))
    if fault=='wrong_dependency_source':memberspec=SimpleNamespace(_fix_inout_args=lambda *a:None)
    with pytest.raises(ValueError):abi.qualify_python_wrapper(bound,d,memberspec)
    assert calls==[]

@pytest.mark.parametrize('raw',[[2,['A','A'],0],[2,['A'],0],[True,[],0],[0,[],True],[0,[],4],[0,[]],[0,[],0,0]])
def test_native_response_rejection_uses_unchanged_decoder(abi,raw):
    with pytest.raises(ValueError):abi.decode_names(raw)


def install_synthetic_comtypes(monkeypatch,abi,memberspec):
    import sys
    monkeypatch.setitem(sys.modules,'comtypes',SimpleNamespace(BSTR=FakeBSTR,_memberspec=memberspec,__version__='OFFLINE_SYNTHETIC'))
    monkeypatch.setattr(ctypes,'HRESULT',ctypes.c_int32,raising=False)

@pytest.mark.parametrize('ret',[0,7])
def test_one_call_and_failed_return_stop_no_retry(abi,memberspec,monkeypatch,ret):
    install_synthetic_comtypes(monkeypatch,abi,memberspec);m,d,calls=model(abi,memberspec,ret=ret);e=evidence();obs=abi.metadata_snapshot(m.FrameObj)
    if ret:
        with pytest.raises(ValueError):abi.read_one_getnamelist(m,e,obs)
        assert e['phases'][-1]=='FIRST_GETTER_RETURNED'
    else:
        assert abi.read_one_getnamelist(m,e,obs)==('F1','F2')
        assert e['phases'][-1]=='FIRST_GETTER_VALIDATED'
    assert e['invocation_attempts']==len(calls)==1 and e['native_return_code']==ret
    with pytest.raises(ValueError):abi.read_one_getnamelist(m,e,obs)
    assert len(calls)==1


def receipt(abi,m,base):
    meta=abi.metadata_snapshot(m.FrameObj);meta['ABI_validation']='FAIL'
    original={'repository':{'HEAD':'bbfd5b675f06eda92a5710818d52e86cd5d2fc1b','TREE':'f15b7cd4c282f5149de468e3a3960c8e51648988'},
        'source_sha_before':abi.CANDIDATE_SOURCE_SHA,'source_sha_after':abi.CANDIDATE_SOURCE_SHA,'source':abi.SOURCE,'pid':2072,
        'identity_before':{'synthetic':'OFFLINE_ONLY'},'identity_after':{'synthetic':'OFFLINE_ONLY'},'native_GetNameList_invoked':False,'metadata':meta}
    p=base/abi.ABI1_RECEIPT_NAME;abi.write_immutable(p,original);return p

@pytest.mark.parametrize('fault',['sidecar','head','source','invoked'])
def test_original_receipt_binding_rejects_invalid_authority(abi,memberspec,tmp_path,fault):
    m,_,_=model(abi,memberspec);p=receipt(abi,m,tmp_path)
    if fault=='sidecar':
        side=p.with_name(p.name+'.sha256');side.chmod(0o644);side.write_text('0'*64+'  '+p.name+'\n')
    else:
        original=json.loads(p.read_text());p.chmod(0o644)
        if fault=='head':original['repository']['HEAD']='a'*40
        if fault=='source':original['source_sha_after']='0'*64
        if fault=='invoked':original['native_GetNameList_invoked']=True
        p.write_text(json.dumps(original));side=p.with_name(p.name+'.sha256');side.chmod(0o644)
        side.write_text(abi.file_sha(p)+'  '+p.name+'\n')
    with pytest.raises(ValueError):abi.load_observed_receipt(p)

@pytest.mark.parametrize('fault',['valid','native_error','source_drift','session_drift','selection_drift'])
def test_outer_gateway_integrity_and_immutable_receipt(abi,memberspec,monkeypatch,tmp_path,fault):
    from tbdy_engine.etabs import safety
    install_synthetic_comtypes(monkeypatch,abi,memberspec)
    m,d,calls=model(abi,memberspec);original=receipt(abi,m,tmp_path)
    if fault=='native_error':
        def backend(self,*a,**k):calls.append('failed');raise RuntimeError('Original synthetic COM error')
        type(m.FrameObj).__com_interface__.GetNameList=memberspec._fix_inout_args(backend,d.argtypes,d.paramflags)
    identity=SimpleNamespace(as_dict=lambda:{'synthetic':'OFFLINE_ONLY'});n=[]
    def reread(s):
        n.append(s)
        return SimpleNamespace(as_dict=lambda:{'synthetic':'DRIFT'}) if fault=='session_drift' and len(n)>2 else identity
    session=SimpleNamespace(identity=identity,capabilities=SimpleNamespace(pid_attach=safety.CapabilityState.SUPPORTED),close=lambda:True)
    repo=tmp_path/'repo';repo.mkdir();out=tmp_path/'out.json';anchor={'HEAD':'a'*40,'TREE':'b'*40,'worktree_status':''}
    realsha=abi.file_sha;shacalls=[];operations=[]
    def sha(p):
        if str(p)==abi.SOURCE:
            shacalls.append(p);return '0'*64 if fault=='source_drift' and len(shacalls)>2 else abi.CANDIDATE_SOURCE_SHA
        return realsha(p)
    def execute(s,callback,*,operation,timeout_seconds):
        operations.append(operation);assert timeout_seconds==30.
        if operation.startswith('r3m_abi2_selection_guard_'):
            return {'synthetic':'DRIFT' if fault=='selection_drift' and operation.endswith('after') else 'UNCHANGED'}
        assert operation=='r3m_abi2_one_FrameObj_GetNameList'
        try:return callback(None,m)
        except Exception as inner:
            raise ETABSCallError('Worker operation failed.',operation=operation,
                details={'exception_type':type(inner).__name__,'exception_message':str(inner)}) from inner
    monkeypatch.setattr(abi,'os',SimpleNamespace(name='nt'));monkeypatch.setattr(abi,'file_sha',sha)
    monkeypatch.setattr(abi,'git_anchor',lambda _:anchor);monkeypatch.setattr(abi,'validate_identity',lambda *a:None)
    monkeypatch.setattr(safety,'attach_verified_to_running_etabs',lambda *a,**k:session)
    monkeypatch.setattr(safety,'reread_verified_session_identity',reread);monkeypatch.setattr(safety,'_execute_verified_read',execute)
    result=abi.run(SimpleNamespace(repo=str(repo),receipt=str(out),pid=2072,expected_head='a'*40,expected_tree='b'*40,
        candidate_sha256=abi.CANDIDATE_SOURCE_SHA,abi1_receipt=str(original)))
    assert result==json.loads(out.read_text()) and result['invocation_attempts']==len(calls)==1
    assert operations.count('r3m_abi2_one_FrameObj_GetNameList')==1
    assert result['matrix_records']==[] and result['modal_result_rows']==0 and result['FC09_production_gate']=='UNCHANGED'
    assert bool(result['errors'])==(fault!='valid')
    if fault=='native_error':
        error=result['errors'][0];assert error['details']['exception_message']==error['chain'][0]['message']=='Original synthetic COM error'
    assert out.with_name(out.name+'.sha256').read_text().split()[0]==realsha(out) and out.stat().st_mode & 0o222==0


def test_safety_surface_no_engineering_or_setters_and_old_artifacts_unchanged(abi):
    tree=ast.parse(Path(abi.__file__).read_text());calls={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
    assert not calls & {'RunAnalysis','StartDesign','Save','SaveAs','SetPresentUnits','QueryInterface','cast','GetTransformationMatrix','JointDispl',
        'GetTableForDisplayArray','SetCaseSelectedForOutput','SetComboSelectedForOutput','GetPoints','GetSection','GetSectProps'}
    old=Path(os.environ['COLUMN_R1_R3M_ABI1_PROBE_PATH']);assert hashlib.sha256(old.read_bytes()).hexdigest()=='e2b94d5a4b557ae9bdfdcd9db83e42ba60821ebdef7f72e1743ad185048c5e0d'
    before={n.name:ast.dump(n,include_attributes=False) for n in ast.parse(old.read_text()).body if isinstance(n,ast.FunctionDef)}
    after={n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef)}
    for name in ('validate_identity','candidate_pin','write_immutable','exception_record','metadata_snapshot'):assert before[name]==after[name]


def test_planned_late_pure_input_cannot_be_assumed_second_positional_argument(abi,memberspec):
    d=_ComMemberSpec(ctypes.c_int32,'SYNTHETIC_ONLY',
        (ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_double),ctypes.POINTER(ctypes.c_double),ctypes.POINTER(ctypes.c_double),ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_int32)),
        ((1,'Name'),(3,'X'),(3,'Y'),(3,'Z'),(1,'CSys'),(10,'pRetVal')),(),None)
    r=abi.classify_parameters(d)
    assert r['python_required_input_names']==['Name','CSys'] and r['python_return_sequence']==['X','Y','Z','pRetVal']
    calls=[]
    def fake(self,*args,**kw):
        calls.append(kw);assert kw['Name']=='P' and kw['CSys']=='Global'
        for key in ('X','Y','Z'):kw[key].value=1.
        return [None,None,None,0]
    wrapped=memberspec.OfflineGenerator()._fix_args(d,fake)
    with pytest.raises((TypeError,ValueError)):wrapped(None,'P','Global')
    assert calls==[] and wrapped(None,Name='P',CSys='Global')==[1.,1.,1.,0]
