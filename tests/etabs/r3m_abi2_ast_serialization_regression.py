"""Offline Python AST serialization repair; no COM initialization or native read."""
import ast
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from r3m_abi2_inout_regression import memberspec, model

SCRIPT_SHA = '1738ac0ce9cc97825035311a2c694bea7e503ce207a09e27dd78830c7a4f2753'
DIAGNOSTIC_SHA = 'c4661b69bdaf3133404d44d104917a288f3912f4e362e3dbd0943570b01a5800'
CPYTHON_SHA = '72d24cbdd65fca15cac9fe57e67d48558e5584ce162b563c60a03ad8b9b5dd90'


@pytest.fixture(scope='module')
def corrected():
    path = Path(os.environ['COLUMN_R1_ABI2_ASTFIX_PROBE_PATH'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SCRIPT_SHA
    spec = importlib.util.spec_from_file_location('abi2_astfix_external', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def observed():
    path = Path(os.environ['COLUMN_R1_ABI2_RUNTIME_DIAGNOSTIC_PATH'])
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == DIAGNOSTIC_SHA
    tokens = Path(str(path) + '.sha256').read_text().strip().split()
    assert tokens == [DIAGNOSTIC_SHA, path.name]
    return json.loads(raw)


@pytest.fixture(scope='module')
def dump314():
    path = Path(os.environ['COLUMN_R1_CPYTHON_314_AST_SOURCE_PATH'])
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == CPYTHON_SHA
    source = raw.decode()
    node = next(n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name == 'dump')
    # Execute only the unchanged official dump function, on offline AST nodes.
    namespace = {'AST': ast.AST}
    exec(compile(ast.get_source_segment(source, node), str(path), 'exec'), namespace)
    return namespace['dump']


def install314(monkeypatch, dump314, node):
    # CPython 3.12 lacks 3.14 _field_types; supply only list metadata for this
    # offline formatter replay. This does not modify the production AST tree.
    for n in ast.walk(node):
        fields = {name: list[ast.AST] for name, value in ast.iter_fields(n)
                  if isinstance(value, list)}
        monkeypatch.setattr(type(n), '_field_types', fields, raising=False)
    monkeypatch.setattr(ast, 'dump', dump314)


def test_original_diagnostic_guards_and_no_target_call(observed):
    assert observed['original_integrity_status'] == 'PASS'
    assert all(observed['original_guard_checks'].values())
    assert observed['original_receipt']['invocation_attempts'] == 0
    assert observed['original_receipt']['phases'] == ['ABI_CHECK_ENTERED']
    assert observed['NATIVE_CALL_EXECUTED'] is False


def test_dependency_source_is_equal_despite_distribution_version(observed):
    source = Path(os.environ['COLUMN_R1_COMTYPES_SOURCE_PATH']).read_text()
    node = next(n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name == '_fix_inout_args')
    assert ast.get_source_segment(source, node) == observed['factory_source']
    assert observed['installed_memberspec_sha256'] == hashlib.sha256(
        Path(os.environ['COLUMN_R1_COMTYPES_SOURCE_PATH']).read_bytes()).hexdigest()
    assert observed['comtypes_distribution_version'] == '1.4.16'


def test_official_314_default_reproduces_original_failure(observed, dump314, monkeypatch):
    node = ast.parse(observed['factory_source']).body[0]
    install314(monkeypatch, dump314, node)
    default = dump314(node, include_attributes=False)
    assert default == observed['factory_AST']
    assert hashlib.sha256(default.encode()).hexdigest() == observed['installed_factory_AST_sha256']
    explicit = dump314(node, include_attributes=False, show_empty=True)
    assert hashlib.sha256(explicit.encode()).hexdigest() == observed['expected_factory_AST_sha256']


@pytest.mark.parametrize('formatter', ['legacy_312', 'official_314'])
def test_exact_wrapper_is_qualified_without_native_invocation(
        corrected, memberspec, observed, dump314, monkeypatch, formatter):
    native, declaration, calls = model(corrected, memberspec)
    if formatter == 'official_314':
        install314(monkeypatch, dump314, ast.parse(observed['factory_source']).body[0])
    result = corrected.qualify_python_wrapper(native.FrameObj.GetNameList, declaration, memberspec)
    assert result['factory_AST_sha256'] == corrected.EXPECTED_INOUT_FACTORY_AST_SHA
    assert result['effective_positional_arguments'] == []
    assert result['effective_keyword_arguments'] == {}
    assert result['returned_order'] == ['NumberNames', 'MyName', 'pRetVal']
    assert calls == []


@pytest.mark.parametrize('formatter', ['legacy_312', 'official_314'])
def test_actual_dependency_wrapper_still_returns_exact_synthetic_tuple(
        corrected, memberspec, observed, dump314, monkeypatch, formatter):
    native, declaration, calls = model(corrected, memberspec)
    if formatter == 'official_314':
        install314(monkeypatch, dump314, ast.parse(observed['factory_source']).body[0])
    corrected.qualify_python_wrapper(native.FrameObj.GetNameList, declaration, memberspec)
    # Synthetic backend only, never ETABS.
    assert native.FrameObj.GetNameList() == [2, ('F1', 'F2'), 0]
    assert calls == [{'args': (), 'kw_names': ['NumberNames', 'MyName']}]


@pytest.mark.parametrize('mutation', ['direction', 'pointee', 'output_order', 'return'])
def test_semantic_changes_still_fail_closed(
        corrected, memberspec, observed, monkeypatch, mutation):
    native, declaration, calls = model(corrected, memberspec)
    source = observed['factory_source']
    old, new = {
        'direction': ('direction & PARAMFLAG_FIN', 'direction & PARAMFLAG_FOUT'),
        'pointee': ('v = atyp()', 'v = None'),
        'output_order': ('rescode[outnum] =', 'rescode[0] ='),
        'return': ('return rescode', 'return None'),
    }[mutation]
    assert old in source
    monkeypatch.setattr(inspect, 'getsource', lambda _: source.replace(old, new))
    with pytest.raises(ValueError, match='implementation not qualified'):
        corrected.qualify_python_wrapper(native.FrameObj.GetNameList, declaration, memberspec)
    assert calls == []


@pytest.mark.parametrize('fault', ['other_callable', 'wrong_closure'])
def test_wrapper_identity_and_closure_checks_preserved(corrected, memberspec, fault):
    native, declaration, calls = model(corrected, memberspec)
    bound = native.FrameObj.GetNameList
    if fault == 'other_callable':
        bound = SimpleNamespace(__func__=lambda: None)
    else:
        declaration = declaration._replace(paramflags=((2, 'NumberNames'), (2, 'MyName'), (10, 'pRetVal')))
    with pytest.raises(ValueError):
        corrected.qualify_python_wrapper(bound, declaration, memberspec)
    assert calls == []


def test_all_other_external_functions_and_native_guards_unchanged(corrected):
    old = Path(os.environ['COLUMN_R1_R3M_ABI2_PROBE_PATH'])
    assert hashlib.sha256(old.read_bytes()).hexdigest() == '3c2ec29d660e6c354ebd7ae534370b24e5c941c35a887821ea5128d8f7e826a3'
    def definitions(path):
        return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(path.read_text()).body
                if isinstance(n, ast.FunctionDef)}
    before, after = definitions(old), definitions(Path(corrected.__file__))
    assert before.keys() == after.keys()
    assert [name for name in before if before[name] != after[name]] == ['qualify_python_wrapper']
    assert corrected.EXPECTED_INOUT_FACTORY_AST_SHA == '5c4668efa8f7b15c312153d246bebbb29c8ccbbfc671515ec18bac12aa8f9e01'
