"""No native calls: source guard for external GetRectangle metadata package."""
import hashlib
import json
import os
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parents[2]
EXPECT = ROOT / 'docs/COLUMN_235_GETRECTANGLE_METADATA_OFFLINE_EXPECTATION_2026-10-14.json'

def fact():
    return json.loads(EXPECT.read_text(encoding='utf-8'))

def test_exact_reviewed_parent_pin():
    d=fact()
    assert d['start_head']=='a16a9865c93c5b64f91f1571247f42088b233e01'
    assert d['start_tree']=='0cc9adef749c231bd656630e63c01bb539467b7b'

def test_source_audit_pin_integrity():
    d=fact();audit=d['audit_source_sha256']
    assert len(audit)==9
    assert all(re.fullmatch('[0-9a-f]{64}',v) for v in audit.values())
    files={n:ROOT/n for n in audit}
    if not all(p.is_file() for p in files.values()):
        pytest.skip('isolated offline fixture lacks complete exact Git source')
    for name,p in files.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest()==audit[name],name

def test_explicitly_unobserved_and_no_live_authority():
    d=fact()
    assert d['status']=='OFFLINE_DERIVED_NO_LIVE'
    assert d['native_declaration']=='PENDING_LIVE'
    assert d['native_getter_attempts']==0
    assert d['live_metadata_authorized'] is False
    assert d['current_235_design_ready'] is False
    assert d['M6_B']=='OPEN'
    assert d['original_abi7']=='CLOSED_REUSE_UNCHANGED'

def test_external_artifact_pins_have_byte_sha256_shape():
    d=fact()
    for k in ('external_python_sha256','external_operator_ps_sha256','external_prepare_ps_sha256','member_spec_sha256','dependency_ast_sha256'):
        assert re.fullmatch('[0-9a-f]{64}',d[k])

def test_pinned_external_scripts_if_explicitly_provided():
    folder=os.environ.get('COLUMN235_GETRECTANGLE_EXTERNAL_DIR')
    if not folder:pytest.skip('external operator package intentionally outside Git')
    d=fact()
    names={'external_python_sha256':'column235_getrectangle_metadata_only.py',
           'external_operator_ps_sha256':'operator_metadata_only.ps1',
           'external_prepare_ps_sha256':'prepare_metadata_only.ps1'}
    for k,n in names.items():
        assert hashlib.sha256((Path(folder)/n).read_bytes()).hexdigest()==d[k]


def test_actual_safety_attach_signature_requires_explicit_model_source():
    import ast
    tree=ast.parse((ROOT/'tbdy_engine/etabs/safety.py').read_text(encoding='utf-8'))
    funcs=[n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)
           and n.name=='attach_verified_to_running_etabs']
    assert len(funcs)==1
    f=funcs[0]
    assert f.args.args[0].arg=='expected_model_full_path'
    assert f.args.defaults==[]
    assert {a.arg for a in f.args.kwonlyargs}>={'pid','allow_pid_fallback'}


def test_external_final_r1_r6_hash_pins():
    d=fact()
    assert d['scope']=='R1_R6_BOUNDED_OFFLINE_OPERATOR_FIX'
    assert d['external_python_sha256']=='ce29772662a3009388f5bdf0b00bd5f62891e9a70797fc952e27c931abdc4756'
    assert d['external_operator_ps_sha256']=='00474d7563f6d6e9d786a316cc4e8fa28786a7e9c4801dd2251da3737827225c'
    assert d['external_prepare_ps_sha256']=='37b11907b21abab99920f807f53c8cb79d9878e11a6442bef815f4c50a03e428'
    assert d['target_native_getters_executed']==0


def test_pinned_external_gateway_invocation_when_bytes_available():
    import ast
    folder=os.environ.get('COLUMN235_GETRECTANGLE_EXTERNAL_DIR')
    if not folder:pytest.skip('External operator intentionally excluded from tracked Git')
    path=Path(folder)/'column235_getrectangle_metadata_only.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==fact()['external_python_sha256']
    tree=ast.parse(path.read_text(encoding='utf-8'))
    functions=[f for f in tree.body if isinstance(f,ast.FunctionDef) and f.name=='run_operator']
    assert len(functions)==1
    calls=[n for n in ast.walk(functions[0]) if isinstance(n,ast.Call)
           and isinstance(n.func,ast.Attribute) and n.func.attr=='attach_verified_to_running_etabs']
    assert len(calls)==1 and len(calls[0].args)==1
    assert isinstance(calls[0].args[0],ast.Name) and calls[0].args[0].id=='SOURCE'


def test_source_authority_not_upgraded_to_native_qualification():
    d=fact()
    assert d['actual_native_metadata']=='NOT_EXECUTED'
    assert d['native_declaration']=='PENDING_LIVE'
    assert d['live_metadata_authorized'] is False
    assert d['m6_b']=='OPEN'
    assert d['regression_profiles']['external_getrectangle_synthetic']==dict(
        total=82,pass=82,fail=0,error=0,skip=0,distinct=82,
        junit_sha256='7946cb313160fe306ab9c0904cc7fcf38078b67527579b64a82cd94385ea31f9')
