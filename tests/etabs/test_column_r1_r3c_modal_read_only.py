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
    model=_Model(_PropMaterial()); model.present=6; model.triplet=(4,6,2,0)
    identity=read_session_identity(NS(GetOAPIVersionNumber=lambda:2.014),model,process_id=16664,attach_strategy='OFFLINE_FIXTURE')
    identity=replace(identity,model_full_path=str(source))
    closed=[]; calls=[]; tables=[]
    session=NS(identity=identity,_gateway_session=NS(close=lambda:closed.append(True)))
    monkeypatch.setattr(tool,'FC09_SHA256',tool.sha256(source))
    monkeypatch.setattr(tool,'FC09_STORY_POPULATION',{'+0.00':(2,4)})
    def attach(path,*,pid,allow_pid_fallback):
        calls.append((path,pid,allow_pid_fallback));return session
    monkeypatch.setattr(tool,'attach_verified_to_running_etabs',attach)
    monkeypatch.setattr(tool,'reread_verified_session_identity',lambda s:s.identity)
    monkeypatch.setattr(tool,'create_trusted_live_acquisition_context',lambda s:NS(source_model_identity=NS(source_model_ref='FC09'),session_provenance_ref='session:16664',acquisition_context_ref='capture:1',evidence_epoch_id='factual:1'))
    def settings(s,case_name):
        outputs=dict(RAW);outputs['GetModalCase']=('ActualModal',0)
        outputs['GetLoads']=(1,['U1' if case_name=='RSX' else 'U2'],['actual-function'],[10.],['Global'],[0.],0)
        return Settings(case_name,tuple(_decode_response_spectrum_setting(m,r) for m,r in outputs.items()),'FC09','session:16664','capture:'+case_name,'before','after')
    monkeypatch.setattr(tool,'get_response_spectrum_settings_from_session',settings)
    def metadata(s,t):
        units={'Response Spectrum Modal Info':{'Mode':'','Period':'sec','U1Amp':'m','U2Amp':'m','U3Amp':'m'},
               'Load Case Definitions - Response Spectrum':{'Name':''},
               'Column Object Connectivity':{'Length':'m'},'Point Object Connectivity':{'X':'m','Y':'m','Z':'m'},
               'Modal Periods And Frequencies':{'Mode':'','Period':'sec'},'Modal Participating Mass Ratios':{'Mode':'','Period':'sec'},
               'Story Forces':{'StepNumber':'','Location':'','VX':'kN','VY':'kN'}}[t]
        keys=list(units)
        return decode_table_field_metadata((1,len(keys),keys,keys,['exact native definition']*len(keys),list(units.values()),[False]*len(keys),0),table_name=t)
    monkeypatch.setattr(tool,'fetch_table_field_metadata_from_session',metadata)
    diagnostics=({'phase':'restore_verify','success':True},{'phase':'temporary_modal_modes','success':True},
                 {'phase':'modal_output_restore_verify','success':True})
    def table(s,t,preferred_output_case=None,modal_mode_range=None):
        tables.append((t,preferred_output_case))
        if t=='Column Object Connectivity':
            rows=({'Story':'+0.00','UniqueName':'C1','UniquePtI':'B1','UniquePtJ':'T1','Length':'3.5'},
                  {'Story':'+0.00','UniqueName':'C2','UniquePtI':'T2','UniquePtJ':'B2','Length':'3.5'})
        elif t=='Point Object Connectivity':
            rows=tuple({'UniqueName':p,'X':'0','Y':'0','Z':'0' if p.startswith('B') else '3.5'} for p in ('B1','B2','T1','T2'))
        elif t=='Response Spectrum Modal Info':
            assert modal_mode_range==(1,100)
            rows=tuple({'SpecCase':preferred_output_case,'ModalCase':'ActualModal','Mode':n,'Period':str(1/n),
                        'U1Amp':-.2,'U2Amp':.3,'U3Amp':0} for n in range(1,101))
        elif t in ('Modal Periods And Frequencies','Modal Participating Mass Ratios'):
            assert modal_mode_range==(1,100)
            rows=tuple({'Case':'ActualModal','Mode':n,'Period':str(1/n)} for n in range(1,101))
        elif t=='Story Forces':
            assert modal_mode_range==(1,100)
            rows=tuple({'OutputCase':'ActualModal','StepType':'Mode','StepNumber':n,'Story':'+0.00','Location':'Bottom','VX':n,'VY':-n} for n in range(1,101))
        else: rows=({'OutputCase':preferred_output_case},)
        return DisplayTableFetchResult(t,ParsedDisplayTable(t,'PARSED',tuple(rows[0]),rows,len(rows),0),capture_status=RuntimeCaptureStatus.FULL,state_diagnostics=diagnostics)
    monkeypatch.setattr(tool,'fetch_display_table_from_session',table)
    monkeypatch.setattr(tool,'fetch_display_table_for_output_from_session',table)
    forces=[]; joints=[]
    def force(s,frame_name,case_name,modal_mode_range=None):
        assert modal_mode_range==(1,100)
        forces.append((frame_name,case_name));return FrameForceResponseFact(frame_name,case_name,tuple(FrameForceResponseRow(frame_name,station,frame_name,station,case_name,'Mode',float(n),-n,0.,0.,0.,0.,0.) for station in (0.,3.5) for n in range(1,101)),0,state_diagnostics=diagnostics)
    def joint(s,point_object,output_name,output_kind,modal_mode_range=None):
        assert modal_mode_range==(1,100)
        joints.append((point_object,output_name));return JointDisplacementResultFact(point_object,output_name,output_kind,tuple(JointDisplacementResultRow(point_object,point_object,output_name,'Mode',float(n),.001*n,0.,0.,0.,0.,0.) for n in range(1,101)),0,state_diagnostics=diagnostics)
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
    assert r['gate_1']=='MODE_POPULATIONS_COMPLETE_NORMALIZATION_AND_B5_BINDING_PENDING'
    assert r['output_state_restored'] is True
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
        def getter(s,t,preferred_output_case,**kwargs):
            fact=original(s,t,preferred_output_case=preferred_output_case,**kwargs)
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
        monkeypatch.setattr(tool,'read_frame_force_response_from_session',lambda s,frame_name,case_name,**kw:FrameForceResponseFact(frame_name,case_name,(),0))
    else:
        monkeypatch.setattr(tool,'read_joint_displ_from_session',lambda s,point_object,output_name,output_kind,**kw:JointDisplacementResultFact(point_object,output_name,output_kind,(),0))
    result=run(capture)
    assert result['status']=='BLOCKED_READ_ONLY_CAPTURE'
    assert 'signed per-mode' in result['errors'][0]['message']
    assert not result['current_b5_qualified']
