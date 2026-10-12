"""ABI4 offline regressions: all owners/backends/responses explicitly SYNTHETIC."""
import ast,ctypes,hashlib,importlib.util,json,os
from pathlib import Path
from types import SimpleNamespace
import pytest
from etabs_gateway.errors import ETABSCallError
from r3m_abi3_metadata_regression import FakeBSTR,HRESULT
from r3m_abi3_wrapper_regression import dependency,method_type,synthetic_model

SCRIPT_SHA='2b8ec761042d985e7812a16f46300ef317899db1752a45c4177c1f8243850b14'
@pytest.fixture(scope='module')
def probe():
    p=Path(os.environ['COLUMN_R1_ABI4_PROBE']);assert hashlib.sha256(p.read_bytes()).hexdigest()==SCRIPT_SHA
    s=importlib.util.spec_from_file_location('abi4_external_offline',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def originals(probe):
    a,pina=probe.load_accepted(Path(os.environ['COLUMN_R1_ABI3_ACCEPTED_RECEIPT']))
    m,pinm=probe.load_metadata(Path(os.environ['COLUMN_R1_WRAPPER_METADATA_RECEIPT']),a)
    w,pinw=probe.load_wrapper(Path(os.environ['COLUMN_R1_ABI4_WRAPPER_RECEIPT']),m)
    return a,m,w,(pina,pinm,pinw)

def state():return {'getter_gateway_invocations':0,'target_getter_invocation_attempts':0,'phases':[]}

def synthetic(probe,dependency,method_type):
    model,observed,ds,backends,calls=synthetic_model(probe,dependency,method_type)
    raw={};d=ds['GetSection'];c=probe.compatible_declaration(d,probe.INVENTORY[0],bstr=FakeBSTR,hresult=HRESULT)
    probe.inspect_existing_wrapper(model.FrameObj,'GetSection',d,c,dependency,method_type,raw)
    wrapper={'wrapper_records':[{'raw_wrapper_metadata_sha256':probe.raw_sha(raw)}]}
    target={'named_inputs':{'Name':'235'},'historical_target':{'section_property_name':'Column_80x80'}}
    return model,observed,wrapper,target,calls

@pytest.mark.parametrize('raw',[['Column_80x80','',0],('SYNTHETIC_CHANGED','SA',0)])
def test_exact_response_accepts_strings_and_zero_without_engineering_semantics(probe,raw):
    assert probe.validate_section_response(raw)==dict(zip(('PropName','SAuto','pRetVal'),raw))

@pytest.mark.parametrize('raw',[None,0,'x',[],['x',0],['x','',0,0],['x','',1],['x','',True],['x','',0.],['x','',-1],['','',0],[' x','',0],['x','a ',0],[None,'',0],['x',None,0],['x',[],0],['x',float('nan'),0]])
def test_malformed_and_unsuccessful_native_responses_fail_closed(probe,raw):
    with pytest.raises(ValueError):probe.validate_section_response(raw)

@pytest.mark.parametrize('fault',['none','missing','modified','sidecar'])
def test_original_live_wrapper_pair_reused_without_modification(probe,tmp_path,fault):
    a,m,w,pins=originals(probe);p=Path(pins[2]['path']);before=probe.file_sha(p)
    if fault=='none':assert len(w['wrapper_records'])==8 and w['target_factual_getter_invocations']==0
    else:
        q=tmp_path/p.name
        if fault!='missing':
            q.write_bytes(p.read_bytes()+(b' ' if fault=='modified' else b''));q.with_name(q.name+'.sha256').write_bytes(p.with_name(p.name+'.sha256').read_bytes()+(b' ' if fault=='sidecar' else b''))
        with pytest.raises((ValueError,FileNotFoundError)):probe.load_wrapper(q,m)
    assert probe.file_sha(p)==before==probe.WRAPPER_SHA

@pytest.mark.parametrize('fault',['none','target','current_name_missing','malformed_names','duplicate_names'])
def test_exact_source_bound_frame_target_has_no_search_or_nearest_fallback(probe,tmp_path,fault):
    a,*_=originals(probe);repo=Path(os.environ['COLUMN_R1_ABI4_REPO'])
    if fault=='none':assert probe.load_target(repo,a)['named_inputs']=={'Name':'235'};return
    if fault=='target':
        target=tmp_path/probe.TARGET_PATH;target.parent.mkdir(parents=True);target.write_bytes((repo/probe.TARGET_PATH).read_bytes()+b' ');repo=tmp_path
    else:
        a=json.loads(json.dumps(a));names=a['raw_response'][1]
        if fault=='current_name_missing':names[names.index('235')]='SYNTHETIC_REPLACEMENT'
        elif fault=='duplicate_names':names[0]=names[1]
        else:a['raw_response'][0]=True
    with pytest.raises(ValueError):probe.load_target(repo,a)

@pytest.mark.parametrize('fault',['native','wrapper','source','descriptor'])
def test_first_guard_failure_never_invokes_target_or_retries(probe,dependency,method_type,monkeypatch,fault):
    model,m,w,target,calls=synthetic(probe,dependency,method_type);e=state()
    if fault=='native':m['metadata_records'][0]['raw_metadata_sha256']='0'*64
    if fault=='wrapper':w['wrapper_records'][0]['raw_wrapper_metadata_sha256']='0'*64
    if fault=='descriptor':setattr(type(model.FrameObj).__com_interface__,'GetSection',property(lambda _:calls.append('UNSAFE')))
    def source():
        if fault=='source':raise ValueError('SYNTHETIC drift')
    with pytest.raises(ValueError):probe.one_getsection(model,e,m,w,target,bstr=FakeBSTR,hresult=HRESULT,memberspec=dependency,instance_method_type=method_type,check_source=source)
    assert e['target_getter_invocation_attempts']==0 and calls==[]
    with pytest.raises(ValueError):probe.one_getsection(model,e,m,w,target,bstr=FakeBSTR,hresult=HRESULT,memberspec=dependency,instance_method_type=method_type,check_source=lambda:None)
    assert calls==[]

@pytest.mark.parametrize('fault',['none','changed','return','shape','source_after','session','gateway','original_missing','artifact','runtime'])
def test_outer_immutable_receipt_one_exact_call_and_failure_metadata(probe,dependency,method_type,monkeypatch,tmp_path,fault):
    import sys
    from tbdy_engine.etabs import safety
    a,m,w,pins=originals(probe);model,synthetic_m,synthetic_w,target,calls=synthetic(probe,dependency,method_type)
    # Real dependency/backend qualification is exercised separately; only invocation
    # is replaced here with a SYNTHETIC Python method so no native ctypes callback runs.
    invoked=[];response=['SYNTHETIC_CHANGED' if fault=='changed' else 'Column_80x80','',1 if fault=='return' else 0]
    if fault=='shape':response=response[:2]
    interface=type(model.FrameObj).__com_interface__
    def fake_read(self,**kw):invoked.append(kw);assert kw=={'Name':'235'};return response
    setattr(interface,'GetSection',method_type(fake_read))
    def inspection(owner,method,*args):assert owner is model.FrameObj and method=='GetSection';return {'SYNTHETIC_INSPECTION_REPLACED_FOR_WRAPPER_ORCHESTRATION':True}
    monkeypatch.setattr(probe,'inspect_existing_wrapper',inspection)
    synthetic_w['wrapper_records'][0]['raw_wrapper_metadata_sha256']=probe.raw_sha({})
    monkeypatch.setattr(probe,'load_metadata',lambda *args:(synthetic_m,pins[1]));monkeypatch.setattr(probe,'load_wrapper',lambda *args:(w|synthetic_w,pins[2]))
    if fault=='original_missing':monkeypatch.setattr(probe,'load_wrapper',lambda *args:(_ for _ in ()).throw(FileNotFoundError('SYNTHETIC missing original')))
    anchor={'HEAD':'a'*40,'TREE':'b'*40,'worktree_status':''};monkeypatch.setattr(probe,'git_anchor',lambda _:anchor)
    realsha=probe.file_sha
    def file_sha(p):
        if str(p)==probe.SOURCE:return '0'*64 if fault=='source_after' and invoked else probe.CANDIDATE_SOURCE_SHA
        return realsha(p)
    monkeypatch.setattr(probe,'file_sha',file_sha);monkeypatch.setattr(probe,'os',SimpleNamespace(name='nt'));monkeypatch.setattr(probe.sys,'version_info',(3,14,0));monkeypatch.setattr(probe,'validate_identity',lambda *a:None)
    identities=[];operations=[];attaches=[]
    identity=SimpleNamespace(as_dict=lambda:w['identity_after']);session=SimpleNamespace(identity=identity,capabilities=SimpleNamespace(pid_attach=safety.CapabilityState.SUPPORTED),close=lambda:True)
    def reread(_):
        data=dict(w['identity_after']);identities.append(1)
        if fault=='session' and invoked:data['SYNTHETIC_DRIFT']=True
        return SimpleNamespace(as_dict=lambda:data)
    def attach(*args,**kw):attaches.append(kw);assert kw=={'pid':2072,'allow_pid_fallback':False};return session
    def execute(s,callback,*,operation,timeout_seconds):
        operations.append(operation);assert operation=='r3m_abi4_one_getsection_235' and timeout_seconds==30.
        try:
            if fault=='gateway':raise RuntimeError('SYNTHETIC worker original exception')
            return callback(None,model)
        except Exception as cause:raise ETABSCallError('Worker operation failed.',operation=operation,details={'exception_type':type(cause).__name__,'exception_message':str(cause)}) from cause
    monkeypatch.setattr(safety,'attach_verified_to_running_etabs',attach);monkeypatch.setattr(safety,'reread_verified_session_identity',reread);monkeypatch.setattr(safety,'_execute_verified_read',execute)
    monkeypatch.setattr(ctypes,'HRESULT',HRESULT,raising=False);monkeypatch.setitem(sys.modules,'comtypes',SimpleNamespace(BSTR=FakeBSTR,_memberspec=dependency,__version__='WRONG' if fault=='runtime' else '1.4.16'))
    monkeypatch.setitem(sys.modules,'comtypes._post_coinit.instancemethod',SimpleNamespace(PyInstanceMethod_Type=method_type))
    repo=tmp_path/'repo';p=repo/probe.TARGET_PATH;p.parent.mkdir(parents=True);p.write_bytes((Path(os.environ['COLUMN_R1_ABI4_REPO'])/probe.TARGET_PATH).read_bytes())
    out=tmp_path/'out.json';r=probe.run(SimpleNamespace(repo=str(repo),receipt=str(out),pid=2072,expected_head='a'*40,expected_tree='b'*40,
        expected_script_sha='0'*64 if fault=='artifact' else SCRIPT_SHA,candidate_sha256=probe.CANDIDATE_SOURCE_SHA,
        accepted_receipt=pins[0]['path'],metadata_receipt=pins[1]['path'],wrapper_receipt=pins[2]['path']))
    success=fault in {'none','changed'}
    assert r['native_getter_qualified']==success and bool(r['errors'])!=success and json.loads(out.read_text())==r
    assert len(invoked)<=1 and len(operations)<=1 and len(attaches)<=1 and calls==[]
    if success:
        assert invoked==[{'Name':'235'}] and r['raw_response_sha256']==probe.raw_sha(response) and r['native_return_code']==0
        assert r['single_assignment_comparison']['exact_comparison']==('DIFFERENT' if fault=='changed' else 'MATCH')
        assert r['single_assignment_comparison']['whole_model_equivalence']=='NOT_PROVEN'
    if fault in {'original_missing','artifact','runtime','gateway'}:assert invoked==[]
    if fault=='gateway':assert r['errors'][0]['details']['exception_message']==r['errors'][0]['chain'][0]['message']=='SYNTHETIC worker original exception'
    if fault=='return':assert r['native_return_code']==1 and r['raw_response_sha256']==probe.raw_sha(response)
    assert r['FC09_production_gate']=='UNCHANGED' and r['source_authority_rebound'] is False and r['GLOBAL_DELTA']=='NOT_PROVEN'
    assert r['target_result_getter_invocations']==r['modal_result_rows']==0 and r['matrix_records']==[]
    assert out.with_name(out.name+'.sha256').read_text().split()[0]==realsha(out) and out.stat().st_mode & 0o222==0


def test_static_safety_and_accepted_helpers_unchanged(probe):
    tree=ast.parse(Path(probe.__file__).read_text());attrs={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    assert attrs.isdisjoint({'GetNameList','GetSection','GetPoints','GetElm','GetTransformationMatrix','JointDispl','Results','Setup','DatabaseTables','RunAnalysis','StartDesign','Save','SaveAs','SetPresentUnits','QueryInterface','cast','GetTableForDisplayArray'})
    bound_calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='bound']
    assert len(bound_calls)==1 and bound_calls[0].args==[] and len(bound_calls[0].keywords)==1 and bound_calls[0].keywords[0].arg is None
    old=Path(os.environ['COLUMN_R1_WRAPPER_PROBE_PATH']);assert hashlib.sha256(old.read_bytes()).hexdigest()=='89a5a53e05f48e5dc3b04cf614ec63e09174f6841b5c924400237e6ee0db3b21'
    def functions(p):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef)}
    a,b=functions(old),functions(Path(probe.__file__))
    for n in ('validate_identity','write_immutable','classify_parameters','compatible_declaration','observe_method','inspect_existing_wrapper','qualify_dependency','load_accepted','load_metadata','exception_record'):assert a[n]==b[n]
