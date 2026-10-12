"""ABI5 offline only: response fixtures/owners are SYNTHETIC; no ETABS/COM invocation."""
import ast,ctypes,hashlib,importlib.util,json,os,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from etabs_gateway.errors import ETABSCallError
from r3m_abi3_metadata_regression import FakeBSTR,HRESULT
from r3m_abi3_wrapper_regression import dependency,method_type,synthetic_model

SCRIPT_SHA='95a15d6faf6eac88be14b3650ad22802e2821545a19a571be2d1c9eaee1b5947'
@pytest.fixture(scope='module')
def probe():
    p=Path(os.environ['COLUMN_R1_ABI5_PROBE']);assert hashlib.sha256(p.read_bytes()).hexdigest()==SCRIPT_SHA
    spec=importlib.util.spec_from_file_location('abi5_external_offline',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def originals(probe):
    a,pa=probe.load_accepted(Path(os.environ['COLUMN_R1_ABI3_ACCEPTED_RECEIPT']))
    m,pm=probe.load_metadata(Path(os.environ['COLUMN_R1_WRAPPER_METADATA_RECEIPT']),a)
    w,pw=probe.load_wrapper(Path(os.environ['COLUMN_R1_ABI4_WRAPPER_RECEIPT']),m)
    assignment,pd=probe.load_assignment(Path(os.environ['COLUMN_R1_ABI5_ASSIGNMENT_RECEIPT']),w,m)
    hist,identity,ph=probe.load_historical(Path(os.environ['COLUMN_R1_FC09_PREFLIGHT_TEST_PATH']))
    return a,m,w,assignment,hist,identity,(pa,pm,pw,pd,ph)

def state():return {'getter_gateway_invocations':0,'target_getter_invocation_attempts':0,'phases':[]}

def synthetic(probe,dependency,method_type):
    model,m,ds,backends,calls=synthetic_model(probe,dependency,method_type)
    type(model.PropFrame).__com_interface__._iid_=probe.PROP_IID
    m['metadata_records'][1]=probe.observe_method(model.PropFrame,probe.INVENTORY[1],bstr=FakeBSTR,hresult=HRESULT)
    raw={};d=ds['GetSectProps'];c=probe.compatible_declaration(d,probe.INVENTORY[1],bstr=FakeBSTR,hresult=HRESULT)
    probe.inspect_existing_wrapper(model.PropFrame,'GetSectProps',d,c,dependency,method_type,raw)
    w={'wrapper_records':[{}, {'raw_wrapper_metadata_sha256':probe.raw_sha(raw)}]}
    return model,m,w,{'named_inputs':{'Name':'Column_80x80'}},ds,calls

@pytest.mark.parametrize('container',[list,tuple])
def test_exact_order_types_container_hash_and_asymmetric_axes(probe,container):
    raw=container([float(i+1) for i in range(12)]+[0]);e={};v=probe.capture_property_response(e,raw)
    assert v['I22']==5. and v['I33']==6. and list(v)==list(probe.FIELDS)+['pRetVal']
    assert e['raw_response_sha256']==probe.raw_sha(raw) and e['raw_response_scalar_types']==['builtins.float']*12+['builtins.int']
    assert e['native_response_python_type']=='builtins.'+container.__name__ and e['native_return_code']==0
    assert e['raw_response_float64_hex'][4]==(5.).hex() and e['raw_response']==list(raw)

@pytest.mark.parametrize('fault',['none','short','long','scalar','dict','tuple_subclass','status_bool','status_float','status_nonzero','status_negative','int_property','bool_property','none_property','nan','inf','negative_inf'])
def test_malformed_response_preserves_partial_evidence_and_fails_closed(probe,fault):
    raw=[float(i+1) for i in range(12)]+[0]
    if fault=='short':raw.pop()
    elif fault=='long':raw.append(0)
    elif fault=='scalar':raw=2.
    elif fault=='dict':raw={'x':2.}
    elif fault=='tuple_subclass':raw=type('SyntheticTuple',(tuple,),{})(raw)
    elif fault.startswith('status_'):raw[-1]={'status_bool':False,'status_float':0.,'status_nonzero':1,'status_negative':-1}[fault]
    elif fault.endswith('property'):raw[4]={'int_property':1,'bool_property':True,'none_property':None}[fault]
    elif fault in ('nan','inf','negative_inf'):raw[4]=float({'negative_inf':'-inf'}.get(fault,fault))
    e={}
    if fault=='none':probe.capture_property_response(e,raw)
    else:
        with pytest.raises(ValueError):probe.capture_property_response(e,raw)
    assert len(e['raw_response_sha256'])==len(e['typed_raw_evidence_sha256'])==64 and 'native_response_python_type' in e
    if fault=='status_nonzero':assert e['native_return_code']==1
    if fault=='nan':assert e['raw_response_scalar_types'][4]=='builtins.float' and e['raw_response_float64_hex'][4]=='nan'

@pytest.mark.parametrize('fault',['none','missing','json_modified','side_modified'])
def test_original_assignment_pair_is_exact_binding_authority(probe,tmp_path,fault):
    a,m,w,d,h,i,pins=originals(probe);original=Path(pins[3]['path']);before=probe.file_sha(original)
    if fault=='none':assert d['validated_response']['PropName']=='Column_80x80'
    else:
        q=tmp_path/original.name
        if fault!='missing':q.write_bytes(original.read_bytes()+(b' ' if fault=='json_modified' else b''));q.with_name(q.name+'.sha256').write_bytes(original.with_name(original.name+'.sha256').read_bytes()+(b' ' if fault=='side_modified' else b''))
        with pytest.raises((ValueError,FileNotFoundError)):probe.load_assignment(q,w,m)
    assert probe.file_sha(original)==before==probe.ABI4_SHA

@pytest.mark.parametrize('fault',['none','target_bytes','wrong_assignment','wrong_historical_ref'])
def test_source_bound_target_rejects_rebinding(probe,tmp_path,fault):
    a,m,w,d,h,i,pins=originals(probe);repo=Path(os.environ['COLUMN_R1_ABI4_REPO'])
    if fault=='none':assert probe.load_target(repo,d,h)['named_inputs']=={'Name':'Column_80x80'};return
    if fault=='target_bytes':
        p=tmp_path/probe.TARGET_PATH;p.parent.mkdir(parents=True);p.write_bytes((repo/probe.TARGET_PATH).read_bytes()+b' ');repo=tmp_path
    elif fault=='wrong_assignment':d=json.loads(json.dumps(d));d['validated_response']['PropName']='SYNTHETIC_OTHER'
    else:h=dict(h,raw_response_ref='SYNTHETIC_OTHER')
    with pytest.raises(ValueError):probe.load_target(repo,d,h)


def test_historical_all_twelve_raw_but_only_two_qualified_unit_comparisons(probe):
    a,m,w,d,h,i,pins=originals(probe);v=probe.validate_property_response(h['raw_response']);v['I22']=5.;v['I33']=6.
    comparison=probe.field_comparison(v,h,i);rows=comparison['fields']
    assert len(rows)==12 and rows[4]['field']=='I22' and rows[5]['field']=='I33' and rows[4]['candidate_float64_hex']==(5.).hex() and rows[5]['candidate_float64_hex']==(6.).hex()
    assert {r['field'] for r in rows if r['comparison']=='DIFFERENT'}=={'I22','I33'}
    for r in rows:
        assert r['conversion']=='NONE' and r['axis_swap'] is False and r['candidate_source_sha256']!=r['historical_source_sha256']
        if r['field'] not in ('I22','I33'):assert r['comparison']=='NOT_COMPARABLE' and r['dimensional_unit']=='NOT_PROVEN'
    assert comparison['whole_model_equivalence']==comparison['analysis_result_equivalence']=='NOT_PROVEN'

@pytest.mark.parametrize('fault',['float32','nonpointer','swap','flags','retval','iid','wrapper','source','descriptor'])
def test_exact_abi_wrapper_type_and_first_failure_stop(probe,dependency,method_type,monkeypatch,fault):
    model,m,w,target,ds,calls=synthetic(probe,dependency,method_type);e=state();_,_,_,_,h,i,_=originals(probe)
    d=ds['GetSectProps']
    if fault in ('float32','nonpointer'):
        types=list(d.argtypes);types[5]=ctypes.POINTER(ctypes.c_float) if fault=='float32' else ctypes.c_double
        changed=d._replace(argtypes=tuple(types));interface=type(model.PropFrame).__com_interface__;interface._methods_=[changed if x.name=='GetSectProps' else x for x in interface._methods_]
    if fault in ('swap','flags','retval'):
        flags=list(d.paramflags)
        if fault=='swap':flags[5],flags[6]=flags[6],flags[5]
        elif fault=='flags':flags[5]=(1,'I22')
        else:flags[-1]=(3,'pRetVal')
        changed=d._replace(paramflags=tuple(flags));interface=type(model.PropFrame).__com_interface__;interface._methods_=[changed if x.name=='GetSectProps' else x for x in interface._methods_]
    if fault=='iid':m['metadata_records'][1]['declaring_IID']='{00000000-0000-0000-0000-000000000000}'
    if fault=='wrapper':w['wrapper_records'][1]['raw_wrapper_metadata_sha256']='0'*64
    if fault=='descriptor':setattr(type(model.PropFrame).__com_interface__,'GetSectProps',property(lambda _:calls.append('UNSAFE')))
    def check():
        if fault=='source':raise ValueError('SYNTHETIC source drift')
    with pytest.raises(ValueError):probe.one_getsectprops(model,e,m,w,target,h,i,bstr=FakeBSTR,hresult=HRESULT,memberspec=dependency,instance_method_type=method_type,check_source=check)
    assert e['target_getter_invocation_attempts']==0 and calls==[]
    with pytest.raises(ValueError):probe.one_getsectprops(model,e,m,w,target,h,i,bstr=FakeBSTR,hresult=HRESULT,memberspec=dependency,instance_method_type=method_type,check_source=lambda:None)
    assert calls==[]


def test_static_safety_no_nested_identity_reads_and_accepted_helpers_unchanged(probe):
    p=Path(probe.__file__);tree=ast.parse(p.read_text());attrs={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    assert attrs.isdisjoint({'GetNameList','GetSection','GetPoints','GetElm','GetTransformationMatrix','JointDispl','Results','Setup','DatabaseTables','RunAnalysis','StartDesign','Save','SaveAs','SetPresentUnits','QueryInterface','cast','GetTableForDisplayArray'})
    funcs={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)};callback=funcs['one_getsectprops']
    assert not any(isinstance(n,ast.Name) and n.id in {'reread_verified_session_identity','attach_verified_to_running_etabs','_execute_verified_read'} for n in ast.walk(callback))
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='bound']
    assert len(calls)==1 and calls[0].args==[] and calls[0].keywords[0].arg is None
    old=ast.parse(Path(os.environ['COLUMN_R1_ABI4_PROBE']).read_text());oldfuncs={n.name:n for n in old.body if isinstance(n,ast.FunctionDef)}
    for name in ('validate_identity','write_immutable','classify_parameters','compatible_declaration','observe_method','inspect_existing_wrapper','qualify_dependency','load_accepted','load_metadata','load_wrapper','exception_record'):
        assert ast.dump(funcs[name],include_attributes=False)==ast.dump(oldfuncs[name],include_attributes=False)


