"""Offline synthetic schema fixtures; never native FC09 results or CSI authority."""
import ast
from dataclasses import replace
import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from tbdy_engine.etabs.oapi import database_tables as owner
from tbdy_engine.etabs import safety
from tools import column_r1_r3k_schema_read_only as tool
from test_oapi_material_properties import _Model, _PropMaterial

ORDER = ("NumberTables", "TableKey", "TableName", "ImportType", "IsEmpty", "pRetVal")
FLAGS = tuple((2 if n != "pRetVal" else 10, n) for n in ORDER)


def available_raw():
    return (2, ["Other Table", tool.TABLE_KEY], ["Other display", "Native display"], [0, 2], [False, True], 0)


class NativeTables:
    _iid_ = "synthetic-cDatabaseTables-iid"
    _methods_ = (NS(name="GetAvailableTables", paramflags=FLAGS),)
    def __init__(self):
        self.calls = []
        self.available = available_raw()
        self.metadata = (7, 3, ["NativeIdentity", "MysteryTranslation", "NativeStep"],
                         ["Name", "Unknown native heading", "Step"],
                         ["Native identity description", "Native direction text", "Native step description"],
                         ["", "native-unit-spelling", ""], [False] * 3, 0)
        self.after_getter = lambda: None
    def GetAvailableTables(self):
        self.calls.append(("GetAvailableTables",)); self.after_getter(); return self.available
    def GetAllFieldsInTable(self, table):
        self.calls.append(("GetAllFieldsInTable", table)); self.after_getter(); return self.metadata
    def __getattr__(self, name):
        raise AssertionError("unexpected native capability: " + name)


def test_generated_available_abi_named_outputs_and_raw_immutability():
    tables = NativeTables(); fact = owner.fetch_available_table_metadata(tables)
    assert fact.status == "PARSED_NATIVE_AVAILABLE_TABLES" and fact.return_code == 0
    assert fact.native_output_order == ORDER and fact.table_keys == ("Other Table", tool.TABLE_KEY)
    tables.available[1][0] = "mutated-after-return"
    assert fact.table_keys[0] == "Other Table" and fact.raw_response[1][0] == "Other Table"
    assert tables.calls == [("GetAvailableTables",)]


def test_available_output_reordering_uses_actual_interface_declaration():
    class Reordered(NativeTables):
        _methods_ = (NS(name="GetAvailableTables", paramflags=tuple(reversed(FLAGS))),)
    tables = Reordered(); tables.available = tuple(reversed(available_raw()))
    fact = owner.fetch_available_table_metadata(tables)
    assert fact.table_keys == ("Other Table", tool.TABLE_KEY) and fact.return_code == 0
    assert fact.native_output_order == tuple(reversed(ORDER))


@pytest.mark.parametrize("defect", ["absent", "missing_spec", "duplicate_spec", "inout", "unknown_name", "missing_iid"])
def test_unqualified_available_interface_never_calls_native(defect):
    class Altered(NativeTables):
        pass
    if defect == "absent": Altered.GetAvailableTables = None
    elif defect == "missing_spec": Altered._methods_ = ()
    elif defect == "duplicate_spec": Altered._methods_ = NativeTables._methods_ * 2
    elif defect == "inout": Altered._methods_ = (NS(name="GetAvailableTables", paramflags=((3, "NumberTables"),) + FLAGS[1:]),)
    elif defect == "unknown_name": Altered._methods_ = (NS(name="GetAvailableTables", paramflags=FLAGS[:-1] + ((10, "OtherReturn"),)),)
    elif defect == "missing_iid": Altered._iid_ = None
    tables = Altered(); fact = owner.fetch_available_table_metadata(tables)
    assert fact.status.startswith(("NOT_OBSERVED:", "UNSUPPORTED")) and tables.calls == []


