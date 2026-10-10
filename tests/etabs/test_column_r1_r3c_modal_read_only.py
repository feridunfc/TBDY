from dataclasses import replace
from types import SimpleNamespace as NS
import ast
import json
import pytest
from tools import column_r1_r3c_modal_read_only as tool
from tbdy_engine.etabs.safety import RuntimeCaptureStatus
from tbdy_engine.etabs.oapi.database_tables import ParsedDisplayTable, DisplayTableFetchResult, decode_table_field_metadata
from tbdy_engine.etabs.oapi.analysis_execution import ResponseSpectrumSettingReadFact as Setting, ResponseSpectrumSettingsFact as Settings
from tbdy_engine.etabs.oapi.eq713_response_results import FrameForceResponseFact, FrameForceResponseRow
from tbdy_engine.etabs.oapi.joint_displacement_results import JointDisplacementResultFact, JointDisplacementResultRow
from test_oapi_material_properties import _Model, _PropMaterial
from tbdy_engine.etabs.safety import read_session_identity
from test_column_r1_r3c_native_settings import RAW
from tbdy_engine.etabs.oapi.analysis_execution import _decode_response_spectrum_setting

@pytest.fixture
def capture(monkeypatch,tmp_path):
    source=tmp_path/'FC09.edb'; source.write_bytes(b'exact offline protected model')
    output=tmp_path/'receipt.json'
    identity=read_session_identity(NS(GetOAPIVersionNumber=lambda:2.014),_Model(_PropMaterial()),process_id=16664,attach_strategy='OFFLINE_FIXTURE')
    identity=replace(identity,model_full_path=str(source))
    closed=[]; calls=[]; tables=[]
    session=NS(identity=identity,_gateway_session=NS(close=lambda:closed.append(True)))
    monkeypatch.setattr(tool,'FC09_SHA256',tool.sha256(source))
    def attach(path,*,pid,allow_pid_fallback):
        calls.append((path,pid,allow_pid_fallback));return session
    monkeypatch.setattr(tool,'attach_verified_to_running_etabs',attach)
    monkeypatch.setattr(tool,'reread_verified_session_identity',lambda s:s.identity)
    monkeypatch.setattr(tool,'create_trusted_live_acquisition_context',lambda s:NS(source_model_identity=NS(source_model_ref='FC09'),session_provenance_ref='session:16664',acquisition_context_ref='capture:1',evidence_epoch_id='factual:1'))
    monkeypatch.setattr(tool,'get_response_spectrum_settings_from_session',lambda s,case_name:
        Settings(case_name,tuple(_decode_response_spectrum_setting(m, ('ActualModal',0) if m=='GetModalCase' else r) for m,r in RAW.items()),'FC09','session:16664','capture:'+case_name,'before','after'))
    metadata=decode_table_field_metadata((1,1,['U1Amp'],['U1Amp'],['source definition'],[''],[False],0),table_name='table')
    monkeypatch.setattr(tool,'fetch_table_field_metadata_from_session',lambda s,t:replace(metadata,table_name=t))
    def table(s,t,preferred_output_case=None):
        tables.append((t,preferred_output_case))
        rows=({'Story':'+0.00','UniqueName':'C1','UniquePtI':'B1','UniquePtJ':'T1'},
              {'Story':'+0.00','UniqueName':'C2','UniquePtI':'T2','UniquePtJ':'B2'}) if t=='Column Object Connectivity' else ({'OutputCase':preferred_output_case,'Mode':1,'U1Amp':.2},)
        return DisplayTableFetchResult(t,ParsedDisplayTable(t,'PARSED',tuple(rows[0]),rows,len(rows),0),capture_status=RuntimeCaptureStatus.FULL,state_diagnostics=({'phase':'restore_verify','success':True},))
    monkeypatch.setattr(tool,'fetch_display_table_from_session',table)
    monkeypatch.setattr(tool,'fetch_display_table_for_output_from_session',table)
    forces=[]; joints=[]
    def force(s,frame_name,case_name):
        forces.append((frame_name,case_name));return FrameForceResponseFact(frame_name,case_name,(FrameForceResponseRow(frame_name,0.,frame_name,0.,case_name,'Mode',1.,-1.,0.,0.,0.,0.,0.),),0)
    def joint(s,point_object,output_name,output_kind):
        joints.append((point_object,output_name));return JointDisplacementResultFact(point_object,output_name,output_kind,(JointDisplacementResultRow(point_object,point_object,output_name,'Mode',1.,.001,0.,0.,0.,0.,0.),),0)
    monkeypatch.setattr(tool,'read_frame_force_response_from_session',force)
    monkeypatch.setattr(tool,'read_joint_displ_from_session',joint)
    return NS(source=source,output=output,session=session,closed=closed,calls=calls,tables=tables,forces=forces,joints=joints)

def run(c): return tool.run_capture(source=c.source,pid=16664,story='+0.00',receipt_path=c.output)

