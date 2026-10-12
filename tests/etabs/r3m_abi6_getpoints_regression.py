"""ABI6 deterministic offline fixtures only; no native ETABS/ctypes backend invocation."""
import ast,ctypes,hashlib,importlib.util,json,os,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from etabs_gateway.errors import ETABSCallError
from r3m_abi3_metadata_regression import FakeBSTR,HRESULT
from r3m_abi3_wrapper_regression import dependency,method_type,synthetic_model

SCRIPT_SHA='847c1d44c0b519ca28417618efd4939a28e25ca7e604ceccf737db7edeaabf76'
@pytest.fixture(scope='module')
def probe():
    p=Path(os.environ['COLUMN_R1_ABI6_PROBE']);assert hashlib.sha256(p.read_bytes()).hexdigest()==SCRIPT_SHA
    s=importlib.util.spec_from_file_location('abi6_external_offline',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def originals(probe):
    a,pa=probe.load_accepted(Path(os.environ['COLUMN_R1_ABI3_ACCEPTED_RECEIPT']))
    m,pm=probe.load_metadata(Path(os.environ['COLUMN_R1_WRAPPER_METADATA_RECEIPT']),a)
    w,pw=probe.load_wrapper(Path(os.environ['COLUMN_R1_ABI4_WRAPPER_RECEIPT']),m)
    d,pd=probe.load_assignment(Path(os.environ['COLUMN_R1_ABI5_ASSIGNMENT_RECEIPT']),w,m)
    p,pp=probe.load_closed_property(Path(os.environ['COLUMN_R1_ABI6_PROPERTY_RECEIPT']),w,m,d)
    return a,m,w,d,p,(pa,pm,pw,pd,pp)

def state():return {'getter_gateway_invocations':0,'target_getter_invocation_attempts':0,'phases':[]}

def synthetic(probe,dependency,method_type):
    model,m,ds,backends,calls=synthetic_model(probe,dependency,method_type);raw={};d=ds['GetPoints']
    c=probe.compatible_declaration(d,probe.INVENTORY[2],bstr=FakeBSTR,hresult=HRESULT)
    probe.inspect_existing_wrapper(model.FrameObj,'GetPoints',d,c,dependency,method_type,raw)
    return model,m,{'wrapper_records':[{}, {}, {'raw_wrapper_metadata_sha256':probe.raw_sha(raw)}]}, {'named_inputs':{'Name':'235'}},ds,calls

@pytest.mark.parametrize('container',[list,tuple])
@pytest.mark.parametrize('names',[('SYNTHETIC_Z','SYNTHETIC_A'),('SYNTHETIC_A','SYNTHETIC_Z')])
def test_exact_native_slot_order_is_preserved_without_role_or_sort_inference(probe,container,names):
    raw=container([*names,0]);e={};v=probe.capture_points_response(e,raw)
    assert v=={'Point1':names[0],'Point2':names[1],'pRetVal':0}
    assert e['raw_response']==list(raw) and e['raw_response_sha256']==probe.raw_sha(raw)
    assert e['native_response_python_type']=='builtins.'+container.__name__ and e['raw_response_scalar_types']==['builtins.str','builtins.str','builtins.int']
    assert 'bottom' not in v and 'top' not in v

@pytest.mark.parametrize('raw',[None,1,'x',[],['P1','P2'],['P1','P2',0,0],['P1','P2',1],['P1','P2',-1],['P1','P2',False],['P1','P2',0.],['','P2',0],['P1','',0],[' P1','P2',0],['P1','P2 ',0],['P1','P1',0],[1,'P2',0],['P1',None,0],['P1',[],0],['P\x00','P2',0],['P1',float('nan'),0]])
def test_malformed_unsuccessful_or_duplicate_response_keeps_evidence_and_stops(probe,raw):
    e={}
    with pytest.raises(ValueError):probe.capture_points_response(e,raw)
    assert len(e['raw_response_sha256'])==len(e['typed_raw_evidence_sha256'])==64
    if raw==['P1','P2',1]:assert e['native_return_code']==1

@pytest.mark.parametrize('fault',['none','missing','json','sidecar'])
def test_accepted_original_abi5_pair_is_reused_without_mutation(probe,tmp_path,fault):
    a,m,w,d,p,pins=originals(probe);original=Path(pins[4]['path']);before=probe.file_sha(original)
    if fault=='none':assert p['target_name']=='Column_80x80' and p['native_return_code']==0
    else:
        q=tmp_path/original.name
        if fault!='missing':q.write_bytes(original.read_bytes()+(b' ' if fault=='json' else b''));q.with_name(q.name+'.sha256').write_bytes(original.with_name(original.name+'.sha256').read_bytes()+(b' ' if fault=='sidecar' else b''))
        with pytest.raises((ValueError,FileNotFoundError)):probe.load_closed_property(q,w,m,d)
    assert before==probe.file_sha(original)==probe.PROPERTY_SHA

@pytest.mark.parametrize('fault',['none','target_bytes','assignment_name','property_name','missing_frame','duplicate_population'])
def test_exact_candidate_frame_target_rejects_source_rebinding_and_fallback(probe,tmp_path,fault):
    a,m,w,d,p,pins=originals(probe);repo=Path(os.environ['COLUMN_R1_ABI4_REPO'])
    if fault=='none':assert probe.load_target(repo,a,d,p)['named_inputs']=={'Name':'235'};return
    if fault=='target_bytes':
        q=tmp_path/probe.TARGET_PATH;q.parent.mkdir(parents=True);q.write_bytes((repo/probe.TARGET_PATH).read_bytes()+b' ');repo=tmp_path
    elif fault=='assignment_name':d=json.loads(json.dumps(d));d['call_arguments']['named']['Name']='SYNTHETIC_236'
    elif fault=='property_name':p=dict(p,target_name='SYNTHETIC_OTHER')
    else:
        a=json.loads(json.dumps(a));names=a['raw_response'][1]
        if fault=='missing_frame':names[names.index('235')]='SYNTHETIC_OTHER'
        else:names[0]=names[1]
    with pytest.raises(ValueError):probe.load_target(repo,a,d,p)

@pytest.mark.parametrize('fault',['nonpointer','wrong_pointee','swap','flags','retval','iid','wrapper','source','descriptor','missing_declaration','ambiguous_declaration'])
def test_exact_abi_wrapper_drift_or_first_guard_failure_stops_without_retry(probe,dependency,method_type,monkeypatch,fault):
    model,m,w,t,ds,calls=synthetic(probe,dependency,method_type);e=state();d=ds['GetPoints'];interface=type(model.FrameObj).__com_interface__
    if fault in ('nonpointer','wrong_pointee'):
        types=list(d.argtypes);types[1]=FakeBSTR if fault=='nonpointer' else ctypes.POINTER(ctypes.c_double);changed=d._replace(argtypes=tuple(types))
        interface._methods_=[changed if x.name=='GetPoints' else x for x in interface._methods_]
    if fault in ('swap','flags','retval'):
        flags=list(d.paramflags)
        if fault=='swap':flags[1],flags[2]=flags[2],flags[1]
        elif fault=='flags':flags[1]=(1,'Point1')
        else:flags[-1]=(3,'pRetVal')
        changed=d._replace(paramflags=tuple(flags));interface._methods_=[changed if x.name=='GetPoints' else x for x in interface._methods_]
    if fault=='missing_declaration':interface._methods_=[x for x in interface._methods_ if x.name!='GetPoints']
    if fault=='ambiguous_declaration':interface._methods_.append(d)
    if fault=='iid':m['metadata_records'][2]['declaring_IID']='{00000000-0000-0000-0000-000000000000}'
    if fault=='wrapper':w['wrapper_records'][2]['raw_wrapper_metadata_sha256']='0'*64
    if fault=='descriptor':setattr(interface,'GetPoints',property(lambda _:calls.append('UNSAFE')))
    def source():
        if fault=='source':raise ValueError('SYNTHETIC source drift')
    with pytest.raises(ValueError):probe.one_getpoints(model,e,m,w,t,bstr=FakeBSTR,hresult=HRESULT,memberspec=dependency,instance_method_type=method_type,check_source=source)
    assert e['target_getter_invocation_attempts']==0 and calls==[]
    with pytest.raises(ValueError):probe.one_getpoints(model,e,m,w,t,bstr=FakeBSTR,hresult=HRESULT,memberspec=dependency,instance_method_type=method_type,check_source=lambda:None)
    assert calls==[]

@pytest.mark.parametrize('fault',['none','reversed','return','shape','duplicate','source_after','session','units','lock','gateway','timeout','property_missing','artifact','runtime','unauthorized'])
def test_outer_immutable_receipt_one_read_preserves_failure_and_never_assigns_bottom_top(probe,dependency,method_type,monkeypatch,tmp_path,fault):
    from tbdy_engine.etabs import safety
    a,m,w,assignment,closed,pins=originals(probe);model,synthetic_m,synthetic_w,target,ds,calls=synthetic(probe,dependency,method_type)
    invoked=[];response=['SYNTHETIC_Z','SYNTHETIC_A',1 if fault=='return' else 0]
    if fault=='reversed':response[:2]=list(reversed(response[:2]))
    if fault=='shape':response=response[:2]
    if fault=='duplicate':response[1]=response[0]
    interface=type(model.FrameObj).__com_interface__
    # Replace only invocation with explicit SYNTHETIC Python method. Actual native
    # wrapper/dependency guards are exercised separately; no ctypes callback runs.
    def fake(self,**kw):invoked.append(kw);assert kw=={'Name':'235'};return response
    setattr(interface,'GetPoints',method_type(fake))
    def inspection(owner,method,*args):assert owner is model.FrameObj and method=='GetPoints';return {'SYNTHETIC_INSPECTION_REPLACED_FOR_ORCHESTRATION':True}
    monkeypatch.setattr(probe,'inspect_existing_wrapper',inspection);synthetic_w['wrapper_records'][2]['raw_wrapper_metadata_sha256']=probe.raw_sha({})
    monkeypatch.setattr(probe,'load_metadata',lambda *args:(synthetic_m,pins[1]));monkeypatch.setattr(probe,'load_wrapper',lambda *args:(w|synthetic_w,pins[2]))
    monkeypatch.setattr(probe,'load_assignment',lambda *args:(assignment,pins[3]));monkeypatch.setattr(probe,'load_closed_property',lambda *args:(closed,pins[4]))
    if fault=='property_missing':monkeypatch.setattr(probe,'load_closed_property',lambda *args:(_ for _ in ()).throw(FileNotFoundError('SYNTHETIC missing original ABI5')))
    anchor={'HEAD':'a'*40,'TREE':'b'*40,'worktree_status':''};monkeypatch.setattr(probe,'git_anchor',lambda _:anchor)
    realsha=probe.file_sha
    def file_sha(p):
        if str(p)==probe.SOURCE:return '0'*64 if fault=='source_after' and invoked else probe.CANDIDATE_SOURCE_SHA
        return realsha(p)
    monkeypatch.setattr(probe,'file_sha',file_sha);monkeypatch.setattr(probe,'os',SimpleNamespace(name='nt'));monkeypatch.setattr(probe.sys,'version_info',(3,14,0));monkeypatch.setattr(probe,'validate_identity',lambda *args:None)
    identity=SimpleNamespace(as_dict=lambda:w['identity_after']);session=SimpleNamespace(identity=identity,capabilities=SimpleNamespace(pid_attach=safety.CapabilityState.SUPPORTED),close=lambda:True)
    reads=[];operations=[];attaches=[]
    def reread(_):
        data=json.loads(json.dumps(w['identity_after']));reads.append(1)
        if invoked:
            if fault=='session':data['SYNTHETIC_DRIFT']=True
            if fault=='units':data['units']['present_length_unit']=5
            if fault=='lock':data['model_locked']=False
        return SimpleNamespace(as_dict=lambda:data)
    def attach(*args,**kw):attaches.append(kw);assert kw=={'pid':2072,'allow_pid_fallback':False};return session
    def execute(s,callback,*,operation,timeout_seconds):
        operations.append(operation);assert operation=='r3m_abi6_one_getpoints_235' and timeout_seconds==30.;before=len(reads)
        try:
            if fault=='gateway':raise RuntimeError('SYNTHETIC original gateway failure')
            if fault=='timeout':raise TimeoutError('SYNTHETIC bounded timeout')
            return callback(None,model)
        except Exception as cause:raise ETABSCallError('Worker operation failed.',operation=operation,details={'exception_type':type(cause).__name__,'exception_message':str(cause)}) from cause
        finally:assert len(reads)==before  # no nested queued identity observation in target callback
    monkeypatch.setattr(safety,'attach_verified_to_running_etabs',attach);monkeypatch.setattr(safety,'reread_verified_session_identity',reread);monkeypatch.setattr(safety,'_execute_verified_read',execute)
    monkeypatch.setattr(ctypes,'HRESULT',HRESULT,raising=False);monkeypatch.setitem(sys.modules,'comtypes',SimpleNamespace(BSTR=FakeBSTR,_memberspec=dependency,__version__='WRONG' if fault=='runtime' else '1.4.16'))
    monkeypatch.setitem(sys.modules,'comtypes._post_coinit.instancemethod',SimpleNamespace(PyInstanceMethod_Type=method_type))
    repo=tmp_path/'repo';q=repo/probe.TARGET_PATH;q.parent.mkdir(parents=True);q.write_bytes((Path(os.environ['COLUMN_R1_ABI4_REPO'])/probe.TARGET_PATH).read_bytes())
    out=tmp_path/'out.json';r=probe.run(SimpleNamespace(repo=str(repo),receipt=str(out),pid=2072,expected_head='a'*40,expected_tree='b'*40,
        expected_script_sha='0'*64 if fault=='artifact' else SCRIPT_SHA,candidate_sha256=probe.CANDIDATE_SOURCE_SHA,
        accepted_receipt=pins[0]['path'],metadata_receipt=pins[1]['path'],wrapper_receipt=pins[2]['path'],assignment_receipt=pins[3]['path'],property_receipt=pins[4]['path'],supervisor_authorized_one_read=fault!='unauthorized'))
    success=fault in {'none','reversed'};assert r['native_getter_qualified']==success and bool(r['errors'])!=success and json.loads(out.read_text())==r
    assert len(invoked)<=1 and len(operations)<=1 and len(attaches)<=1 and calls==[]
    if success:
        assert invoked==[{'Name':'235'}] and r['raw_response']==response and r['raw_response_sha256']==probe.raw_sha(response)
        assert r['call_arguments']['omitted_INOUT']==['Point1','Point2']
        point=r['endpoint_evidence'];assert (point['Point1'],point['Point2'])==tuple(response[:2])
        assert point['bottom_point']==point['top_point']==point['point_object_to_analysis_joint_binding']==point['panel_zone_applicability']=='NOT_PROVEN'
    if fault in {'property_missing','artifact','runtime','gateway','timeout','unauthorized'}:assert invoked==[]
    if fault=='gateway':assert r['errors'][0]['details']['exception_message']==r['errors'][0]['chain'][0]['message']=='SYNTHETIC original gateway failure'
    if fault=='return':assert r['native_return_code']==1 and r['raw_response_sha256']==probe.raw_sha(response)
    if fault in {'session','units','lock'}:assert r['endpoint_evidence']['final_integrity_qualification']=='INVALID_NO_PHYSICAL_BINDING_AUTHORITY'
    assert r['FC09_production_gate']=='UNCHANGED' and r['source_authority_rebound'] is False and r['GLOBAL_DELTA']=='NOT_PROVEN' and r['bottom_top_assignment']=='NOT_PROVEN'
    assert r['target_result_getter_invocations']==r['modal_result_rows']==0 and r['matrix_records']==[]
    assert out.with_name(out.name+'.sha256').read_text().split()[0]==realsha(out) and out.stat().st_mode & 0o222==0


def test_static_safety_sole_bound_call_no_nested_identity_and_preserved_helpers(probe):
    tree=ast.parse(Path(probe.__file__).read_text());attrs={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    assert attrs.isdisjoint({'GetNameList','GetSection','GetSectProps','GetPoints','GetCoordCartesian','GetElm','GetTransformationMatrix','JointDispl','PropFrame','PointObj','PointElm','Results','Setup','DatabaseTables','RunAnalysis','StartDesign','Save','SaveAs','SetPresentUnits','QueryInterface','cast','GetTableForDisplayArray'})
    functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)};callback=functions['one_getpoints']
    assert not any(isinstance(n,ast.Name) and n.id in {'reread_verified_session_identity','attach_verified_to_running_etabs','_execute_verified_read'} for n in ast.walk(callback))
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in {'sorted','min','max'} for n in ast.walk(callback))
    bound=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='bound'];assert len(bound)==1 and bound[0].args==[] and bound[0].keywords[0].arg is None
    old=ast.parse(Path(os.environ['COLUMN_R1_ABI5_PROBE']).read_text());oldfuncs={n.name:n for n in old.body if isinstance(n,ast.FunctionDef)}
    for name in ('validate_identity','write_immutable','classify_parameters','compatible_declaration','observe_method','inspect_existing_wrapper','qualify_dependency','load_accepted','load_metadata','load_wrapper','load_assignment','exception_record'):
        assert ast.dump(functions[name],include_attributes=False)==ast.dump(oldfuncs[name],include_attributes=False)
