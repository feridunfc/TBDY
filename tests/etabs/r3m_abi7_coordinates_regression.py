"""Offline ABI7 package tests: synthetic Python owners only; no COM target calls."""
import ast
import ctypes
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from etabs_gateway.errors import ETABSCallError
from r3m_abi3_metadata_regression import FakeBSTR, HRESULT
from r3m_abi3_wrapper_regression import dependency, method_type, synthetic_model


@pytest.fixture(scope="module")
def probe():
    p = Path(os.environ["COLUMN_235_ABI7_PROBE"])
    receipt = json.loads((Path(os.environ["COLUMN_R1_ABI4_REPO"]) /
        "docs/COLUMN_235_ABI6_ADOPTION_AND_ABI7_OFFLINE_RECEIPT_2026-10-13.json").read_text())
    assert hashlib.sha256(p.read_bytes()).hexdigest() == receipt["ABI7_offline_proposal"]["external_python_sha256"]
    spec = importlib.util.spec_from_file_location("abi7_offline", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def helper(probe):
    return probe.load_helper(os.environ["COLUMN_R1_ABI6_PROBE"])


def originals(probe, helper):
    paths = [Path(os.environ[n]) for n in ("COLUMN_R1_ABI3_ACCEPTED_RECEIPT",
        "COLUMN_R1_WRAPPER_METADATA_RECEIPT", "COLUMN_R1_ABI4_WRAPPER_RECEIPT",
        "COLUMN_R1_ABI5_ASSIGNMENT_RECEIPT", "COLUMN_R1_ABI6_PROPERTY_RECEIPT", "COLUMN_235_ABI6_ORIGINAL")]
    return paths, probe.load_originals(helper, paths)


def target(probe, helper):
    return probe.load_target(helper, Path(os.environ["COLUMN_R1_ABI4_REPO"]))


def evidence():
    return {"errors": [], "coordinate_records": [], "getter_gateway_invocations": 0,
            "target_getter_invocation_attempts": 0}


def test_original_pair_and_dependencies_survive_adoption_without_native_execution(probe, helper):
    paths, (m, w, g, pins) = originals(probe, helper)
    assert len(pins) == 6 and g["raw_response"] == ["955", "758", 0]
    assert g["bottom_top_assignment"] == "NOT_PROVEN"
    assert all(probe.file_sha(p) == pin["json_sha256"] for p, pin in zip(paths, pins))
    assert m["metadata_records"][4]["numeric_flags"] == [1, 3, 3, 3, 17, 10]
    assert w["wrapper_records"][4]["wrapper_contract"]["backend_vtable_identity"] == "NOT_OBSERVED_NOT_PROBED"


@pytest.mark.parametrize("fault", ["source", "session", "units", "lock", "fingerprint", "names", "container",
    "types", "status", "shape", "raw_hash", "typed_hash", "metadata", "wrapper", "call", "count", "phases", "authority", "time", "head"])
def test_original_drift_cannot_be_rebound_as_current_geometry(probe, helper, fault):
    paths, (m, w, original, _) = originals(probe, helper)
    assignment, prop = (json.loads(paths[i].read_text()) for i in (3, 4))
    g = deepcopy(original)
    if fault == "source": g["source_sha_before"] = "0" * 64
    elif fault == "session": g["identity_after"]["process_id"] = 3000
    elif fault == "units": g["identity_after"]["units"]["present_length_unit"] = 4
    elif fault == "lock": g["identity_before"]["model_locked"] = False
    elif fault == "fingerprint": g["identity_after"]["model_fingerprint"] = "FAKE"
    elif fault == "names": g["raw_response"][0] = "956"
    elif fault == "container": g["native_response_python_type"] = "builtins.tuple"
    elif fault == "types": g["raw_response_scalar_types"][-1] = "builtins.bool"
    elif fault == "status": g["raw_response"][-1] = 1
    elif fault == "shape": g["raw_response"].append(0)
    elif fault == "raw_hash": g["raw_response_sha256"] = "0" * 64
    elif fault == "typed_hash": g["typed_raw_evidence_sha256"] = "0" * 64
    elif fault == "metadata": g["native_metadata"]["declaring_IID"] = "FAKE"
    elif fault == "wrapper": g["current_wrapper_raw_sha256"] = "0" * 64
    elif fault == "call": g["call_arguments"]["positional"] = ["235"]
    elif fault == "count": g["target_getter_invocation_attempts"] = 2
    elif fault == "phases": g["phases"].reverse()
    elif fault == "authority": g["source_authority_rebound"] = True
    elif fault == "time": g["finished_utc"] = g["started_utc"]
    elif fault == "head": g["repository"]["HEAD"] = "0" * 40
    with pytest.raises(ValueError): probe.validate_points_receipt(helper, g, m, w, assignment, prop)


@pytest.mark.parametrize("container", [list, tuple])
def test_coordinates_keep_original_container_types_slot_order_and_signed_values(probe, helper, container):
    raw = container([1.25, 2.5, -5.15, 0])
    e = {}
    value = probe.capture_coordinates(helper, e, raw)
    assert value == {"X": 1.25, "Y": 2.5, "Z": -5.15, "pRetVal": 0}
    assert e["native_response_python_type"] == "builtins." + container.__name__
    assert e["raw_response_sha256"] == helper.raw_sha(raw)
    assert e["raw_response_scalar_types"] == ["builtins.float"] * 3 + ["builtins.int"]
    assert "bottom" not in value and "top" not in value


@pytest.mark.parametrize("raw", [None, [], [1., 2., 3.], [1., 2., 3., 0, 0], [1., 2., 3., 1],
    [1., 2., 3., False], [1., 2., 3., 0.], [1, 2., 3., 0], [1., "2", 3., 0],
    [1., 2., float("nan"), 0], [float("inf"), 2., 3., 0], [1., None, 3., 0]])
def test_invalid_native_response_keeps_partial_raw_evidence_and_fails_closed(probe, helper, raw):
    e = {}
    with pytest.raises(ValueError): probe.capture_coordinates(helper, e, raw)
    assert len(e["raw_response_sha256"]) == len(e["typed_raw_evidence_sha256"]) == 64


@pytest.mark.parametrize("fault", ["name", "order", "csys", "missing_csys", "third", "source", "receipt", "budget", "authorization", "units", "roles"])
def test_two_points_only_no_positional_global_or_fallback_target(probe, helper, fault):
    t = deepcopy(target(probe, helper))
    if fault == "name": t["calls"][0]["Name"] = "SYNTHETIC_OTHER"
    elif fault == "order": t["calls"].reverse()
    elif fault == "csys": t["calls"][0]["CSys"] = "Local"
    elif fault == "missing_csys": del t["calls"][0]["CSys"]
    elif fault == "third": t["calls"].append({"Name": "1044", "CSys": "Global"})
    elif fault == "source": t["source_sha256"] = "0" * 64
    elif fault == "receipt": t["binding_receipt_sha256"] = "0" * 64
    elif fault == "budget": t["maximum_target_attempts"] = 3
    elif fault == "authorization": t["execution_authorized"] = True
    elif fault == "units": t["unit_policy"] = "INFERRED"
    elif fault == "roles": t["bottom_top_assignment"] = "INFERRED"
    with pytest.raises(ValueError): probe.validate_target(t)


def synthetic(probe, helper, dependency, method_type):
    model, m, ds, backends, calls = synthetic_model(helper, dependency, method_type)
    interface = type(model.PointObj).__com_interface__
    interface._iid_ = probe.POINT_IID
    m["metadata_records"][4] = helper.observe_method(model.PointObj, helper.INVENTORY[4], bstr=FakeBSTR, hresult=HRESULT)
    d = ds["GetCoordCartesian"]
    c = helper.compatible_declaration(d, helper.INVENTORY[4], bstr=FakeBSTR, hresult=HRESULT)
    raw = {}
    helper.inspect_existing_wrapper(model.PointObj, "GetCoordCartesian", d, c, dependency, method_type, raw)
    w = {"wrapper_records": [{}, {}, {}, {}, {"raw_wrapper_metadata_sha256": helper.raw_sha(raw)}]}
    return model, m, w, ds, calls


def test_exact_observed_inout_and_optional_global_binding_without_native_backend(probe, helper, dependency, method_type):
    model, m, w, ds, calls = synthetic(probe, helper, dependency, method_type)
    c = helper.compatible_declaration(ds["GetCoordCartesian"], helper.INVENTORY[4], bstr=FakeBSTR, hresult=HRESULT)
    assert helper.construct_named_arguments(c, {"Name": "955", "CSys": "Global"})["omitted_named_INOUT"] == ["X", "Y", "Z"]
    assert c["python_return_sequence"] == ["X", "Y", "Z", "pRetVal"] and calls == []


@pytest.mark.parametrize("fault", ["missing", "ambiguous", "iid", "pointer", "axis_order", "flags", "wrapper_hash", "descriptor"])
def test_exact_abi_and_existing_wrapper_guards_fail_before_any_attempt(probe, helper, dependency, method_type, fault):
    model, m, w, ds, calls = synthetic(probe, helper, dependency, method_type)
    interface = type(model.PointObj).__com_interface__; d = ds["GetCoordCartesian"]
    if fault == "missing": interface._methods_ = [x for x in interface._methods_ if x.name != d.name]
    elif fault == "ambiguous": interface._methods_.append(d)
    elif fault == "iid": interface._iid_ = "{11111111-2222-3333-4444-555555555555}"
    elif fault in ("pointer", "axis_order", "flags"):
        flags = list(d.paramflags); types = list(d.argtypes)
        if fault == "pointer": types[1] = ctypes.POINTER(ctypes.c_float)
        elif fault == "axis_order": flags[1], flags[2] = flags[2], flags[1]
        else: flags[1] = (1, "X")
        changed = d._replace(paramflags=tuple(flags), argtypes=tuple(types))
        interface._methods_ = [changed if x.name == d.name else x for x in interface._methods_]
    elif fault == "wrapper_hash": w["wrapper_records"][4]["raw_wrapper_metadata_sha256"] = "0" * 64
    else: setattr(interface, d.name, property(lambda _: calls.append("UNSAFE")))
    e = evidence()
    with pytest.raises(ValueError): probe.two_coordinates(model, e, helper, m, w, target(probe, helper),
        bstr=FakeBSTR, hresult=HRESULT, memberspec=dependency, instance_method_type=method_type, check_source=lambda: None)
    assert e["target_getter_invocation_attempts"] == 0 and calls == []


@pytest.mark.parametrize("fault", ["none", "first_response", "first_exception", "second_response", "source_before", "source_after_first", "timeout_after_first"])
def test_callback_two_exact_keyword_reads_first_failure_stops_no_retry(probe, helper, dependency, method_type, monkeypatch, fault):
    model, m, w, ds, native_calls = synthetic(probe, helper, dependency, method_type)
    invoked = []; source_checks = []
    # Explicit synthetic Python target, never native ctypes callback execution.
    def fake(self, **kwargs):
        invoked.append(kwargs)
        if fault == "first_exception": raise RuntimeError("SYNTHETIC first native failure")
        bad = fault == "first_response" or fault == "second_response" and len(invoked) == 2
        return [1.25, 2.5, -5.15, 1 if bad else 0]
    setattr(type(model.PointObj).__com_interface__, "GetCoordCartesian", method_type(fake))
    def inspect(owner, method, declaration, classified, dep, mt, raw):
        assert owner is model.PointObj and method == "GetCoordCartesian"
        raw.update(SYNTHETIC_ORCHESTRATION_ONLY=True)
        return {"SYNTHETIC": True}
    monkeypatch.setattr(helper, "inspect_existing_wrapper", inspect)
    w["wrapper_records"][4]["raw_wrapper_metadata_sha256"] = helper.raw_sha({"SYNTHETIC_ORCHESTRATION_ONLY": True})
    def source():
        source_checks.append(None)
        if fault == "source_before" or fault == "source_after_first" and invoked:
            raise ValueError("SYNTHETIC source drift")
    def clock(): return 31.0 if fault == "timeout_after_first" and invoked else 0.0
    e = evidence()
    kw = dict(bstr=FakeBSTR, hresult=HRESULT, memberspec=dependency, instance_method_type=method_type,
              check_source=source, clock=clock)
    if fault == "none": probe.two_coordinates(model, e, helper, m, w, target(probe, helper), **kw)
    else:
        with pytest.raises((ValueError, RuntimeError)): probe.two_coordinates(model, e, helper, m, w, target(probe, helper), **kw)
    expected = 2 if fault in ("none", "second_response") else 0 if fault == "source_before" else 1
    assert len(invoked) == e["target_getter_invocation_attempts"] == expected
    assert invoked == [{"Name": name, "CSys": "Global"} for name in probe.POINT_NAMES[:expected]]
    assert native_calls == []
    with pytest.raises(ValueError): probe.two_coordinates(model, e, helper, m, w, target(probe, helper), **kw)
    assert len(invoked) == expected


def test_original_gateway_error_and_chained_cause_survive_immutable_outer_evidence(probe, helper, tmp_path):
    try:
        try: raise TypeError("SYNTHETIC original exception")
        except TypeError as cause:
            raise ETABSCallError("Worker operation failed.", operation="column235_abi7_two_point_coordinates",
                details={"exception_type": "TypeError", "exception_message": str(cause)}) from cause
    except ETABSCallError as exc:
        e = evidence(); helper.record_failure(e, exc)
    out = tmp_path / "synthetic-failure.json"; helper.write_immutable(out, e)
    original = json.loads(out.read_text())["errors"][0]
    assert original["operation"] == "column235_abi7_two_point_coordinates"
    assert original["details"]["exception_type"] == "TypeError"
    assert original["chain"][0]["message"] == "SYNTHETIC original exception"
    with pytest.raises(FileExistsError): helper.write_immutable(out, e)


def test_external_code_has_only_reviewed_target_and_no_production_or_native_mutation_calls(probe):
    tree = ast.parse(Path(probe.__file__).read_text())
    calls = [n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    forbidden = {"RunAnalysis", "StartDesign", "Save", "SaveAs", "SetPresentUnits", "SetCaseSelectedForOutput",
                 "SetComboSelectedForOutput", "GetPoints", "JointDispl", "GetTransformationMatrix", "QueryInterface"}
    assert not forbidden.intersection(calls)
    source = Path(probe.__file__).read_text()
    assert "allow_pid_fallback=False" in source and "timeout_seconds=30.0" in source
    assert "bound(**plan[\"keyword_arguments\"])" in source


@pytest.mark.parametrize("fault", ["none", "unauthorized", "source_before", "source_after", "units_after", "session_after",
    "lock_after", "wrapper", "gateway", "timeout", "first_response", "second_response", "original_after"])
def test_outer_gateway_and_integrity_failures_preserve_immutable_receipt_without_retry(
        probe, helper, dependency, method_type, monkeypatch, tmp_path, fault):
    from tbdy_engine.etabs import safety
    paths, (m, w, g, pins) = originals(probe, helper)
    invoked = []; callback = []; identities = []; closed = []
    repo = tmp_path / "SYNTHETIC_REPO"; repo.mkdir()
    anchor = {"HEAD": "a" * 40, "TREE": "b" * 40, "worktree_status": ""}
    monkeypatch.setattr(helper, "git_anchor", lambda _: anchor)
    monkeypatch.setattr(probe, "load_helper", lambda _: helper)
    monkeypatch.setattr(probe, "load_originals", lambda *args: (m, w, g, pins))
    t = target(probe, helper); monkeypatch.setattr(probe, "load_target", lambda *args: t)
    monkeypatch.setattr(probe, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(probe, "ctypes", SimpleNamespace(HRESULT=HRESULT))  # Linux synthetic Windows transport type only
    monkeypatch.setattr(probe.sys, "version_info", (3, 14, 0))
    # Fake COM package is only imported after a fake attach. No COM backend exists.
    monkeypatch.setitem(probe.sys.modules, "comtypes", SimpleNamespace(__version__="1.4.16", BSTR=FakeBSTR, _memberspec=dependency))
    monkeypatch.setitem(probe.sys.modules, "comtypes._memberspec", dependency)
    monkeypatch.setitem(probe.sys.modules, "comtypes._post_coinit.instancemethod", SimpleNamespace(PyInstanceMethod_Type=method_type))
    monkeypatch.setattr(helper, "validate_identity", lambda *args: None)  # exact equality boundary tested here
    identity = SimpleNamespace(as_dict=lambda: deepcopy(g["identity_after"]))
    session = SimpleNamespace(identity=identity, capabilities=SimpleNamespace(pid_attach=safety.CapabilityState.SUPPORTED),
                              close=lambda: closed.append(True) or True)
    def attach(*args, **kw):
        assert kw == {"pid": 2072, "allow_pid_fallback": False}
        return session
    monkeypatch.setattr(safety, "attach_verified_to_running_etabs", attach)
    def reread(_):
        d = deepcopy(g["identity_after"]); identities.append(None)
        if invoked:
            if fault == "units_after": d["units"]["present_length_unit"] = 4
            if fault == "session_after": d["process_id"] = 3000
            if fault == "lock_after": d["model_locked"] = False
        return SimpleNamespace(as_dict=lambda: d)
    monkeypatch.setattr(safety, "reread_verified_session_identity", reread)
    realsha = probe.file_sha
    def sha(path):
        if str(path) == helper.SOURCE:
            return "0" * 64 if fault == "source_before" or fault == "source_after" and invoked else helper.CANDIDATE_SOURCE_SHA
        if Path(path) == repo / probe.TARGET_PATH: return probe.TARGET_SHA
        if fault == "original_after" and invoked and Path(path) == paths[-1]: return "0" * 64
        return realsha(path)
    monkeypatch.setattr(probe, "file_sha", sha)
    def fake_two(model, e, h, *args, **kwargs):
        # Orchestration only; native declaration/wrapper guards tested separately.
        assert model is synthetic_model_marker and kwargs["check_source"]
        if fault == "wrapper": raise ValueError("SYNTHETIC wrapper drift")
        e["getter_gateway_invocations"] += 1
        for name in probe.POINT_NAMES:
            invoked.append(name); e["target_getter_invocation_attempts"] += 1
            row = {"Name": name, "phases": ["COORDINATE_RETURNED"]}; e["coordinate_records"].append(row)
            raw = [1., 2., 3., 1 if fault == "first_response" or fault == "second_response" and len(invoked) == 2 else 0]
            probe.capture_coordinates(h, row, raw); kwargs["check_source"]()
            row["phases"].append("COORDINATE_RESPONSE_VALIDATED")
    monkeypatch.setattr(probe, "two_coordinates", fake_two)
    synthetic_model_marker = object()
    def execute(s, cb, **kw):
        assert s is session and kw == {"operation": "column235_abi7_two_point_coordinates", "timeout_seconds": 30.0}
        callback.append(kw)
        if fault in ("gateway", "timeout"):
            cause = TypeError("SYNTHETIC original transport failure")
            error_type = ETABSCallError if fault == "gateway" else __import__("etabs_gateway.errors", fromlist=["ETABSTimeoutError"]).ETABSTimeoutError
            raise error_type("Worker operation failed.", operation=kw["operation"],
                details={"exception_type": "TypeError", "exception_message": str(cause)}) from cause
        cb(None, synthetic_model_marker)
    monkeypatch.setattr(safety, "_execute_verified_read", execute)
    a = SimpleNamespace(repo=str(repo), helper=os.environ["COLUMN_R1_ABI6_PROBE"], receipt=str(tmp_path / "synthetic-new.json"),
        expected_head="a" * 40, expected_tree="b" * 40, expected_script_sha=realsha(probe.__file__),
        pid=2072, candidate_sha256=helper.CANDIDATE_SOURCE_SHA, supervisor_authorized_two_coordinates=fault != "unauthorized")
    for name, path in zip(("accepted_receipt", "metadata_receipt", "wrapper_receipt", "assignment_receipt", "property_receipt", "points_receipt"), paths):
        setattr(a, name, str(path))
    result = probe.run(a)
    assert bool(result["errors"]) is (fault != "none"), result["errors"]
    assert result["native_coordinates_qualified"] is (fault == "none")
    assert len(callback) <= 1 and len(invoked) <= 2
    if fault in ("unauthorized", "source_before", "wrapper", "gateway", "timeout"): assert invoked == []
    if fault in ("first_response", "source_after"): assert invoked == ["955"]
    assert result["bottom_top_assignment"] == result["regulatory_ln"] == "NOT_DERIVED"
    assert result["FC09_production_gate"] == "UNCHANGED" and result["B5"] is result["B6"] is None
    assert result == json.loads(Path(a.receipt).read_text())
    assert Path(a.receipt + ".sha256").read_text().split()[0] == realsha(a.receipt)
    if fault in ("gateway", "timeout"):
        error = result["errors"][0]
        assert error["details"]["exception_type"] == "TypeError" and error["chain"][0]["message"] == "SYNTHETIC original transport failure"
    with pytest.raises(ValueError): probe.run(a)
    assert len(callback) <= 1


def test_windows_checkout_scoped_lf_target_hash_survives_autocrlf_true(probe, tmp_path):
    import subprocess
    repo = Path(os.environ["COLUMN_R1_ABI4_REPO"])
    r = tmp_path / "checkout"; r.mkdir()
    def git(*args): return subprocess.run(["git", "-C", str(r), *args], check=True, capture_output=True)
    git("init", "-q"); git("config", "core.autocrlf", "true")
    (r / ".gitattributes").write_bytes((repo / ".gitattributes").read_bytes())
    p = r / probe.TARGET_PATH; p.parent.mkdir(); p.write_bytes((repo / probe.TARGET_PATH).read_bytes())
    git("add", "."); p.unlink(); git("checkout-index", "--all")
    assert b"\r" not in p.read_bytes() and probe.file_sha(p) == probe.TARGET_SHA