def test_bounded_factual_capture_exact_source_complete_story_actual_modal_dependency_and_no_b5(capture):
    c=capture;r=run(c)
    assert not r['errors'] and r['source_unchanged']
    assert c.calls==[(str(c.source),16664,False)] and c.closed==[True]
    assert r['complete_factual_story_column_count']==2
    assert c.forces==[('C1','ActualModal'),('C2','ActualModal')]
    assert c.joints==[(p,'ActualModal') for p in ('B1','B2','T1','T2')]
    assert not r['current_b5_qualified'] and not r['stability_promotion'] and not r['R2_RERUN_READY']
    assert r['factual_capture_binding']['is_analysis_result_epoch'] is False
    assert r['gate_1']=='PENDING_NATIVE_FIELD_NORMALIZATION_AND_B5_BINDING'
    assert ('Response Spectrum Modal Info','RSX') in c.tables and ('Response Spectrum Modal Info','RSY') in c.tables
    assert all('capture_payload_ref' in f for f in r['facts'].values())
    assert json.loads(c.output.read_text())['source_unchanged']

@pytest.mark.parametrize('defect',['wrong_hash','pid','path','version','units','missing_story','drift','hash_after','missing_metadata','partial','restore'])
def test_precise_failure_never_promotes_stale_or_incomplete_facts(capture,monkeypatch,defect):
    c=capture
    if defect=='wrong_hash': c.source.write_bytes(b'changed')
    elif defect=='pid': c.session.identity=replace(c.session.identity,process_id=99)
    elif defect=='path': c.session.identity=replace(c.session.identity,model_full_path='other.edb')
    elif defect=='version': c.session.identity=replace(c.session.identity,program_version='24')
    elif defect=='units': c.session.identity=replace(c.session.identity,units=replace(c.session.identity.units,database_observation_status='UNIT_UNQUALIFIED'))
    elif defect=='missing_story':
        original=tool.fetch_display_table_from_session
        monkeypatch.setattr(tool,'fetch_display_table_from_session',lambda s,t:replace(original(s,t),parsed=replace(original(s,t).parsed,rows=(),row_count_reported=0)) if t=='Column Object Connectivity' else original(s,t))
    elif defect=='drift':
        original=tool.get_response_spectrum_settings_from_session
        def getter(s,case_name):
            result=original(s,case_name=case_name);s.identity=replace(s.identity,model_full_path='drift.edb');return result
        monkeypatch.setattr(tool,'get_response_spectrum_settings_from_session',getter)
    elif defect=='hash_after':
        original=tool.get_response_spectrum_settings_from_session
        def getter(s,case_name):
            c.source.write_bytes(b'mutated');return original(s,case_name=case_name)
        monkeypatch.setattr(tool,'get_response_spectrum_settings_from_session',getter)
    elif defect=='missing_metadata':
        monkeypatch.setattr(tool,'fetch_table_field_metadata_from_session',lambda s,t:decode_table_field_metadata((1,1,[],[],[],[],[],1),table_name=t))
    else:
        original=tool.fetch_display_table_for_output_from_session
        def getter(s,t,preferred_output_case):
            fact=original(s,t,preferred_output_case=preferred_output_case)
            return replace(fact,capture_status=RuntimeCaptureStatus.PARTIAL) if defect=='partial' else replace(fact,state_diagnostics=())
        monkeypatch.setattr(tool,'fetch_display_table_for_output_from_session',getter)
    r=run(c)
    assert r['status']=='BLOCKED_READ_ONLY_CAPTURE'
    assert not r['current_b5_qualified'] and not r['R2_RERUN_READY']
    if defect!='hash_after': assert r['errors']
    assert c.closed==([] if defect=='wrong_hash' else [True])
    if defect in ('wrong_hash','hash_after'): assert not r['source_unchanged']

@pytest.mark.parametrize('defect',['repo_receipt','existing_receipt','nonpositive_pid'])
def test_refuses_invalid_output_and_attach_arguments_before_read(capture,defect):
    c=capture
    if defect=='repo_receipt': c.output=tool.REPO_ROOT/'receipt.json'
    if defect=='existing_receipt': c.output.write_text('preserve')
    with pytest.raises(ValueError):
        tool.run_capture(source=c.source,pid=0 if defect=='nonpositive_pid' else 16664,story='+0.00',receipt_path=c.output)
    assert c.calls==[]


def test_production_capture_and_native_owner_have_no_analysis_design_save_or_unit_mutation():
    import inspect
    import tbdy_engine.etabs.oapi.analysis_execution as owner
    texts=(Path(tool.__file__).read_text(),inspect.getsource(owner.get_response_spectrum_settings_from_session))
    forbidden={'RunAnalysis','StartDesign','SetPresentUnits','SetPresentUnits_2','Save','SaveAs','SetLoads','SetModalCase','SetEccentricity'}
    for text in texts:
        tree=ast.parse(text)
        assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden for n in ast.walk(tree))

from pathlib import Path

@pytest.mark.parametrize('source',['FrameForce','JointDispl'])
def test_missing_native_modal_rows_fail_closed(capture,monkeypatch,source):
    if source=='FrameForce':
        monkeypatch.setattr(tool,'read_frame_force_response_from_session',lambda s,frame_name,case_name:FrameForceResponseFact(frame_name,case_name,(),0))
    else:
        monkeypatch.setattr(tool,'read_joint_displ_from_session',lambda s,point_object,output_name,output_kind:JointDisplacementResultFact(point_object,output_name,output_kind,(),0))
    result=run(capture)
    assert result['status']=='BLOCKED_READ_ONLY_CAPTURE'
    assert 'signed per-mode' in result['errors'][0]['message']
    assert not result['current_b5_qualified']