@pytest.mark.parametrize("defect", ["shape", "false_ret", "float_ret", "nonzero_ret", "count", "length", "duplicate", "blank_key", "bad_name", "import_bool", "empty_int", "exception"])
def test_available_unsuccessful_or_malformed_response_rejected_without_retry(defect):
    tables = NativeTables(); raw = list(available_raw())
    if defect == "shape": raw = raw[:-1]
    elif defect == "false_ret": raw[-1] = False
    elif defect == "float_ret": raw[-1] = 0.0
    elif defect == "nonzero_ret": raw[-1] = 1
    elif defect == "count": raw[0] = True
    elif defect == "length": raw[2] = raw[2][:-1]
    elif defect == "duplicate": raw[1] = [tool.TABLE_KEY] * 2
    elif defect == "blank_key": raw[1][0] = " "
    elif defect == "bad_name": raw[2][0] = 3
    elif defect == "import_bool": raw[3][0] = False
    elif defect == "empty_int": raw[4][0] = 0
    elif defect == "exception": tables.after_getter = lambda: (_ for _ in ()).throw(RuntimeError("native failure"))
    tables.available = tuple(raw)
    fact = owner.fetch_available_table_metadata(tables)
    assert fact.status.startswith("BLOCKED:") and tables.calls == [("GetAvailableTables",)]


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    source = tmp_path / "B-BLOK_Revised.EDB"; source.write_bytes(b"synthetic protected source")
    output = tmp_path / "immutable-evidence.json"
    model = _Model(_PropMaterial()); model.present = 6; model.triplet = (4, 6, 2, 0)
    model.DatabaseTables = tables = NativeTables()
    application = NS(GetOAPIVersionNumber=lambda: 2.014)
    identity = safety.read_session_identity(application, model, process_id=16664, attach_strategy="comtypes_create_helper_get_object_process")
    identity = replace(identity, model_full_path=str(source))
    calls = []; closed = []
    class FakeSession:
        def close(self): closed.append(True); return True
    session = FakeSession(); session.identity = identity
    session.capabilities = NS(pid_attach=safety.CapabilityState.SUPPORTED)
    def attach(path, *, pid, allow_pid_fallback):
        calls.append((path, pid, allow_pid_fallback)); return session
    def gateway_read(s, function, *, operation, timeout_seconds):
        assert s is session and timeout_seconds > 0
        assert operation in {"oapi_database_tables_get_available_tables", "oapi_database_tables_get_all_fields_in_table"}
        return function(application, model)
    monkeypatch.setattr(safety, "EtabsVerifiedSession", FakeSession)
    monkeypatch.setattr(safety, "_execute_verified_read", gateway_read)
    monkeypatch.setattr(tool, "FC09_SOURCE_PATH", str(source))
    monkeypatch.setattr(tool, "FC09_SHA256", tool._file_sha256(source))
    monkeypatch.setattr(tool, "_git_anchor", lambda: {"HEAD": "a" * 40, "TREE": "b" * 40, "worktree_status": ""})
    monkeypatch.setattr(tool, "attach_verified_to_running_etabs", attach)
    monkeypatch.setattr(tool, "reread_verified_session_identity", lambda s: s.identity)
    return NS(source=source, output=output, session=session, tables=tables, calls=calls, closed=closed)


def run(r):
    return tool.run_probe(source=r.source, pid=16664, receipt_path=r.output, expected_head="a" * 40)


