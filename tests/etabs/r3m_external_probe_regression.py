"""Explicit offline suite for the pinned repo-external artifact.

Run with COLUMN_R1_R3M_EXTERNAL_PROBE_PATH. No download, COM or live ETABS.
The filename deliberately requires explicit invocation: CI cannot assume an
operator artifact outside Git exists. Missing/wrong artifact fails, never skips.
"""
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT_SHA = "3531a45013ab57dd6993ead7b1fa71117a690b3a0f22c14c296cced9e1cb391d"


@pytest.fixture(scope="module")
def probe():
    path = Path(os.environ["COLUMN_R1_R3M_EXTERNAL_PROBE_PATH"]).resolve()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == SCRIPT_SHA
    from tools import column_r1_r3l_route_offline as accepted
    assert not path.is_relative_to(Path(accepted.__file__).resolve().parents[1])
    spec = importlib.util.spec_from_file_location("r3m_external_test_artifact", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def native_owner(methods, **values):
    declarations = [SimpleNamespace(name=name, paramflags=flags) for name, flags in methods.items()]
    cls = type("SYNTHETIC_NATIVE_INTERFACE", (), {"_iid_": "SYNTHETIC_ONLY", "_methods_": declarations})
    owner = cls()
    for name, value in values.items():
        setattr(owner, name, value)
    return owner


ROTATION = (0., -1., 0., 1., 0., 0., 0., 0., 1.)


def static_raw(point="1", elm="elm1"):
    return [1, [point], [elm], ["LC_DL"], ["Single Value"], [0.], [.01], [.02], [.03], [0.], [0.], [0.], 0]


def synthetic_plan():
    cols = [{"column_unique_name": "col"+str(i), "column_story": "+0.00",
        "bottom": {"UniqueName": str(i*2), "object_story": "Base", "retained_local_Elm": "elm"+str(i*2)},
        "top": {"UniqueName": str(i*2+1), "object_story": "+0.00", "retained_local_Elm": "elm"+str(i*2+1)}} for i in range(86)]
    return {"column_count": 86, "endpoint_count": 172, "columns": cols,
        "R3D_original_sha256": "SYNTHETIC_NOT_ORIGINAL", "physical_plan_sha256": "SYNTHETIC_ONLY"}


def model(probe, matrix=ROTATION, result=None):
    calls = []
    selection = {"case_flags": [["LC_DL", True]], "combo_flags": [],
        "raw_getters": {"LoadCases.GetNameList": [1, ["LC_DL"], 0], "RespCombo.GetNameList": [0, [], 0],
            "case_flags": [["LC_DL", [True, 0]]], "combo_flags": []}}
    selection["raw_getters_sha256"] = probe.raw_sha(selection["raw_getters"])
    pointelm = native_owner({"GetTransformationMatrix": [(1,"Name"),(2,"Value"),(2,"pRetVal")]},
        GetTransformationMatrix=lambda name: calls.append(("matrix",name)) or [matrix,0])
    results = native_owner({"JointDispl": [(1,"Name"),(17,"ItemTypeElm",0)]+[(2,n) for n in probe.JOINT_OUTPUTS]},
        JointDispl=lambda name,item: calls.append(("static",name,item)) or deepcopy(result if result is not None else static_raw(name,"elm"+name)),
        Setup=SimpleNamespace(GetCaseSelectedForOutput=lambda n:[True,0], GetComboSelectedForOutput=lambda n:[False,0]))
    m = SimpleNamespace(PointElm=pointelm, Results=results,
        LoadCases=SimpleNamespace(GetNameList=lambda:[1,["LC_DL"],0]), RespCombo=SimpleNamespace(GetNameList=lambda:[0,[],0]))
    return m, calls, selection


def test_nonidentity_two_hypotheses_are_separately_calculated(probe):
    p = probe.compare_hypotheses(ROTATION, [.01,.02,.03], 6)
    assert p["hypothesis_T_times_Ulocal"] == pytest.approx([-.02,.01,.03])
    assert p["hypothesis_transposeT_times_Ulocal"] == pytest.approx([.02,-.01,.03])
    assert p["discriminating_components"] == ["X","Y"]
    assert p["coordinate_semantics"].startswith("TWO_UNQUALIFIED")


@pytest.mark.parametrize("matrix,u", [(None,[.01,.02,.03]), (ROTATION,[0.,0.,0.]), (ROTATION,[0.,0.,.03]),
    ((-1.,0.,0.,0.,-1.,0.,0.,0.,1.),[.01,.02,.03])])
def test_identity_zero_symmetric_and_axis_aligned_cannot_discriminate(probe,matrix,u):
    p = probe.compare_hypotheses(probe.IDENTITY if matrix is None else matrix,u,6)
    assert p["discriminating_components"] == []


@pytest.mark.parametrize("places,expected", [(3,False),(4,False),(5,True),(6,True)])
def test_candidates_must_exceed_two_gui_rounding_intervals(probe,places,expected):
    p=probe.compare_hypotheses(ROTATION,[2e-5,1e-5,0.],places)
    assert bool(p["discriminating_components"]) is expected


@pytest.mark.parametrize("raw", [[], [[],0], [[1]*8,0], [[1]*10,0], [list(ROTATION),1], [list(ROTATION),True],
    [[True]+list(ROTATION)[1:],0], [[float("nan")]+list(ROTATION)[1:],0], [[float("inf")]+list(ROTATION)[1:],0],
    [[2.,0.,0.,0.,1.,0.,0.,0.,1.],0], [[-1.,0.,0.,0.,1.,0.,0.,0.,1.],0]])
def test_malformed_or_unsuccessful_matrix_is_rejected(probe,raw):
    with pytest.raises(ValueError): probe.decode_matrix(raw)


@pytest.mark.parametrize("precision", [-1,13,True,1.5])
def test_gui_precision_must_be_explicit_valid_integer(probe,precision):
    with pytest.raises(ValueError): probe.compare_hypotheses(ROTATION,[1.,2.,3.],precision)


@pytest.mark.parametrize("defect", ["return","count","duplicate","length","object","element","case","mode","step","nan","bool"])
def test_static_duplicate_or_wrong_identity_is_rejected(probe,defect):
    r=static_raw()
    if defect=="return": r[-1]=1
    elif defect=="count": r[0]=0
    elif defect=="duplicate": r[0]=2; r[1:-1]=[x*2 for x in r[1:-1]]
    elif defect=="length": r[5].append(0.)
    elif defect=="object": r[1]=["nearest"]
    elif defect=="element": r[2]=["generated-panel-joint"]
    elif defect=="case": r[3]=["Modal"]
    elif defect=="mode": r[4]=["Mode"]
    elif defect=="step": r[5]=[1.]
    elif defect=="nan": r[6]=[float("nan")]
    else: r[6]=[True]
    with pytest.raises(ValueError): probe.decode_static(r,"1","elm1")


@pytest.mark.parametrize("defect", ["extra-case","combo","not-selected","missing-case"])
def test_no_result_call_when_existing_selection_is_not_exact_lc_dl(probe,defect):
    m,calls,s=model(probe)
    if defect=="extra-case": s["case_flags"].append(["other",True])
    elif defect=="combo": s["combo_flags"]=[["combo",True]]
    elif defect=="not-selected": s["case_flags"][0][1]=False
    else: s["case_flags"]=[]
    with pytest.raises(ValueError): probe.acquire_static_candidates(m,[],s,6,lambda:None)
    assert calls==[]


def test_each_matrix_uses_retained_element_not_assumed_object_name(probe):
    m,calls,_=model(probe)
    records=[]
    probe.scan_matrices(m,[{"UniqueName":"1","retained_Elm":"different-actual-element"}],records,lambda:None)
    assert calls==[("matrix","different-actual-element")]
    assert records[0]["classification"]=="NONIDENTITY"
    assert records[0]["raw_response_sha256"]==probe.raw_sha([ROTATION,0])


def test_nonidentity_result_read_has_exact_lc_dl_and_no_table_or_selection_setters(probe):
    m,calls,s=model(probe)
    record={"Story":"+0.00","UniqueName":"1","Column":"col","endpoint":"top","retained_Elm":"elm1"}
    records=[];probe.scan_matrices(m,[record],records,lambda:None)
    probe.acquire_static_candidates(m,records,s,6,lambda:None)
    assert calls==[("matrix","elm1"),("static","1",0)]
    p=probe.choose_operator_point(records)
    assert (p["Story"],p["UniqueName"],p["Case"])==("+0.00","1","LC_DL")
    assert p["global_qualification"]=="NOT_PROVEN" and p["panel_zone_applicability"].startswith("BLOCKED")
    assert p["GUI_exact_filters"]=={"Story":"+0.00","UniqueName":"1","OutputCase":"LC_DL"}
    assert "StepType" not in p and p["JointDispl_StepType"]=="Single Value"


def test_selection_drift_before_call_is_rejected(probe):
    m,calls,s=model(probe);m.Results.Setup.GetCaseSelectedForOutput=lambda n:[False,0]
    with pytest.raises(ValueError,match="drift before"):
        probe.acquire_static_candidates(m,[{"classification":"NONIDENTITY","UniqueName":"1"}],s,6,lambda:None)
    assert calls==[]


def test_selection_drift_after_call_is_rejected(probe):
    m,calls,s=model(probe)
    def read(n,item):
        m.Results.Setup.GetCaseSelectedForOutput=lambda n:[False,0]
        return static_raw()
    m.Results.JointDispl=read
    r={"classification":"NONIDENTITY","UniqueName":"1","retained_Elm":"elm1","flat_nine":ROTATION}
    with pytest.raises(ValueError,match="drift after"): probe.acquire_static_candidates(m,[r],s,6,lambda:None)


@pytest.mark.parametrize("defect", ["missing","inout","order","extra-input","iid"])
def test_generated_abi_must_be_qualified_before_matrix_call(probe,defect):
    m,calls,_=model(probe);owner=m.PointElm
    if defect=="missing": type(owner)._methods_=[]
    elif defect=="iid": type(owner)._iid_=None
    else:
        f=type(owner)._methods_[0].paramflags
        if defect=="inout": f[1]=(3,"Value")
        elif defect=="order": f[1:]=reversed(f[1:])
        else: f.insert(1,(1,"unknown"))
    with pytest.raises(ValueError): probe.scan_matrices(m,[{"retained_Elm":"elm1"}],[],lambda:None)
    assert calls==[]


@pytest.mark.parametrize("defect", ["duplicate-object","duplicate-element","missing","story"])
def test_physical_population_requires_exact_172_bindings(probe,defect):
    plan=synthetic_plan()
    if defect=="duplicate-object": plan["columns"][0]["top"]["UniqueName"]="0"
    elif defect=="duplicate-element": plan["columns"][0]["top"]["retained_local_Elm"]="elm0"
    elif defect=="missing": plan["columns"].pop()
    else: plan["columns"][0]["top"]["object_story"]=""
    with pytest.raises(ValueError): probe.flatten_plan(plan)


def test_both_stories_are_retained_no_plus_zero_endpoint_filter(probe):
    rows=probe.flatten_plan(synthetic_plan())
    assert len(rows)==172 and {r["Story"] for r in rows}=={"Base","+0.00"}


@pytest.mark.parametrize("complete,integrity,n", [(False,True,172),(True,False,172),(True,True,1),(True,True,171)])
def test_not_found_requires_complete_valid_native_population(probe,complete,integrity,n):
    rows=[{"UniqueName":str(i),"classification":"IDENTITY_WITHIN_TOLERANCE"} for i in range(n)]
    assert probe.scan_disposition(rows,complete=complete,integrity=integrity).startswith("NOT_OBSERVED")


def test_complete_identity_scan_not_found_cannot_imply_global_semantics(probe):
    rows=[{"UniqueName":str(i),"classification":"IDENTITY_WITHIN_TOLERANCE"} for i in range(172)]
    assert probe.scan_disposition(rows,complete=True,integrity=True)=="NOT_FOUND"
    assert probe.choose_operator_point(rows) is None


def test_successful_nonidentity_scan_found_is_not_engineering_pass(probe):
    rows=[{"UniqueName":str(i),"classification":"IDENTITY_WITHIN_TOLERANCE"} for i in range(172)]
    rows[0]["classification"]="NONIDENTITY"
    assert probe.scan_disposition(rows,complete=True,integrity=True)=="FOUND"
    assert probe.choose_operator_point(rows) is None  # No LC_DL result/rounding evidence.


def test_no_setters_or_alternate_com_attach_in_external_ast(probe):
    source=Path(probe.__file__).read_text();tree=ast.parse(source)
    calls={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
    forbidden={"RunAnalysis","StartDesign","Save","SetPresentUnits","GetTableForDisplayArray",
        "SetCaseSelectedForOutput","SetComboSelectedForOutput","DeselectAllCasesAndCombosForOutput",
        "SetLoadCasesSelectedForDisplay","SetLoadCombinationsSelectedForDisplay",
        "GetObject","GetActiveObject","GetObjectProcess","CreateObject"}
    assert not calls & forbidden
    assert not any(n.startswith("Set") for n in calls)
    assert "allow_pid_fallback=False" in source and "_execute_verified_read" in source
    assert "ResultsSetupReadTransaction" not in source and "DatabaseTablesReadTransaction" not in source


def test_exclusive_evidence_does_not_overwrite_existing_file(probe,tmp_path):
    p=tmp_path/"receipt.json";p.write_bytes(b"original")
    with pytest.raises(FileExistsError): probe.write_immutable(p,{"synthetic":True})
    assert p.read_bytes()==b"original"


def test_immutable_raw_evidence_and_sidecar_exact_byte_hash(probe,tmp_path):
    p=tmp_path/"receipt.json";probe.write_immutable(p,{"scope":"SYNTHETIC_ONLY"})
    assert p.with_name(p.name+".sha256").read_text()==hashlib.sha256(p.read_bytes()).hexdigest()+"  receipt.json\n"
    assert p.stat().st_mode & 0o222==0


@pytest.mark.parametrize("defect", ["pid","path","lock","units","version","strategy","native-return"])
def test_exact_source_session_and_units_are_mandatory(probe,defect):
    raw={"GetPresentUnits":"6","GetDatabaseUnits":"6","GetPresentUnits_2":"[4,6,2,0]","GetDatabaseUnits_2":"[4,6,2,0]"}
    units=SimpleNamespace(present_units=6,database_units=6,present_force_unit=4,present_length_unit=6,
        present_temperature_unit=2,database_force_unit=4,database_length_unit=6,database_temperature_unit=2,
        present_observation_status="OBSERVED_CONSISTENT",database_observation_status="OBSERVED_CONSISTENT",raw_unit_reads=raw)
    identity=SimpleNamespace(process_id=2072,model_full_path=probe.SOURCE,model_locked=True,units=units,
        program_name="ETABS",program_version="23.2.0",program_api_version=2.014,
        attach_strategy="comtypes_create_helper_get_object_process")
    if defect=="pid": identity.process_id=999
    elif defect=="path": identity.model_full_path=r"C:\other.edb"
    elif defect=="lock": identity.model_locked=False
    elif defect=="units": units.present_length_unit=4
    elif defect=="version": identity.program_version="other"
    elif defect=="strategy": identity.attach_strategy="fallback"
    else: raw["GetPresentUnits_2"]="[4,6,2,1]"
    with pytest.raises(ValueError): probe.validate_identity(identity,2072)


@pytest.mark.parametrize("scenario", ["identity-only","nonidentity","source-drift","session-drift",
    "selection-drift","selection-superset","static-duplicate"])
def test_whole_probe_uses_fake_sta_and_never_promotes_invalid_capture(probe,monkeypatch,tmp_path,scenario):
    from tbdy_engine.etabs import safety
    from tools import column_r1_r3l_route_offline as accepted
    repo=Path(accepted.__file__).resolve().parents[1]
    anchor={"HEAD":"a"*40,"TREE":"b"*40,"worktree_status":""}
    monkeypatch.setattr(probe,"os",SimpleNamespace(name="nt"))
    monkeypatch.setattr(probe,"git_anchor",lambda _:deepcopy(anchor))
    source_reads=[]
    def hash_file(path):
        if str(path)=="manual-synthetic.json": return probe.MANUAL_SHA
        if str(path)==probe.SOURCE:
            source_reads.append(path)
            if scenario=="source-drift" and len(source_reads)>1: return "0"*64
        return probe.SOURCE_SHA.lower()
    monkeypatch.setattr(probe,"file_sha",hash_file)
    monkeypatch.setattr(accepted,"derive_physical_plan",lambda _:synthetic_plan())
    m,calls,_=model(probe,probe.IDENTITY if scenario=="identity-only" else ROTATION)
    if scenario=="static-duplicate":
        def duplicate(n,item):
            r=static_raw(n,"elm"+n);r[0]=2;r[1:-1]=[a*2 for a in r[1:-1]]
            return r
        m.Results.JointDispl=duplicate
    if scenario=="selection-superset":
        m.LoadCases.GetNameList=lambda:[2,["LC_DL","other-selected-static"],0]
    if scenario=="selection-drift":
        flag_reads=[]
        def flag(n):
            flag_reads.append(n)
            return [len(flag_reads)==1,0]
        m.Results.Setup.GetCaseSelectedForOutput=flag
    raw={"GetPresentUnits":"6","GetDatabaseUnits":"6","GetPresentUnits_2":"[4,6,2,0]","GetDatabaseUnits_2":"[4,6,2,0]"}
    units=SimpleNamespace(present_units=6,database_units=6,present_force_unit=4,present_length_unit=6,
        present_temperature_unit=2,database_force_unit=4,database_length_unit=6,database_temperature_unit=2,
        present_observation_status="OBSERVED_CONSISTENT",database_observation_status="OBSERVED_CONSISTENT",raw_unit_reads=raw)
    class FakeIdentity(SimpleNamespace):
        def as_dict(self):
            return {k:deepcopy(vars(v) if k=="units" else v) for k,v in vars(self).items()}
    identity=FakeIdentity(process_id=2072,model_full_path=probe.SOURCE,model_locked=True,units=units,
        program_name="ETABS",program_version="23.2.0",program_api_version=2.014,
        attach_strategy="comtypes_create_helper_get_object_process")
    session=SimpleNamespace(identity=identity,capabilities=SimpleNamespace(pid_attach=safety.CapabilityState.SUPPORTED),close=lambda:True)
    attaches=[]
    def attach(source,*,pid,allow_pid_fallback):
        attaches.append((source,pid,allow_pid_fallback));return session
    monkeypatch.setattr(safety,"attach_verified_to_running_etabs",attach)
    rereads=[]
    def reread(s):
        rereads.append(s)
        value=deepcopy(identity)
        if scenario=="session-drift" and len(rereads)>3:value.process_id=2073
        return value
    monkeypatch.setattr(safety,"reread_verified_session_identity",reread)
    operations=[]
    def execute(s,callback,**kw):
        assert s is session
        operations.append(kw["operation"])
        return callback(None,m)
    monkeypatch.setattr(safety,"_execute_verified_read",execute)
    output=tmp_path/"synthetic-receipt.json"
    result=probe.run(SimpleNamespace(repo=str(repo),receipt=str(output),pid=2072,expected_head=anchor["HEAD"],
        expected_tree=anchor["TREE"],manual_receipt="manual-synthetic.json",r3d_receipt="synthetic-r3d.json",gui_decimal_places=6))
    assert attaches==[(probe.SOURCE,2072,False)]
    assert output.is_file() and result["global_endpoint_modal_rows"]==0
    assert result["GLOBAL_COORDINATE_CONTRACT"]==result["GLOBAL_STORY_DELTA"]=="NOT_PROVEN"
    assert result["R2_RERUN_READY"] is False and result["M6_B"]=="OPEN"
    if scenario=="identity-only":
        assert result["NONIDENTITY_POINT_FOUND"]=="NOT_FOUND" and result["operator_point"] is None
        assert len([x for x in calls if x[0]=="matrix"])==172 and not any(x[0]=="static" for x in calls)
    elif scenario=="nonidentity":
        assert result["NONIDENTITY_POINT_FOUND"]=="FOUND" and result["operator_point"]["Case"]=="LC_DL"
        assert len([x for x in calls if x[0]=="matrix"])==172
    elif scenario=="selection-superset":
        assert result["NONIDENTITY_POINT_FOUND"]=="FOUND" and result["operator_point"] is None
        assert result["candidate_stage"].startswith("BLOCKED_EXISTING_SELECTION")
        assert not any(x[0]=="static" for x in calls)
    else:
        assert result["errors"] and result["NONIDENTITY_POINT_FOUND"].startswith("NOT_OBSERVED")
        assert result["operator_point"] is None
