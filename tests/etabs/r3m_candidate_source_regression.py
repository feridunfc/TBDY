"""Explicit offline tests for the external current-source probe; no live access."""
import ast
from copy import deepcopy
import hashlib
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from r3m_external_probe_regression import native_owner, synthetic_plan, model, ROTATION

@pytest.fixture(scope="module")
def candidate():
    path = Path(os.environ["COLUMN_R1_R3M_CANDIDATE_PROBE_PATH"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "27362d2fd9c5cbb1d5a9800f4b207d4e6832f057f1cff2982f06500f2089248b"
    spec = importlib.util.spec_from_file_location("candidate_external", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@pytest.mark.parametrize("value", ["61FA288F...246621", "", None, True, "0"*64,
    "FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F"])
def test_abbreviated_wrong_or_historical_source_cannot_be_candidate(candidate, value):
    with pytest.raises(ValueError): candidate.candidate_pin(value)

def test_explicit_full_candidate_is_separate_from_historical_authority(candidate):
    synthetic = "61FA288F"+"0"*50+"246621"
    assert candidate.candidate_pin(synthetic.lower()) == synthetic
    assert candidate.HISTORICAL_SOURCE_SHA.startswith("FC09E5EE")

@pytest.mark.parametrize("missing", [[], ["mass source"], ["loads", "panel zones"]])
def test_matching_observed_subset_never_proves_whole_model_or_rebind(candidate, missing):
    value = candidate.engineering_disposition([{"comparison":"MATCH_EXACT"}],missing)
    assert value["whole_model_equivalence"] == "NOT_PROVEN"
    assert value["engineering_relevant_change"] == "NOT_ESTABLISHED"
    assert value["source_authority_rebound"] is False
    assert value["unobserved_categories"] == sorted(missing)

@pytest.mark.parametrize("key", ["geometry", "section", "element mapping", "frame population"])
def test_observed_engineering_difference_is_reported_with_remaining_gaps(candidate,key):
    value=candidate.engineering_disposition([{"key":key,"comparison":"CHANGED"}],["mass source"])
    assert value["engineering_relevant_change"] == "OBSERVED"
    assert value["unobserved_categories"] == ["mass source"]

@pytest.mark.parametrize("old,new,numeric,expected", [
    ([1.],[1.+1e-13],True,"MATCH_WITHIN_NUMERIC_TOLERANCE"),
    ([1.],[1.01],True,"CHANGED"), (["Base"],["+0.00"],False,"CHANGED"),
    (["1044"],["generated1044"],False,"CHANGED")])
def test_fact_comparison_does_not_hide_physical_changes(candidate,old,new,numeric,expected):
    assert candidate.compare_fact(old,new,numeric=numeric) == expected

@pytest.mark.parametrize("raw", [[1.,1], [1.,True], [float("nan"),0], [1.,0,0], None])
def test_unsuccessful_or_malformed_fact_getters_rejected(candidate,raw):
    owner=native_owner({"GetSection": [(1,"Name"),(2,"PropName"),(2,"pRetVal")]},GetSection=lambda _:raw)
    with pytest.raises((ValueError,TypeError)):
        candidate.native_get(owner,"GetSection",("Name",),("1",),("PropName",),[],"section1")

@pytest.mark.parametrize("method", ["Save","RunAnalysis","StartDesign","SetPresentUnits","SetCaseSelectedForOutput"])
def test_closed_fact_getter_set_rejects_state_changing_methods(candidate,method):
    with pytest.raises(ValueError,match="closed read-only"):
        candidate.native_get(None,method,(),(),(),[],"forbidden")

def test_native_fact_original_raw_hash_and_abi_are_retained(candidate):
    owner=native_owner({"GetSection": [(1,"Name"),(2,"PropName"),(2,"pRetVal")]},GetSection=lambda _:["C80",0])
    records=[]
    assert candidate.native_get(owner,"GetSection",("Name",),("1",),("PropName",),records,"section1") == ["C80"]
    assert records[0]["raw_response"] == ["C80",0]
    assert records[0]["raw_sha256"] == candidate.raw_sha(["C80",0])

def test_identity_manual_match_cannot_discriminate_candidate_direction(candidate):
    assert candidate.compare_hypotheses(candidate.IDENTITY,[.01,.02,.03],6)["discriminating_components"] == []

@pytest.mark.parametrize("complete,integrity", [(False,True),(True,False),(False,False)])
def test_current_source_scan_cannot_close_when_incomplete_or_integrity_failed(candidate,complete,integrity):
    observations=[dict(p,classification="NONIDENTITY") for p in candidate.flatten_plan(synthetic_plan())]
    assert candidate.scan_disposition(observations,complete=complete,integrity=integrity).startswith("NOT_OBSERVED")

def test_candidate_scan_uses_native_element_not_point_object_name(candidate):
    m,calls,_=model(candidate)
    p={"UniqueName":"7","retained_Elm":"native-element-7"}
    records=[]
    candidate.scan_matrices(m,[p],records,lambda:None)
    assert calls == [("matrix","native-element-7")]

def test_external_program_preserves_all_production_and_native_safety_boundaries(candidate):
    text=Path(candidate.__file__).read_text(); tree=ast.parse(text)
    calls={n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)}
    assert not calls & {"Save","RunAnalysis","StartDesign","SetPresentUnits","SetCaseSelectedForOutput",
                        "SetComboSelectedForOutput","GetTableForDisplayArray"}
    assert "allow_pid_fallback=False" in text
    assert "independent candidate source hash drift" in text
    assert "source/session/lock/units drift" in text
    assert '"FC09_production_gate": "UNCHANGED"' in text
    assert "no silent physical-population rebind" in text
    assert "candidate_sha256" in text and "engineering_disposition" in text

def test_no_native_calls_at_module_import(candidate):
    assert not hasattr(candidate,"session")
    assert "operator execution requires Windows" in Path(candidate.__file__).read_text()


def census_model(candidate, *, drift=None):
    plan=synthetic_plan(); endpoints=candidate.flatten_plan(plan)
    names=[c['column_unique_name'] for c in plan['columns']]
    baseline={'frame_population':{'names':names},'section_facts':[{'section_name':'C','raw_response':[1.]*12+[0]}],
        'r0_facts':{'Frame Assignments - Section Properties':{'value':{'parsed':{'rows':[
            {'UniqueName':n,'SectProp':'C'} for n in names]}}}}}
    original={'facts':{'Point Object Connectivity':{'payload':{'parsed':{'rows':[
        {'UniqueName':p['UniqueName'],'X':'1','Y':'2','Z':'3'} for p in endpoints]}}}}}
    def owner(methods):
        return native_owner({k:[(1,n) for n in inputs]+[(2,n) for n in outputs]+[(2,'pRetVal')]
            for k,(inputs,outputs,_) in methods.items()},**{k:v[2] for k,v in methods.items()})
    pairs={c['column_unique_name']:[c['bottom']['UniqueName'],c['top']['UniqueName']] for c in plan['columns']}
    stories={p['UniqueName']:p['Story'] for p in endpoints}
    m=SimpleNamespace(FrameObj=owner({
        'GetNameList':((),('NumberNames','MyName'),lambda:[86,names,0]),
        'GetSection':(('Name',),('PropName','SAuto'),lambda n:['C2' if drift=='section' and n==names[0] else 'C','',0]),
        'GetPoints':(('Name',),('Point1','Point2'),lambda n:[*(list(reversed(pairs[n])) if drift=='connectivity' and n==names[0] else pairs[n]),0])}),
        PropFrame=owner({'GetSectProps':(('Name',),('Area','As2','As3','Torsion','I22','I33','S22','S33','Z22','Z33','R22','R33'),lambda n:[1.]*12+[0])}),
        PointObj=owner({
        'GetLabelFromName':(('Name',),('Label','Story'),lambda n:['L','Other' if drift=='story' and n=='0' else stories[n],0]),
        'GetCoordCartesian':(('Name','CSys'),('X','Y','Z'),lambda n,cs:[9. if drift=='geometry' and n=='0' else 1.,2.,3.,0]),
        'GetElm':(('Name',),('Elm',),lambda n:['current-native-0' if drift=='duplicate' else 'current-native-'+n,0])}))
    return m,baseline,original,plan


def test_full_census_reuses_evidence_without_historical_edb_and_keeps_new_element_identity(candidate):
    m,baseline,original,plan=census_model(candidate); records=[]; comparisons=[]
    points=candidate.reconcile_native(m,baseline,original,plan,records,comparisons,lambda:None)
    assert len(points)==172 and len({p['retained_Elm'] for p in points})==172
    assert points[0]['historical_Elm'] != points[0]['retained_Elm']
    assert any(c['key'].startswith('point_associated_elm') and c['comparison']=='CHANGED' for c in comparisons)
    assert all(r['raw_sha256']==candidate.raw_sha(r['raw_response']) for r in records)
    disposition=candidate.engineering_disposition(comparisons, ['mass source'])
    assert disposition['engineering_relevant_change']=='NOT_ESTABLISHED'
    assert len(disposition['native_binding_name_changes'])==172


@pytest.mark.parametrize('drift',['geometry','story','connectivity','duplicate'])
def test_current_physical_drift_or_duplicate_mapping_stops_population_scan(candidate,drift):
    m,baseline,original,plan=census_model(candidate,drift=drift)
    with pytest.raises(ValueError): candidate.reconcile_native(m,baseline,original,plan,[],[],lambda:None)


def test_section_change_is_reported_without_rebinding_source_or_blocking_read_only_investigation(candidate):
    m,baseline,original,plan=census_model(candidate,drift='section'); comparisons=[]
    points=candidate.reconcile_native(m,baseline,original,plan,[],comparisons,lambda:None)
    assert len(points)==172
    assert candidate.engineering_disposition(comparisons,['mass source'])['engineering_relevant_change']=='OBSERVED'