def test_probe_schema_only_preserves_unknown_fields_units_and_immutable_raw_receipt(runtime):
    r = runtime; result = run(r)
    assert result["status"] == "SCHEMA_DISCOVERY_COMPLETE_SOURCE_SEMANTICS_NOT_QUALIFIED"
    assert result["errors"] == [] and result["source_unchanged"] and result["session_units_unchanged"]
    assert r.calls == [(str(r.source), 16664, False)] and r.closed == [True]
    assert r.tables.calls == [("GetAvailableTables",), ("GetAllFieldsInTable", tool.TABLE_KEY)]
    assert result["fields"][1] == {"FieldKey": "MysteryTranslation", "FieldName": "Unknown native heading", "Description": "Native direction text", "UnitsString": "native-unit-spelling", "IsImportable": False}
    assert result["table_version"] == 7 and result["NATIVE_TABLE_AVAILABILITY"]["IsEmpty"] is True
    assert result["result_rows_acquired"] == 0 and not result["engineering_interpretation"]
    assert result["GLOBAL_MODAL_DELTA"] == "NOT_PROVEN" and not result["R2_RERUN_READY"]
    raw_hash = result["facts"]["GetAllFieldsInTable"]["raw_response_sha256"]
    assert raw_hash == tool._raw_sha256(r.tables.metadata)
    assert json.loads(r.output.read_text())["facts"]["GetAllFieldsInTable"]["raw_response_sha256"] == raw_hash
    sidecar = r.output.with_name(r.output.name + ".sha256")
    assert sidecar.read_text().split()[0] == hashlib.sha256(r.output.read_bytes()).hexdigest()
    assert r.output.stat().st_mode & 0o222 == 0 and sidecar.stat().st_mode & 0o222 == 0


def test_optional_available_abi_unavailable_does_not_invent_availability(runtime, monkeypatch):
    monkeypatch.setattr(NativeTables, "_methods_", ())
    result = run(runtime)
    assert result["status"] == "SCHEMA_DISCOVERY_COMPLETE_SOURCE_SEMANTICS_NOT_QUALIFIED"
    assert result["NATIVE_TABLE_AVAILABILITY"].startswith("NOT_OBSERVED:")
    assert runtime.tables.calls == [("GetAllFieldsInTable", tool.TABLE_KEY)]


@pytest.mark.parametrize("defect", ["hash", "pid", "path", "version", "units", "unit_return", "unit_scalar_return", "strategy", "pid_capability", "lock", "drift", "unit_drift", "pid_drift", "hash_after", "metadata_shape", "metadata_return", "metadata_length", "duplicate_fields", "empty_fields", "availability_failed", "binding", "close"])
def test_probe_fails_closed_and_preserves_open_gates(runtime, monkeypatch, defect):
    r = runtime
    if defect == "hash": r.source.write_bytes(b"wrong bytes")
    elif defect == "pid": r.session.identity = replace(r.session.identity, process_id=99)
    elif defect == "path": r.session.identity = replace(r.session.identity, model_full_path="other.edb")
    elif defect == "version": r.session.identity = replace(r.session.identity, program_version="24.0")
    elif defect == "units": r.session.identity = replace(r.session.identity, units=replace(r.session.identity.units, database_observation_status="UNIT_UNQUALIFIED"))
    elif defect in ("unit_return", "unit_scalar_return"):
        reads = dict(r.session.identity.units.raw_unit_reads)
        reads["GetPresentUnits_2" if defect == "unit_return" else "GetDatabaseUnits"] = "(4, 6, 2, 1)" if defect == "unit_return" else "(6, 1)"
        r.session.identity = replace(r.session.identity, units=replace(r.session.identity.units, raw_unit_reads=tuple(reads.items())))
    elif defect == "strategy": r.session.identity = replace(r.session.identity, attach_strategy="fallback")
    elif defect == "pid_capability": r.session.capabilities.pid_attach = safety.CapabilityState.UNSUPPORTED
    elif defect == "lock": r.session.identity = replace(r.session.identity, model_locked=None)
    elif defect == "drift": r.tables.after_getter = lambda: setattr(r.session, "identity", replace(r.session.identity, model_full_path="drift.edb"))
    elif defect == "unit_drift": r.tables.after_getter = lambda: setattr(r.session, "identity", replace(r.session.identity, units=replace(r.session.identity.units, present_units=10, present_force_unit=3)))
    elif defect == "pid_drift": r.tables.after_getter = lambda: setattr(r.session, "identity", replace(r.session.identity, process_id=99))
    elif defect == "hash_after": r.tables.after_getter = lambda: r.source.write_bytes(b"changed during read")
    elif defect == "metadata_shape": r.tables.metadata = r.tables.metadata[:-1]
    elif defect == "metadata_return": r.tables.metadata = r.tables.metadata[:-1] + (1,)
    elif defect == "metadata_length": r.tables.metadata[4].pop()
    elif defect == "duplicate_fields": r.tables.metadata[2][1] = r.tables.metadata[2][0]
    elif defect == "empty_fields": r.tables.metadata = (1, 0, [], [], [], [], [], 0)
    elif defect == "availability_failed": r.tables.available = r.tables.available[:-1] + (1,)
    elif defect == "binding":
        original = tool.fetch_table_field_metadata_from_session
        monkeypatch.setattr(tool, "fetch_table_field_metadata_from_session", lambda *a, **kw: replace(original(*a, **kw), capture_ref="other-capture"))
    elif defect == "close": monkeypatch.setattr(r.session, "close", lambda: False)
    result = run(r)
    assert result["status"] == "BLOCKED_SCHEMA_DISCOVERY" and result["errors"]
    assert result["GLOBAL_MODAL_DELTA"] == "NOT_PROVEN" and result["CURRENT_B5"] == "NOT_PROVIDED"
    assert not result["R2_RERUN_READY"] and result["result_rows_acquired"] == 0
    if defect == "hash": assert r.calls == []
    if defect in ("drift", "unit_drift", "pid_drift", "availability_failed"): assert not any(c[0] == "GetAllFieldsInTable" for c in r.tables.calls)


