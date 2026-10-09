"""Offline safety/integrity tests for the operator-only R0/R1 preflight."""
import ast
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from test_native_frame_section_provenance import runtime, acquire
import tbdy_engine.etabs.oapi.frame_section_mechanics as native
from tbdy_engine.etabs.oapi.database_tables import DisplayTableFetchResult, ParsedDisplayTable
from tbdy_engine.etabs.safety import RuntimeCaptureStatus


@pytest.fixture
def tool():
    path = Path(__file__).resolve().parents[2] / "tools/column_r1_r2_live_preflight.py"
    spec = importlib.util.spec_from_file_location("r1_preflight_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def preflight(tool, runtime, monkeypatch, tmp_path):
    session, prop = runtime
    source = tmp_path / "source.edb"
    source.write_bytes(b"OFFLINE_SYNTHETIC_FC09_SUBSTITUTE_NOT_LIVE_AUTHORITY")
    output = tmp_path / "receipt.json"
    monkeypatch.setattr(tool, "FC09_SHA256", tool.sha256(source))
    session.identity = replace(session.identity, model_full_path=str(source))
    original_reader = native.read_session_identity
    def reader(*args, **kwargs):
        return replace(original_reader(*args, **kwargs), model_full_path=str(source))
    monkeypatch.setattr(native, "read_session_identity", reader)
    closed = []
    session.close = lambda: closed.append(True) or True
    monkeypatch.setattr(tool, "reread_verified_session_identity", lambda s: s.identity)
    calls = []
    def attach(path, *, pid, allow_pid_fallback):
        assert path == str(source) and pid == 16664 and allow_pid_fallback is False
        calls.append((path, pid))
        return session
    monkeypatch.setattr(tool, "attach_verified_to_running_etabs", attach)
    monkeypatch.setattr(tool, "git_anchor", lambda: {"HEAD":"offline:head", "TREE":"offline:tree", "worktree_status":""})
    context = NS(source_model_identity=NS(source_model_ref="offline:source"),
                 session_provenance_ref="offline:session", acquisition_context_ref="offline:context",
                 evidence_epoch_id="offline:epoch")
    monkeypatch.setattr(tool, "create_trusted_live_acquisition_context", lambda s: context)
    monkeypatch.setattr(tool, "read_frame_names_from_session", lambda s: (("C1", "C2"), (2, ("C1","C2"), 0)))
    assignments = DisplayTableFetchResult(tool.TABLE_FRAME_ASSIGNMENTS,
        ParsedDisplayTable(tool.TABLE_FRAME_ASSIGNMENTS, "SUCCESS", ("UniqueName","SectProp"),
                           ({"UniqueName":"C1","SectProp":"S"}, {"UniqueName":"C2","SectProp":"S"}), 2, 0),
        capture_status=RuntimeCaptureStatus.FULL)
    def table(s, name, *, max_rows):
        assert max_rows is None
        return assignments if name == tool.TABLE_FRAME_ASSIGNMENTS else replace(assignments, table_name=name,
                    parsed=replace(assignments.parsed, actual_table_name=name))
    monkeypatch.setattr(tool, "fetch_display_table_from_session", table)
    monkeypatch.setattr(tool, "fetch_table_field_metadata_from_session", lambda *args: {"raw":"offline:metadata"})
    monkeypatch.setattr(tool, "read_rebar_column_from_session", lambda *args: {"longitudinal_material":"B420C", "raw": [0]})
    monkeypatch.setattr(tool, "acquire_actual_concrete_design_combo_selection_from_context", lambda **kwargs: {"names":["C"],"complete":True})
    monkeypatch.setattr(tool, "capture_all_etabs_combo_definitions_from_session", lambda s: [{"name":"C","constituents":["G","Q"]}])
    monkeypatch.setattr(tool, "read_load_pattern_names_from_session", lambda s: (("G", "W"), (2,("G","W"),0)))
    monkeypatch.setattr(tool, "read_load_pattern_type_from_session", lambda s,n: {"name":n,"raw":[1,0]})
    monkeypatch.setattr(tool, "read_load_case_names_from_session", lambda s: (("G", "RSX"), (2,("G","RSX"),0)))
    monkeypatch.setattr(tool, "read_load_case_type_from_session", lambda s,n: NS())
    # Use real typed-owner DTOs/serialization; no raw COM or native ETABS runtime.
    from tbdy_engine.etabs.oapi.load_definitions import LoadCaseTypeFact
    monkeypatch.setattr(tool, "read_load_case_type_from_session", lambda s,n:
                        LoadCaseTypeFact(n,1 if n=="G" else 4,0,0,0,0,(1,0,0,0,0,0)))
    monkeypatch.setattr(tool, "read_static_linear_case_from_session", lambda s,n: {"case":n,"raw":[1,["Load"],["G"],[1.],0]})
    return NS(tool=tool, session=session, prop=prop, source=source, output=output,
              calls=calls, closed=closed, assignments=assignments, context=context)


def run(p):
    code = p.tool.run_preflight(source=p.source, pid=16664, receipt_path=p.output)
    return code, json.loads(p.output.read_text())


def test_read_only_preflight_real_native_path_emits_exact_refs_and_factual_r0(preflight, capsys):
    p = preflight
    code, receipt = run(p)
    assert code == 0 and receipt["status"] == "PASS_NATIVE_PENDING_R0_REVIEW"
    assert p.calls == [(str(p.source),16664)] and p.closed == [True]
    assert p.prop.calls == ["S"]  # Shared factual section acquired exactly once.
    assert receipt["source_sha256_before"] == receipt["source_sha256_after"] == p.tool.sha256(p.source)
    assert receipt["identity_before"] == receipt["identity_after"]
    fact = receipt["section_facts"][0]
    assert fact["raw_response"] == list(p.prop.raw)
    assert fact["qualified_L4"] and receipt["successful_native_count"] == 1
    for binding in fact["unit_provenance"]:
        assert binding["source_model_ref"] == str(p.source)
        for key in ("session_ref", "capture_ref", "raw_response_ref"):
            assert binding[key] == fact[key]
    printed = capsys.readouterr().out
    for key in ("source_model_ref", "session_ref", "capture_ref", "raw_response_ref"):
        assert fact[key] in printed
    assert '"program_version": "23.2.0"' in printed and '"API_version": 2.014' in printed
    facts = receipt["r0_facts"]
    for key in ("selected_concrete_design_combos", "all_combo_definitions", "rebar_column:S",
                "load_pattern:W", "load_case:RSX", "static_linear_loads:G"):
        assert facts[key]["status"] == "CAPTURED"
        assert facts[key]["context_refs"] == receipt["r0_context_refs"]
        assert facts[key]["payload_ref"].startswith("preflight-fact:sha256:")
    assert receipt["R2_READY"] is False


@pytest.mark.parametrize("pid", [None,0,-1,True])
def test_exact_pid_required_before_attach(preflight, pid):
    with pytest.raises(ValueError, match="PID"):
        preflight.tool.run_preflight(source=preflight.source,pid=pid,receipt_path=preflight.output)
    assert not preflight.calls and not preflight.output.exists()


def test_receipt_inside_repository_rejected_before_attach(preflight):
    with pytest.raises(ValueError, match="outside"):
        preflight.tool.run_preflight(source=preflight.source,pid=16664,
                                     receipt_path=preflight.tool.REPO_ROOT / "forbidden-receipt.json")
    assert not preflight.calls


def test_existing_receipt_not_overwritten(preflight):
    preflight.output.write_text("preserved")
    with pytest.raises(ValueError, match="new file"):
        run(preflight)
    assert preflight.output.read_text() == "preserved" and not preflight.calls


def test_wrong_physical_source_prevents_attach_and_emits_failure(preflight):
    preflight.source.write_bytes(b"foreign")
    code, receipt = run(preflight)
    assert code == 1 and not preflight.calls
    assert "exact FC09" in str(receipt["errors"])
    assert receipt["source_sha256_after"] == receipt["source_sha256_before"]


def test_attach_failure_still_rehashes_and_records_fact(preflight, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("no exact PID available")
    monkeypatch.setattr(preflight.tool, "attach_verified_to_running_etabs", fail)
    code, receipt = run(preflight)
    assert code == 1 and not preflight.prop.calls
    assert receipt["source_sha256_after"] == receipt["source_sha256_before"]
    assert "no exact PID" in str(receipt["errors"])


@pytest.mark.parametrize("change", ["hash", "identity", "version", "units", "nonzero", "unqualified"])
def test_integrity_or_native_qualification_failure_never_authorizes_r2(preflight, monkeypatch, change):
    p = preflight
    if change == "hash":
        p.prop.after_getter = lambda: p.source.write_bytes(b"changed")
    elif change == "identity":
        p.prop.after_getter = lambda: setattr(p.session,"identity",replace(p.session.identity, process_id=20000))
    elif change == "version":
        p.session.identity = replace(p.session.identity, program_version="24.0.0")
    elif change == "units":
        p.prop.after_getter = lambda: setattr(p.prop.model,"triplet",(4,6,2,0))
    elif change == "nonzero":
        p.prop.raw = (*p.prop.raw[:-1],4)
    else:
        fact = replace(acquire((p.session,p.prop)),unit_provenance=())
        p.prop.calls.clear()
        monkeypatch.setattr(p.tool,"get_frame_section_mechanics_from_session",lambda *args, **kwargs: fact)
    code, receipt = run(p)
    assert code == 1 and receipt["status"] == "FAIL" and receipt["errors"]
    assert receipt["R2_READY"] is False and p.closed == [True]
    if change == "nonzero":
        assert receipt["section_facts"][0]["unit_provenance"] == []


def test_missing_r0_leaf_is_explicit_and_native_proof_is_preserved(preflight, monkeypatch):
    def missing(*args, **kwargs):
        raise RuntimeError("current fact unavailable")
    monkeypatch.setattr(preflight.tool,"acquire_actual_concrete_design_combo_selection_from_context",missing)
    code, receipt = run(preflight)
    assert code == 0 and receipt["successful_native_count"] == 1
    leaf = receipt["r0_facts"]["selected_concrete_design_combos"]
    assert leaf["status"] == "NOT_CAPTURED" and "value" not in leaf
    assert receipt["R2_READY"] is False


@pytest.mark.parametrize("change", ["duplicate", "missing", "partial", "wrong_field"])
def test_incomplete_discovery_never_claims_native_population_proof(preflight, monkeypatch, change):
    p = preflight
    rows = p.assignments.parsed.rows
    if change == "duplicate":
        rows = (rows[0], rows[0])
    elif change == "missing":
        rows = rows[:1]
    elif change == "wrong_field":
        rows = ({"UniqueName":"C1","guessed_section":"S"},rows[1])
    assignments = replace(p.assignments,parsed=replace(p.assignments.parsed,rows=rows),
                          capture_status=RuntimeCaptureStatus.PARTIAL if change=="partial" else RuntimeCaptureStatus.FULL)
    monkeypatch.setattr(p.tool,"fetch_display_table_from_session",lambda *args, **kwargs: assignments)
    code, receipt = run(p)
    assert code == 1 and not p.prop.calls and receipt["section_facts"] == []


def test_tool_has_no_mutating_api_or_raw_gateway_escape(tool):
    tree = ast.parse(Path(tool.__file__).read_text())
    forbidden = {"RunAnalysis","StartDesign","SetPresentUnits","SetPresentUnits_2",
                 "Save","OpenFile","NewBlank","ApplicationStart","ApplicationExit",
                 "_execute_verified_read","fetch_display_table_for_output_from_session"}
    calls = {node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
             for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,(ast.Name,ast.Attribute))}
    assert not calls & forbidden
    assert "attach_verified_to_running_etabs" in calls
