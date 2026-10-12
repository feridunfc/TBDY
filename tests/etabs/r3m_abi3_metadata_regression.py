"""ABI-3 offline regressions. All COM declarations/backends below are SYNTHETIC.
Original operator evidence is only read and hashed; no ETABS is initialized.
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
from r3m_abi2_inout_regression import _ComMemberSpec, FakeBSTR, memberspec

SCRIPT_SHA = 'b46144d729c0f539fa629752f14a5149905746bc551370f6cc5d1eca5725acc4'
I32 = ctypes.c_int32
HRESULT = ctypes.c_int32

@pytest.fixture(scope='module')
def abi3():
    path = Path(os.environ['COLUMN_R1_ABI3_PROBE_PATH'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SCRIPT_SHA
    spec = importlib.util.spec_from_file_location('abi3_external_offline', path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def declaration(spec, *, ref_flag=3):
    # Synthetic contract projections, not copies of unobserved ETABS metadata.
    def t(kind):
        if kind == 'in_enum_i32': return I32
        if kind.startswith('in_'): return FakeBSTR
        if 'array_' in kind:
            item = FakeBSTR if kind.endswith('bstr') else ctypes.c_double
            array = type('SyntheticSAFEARRAY', (ctypes.Structure,), {'_fields_': []})
            ptr = ctypes.POINTER(array); ptr._itemtype_ = item
            return ctypes.POINTER(ptr)
        scalar = FakeBSTR if 'bstr' in kind else ctypes.c_double if 'double' in kind else I32
        return ctypes.POINTER(scalar)
    flags = tuple((1 if k.startswith('in_') else 10 if k == 'retval_i32' else ref_flag, n)
                  for n, k in spec['parameters'])
    return _ComMemberSpec(HRESULT, spec['method'], tuple(t(k) for _, k in spec['parameters']), flags, (), None)


def owner(abi3, spec, declarations=None, *, representation='link', inherited=False):
    d = declaration(spec)
    iid = abi3.OBSERVED_IID if spec['owner'] == 'FrameObj' else '{11111111-2222-3333-4444-555555555555}'
    def forbidden(*args): raise AssertionError('target method descriptor accessed')
    attrs = {'_iid_': iid, '_methods_': [d] if declarations is None else declarations,
             spec['method']: property(forbidden)}
    base = type(spec['documented_interface'], (), attrs)
    interface = type('SyntheticDerived', (base,), {'_iid_': iid}) if inherited else base
    if representation == 'direct': return interface(), d
    if representation == 'ctype': return ctypes.POINTER(interface), d  # not used: non-ctypes interface
    pointer = type('POINTER('+spec['documented_interface']+')', (), {'__com_interface__': interface})
    return pointer(), d


def model(abi3):
    owners = {}
    for s in abi3.INVENTORY:
        if s['owner'] not in owners:
            attrs = {'_iid_': abi3.OBSERVED_IID if s['owner'] == 'FrameObj' else '{11111111-2222-3333-4444-555555555555}', '_methods_': []}
            cls = type(s['documented_interface'], (), attrs)
            ptr = type('POINTER('+cls.__name__+')', (), {'__com_interface__': cls})
            owners[s['owner']] = ptr()
        cls = type(owners[s['owner']]).__com_interface__
        cls._methods_.append(declaration(s))
        def forbidden(self): raise AssertionError('target descriptor accessed')
        setattr(cls, s['method'], property(forbidden))
    return SimpleNamespace(**owners)

@pytest.mark.parametrize('index', range(8))
@pytest.mark.parametrize('ref_flag', [2, 3])
def test_source_compatible_projections_keep_live_qualification_blocked(abi3, index, ref_flag):
    s = abi3.INVENTORY[index]; d = declaration(s, ref_flag=ref_flag)
    obj, _ = owner(abi3, s, [d])
    r = abi3.observe_method(obj, s, bstr=FakeBSTR, hresult=HRESULT)
    assert 'failure' not in r and r['numeric_flags'] == [x[0] for x in d.paramflags]
    assert r['parameter_names'] == [n for n, _ in s['parameters']]
    assert r['target_invoked'] is False and r['live_getter_qualified'] is False
    assert r['native_return'] == 'NOT_OBSERVED'
    assert r['raw_metadata_sha256'] == abi3.raw_sha(r['raw_metadata'])
    assert r['classified_contract']['native_hresult_in_return_sequence'] is False

@pytest.mark.parametrize('representation', ['link', 'type', 'direct', 'inherited'])
def test_existing_pointer_and_inherited_interface_discovery(abi3, representation):
    s = abi3.INVENTORY[0]; obj, d = owner(abi3, s, inherited=representation == 'inherited',
                                        representation='direct' if representation == 'direct' else 'link')
    if representation == 'type':
        cls = type(obj); cls._type_ = cls.__com_interface__; del cls.__com_interface__
    r = abi3.observe_method(obj, s, bstr=FakeBSTR, hresult=HRESULT)
    assert 'failure' not in r
    assert r['declaring_IID'] == abi3.OBSERVED_IID
    assert r['declaration_table'] == '_methods_'

@pytest.mark.parametrize('fault', ['missing', 'ambiguous', 'inherited_duplicate', 'dispatch_only', 'malformed_table',
    'conflicting_interface', 'bad_iid', 'bad_hresult', 'missing_hresult', 'output_order', 'duplicate_names',
    'wrong_pointer', 'wrong_safearray', 'wrong_bstr', 'wrong_enum', 'missing_retval', 'type_count', 'property'])
def test_malformed_or_ambiguous_metadata_stops_without_target_access(abi3, fault):
    s = abi3.INVENTORY[6 if fault == 'wrong_safearray' else 7 if fault == 'wrong_enum' else 0]
    obj, d = owner(abi3, s); cls = type(obj).__com_interface__
    if fault == 'missing': cls._methods_ = []
    elif fault == 'ambiguous': cls._methods_ = [d, d]
    elif fault == 'inherited_duplicate':
        derived = type('SyntheticInheritedConflict', (cls,), {'_iid_': cls._iid_, '_methods_': [d]})
        type(obj).__com_interface__ = derived
    elif fault == 'dispatch_only': cls._disp_methods_ = cls._methods_; del cls._methods_
    elif fault == 'malformed_table': cls._methods_ = {'wrong': d}
    elif fault == 'conflicting_interface': type(obj)._type_ = type('WrongInterface', (), {})
    elif fault == 'bad_iid': cls._iid_ = 'not-an-iid'
    elif fault == 'bad_hresult': d = d._replace(restype=ctypes.c_double)
    elif fault == 'missing_hresult': d = d._replace(restype=None)
    elif fault == 'output_order': d = d._replace(paramflags=(d.paramflags[0], d.paramflags[2], d.paramflags[1], d.paramflags[3]))
    elif fault == 'duplicate_names': d = d._replace(paramflags=(*d.paramflags[:2], (3, d.paramflags[1][1]), d.paramflags[-1]))
    elif fault == 'wrong_pointer': d = d._replace(argtypes=(d.argtypes[0], ctypes.c_double, *d.argtypes[2:]))
    elif fault == 'wrong_safearray': d = d._replace(argtypes=(d.argtypes[0], ctypes.POINTER(ctypes.POINTER(ctypes.c_double)), d.argtypes[-1]))
    elif fault == 'wrong_bstr': d = d._replace(argtypes=(ctypes.c_wchar_p, *d.argtypes[1:]))
    elif fault == 'wrong_enum': d = d._replace(argtypes=(d.argtypes[0], ctypes.c_double, *d.argtypes[2:]))
    elif fault == 'missing_retval': d = d._replace(paramflags=(*d.paramflags[:-1], (2, 'pRetVal')))
    elif fault == 'type_count': d = d._replace(argtypes=d.argtypes[:-1])
    elif fault == 'property': d = d._replace(idlflags=('propget',))
    if fault in {'bad_hresult','missing_hresult','output_order','duplicate_names','wrong_pointer','wrong_safearray','wrong_bstr','wrong_enum','missing_retval','type_count','property'}: cls._methods_ = [d]
    r = abi3.observe_method(obj, s, bstr=FakeBSTR, hresult=HRESULT)
    assert 'failure' in r and r['target_invoked'] is False
    assert r['raw_metadata_sha256'] == abi3.raw_sha(r['raw_metadata'])
    if fault == 'missing': assert r['failure_kind'] == 'MISSING_DECLARATION'
    if fault in {'ambiguous', 'inherited_duplicate'}: assert r['failure_kind'] == 'AMBIGUOUS_DECLARATIONS'

@pytest.mark.parametrize('flag', [0, 4, 8, 9, 11, -1, True, 32, 64, 19])
def test_unsupported_flag_preserves_original_numeric_value(abi3, flag):
    s = abi3.INVENTORY[0]; d = declaration(s)
    d = d._replace(paramflags=(d.paramflags[0], (flag, 'PropName'), *d.paramflags[2:]))
    obj, _ = owner(abi3, s, [d]); r = abi3.observe_method(obj, s, bstr=FakeBSTR, hresult=HRESULT)
    assert 'failure' in r and r['numeric_flags'][1] == flag


def test_actual_comtypes_dependency_late_input_binding(abi3, memberspec):
    s = abi3.INVENTORY[4]; d = declaration(s)
    c = abi3.compatible_declaration(d, s, bstr=FakeBSTR, hresult=HRESULT)
    assert c['python_return_sequence'] == ['X', 'Y', 'Z', 'pRetVal']
    assert c['python_required_input_names'] == ['Name', 'CSys']
    plan = abi3.construct_named_arguments(c, {'Name': 'SYNTHETIC_POINT', 'CSys': 'Global'})
    assert plan['positional_arguments'] == [] and plan['omitted_named_INOUT'] == ['X', 'Y', 'Z']
    calls = []
    def backend(self, *a, **kw):
        calls.append(kw)
        assert kw['Name'] == 'SYNTHETIC_POINT' and kw['CSys'] == 'Global'
        for n, value in zip(('X','Y','Z'), (1., 2., 3.)): kw[n].value = value
        return [None, None, None, 0]
    wrapped = memberspec.OfflineGenerator()._fix_args(d, backend)
    with pytest.raises((TypeError, ValueError)): wrapped(None, 'SYNTHETIC_POINT', 'Global')
    assert calls == []
    assert wrapped(None, **plan['keyword_arguments']) == [1., 2., 3., 0]
    assert 'BLOCKED' in plan['runtime_bound_wrapper_qualification']
    with pytest.raises(ValueError): abi3.construct_named_arguments(c, {'Name': 'P'})


def test_all_metadata_records_and_one_budget_without_target_calls(abi3):
    e = {'metadata_gateway_invocations': 0, 'phases': [], 'metadata_records': []}
    m = model(abi3); abi3.observe_inventory(m, e, bstr=FakeBSTR, hresult=HRESULT)
    assert len(e['metadata_records']) == 8 and e['metadata_gateway_invocations'] == 1
    assert all(r['target_invoked'] is False and r['native_return'] == 'NOT_OBSERVED' for r in e['metadata_records'])
    with pytest.raises(ValueError): abi3.observe_inventory(m, e, bstr=FakeBSTR, hresult=HRESULT)
    assert len(e['metadata_records']) == 8


def test_bad_method_preserves_all_metadata_and_does_not_retry(abi3):
    m = model(abi3); type(m.PropFrame).__com_interface__._methods_ = []
    e = {'metadata_gateway_invocations': 0, 'phases': [], 'metadata_records': []}
    with pytest.raises(ValueError): abi3.observe_inventory(m, e, bstr=FakeBSTR, hresult=HRESULT)
    assert len(e['metadata_records']) == 8 and e['metadata_records'][1]['failure_kind'] == 'MISSING_DECLARATION'
    assert e['metadata_gateway_invocations'] == 1

@pytest.mark.parametrize('raw', [(['E1', 'E2'], 0), ('E1', 1), ('E1', True), (' E1', 0), ('E1', 0, 0)])
def test_getelm_does_not_choose_one_or_tolerate_invalid_return(abi3, raw):
    with pytest.raises(ValueError): abi3.validate_future_response(abi3.INVENTORY[5], raw)

@pytest.mark.parametrize('raw', [([1,0,0,0,1,0,0,0],0), ([1,0,0,0,1,0,0,0,2],0), ([1,0,0,0,1,0,0,0,-1],0), ([1,0,0,0,1,0,0,0,float('nan')],0)])
def test_matrix_structure_cannot_be_repaired_or_qualified(abi3, raw):
    with pytest.raises(ValueError): abi3.validate_future_response(abi3.INVENTORY[6], raw)

@pytest.mark.parametrize('a', [[1,0,0,0,1,0,0,0,1], [0,-1,0,1,0,0,0,0,1]])
def test_matrix_identity_and_nonidentity_both_leave_layout_direction_blocked(abi3, a):
    r = abi3.validate_future_response(abi3.INVENTORY[6], (a, 0))
    assert r['global_qualified'] is False and r['matrix_layout_direction'] == 'BLOCKED_UNQUALIFIED'


def test_section_axis_provenance_and_endpoint_order(abi3):
    s = abi3.INVENTORY[1]; r = abi3.validate_future_response(s, (*range(12), 0))
    assert r['output_names'][4:6] == ['I22', 'I33'] and r['global_qualified'] is False
    r = abi3.validate_future_response(abi3.INVENTORY[2], ('P_upper', 'P_lower', 0))
    assert r['output_names'] == ['Point1', 'Point2', 'pRetVal']
    with pytest.raises(ValueError): abi3.validate_future_response(abi3.INVENTORY[2], ('P', 'P', 0))

@pytest.mark.parametrize('fault', ['none', 'length', 'ret', 'nested', 'step_type'])
def test_joint_rows_preserved_without_mode_or_global_qualification(abi3, fault):
    raw = [2, ['P','P'], ['E1','E2'], ['LC_DL','LC_DL'], ['Mode','Mode'], [1.,2.]] + [[-1., 2.] for _ in range(6)] + [0]
    if fault == 'length': raw[2] = ['E1']
    if fault == 'ret': raw[-1] = 4
    if fault == 'nested': raw[6] = [[1], [2]]
    if fault == 'step_type': raw[4] = [None, 'Mode']
    if fault == 'none':
        r = abi3.validate_future_response(abi3.INVENTORY[7], raw)
        assert r['global_qualified'] is False and raw[2] == ['E1','E2'] and raw[6] == [-1.,2.]
    else:
        with pytest.raises(ValueError): abi3.validate_future_response(abi3.INVENTORY[7], raw)

@pytest.mark.parametrize('fault', ['none', 'missing', 'modified', 'sidecar'])
def test_original_evidence_required_without_manufacturing_native_responses(abi3, tmp_path, fault):
    original = Path(os.environ['COLUMN_R1_ABI3_ACCEPTED_RECEIPT'])
    before = abi3.file_sha(original)
    if fault == 'none':
        r, pins = abi3.load_accepted(original)
        assert r['validated_frame_count'] == 998 and pins['json_sha256'] == before
    else:
        p = tmp_path/original.name
        if fault != 'missing':
            p.write_bytes(original.read_bytes() + (b' ' if fault == 'modified' else b''))
            side = original.with_name(original.name+'.sha256')
            p.with_name(p.name+'.sha256').write_bytes(side.read_bytes() + (b' ' if fault == 'sidecar' else b''))
        with pytest.raises((ValueError, FileNotFoundError)): abi3.load_accepted(p)
    assert abi3.file_sha(original) == before == abi3.ACCEPTED_SHA

@pytest.mark.parametrize('fault', ['none', 'source', 'session', 'unit', 'lock', 'gateway', 'version', 'script', 'missing_original'])
def test_outer_wrapper_preserves_integrity_failure_and_zero_getter_receipt(abi3, monkeypatch, tmp_path, fault):
    import sys
    from tbdy_engine.etabs import safety
    accepted_path = Path(os.environ['COLUMN_R1_ABI3_ACCEPTED_RECEIPT'])
    accepted, _ = abi3.load_accepted(accepted_path)
    identity_data = accepted['identity_after']; reads=[]; source_reads=[]; operations=[]; attaches=[]
    identity = SimpleNamespace(as_dict=lambda: identity_data)
    session = SimpleNamespace(identity=identity, capabilities=SimpleNamespace(pid_attach=safety.CapabilityState.SUPPORTED), close=lambda: True)
    def reread(_):
        reads.append(1)
        data = dict(identity_data)
        if len(reads)>2 and fault in {'session','unit','lock'}: data[fault+'_DRIFT'] = True
        return SimpleNamespace(as_dict=lambda: data)
    m = model(abi3)
    def execute(s, callback, *, operation, timeout_seconds):
        operations.append(operation); assert s is session and timeout_seconds == 30.
        if fault == 'gateway':
            try: raise ValueError('SYNTHETIC original metadata failure')
            except Exception as inner:
                raise ETABSCallError('Worker operation failed.', operation=operation,
                    details={'exception_type': type(inner).__name__, 'exception_message': str(inner)}) from inner
        return callback(None, m)
    realsha = abi3.file_sha
    def sha(p):
        if str(p) == abi3.SOURCE:
            source_reads.append(1)
            return '0'*64 if fault == 'source' and len(source_reads)>2 else abi3.CANDIDATE_SOURCE_SHA
        return realsha(p)
    def attach(*a, **k):
        attaches.append(k); assert k == {'pid':2072, 'allow_pid_fallback':False}; return session
    anchor = {'HEAD':'a'*40, 'TREE':'b'*40, 'worktree_status':''}
    monkeypatch.setattr(abi3, 'os', SimpleNamespace(name='nt')); monkeypatch.setattr(abi3, 'file_sha', sha)
    monkeypatch.setattr(abi3, 'git_anchor', lambda _:anchor); monkeypatch.setattr(abi3, 'validate_identity', lambda *a:None)
    monkeypatch.setattr(abi3.sys, 'version_info', (3,14,0))
    monkeypatch.setitem(sys.modules, 'comtypes', SimpleNamespace(BSTR=FakeBSTR, __version__='WRONG' if fault=='version' else '1.4.16'))
    monkeypatch.setattr(ctypes, 'HRESULT', HRESULT, raising=False)
    monkeypatch.setattr(safety, 'attach_verified_to_running_etabs', attach)
    monkeypatch.setattr(safety, 'reread_verified_session_identity', reread)
    monkeypatch.setattr(safety, '_execute_verified_read', execute)
    repo = tmp_path/'repo'; repo.mkdir(); out = tmp_path/'receipt.json'
    r = abi3.run(SimpleNamespace(repo=str(repo), receipt=str(out), pid=2072, expected_head='a'*40, expected_tree='b'*40,
        candidate_sha256=abi3.CANDIDATE_SOURCE_SHA, expected_script_sha='0'*64 if fault=='script' else SCRIPT_SHA,
        accepted_receipt=str(tmp_path/accepted_path.name) if fault=='missing_original' else str(accepted_path)))
    assert r == json.loads(out.read_text())
    assert bool(r['errors']) == (fault!='none')
    assert len(operations) <= 1 and len(attaches) <= 1
    assert r['target_factual_getter_invocations'] == r['target_result_getter_invocations'] == r['modal_result_rows'] == 0
    assert r['matrix_records'] == [] and r['source_authority_rebound'] is False and r['FC09_production_gate'] == 'UNCHANGED'
    assert out.with_name(out.name+'.sha256').read_text().split()[0] == realsha(out)
    assert out.stat().st_mode & 0o222 == 0
    if fault=='gateway':
        e = r['errors'][0]; assert e['operation']=='r3m_abi3_remaining_native_metadata'
        assert e['details']['exception_message'] == e['chain'][0]['message'] == 'SYNTHETIC original metadata failure'
    if fault in {'script','missing_original'}: assert attaches == operations == []
    if fault=='none': assert len(r['metadata_records']) == 8 and r['metadata_gateway_invocations'] == 1


def test_static_safety_and_accepted_helpers_are_unchanged(abi3):
    tree = ast.parse(Path(abi3.__file__).read_text())
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    forbidden = {s['method'] for s in abi3.INVENTORY} | {'GetNameList','QueryInterface','cast','Setup','DatabaseTables',
        'RunAnalysis','StartDesign','Save','SaveAs','SetPresentUnits','SetCaseSelectedForOutput','SetComboSelectedForOutput','GetTableForDisplayArray'}
    assert not attributes & forbidden
    old = Path(os.environ['COLUMN_R1_ABI2_ASTFIX_PROBE_PATH'])
    assert hashlib.sha256(old.read_bytes()).hexdigest() == '1738ac0ce9cc97825035311a2c694bea7e503ce207a09e27dd78830c7a4f2753'
    def funcs(t): return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(t).body if isinstance(n,ast.FunctionDef)}
    a,b = funcs(old.read_text()), funcs(Path(abi3.__file__).read_text())
    for n in ('validate_identity','write_immutable','exception_record','classify_parameters','static_class_value'): assert a[n] == b[n]

@pytest.mark.parametrize('fault', ['none', 'pid', 'path', 'version', 'api', 'attach', 'lock', 'unit', 'unit_status', 'unit_ret'])
def test_real_accepted_identity_guard_rejects_each_independent_drift(abi3, fault):
    original = Path(os.environ['COLUMN_R1_ABI3_ACCEPTED_RECEIPT'])
    data = json.loads(original.read_text())['identity_after']
    units = SimpleNamespace(**data.pop('units')); identity = SimpleNamespace(**data, units=units)
    if fault == 'pid': identity.process_id = 2073
    elif fault == 'path': identity.model_full_path = r'C:\tmp\other.EDB'
    elif fault == 'version': identity.program_version = '23.1.0'
    elif fault == 'api': identity.program_api_version = 2.013
    elif fault == 'attach': identity.attach_strategy = 'fallback'
    elif fault == 'lock': identity.model_locked = False
    elif fault == 'unit': units.database_length_unit = 4
    elif fault == 'unit_status': units.present_observation_status = 'UNOBSERVED'
    elif fault == 'unit_ret': units.raw_unit_reads['GetPresentUnits_2'] = '[4,6,2,1]'
    if fault == 'none': abi3.validate_identity(identity, 2072)
    else:
        with pytest.raises(ValueError): abi3.validate_identity(identity, 2072)


def test_raw_declaration_hash_distinguishes_original_flags_and_inherited_declaring_owner(abi3):
    s = abi3.INVENTORY[0]; a, _ = owner(abi3, s, [declaration(s, ref_flag=3)])
    b, _ = owner(abi3, s, [declaration(s, ref_flag=2)], inherited=True)
    ra = abi3.observe_method(a, s, bstr=FakeBSTR, hresult=HRESULT)
    rb = abi3.observe_method(b, s, bstr=FakeBSTR, hresult=HRESULT)
    assert ra['raw_metadata_sha256'] != rb['raw_metadata_sha256']
    assert len(rb['raw_metadata']['interfaces']) > len(ra['raw_metadata']['interfaces'])
    assert rb['raw_metadata']['matching_declarations'][0]['paramflags'][1] == [2, 'PropName']