@pytest.mark.parametrize("defect", ["pid_zero", "pid_bool", "other_source", "repo_output", "existing_output", "existing_sidecar", "missing_parent", "head", "dirty"])
def test_operator_preconditions_rejected_before_attachment(runtime, monkeypatch, defect):
    r = runtime; pid = 16664; head = "a" * 40
    if defect == "pid_zero": pid = 0
    elif defect == "pid_bool": pid = True
    elif defect == "other_source": r.source = r.source.parent / "other.edb"; r.source.write_bytes(b"synthetic")
    elif defect == "repo_output": r.output = tool.REPO_ROOT / "prohibited-receipt.json"
    elif defect == "existing_output": r.output.write_text("preserve")
    elif defect == "existing_sidecar": r.output.with_name(r.output.name + ".sha256").write_text("preserve")
    elif defect == "missing_parent": r.output = r.output.parent / "missing" / "receipt.json"
    elif defect == "head": head = "c" * 40
    elif defect == "dirty": monkeypatch.setattr(tool, "_git_anchor", lambda: {"HEAD": head, "TREE": "b" * 40, "worktree_status": "modified"})
    with pytest.raises(ValueError): tool.run_probe(source=r.source, pid=pid, receipt_path=r.output, expected_head=head)
    assert r.calls == [] and r.tables.calls == []


def test_probe_and_new_adapters_have_no_state_mutation_or_result_acquisition():
    functions = (tool, owner.fetch_available_table_metadata, owner.fetch_available_table_metadata_from_session,
                 owner._available_table_native_abi, owner.decode_available_table_metadata,
                 owner.fetch_table_field_metadata, owner.fetch_table_field_metadata_from_session)
    prohibited = {"RunAnalysis", "StartDesign", "Save", "SaveAs", "SetPresentUnits", "SetPresentUnits_2",
                  "GetTableForDisplayArray", "JointDispl", "FrameForce", "SetModelIsLocked", "OpenFile"}
    for f in functions:
        tree = ast.parse(inspect.getsource(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in prohibited and not node.func.attr.startswith("Set")
    text = inspect.getsource(tool)
    assert "allow_pid_fallback=False" in text
    assert "DatabaseTablesReadTransaction" not in text and "modal_mode_range" not in text