@pytest.mark.parametrize('fault',['none','changed','return','shape','source_after','session','gateway','original_missing','artifact','runtime','unauthorized','assignment_missing','timeout','nan'])
def test_outer_immutable_receipt_one_exact_call_and_failure_metadata(probe,dependency,method_type,monkeypatch,tmp_path,fault):
    import sys
    from tbdy_engine.etabs import safety
    a,m,w,assignment,hist,hist_identity,pins=originals(probe);model,synthetic_m,synthetic_w,target,ds,calls=synthetic(probe,dependency,method_type)
    # Real dependency/backend qualification is exercised separately; only invocation
    # is replaced here with a SYNTHETIC Python method so no native ctypes callback runs.
    invoked=[];response=[float(v) for v in hist['raw_response'][:-1]]+[1 if fault=='return' else 0]
    if fault=='changed':response[4]=5.;response[5]=6.
    if fault=='shape':response=response[:2]
    if fault=='nan':response[4]=float('nan')
    interface=type(model.PropFrame).__com_interface__
    def fake_read(self,**kw):invoked.append(kw);assert kw=={'Name':'Column_80x80'};return response
    setattr(interface,'GetSectProps',method_type(fake_read))
    def inspection(owner,method,*args):assert owner is model.PropFrame and method=='GetSectProps';return {'SYNTHETIC_INSPECTION_REPLACED_FOR_WRAPPER_ORCHESTRATION':True}
    monkeypatch.setattr(probe,'inspect_existing_wrapper',inspection)
    synthetic_w['wrapper_records'][1]['raw_wrapper_metadata_sha256']=probe.raw_sha({})
    monkeypatch.setattr(probe,'load_assignment',lambda *args:(assignment,pins[3]))
    if fault=='assignment_missing':monkeypatch.setattr(probe,'load_assignment',lambda *args:(_ for _ in ()).throw(FileNotFoundError('SYNTHETIC missing assignment')))
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
        operations.append(operation);assert operation=='r3m_abi5_one_getsectprops_column_80x80' and timeout_seconds==30.
        try:
            if fault=='timeout':raise TimeoutError('SYNTHETIC bounded gateway timeout')
            if fault=='gateway':raise RuntimeError('SYNTHETIC worker original exception')
            return callback(None,model)
        except Exception as cause:raise ETABSCallError('Worker operation failed.',operation=operation,details={'exception_type':type(cause).__name__,'exception_message':str(cause)}) from cause
    monkeypatch.setattr(safety,'attach_verified_to_running_etabs',attach);monkeypatch.setattr(safety,'reread_verified_session_identity',reread);monkeypatch.setattr(safety,'_execute_verified_read',execute)
    monkeypatch.setattr(ctypes,'HRESULT',HRESULT,raising=False);monkeypatch.setitem(sys.modules,'comtypes',SimpleNamespace(BSTR=FakeBSTR,_memberspec=dependency,__version__='WRONG' if fault=='runtime' else '1.4.16'))
    monkeypatch.setitem(sys.modules,'comtypes._post_coinit.instancemethod',SimpleNamespace(PyInstanceMethod_Type=method_type))
    repo=tmp_path/'repo';p=repo/probe.TARGET_PATH;p.parent.mkdir(parents=True);p.write_bytes((Path(os.environ['COLUMN_R1_ABI4_REPO'])/probe.TARGET_PATH).read_bytes())
    out=tmp_path/'out.json';r=probe.run(SimpleNamespace(repo=str(repo),receipt=str(out),pid=2072,expected_head='a'*40,expected_tree='b'*40,
        expected_script_sha='0'*64 if fault=='artifact' else SCRIPT_SHA,candidate_sha256=probe.CANDIDATE_SOURCE_SHA,
        accepted_receipt=pins[0]['path'],metadata_receipt=pins[1]['path'],wrapper_receipt=pins[2]['path'],assignment_receipt=pins[3]['path'],historical_receipt=pins[4]['path'],supervisor_authorized_one_read=fault!='unauthorized'))
    success=fault in {'none','changed'}
    assert r['native_getter_qualified']==success and bool(r['errors'])!=success and json.loads(out.read_text())==r
    assert len(invoked)<=1 and len(operations)<=1 and len(attaches)<=1 and calls==[]
    if success:
        assert invoked==[{'Name':'Column_80x80'}] and r['raw_response_sha256']==probe.raw_sha(response) and r['native_return_code']==0
        assert r['field_comparison']['fields'][4]['comparison']==('DIFFERENT' if fault=='changed' else 'MATCH')
        assert r['call_arguments']['omitted_INOUT']==list(probe.FIELDS)
        assert r['field_comparison']['whole_model_equivalence']=='NOT_PROVEN'
    if fault in {'original_missing','artifact','runtime','gateway','unauthorized','assignment_missing','timeout'}:assert invoked==[]
    if fault=='gateway':assert r['errors'][0]['details']['exception_message']==r['errors'][0]['chain'][0]['message']=='SYNTHETIC worker original exception'
    if fault=='return':assert r['native_return_code']==1 and r['raw_response_sha256']==probe.raw_sha(response)
    assert r['FC09_production_gate']=='UNCHANGED' and r['source_authority_rebound'] is False and r['GLOBAL_DELTA']=='NOT_PROVEN'
    assert r['target_result_getter_invocations']==r['modal_result_rows']==0 and r['matrix_records']==[]
    assert out.with_name(out.name+'.sha256').read_text().split()[0]==realsha(out) and out.stat().st_mode & 0o222==0



@pytest.mark.parametrize('index',range(12))
def test_every_property_requires_exact_float64_without_integer_coercion(probe,index):
    raw=[1.]*12+[0];raw[index]=1
    with pytest.raises(ValueError):probe.validate_property_response(raw)

def test_signed_zero_container_type_hash_preserves_original_bits(probe):
    a={};b={};probe.capture_property_response(a,[-0.]+[1.]*11+[0]);probe.capture_property_response(b,tuple([0.]+[1.]*11+[0]))
    assert a['raw_response_float64_hex'][0]=='-0x0.0p+0' and b['raw_response_float64_hex'][0]=='0x0.0p+0'
    assert a['typed_raw_evidence_sha256']!=b['typed_raw_evidence_sha256']
