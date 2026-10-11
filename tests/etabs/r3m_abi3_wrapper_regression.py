"""Wrapper qualification offline only. COM owners/declarations/backends are SYNTHETIC.
Native C callbacks are never invoked. Original operator JSON files stay unmodified.
"""
import ast
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from etabs_gateway.errors import ETABSCallError
from r3m_abi3_metadata_regression import declaration, FakeBSTR, HRESULT

SCRIPT_SHA='89a5a53e05f48e5dc3b04cf614ec63e09174f6841b5c924400237e6ee0db3b21'

@pytest.fixture(scope='module')
def wrapper():
    p=Path(os.environ['COLUMN_R1_WRAPPER_PROBE_PATH']);assert hashlib.sha256(p.read_bytes()).hexdigest()==SCRIPT_SHA
    s=importlib.util.spec_from_file_location('wrapper_external_offline',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

@pytest.fixture(scope='module')
def dependency():
    p=Path(os.environ['COLUMN_R1_COMTYPES_SOURCE_PATH'])
    assert hashlib.sha256(p.read_bytes()).hexdigest()=='bc85a42d1daf6d84b2697c7ab0f56f70689db4e97122e06bee40af15e583ada2'
    with pytest.MonkeyPatch.context() as patch:
        import sys
        patch.setitem(sys.modules,'comtypes',SimpleNamespace())
        s=importlib.util.spec_from_file_location('actual_memberspec_offline',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    return m

@pytest.fixture(scope='module')
def method_type():
    # CPython descriptor creation only; no COM interface or ETABS call.
    make=ctypes.pythonapi.PyInstanceMethod_New;make.argtypes=[ctypes.py_object];make.restype=ctypes.py_object
    return type(make(lambda self:None))


def synthetic_model(wrapper,dependency,method_type):
    owners={}; declarations={}; callbacks=[]; calls=[]
    for s in wrapper.INVENTORY:
        d=declaration(s)
        if s['method']=='GetCoordCartesian':d=d._replace(paramflags=(*d.paramflags[:4],(17,'CSys','Global'),d.paramflags[-1]))
        if s['owner'] not in owners:
            interface=type(s['documented_interface'],(),{'_iid_':wrapper.OBSERVED_IID if s['owner']=='FrameObj' else '{11111111-2222-3333-4444-555555555555}','_methods_':[]})
            pointer=type('POINTER('+interface.__name__+')',(interface,),{'__com_interface__':interface})
            owners[s['owner']]=pointer()
        interface=type(owners[s['owner']]).__com_interface__;interface._methods_.append(d)
        def forbidden_backend(*a):calls.append(a);return 0
        backend=ctypes.CFUNCTYPE(d.restype,*d.argtypes)(forbidden_backend);callbacks.append(backend)
        fn=dependency._fix_inout_args(backend,d.argtypes,d.paramflags);fn.__name__=s['method']
        setattr(interface,s['method'],method_type(fn));declarations[s['method']]=d
    model=SimpleNamespace(**owners)
    original={'metadata_records':[wrapper.observe_method(owners[s['owner']],s,bstr=FakeBSTR,hresult=HRESULT) for s in wrapper.INVENTORY]}
    return model,original,declarations,callbacks,calls

@pytest.mark.parametrize('index',range(8))
def test_exact_source_code_closure_and_owner_binding_without_invocation(wrapper,dependency,method_type,index):
    m,original,ds,backends,calls=synthetic_model(wrapper,dependency,method_type);s=wrapper.INVENTORY[index]
    owner=getattr(m,s['owner']);d=ds[s['method']];classified=wrapper.compatible_declaration(d,s,bstr=FakeBSTR,hresult=HRESULT)
    raw={};r=wrapper.inspect_existing_wrapper(owner,s['method'],d,classified,dependency,method_type,raw)
    assert r['status']=='EXACT_EXISTING_CODE_CLOSURE_BOUND_OWNER_VALIDATED_WITHOUT_INVOCATION'
    assert r['required_named_inputs']==(['Name','CSys'] if index==4 else ['Name','ItemTypeElm'] if index==7 else ['Name'])
    assert r['returned_order_from_declaration']==original['metadata_records'][index]['effective_call_plan']['returned_order']
    assert r['native_fact_or_result_qualified'] is False and raw['bound_owner_is_existing_verified_owner'] is True
    assert raw['native_backend_invoked'] is False and calls==[]

@pytest.mark.parametrize('fault',['property','missing','duplicate','instance_override','other_code','wrong_argtypes','wrong_flags','python_backend','backend_type','backend_return'])
def test_wrong_descriptor_or_closure_rejected_before_binding_or_backend_call(wrapper,dependency,method_type,fault):
    m,original,ds,backends,calls=synthetic_model(wrapper,dependency,method_type);s=wrapper.INVENTORY[0];owner=m.FrameObj;interface=type(owner).__com_interface__;d=ds[s['method']]
    fn=vars(interface)[s['method']].__func__
    if fault=='property':setattr(interface,s['method'],property(lambda _:calls.append('UNSAFE_DESCRIPTOR')))
    elif fault=='missing':delattr(interface,s['method'])
    elif fault=='duplicate':setattr(type(owner),s['method'],vars(interface)[s['method']])
    elif fault=='instance_override':vars(owner)[s['method']]=lambda:None
    elif fault=='other_code':setattr(interface,s['method'],method_type(lambda self:None))
    else:
        args=d.argtypes;flags=d.paramflags;backend=backends[0]
        if fault=='wrong_argtypes':args=(ctypes.c_double,*args[1:])
        if fault=='wrong_flags':flags=(d.paramflags[0],(2,'PropName'),*d.paramflags[2:])
        if fault=='python_backend':backend=lambda *a:calls.append('UNSAFE_BACKEND')
        if fault=='backend_type':backend=ctypes.CFUNCTYPE(d.restype,ctypes.c_int32)(lambda _:0)
        if fault=='backend_return':backend=ctypes.CFUNCTYPE(ctypes.c_double,*d.argtypes)(lambda *a:0.)
        fn=dependency._fix_inout_args(backend,args,flags);setattr(interface,s['method'],method_type(fn))
    c=wrapper.classify_parameters(d)
    with pytest.raises(ValueError):wrapper.inspect_existing_wrapper(owner,s['method'],d,c,dependency,method_type,{})
    assert calls==[]

@pytest.mark.parametrize('fault',['factory','helper','globals','source'])
def test_dependency_source_and_existing_bytecode_drift_blocked(wrapper,dependency,monkeypatch,fault):
    module=SimpleNamespace(**vars(dependency))
    if fault=='factory':module._fix_inout_args=lambda *a:None
    if fault=='helper':module._prepare_parameter=lambda *a:None
    if fault=='source':module.__file__=__file__
    if fault=='globals':monkeypatch.setitem(dependency._fix_inout_args.__globals__,'PARAMFLAG_FIN',8)
    with pytest.raises(ValueError):wrapper.qualify_dependency(module)


def test_complete_eight_wrapper_observations_have_zero_invocations_and_one_budget(wrapper,dependency,method_type):
    m,observed,ds,backends,calls=synthetic_model(wrapper,dependency,method_type)
    e={'wrapper_gateway_invocations':0,'phases':[],'wrapper_records':[]}
    wrapper.observe_wrappers(m,e,observed,bstr=FakeBSTR,hresult=HRESULT,memberspec=dependency,instance_method_type=method_type)
    assert len(e['wrapper_records'])==8 and e['wrapper_gateway_invocations']==1 and calls==[]
    for row in e['wrapper_records']:
        assert row['target_invoked'] is False and row['raw_wrapper_metadata_sha256']==wrapper.raw_sha(row['raw_wrapper_metadata'])
    with pytest.raises(ValueError):wrapper.observe_wrappers(m,e,observed,bstr=FakeBSTR,hresult=HRESULT,memberspec=dependency,instance_method_type=method_type)
    assert len(e['wrapper_records'])==8 and calls==[]

@pytest.mark.parametrize('fault',['native_drift','wrapper_mismatch'])
def test_first_failure_preserved_without_later_wrapper_inspection(wrapper,dependency,method_type,fault):
    m,observed,ds,backends,calls=synthetic_model(wrapper,dependency,method_type)
    if fault=='native_drift':observed['metadata_records'][0]['raw_metadata_sha256']='0'*64
    else:setattr(type(m.FrameObj).__com_interface__,'GetSection',property(lambda _:calls.append('UNSAFE')))
    e={'wrapper_gateway_invocations':0,'phases':[],'wrapper_records':[]}
    with pytest.raises(ValueError):wrapper.observe_wrappers(m,e,observed,bstr=FakeBSTR,hresult=HRESULT,memberspec=dependency,instance_method_type=method_type)
    assert len(e['wrapper_records'])==1 and 'failure' in e['wrapper_records'][0] and calls==[]
    assert e['wrapper_records'][0]['raw_wrapper_metadata_sha256']==wrapper.raw_sha(e['wrapper_records'][0]['raw_wrapper_metadata'])

@pytest.mark.parametrize('fault',['none','missing','modified','sidecar'])
def test_original_metadata_pair_is_required_and_not_reconstructed(wrapper,tmp_path,fault):
    p=Path(os.environ['COLUMN_R1_WRAPPER_METADATA_RECEIPT']);accepted,_=wrapper.load_accepted(Path(os.environ['COLUMN_R1_ABI3_ACCEPTED_RECEIPT']))
    before=wrapper.file_sha(p)
    if fault=='none':
        r,pins=wrapper.load_metadata(p,accepted);assert len(r['metadata_records'])==8 and pins['json_sha256']==before
    else:
        target=tmp_path/p.name
        if fault!='missing':
            target.write_bytes(p.read_bytes()+(b' ' if fault=='modified' else b''))
            target.with_name(target.name+'.sha256').write_bytes(p.with_name(p.name+'.sha256').read_bytes()+(b' ' if fault=='sidecar' else b''))
        with pytest.raises((ValueError,FileNotFoundError)):wrapper.load_metadata(target,accepted)
    assert wrapper.file_sha(p)==before==wrapper.METADATA_SHA


def test_named_late_input_plan_replayed_against_observed_17_default_without_COM(wrapper,dependency):
    d=declaration(wrapper.INVENTORY[4]);d=d._replace(paramflags=(*d.paramflags[:4],(17,'CSys','Global'),d.paramflags[-1]))
    c=wrapper.compatible_declaration(d,wrapper.INVENTORY[4],bstr=FakeBSTR,hresult=HRESULT)
    plan=wrapper.construct_named_arguments(c,{'Name':'SYNTHETIC','CSys':'Global'});calls=[]
    def offline_backend(self,*a,**kw):
        calls.append(kw);assert a==() and kw['Name']=='SYNTHETIC' and kw['CSys']=='Global'
        for n,v in zip(('X','Y','Z'),(1.,2.,3.)):kw[n].value=v
        return [None,None,None,0]
    f=dependency._fix_inout_args(offline_backend,d.argtypes,d.paramflags)
    with pytest.raises((TypeError,ValueError)):f(None,'SYNTHETIC','Global')
    assert calls==[] and f(None,**plan['keyword_arguments'])==[1.,2.,3.,0]

@pytest.mark.parametrize('fault',['none','source_drift','session_drift','gateway','native_drift','original_missing','artifact','runtime'])
def test_outer_receipts_failure_chain_integrity_and_no_retry(wrapper,dependency,method_type,monkeypatch,tmp_path,fault):
    import sys
    from tbdy_engine.etabs import safety
    p=Path(os.environ['COLUMN_R1_WRAPPER_METADATA_RECEIPT']);abi2=Path(os.environ['COLUMN_R1_ABI3_ACCEPTED_RECEIPT'])
    accepted,_=wrapper.load_accepted(abi2);original,pin=wrapper.load_metadata(p,accepted)
    m,synthetic,ds,backends,calls=synthetic_model(wrapper,dependency,method_type)
    synthetic.update(identity_after=original['identity_after'])
    if fault=='native_drift':synthetic['metadata_records'][0]['raw_metadata_sha256']='0'*64
    monkeypatch.setattr(wrapper,'load_metadata',lambda *a:(synthetic,pin))
    identity=SimpleNamespace(as_dict=lambda:original['identity_after']);reads=[];source_reads=[];operations=[];attaches=[]
    session=SimpleNamespace(identity=identity,capabilities=SimpleNamespace(pid_attach=safety.CapabilityState.SUPPORTED),close=lambda:True)
    def reread(_):
        reads.append(1);data=dict(original['identity_after'])
        if fault=='session_drift' and len(reads)>2:data['SYNTHETIC_DRIFT']=True
        return SimpleNamespace(as_dict=lambda:data)
    def attach(*a,**kw):attaches.append(kw);assert kw=={'pid':2072,'allow_pid_fallback':False};return session
    def execute(s,callback,*,operation,timeout_seconds):
        operations.append(operation);assert operation=='r3m_abi3_existing_wrapper_code_closure' and timeout_seconds==30.
        try:
            if fault=='gateway':raise RuntimeError('SYNTHETIC original worker exception')
            return callback(None,m)
        except Exception as inner:
            raise ETABSCallError('Worker operation failed.',operation=operation,details={'exception_type':type(inner).__name__,'exception_message':str(inner)}) from inner
    realsha=wrapper.file_sha
    def file_sha(p):
        if str(p)==wrapper.SOURCE:
            source_reads.append(1);return '0'*64 if fault=='source_drift' and len(source_reads)>2 else wrapper.CANDIDATE_SOURCE_SHA
        return realsha(p)
    monkeypatch.setattr(wrapper,'file_sha',file_sha);monkeypatch.setattr(wrapper,'os',SimpleNamespace(name='nt'))
    monkeypatch.setattr(wrapper.sys,'version_info',(3,14,0));monkeypatch.setattr(wrapper,'validate_identity',lambda *a:None)
    anchor={'HEAD':'a'*40,'TREE':'b'*40,'worktree_status':''};monkeypatch.setattr(wrapper,'git_anchor',lambda _:anchor)
    monkeypatch.setattr(safety,'attach_verified_to_running_etabs',attach);monkeypatch.setattr(safety,'reread_verified_session_identity',reread);monkeypatch.setattr(safety,'_execute_verified_read',execute)
    monkeypatch.setattr(ctypes,'HRESULT',HRESULT,raising=False)
    monkeypatch.setitem(sys.modules,'comtypes',SimpleNamespace(BSTR=FakeBSTR,_memberspec=dependency,__version__='WRONG' if fault=='runtime' else '1.4.16'))
    monkeypatch.setitem(sys.modules,'comtypes._post_coinit.instancemethod',SimpleNamespace(PyInstanceMethod_Type=method_type))
    repo=tmp_path/'repo';repo.mkdir();out=tmp_path/'out.json'
    if fault=='original_missing':monkeypatch.setattr(wrapper,'load_metadata',lambda *a:(_ for _ in ()).throw(FileNotFoundError('SYNTHETIC missing original')))
    r=wrapper.run(SimpleNamespace(repo=str(repo),receipt=str(out),pid=2072,expected_head='a'*40,expected_tree='b'*40,
        expected_script_sha='0'*64 if fault=='artifact' else SCRIPT_SHA,candidate_sha256=wrapper.CANDIDATE_SOURCE_SHA,
        accepted_receipt=str(abi2),metadata_receipt=str(p)))
    assert bool(r['errors'])==(fault!='none') and json.loads(out.read_text())==r
    assert len(operations)<=1 and len(attaches)<=1 and calls==[]
    assert r['target_factual_getter_invocations']==r['target_result_getter_invocations']==r['modal_result_rows']==0
    assert r['matrix_records']==[] and r['FC09_production_gate']=='UNCHANGED' and r['source_authority_rebound'] is False
    assert out.with_name(out.name+'.sha256').read_text().split()[0]==realsha(out) and out.stat().st_mode & 0o222==0
    if fault=='none':assert len(r['wrapper_records'])==8
    if fault=='gateway':assert r['errors'][0]['details']['exception_message']==r['errors'][0]['chain'][0]['message']=='SYNTHETIC original worker exception'
    if fault in {'original_missing','artifact'}:assert operations==attaches==[]


def test_static_boundaries_and_originals_unchanged(wrapper):
    p=Path(wrapper.__file__);tree=ast.parse(p.read_text());attrs={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    forbidden={s['method'] for s in wrapper.INVENTORY}|{'GetNameList','RunAnalysis','StartDesign','Save','SaveAs','SetPresentUnits','Setup','DatabaseTables','QueryInterface','cast','GetTableForDisplayArray','SetCaseSelectedForOutput'}
    assert attrs.isdisjoint(forbidden)
    # No target callable/backend invocation occurs anywhere in the operator artifact.
    called={n.func.id for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
    assert called.isdisjoint({'bound','function','backend','descriptor','factory'})
    old=Path(os.environ['COLUMN_R1_ABI3_PROBE_PATH']);assert hashlib.sha256(old.read_bytes()).hexdigest()=='b46144d729c0f539fa629752f14a5149905746bc551370f6cc5d1eca5725acc4'
    def functions(text):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
    a,b=functions(old.read_text()),functions(p.read_text())
    for n in ('validate_identity','write_immutable','classify_parameters','snapshot_owner','compatible_declaration','observe_method','load_accepted','exception_record'):assert a[n]==b[n]
