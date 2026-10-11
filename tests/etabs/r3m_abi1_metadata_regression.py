"""Offline ABI-1 regressions; concrete ctypes/comtypes-style declarations, no COM."""
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

SCRIPT_SHA = 'e2b94d5a4b557ae9bdfdcd9db83e42ba60821ebdef7f72e1743ad185048c5e0d'
OUTPUTS = ('NumberNames', 'MyName', 'pRetVal')
CANDIDATE_SHA = '61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621'

class ComMemberSpec(NamedTuple):
    restype: object
    name: str
    argtypes: tuple
    paramflags: object
    idlflags: tuple
    doc: object

class DispMemberSpec(NamedTuple):
    what: str
    name: str
    idlflags: tuple
    restype: object
    argspec: tuple

def spec(flags=None):
    return ComMemberSpec(ctypes.c_long, 'GetNameList', (ctypes.c_void_p,)*3,
        tuple((2,n) for n in OUTPUTS) if flags is None else flags, (), None)

def owner(shape='comtypes', declarations=None):
    interface = type('cFrameObj', (), {'_iid_':'{12345678-1234-1234-1234-123456789ABC}',
        '_methods_': [spec()] if declarations is None else declarations,
        'GetNameList': lambda self: pytest.fail('Native getter must never be called')})
    if shape=='direct': return interface()
    if shape=='ctypes': return type('ExplicitPointer', (), {'_type_':interface})()
    if shape=='inherited':
        interface=type('DerivedFrameObj',(interface,),{'_iid_':'{22345678-1234-1234-1234-123456789ABC}','_methods_':[]})
    # Actual comtypes uses a c_void_p pointer base plus the interface mixin
    # and sets __com_interface__; inherited _type_ is the c_void_p code 'P'.
    base=type('CompointerBase',(ctypes.c_void_p,),{})
    pointer=type(base)('POINTER(cFrameObj)',(interface,base),{'__com_interface__':interface})
    return pointer()

@pytest.fixture(scope='module')
def abi():
    path=Path(os.environ['COLUMN_R1_R3M_ABI1_PROBE_PATH'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==SCRIPT_SHA
    s=importlib.util.spec_from_file_location('r3m_abi1_external',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    return m

@pytest.mark.parametrize('shape',['comtypes','ctypes','direct','inherited'])
def test_exact_method_resolution_without_native_invocation(abi,shape):
    o=owner(shape);report=abi.metadata_snapshot(o);result=abi.generated_abi(o,'GetNameList',(),OUTPUTS)
    assert result['inputs']==[] and result['outputs']==list(OUTPUTS) and result['native_getter_invoked'] is False
    assert len(report['exact_matching_declarations'])==1
    if shape in ('comtypes','inherited'):
        assert type(o)._type_=='P' and report['resolution_path']=='__com_interface__'
        assert not isinstance(type(o)._type_,type)
    if shape=='inherited':assert result['declaring_interface']!=result['interface']

def test_previous_resolver_concrete_pointer_failure_is_reproduced(abi):
    o=owner();interface=getattr(type(o),'_type_',type(o))
    assert interface=='P' and not [m for m in getattr(interface,'_methods_',()) if getattr(m,'name',None)=='GetNameList']
    assert abi.generated_abi(o,'GetNameList',(),OUTPUTS)['resolution_path']=='__com_interface__'

@pytest.mark.parametrize('flags',[None,[],[(True,'NumberNames')],[(2,' NumberNames')],[(2,'')],
    [(3,n) for n in OUTPUTS],[(4,n) for n in OUTPUTS],[(-2,n) for n in OUTPUTS],
    [(34,n) for n in OUTPUTS],[(2,'NumberNames'),(2,'NumberNames'),(2,'pRetVal')],
    [(2,'MyName'),(2,'NumberNames'),(2,'pRetVal')],[(2,'NumberNames'),(2,'MyName')],[(2,'NumberNames',0,1)]])
def test_malformed_flags_and_wrong_exact_order_fail_closed(abi,flags):
    declaration=spec()._replace(paramflags=flags)
    with pytest.raises(ValueError):abi.generated_abi(owner(declarations=[declaration]),'GetNameList',(),OUTPUTS)

@pytest.mark.parametrize('fault',['missing','duplicate','inherited_duplicate','malformed_table','conflicting_interfaces','malformed_link','missing_iid','dispatch_only','vtable_and_dispatch'])
def test_metadata_ambiguity_and_unsupported_representation_fail_closed(abi,fault):
    o=owner();i=type(o).__com_interface__
    if fault=='missing':i._methods_=[]
    if fault=='duplicate':i._methods_=[spec(),spec()]
    if fault=='inherited_duplicate':
        child=type('Child',(i,),{'_methods_':[spec()], '_iid_':i._iid_});type(o).__com_interface__=child
    if fault=='malformed_table':i._methods_={}
    if fault=='conflicting_interfaces':type(o)._type_=type('Wrong',(),{})
    if fault=='malformed_link':type(o).__com_interface__='not-a-class'
    if fault=='missing_iid':i._iid_=None
    if fault in ('dispatch_only','vtable_and_dispatch'):
        i._disp_methods_=[DispMemberSpec('DISPMETHOD','GetNameList',(),ctypes.c_long,())]
        if fault=='dispatch_only':i._methods_=[]
    with pytest.raises(ValueError):abi.generated_abi(o,'GetNameList',(),OUTPUTS)

def test_only_exact_case_and_bounded_getter_are_accepted(abi):
    o=owner(declarations=[spec()._replace(name='getnamelist')])
    with pytest.raises(ValueError):abi.generated_abi(o,'GetNameList',(),OUTPUTS)
    with pytest.raises(ValueError):abi.metadata_snapshot(owner(),'GetPoints')

def test_metadata_inspection_does_not_access_native_callable_or_other_owners(abi):
    calls=[];o=owner()
    def bomb(_):calls.append('GetNameList descriptor');raise AssertionError('Native callable accessed')
    type(o).__com_interface__.GetNameList=property(bomb)
    model=SimpleNamespace(FrameObj=o);retained={}
    assert abi.inspect_frame_metadata(model,retained) is retained
    assert calls==[] and retained['native_return']=='NOT_OBSERVED'
    assert retained['ABI_validation']=='PASS_METADATA_ONLY_LIVE_GETTER_NOT_VALIDATED'
    assert retained['exact_matching_declarations'][0]['paramflags']==[[2,n] for n in OUTPUTS]
    json.dumps(retained,allow_nan=False)

@pytest.mark.parametrize('fault',['valid','abi_failure','source_drift','session_drift'])
def test_outer_metadata_only_gateway_receipt_and_independent_integrity(abi,monkeypatch,tmp_path,fault):
    from tbdy_engine.etabs import safety
    o=owner(declarations=[] if fault=='abi_failure' else None);model=SimpleNamespace(FrameObj=o)
    before=SimpleNamespace(as_dict=lambda:{'synthetic':'OFFLINE_ONLY'})
    after=SimpleNamespace(as_dict=lambda:{'synthetic':'DRIFT' if fault=='session_drift' else 'OFFLINE_ONLY'})
    session=SimpleNamespace(identity=before,capabilities=SimpleNamespace(pid_attach=safety.CapabilityState.SUPPORTED),close=lambda:True)
    repo=tmp_path/'repo';repo.mkdir();receipt=tmp_path/'metadata.json';calls=[];source_reads=[];identity_reads=[]
    real_sha=abi.file_sha;anchor={'HEAD':'a'*40,'TREE':'b'*40,'worktree_status':''}
    def file_sha(p):
        if str(p)==abi.SOURCE:
            source_reads.append(p)
            return '0'*64 if fault=='source_drift' and len(source_reads)>1 else CANDIDATE_SHA
        return real_sha(p)
    def reread(s):
        identity_reads.append(s);return before if len(identity_reads)==1 else after
    def execute(s,callback,*,operation,timeout_seconds):
        calls.append(operation);assert operation=='r3m_abi1_frame_metadata_only' and timeout_seconds==30.
        try:return callback(None,model)
        except Exception as inner:
            raise ETABSCallError('Worker operation failed.',operation=operation,
                details={'exception_type':type(inner).__name__,'exception_message':str(inner)}) from inner
    monkeypatch.setattr(abi,'os',SimpleNamespace(name='nt'));monkeypatch.setattr(abi,'file_sha',file_sha)
    monkeypatch.setattr(abi,'git_anchor',lambda _:anchor);monkeypatch.setattr(abi,'validate_identity',lambda *a:None)
    monkeypatch.setattr(safety,'attach_verified_to_running_etabs',lambda *a,**k:session)
    monkeypatch.setattr(safety,'reread_verified_session_identity',reread);monkeypatch.setattr(safety,'_execute_verified_read',execute)
    args=SimpleNamespace(repo=str(repo),receipt=str(receipt),pid=2072,expected_head='a'*40,expected_tree='b'*40,candidate_sha256=CANDIDATE_SHA)
    result=abi.run(args);assert result==json.loads(receipt.read_text())
    assert calls==['r3m_abi1_frame_metadata_only'] and len(source_reads)==2
    assert not result['native_GetNameList_invoked'] and not result['selection_accessed']
    assert result['native_fact_records']==result['matrix_records']==[]
    assert (not result['errors'])==(fault=='valid')
    if fault=='abi_failure':
        assert result['metadata']['ABI_validation']=='FAIL'
        e=result['errors'][0];assert e['details']['exception_message']==e['chain'][0]['message']
    assert result['FC09_production_gate']=='UNCHANGED' and result['source_authority_rebound'] is False
    assert receipt.with_name(receipt.name+'.sha256').read_text().split()[0]==real_sha(receipt)
    assert receipt.stat().st_mode & 0o222==0

def test_metadata_artifact_has_no_native_method_invocations_and_originals_unchanged(abi):
    tree=ast.parse(Path(abi.__file__).read_text());names={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
    assert not names & {'GetNameList','QueryInterface','cast','RunAnalysis','StartDesign','Save','SetPresentUnits','JointDispl',
        'GetTransformationMatrix','GetTableForDisplayArray','SetCaseSelectedForOutput','SetComboSelectedForOutput'}
    original=Path(os.environ['COLUMN_R1_R3M_DIAG1_PROBE_PATH'])
    assert hashlib.sha256(original.read_bytes()).hexdigest()=='8a55a6d3792066f5acfd68b4c7226c3482b846586f4d4f8d832058a8bdc63df5'
    prior={n.name:ast.dump(n,include_attributes=False) for n in ast.parse(original.read_text()).body if isinstance(n,ast.FunctionDef)}
    new={n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef)}
    for name in ('candidate_pin','validate_identity','git_anchor','exception_record','record_failure','write_immutable'):
        assert prior[name]==new[name]

@pytest.mark.parametrize('fault',['argument_count','return_type','property'])
def test_malformed_type_or_property_declaration_rejected(abi,fault):
    d=spec()
    if fault=='argument_count':d=d._replace(argtypes=())
    if fault=='return_type':d=d._replace(restype=None)
    if fault=='property':d=d._replace(idlflags=('propget',))
    with pytest.raises(ValueError):abi.generated_abi(owner(declarations=[d]),'GetNameList',(),OUTPUTS)

def test_partial_metadata_survives_resolution_failure(abi):
    o=owner();type(o).__com_interface__='malformed';retained={}
    with pytest.raises(ValueError):abi.inspect_frame_metadata(SimpleNamespace(FrameObj=o),retained)
    assert retained['owner_class'].endswith('POINTER(cFrameObj)')
    assert retained['__com_interface__']=='malformed' and retained['ABI_validation']=='FAIL'
    assert retained['ABI_error']['original_exception_message']=='malformed __com_interface__ metadata'
