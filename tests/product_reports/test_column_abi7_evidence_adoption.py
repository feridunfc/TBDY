"""Deterministic public product regressions for accepted coordinate evidence."""
from copy import deepcopy
import json
from pathlib import Path
from threading import Thread
from urllib.request import Request, urlopen
from io import BytesIO
from hashlib import sha256
import subprocess
import pytest
from pypdf import PdfReader
from apps.column_v2.server import make_server
from tbdy_engine.application.column_235_coordinate_evidence import load_coordinate_adoption,validate_adoption,ORIGINAL_SHA256,ADOPTION_NAME,ADOPTION_SHA256
from tbdy_engine.application.column_product_workspace import validate_packet,evaluate_column_product
from tbdy_engine.product_reports.column_product_report import product_authority,product_manifest,render_product_html,render_product_pdf
from tbdy_engine.product_reports.column_v2_report import column_235_manifest,render_manifest_pdf

REPO=Path(__file__).resolve().parents[2]

@pytest.mark.parametrize('autocrlf',['true','false'])
def test_pinned_coordinate_adoption_bytes_survive_scoped_windows_checkout(tmp_path,autocrlf):
    def git(*args):
        return subprocess.run(['git','-C',str(tmp_path),*args],check=True,capture_output=True,text=True)
    git('init','-q');git('config','core.autocrlf',autocrlf)
    (tmp_path/'.gitattributes').write_bytes((REPO/'.gitattributes').read_bytes())
    target=tmp_path/'docs'/ADOPTION_NAME;target.parent.mkdir()
    target.write_bytes((REPO/'docs'/ADOPTION_NAME).read_bytes())
    other=tmp_path/'unrelated.json';other.write_bytes(b'{"unrelated": true}\n')
    git('add','.');target.unlink();other.unlink()
    git('checkout-index','-u','--all')
    assert sha256(target.read_bytes()).hexdigest()==ADOPTION_SHA256
    assert b'\r' not in target.read_bytes()
    assert other.read_bytes()==(b'{"unrelated": true}\r\n' if autocrlf=='true' else b'{"unrelated": true}\n')
    assert git('diff','--name-only').stdout==''

def test_section_material_next_step_is_metadata_only_with_exact_existing_owner():
    plan=json.loads((REPO/'docs/COLUMN_235_SECTION_MATERIAL_OFFLINE_PLAN_2026-10-14.json').read_text())
    first=plan['first_proposal']
    assert first['method']=='GetRectangle' and first['target_getter_attempts']==0
    assert first['inspection_only'] is True and first['native_abi']=='NOT_OBSERVED'
    assert first['python_call_contract']==first['response_order']=='NOT_QUALIFIED'
    assert 'PropFrame.GetRectangle' not in plan['accepted_metadata_methods']
    assert plan['subject']['section_dimensions'] is plan['subject']['material_name'] is None
    assert not plan['boundaries']['live_metadata_authorized'] and not plan['boundaries']['live_getter_authorized']
    for file,digest in plan['audit_sources_sha256'].items():
        assert sha256((REPO/file).read_bytes()).hexdigest()==digest

def test_exact_source_bound_points_leave_design_inputs_empty():
    a=product_authority(REPO);p=a.packet();validate_packet(p,a)
    assert [(x['native_slot'],x['point_name'],x['Z']) for x in p['accepted_native_coordinates']]==[('Point1','955',-5.15),('Point2','758',0.0)]
    assert all(v is None for v in p['values'].values()) and p['result_epoch'] is None
    assert a.original_pins['coordinates']['json_sha256']==ORIGINAL_SHA256
    result=product_manifest(evaluate_column_product(p,a),a)
    assert not result['real_235_design_ready'] and result['global_delta']=='NOT_PROVEN'
    assert all(c['status']=='BLOCKED' for c in result['checks'])

@pytest.mark.parametrize('fault',['source','unit','slot','role','nonfinite','global','ln'])
def test_derived_authority_or_engineering_promotion_rejected(fault):
    d=load_coordinate_adoption(REPO)
    if fault=='source':d['source']['candidate_sha256']='0'*64
    elif fault=='unit':d['points'][0]['unit']='mm'
    elif fault=='slot':d['points'].reverse()
    elif fault=='role':d['points'][0]['native_slot']='bottom'
    elif fault=='nonfinite':d['points'][0]['Z']=float('inf')
    elif fault=='global':d['qualification_limits']['GLOBAL_DELTA']='PROVEN'
    elif fault=='ln':d['qualification_limits']['regulatory_ln']=5150
    with pytest.raises(ValueError):validate_adoption(d)

def test_client_cannot_overwrite_accepted_point_evidence():
    a=product_authority(REPO);p=a.packet();p['accepted_native_coordinates'][0]['Z']=0.0
    with pytest.raises(ValueError):validate_packet(p,a)
    assert a.packet()['accepted_native_coordinates'][0]['Z']==-5.15

def test_adoption_file_drift_fails_closed(tmp_path):
    (tmp_path/'docs').mkdir();(tmp_path/'docs'/ADOPTION_NAME).write_text('{}')
    with pytest.raises(ValueError):load_coordinate_adoption(tmp_path)

def test_current_evidence_pdf_and_product_exports_keep_same_points_and_limits():
    m=column_235_manifest(REPO);a=product_authority(REPO);r=product_manifest(evaluate_column_product(a.packet(),a),a)
    assert r['native_evidence']['current_point_coordinates']==m['current_point_coordinates']
    for pdf in (render_manifest_pdf(m),render_product_pdf(r)):
        text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
        assert all(t in text for t in ('955','758','74.0','22.3','-5.15','Global','ABI7',ORIGINAL_SHA256))
    h=render_product_html(r);assert '955' in h and '-5.15' in h and 'ln değildir' in h

def test_actual_http_context_and_export_use_accepted_observation_without_calculation():
    server=make_server(REPO,0);t=Thread(target=server.serve_forever,daemon=True);t.start()
    def post(route,body):
        q=Request(f'http://127.0.0.1:{server.server_port}/api/'+route,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
        with urlopen(q,timeout=10) as r:return json.loads(r.read())
    try:
        w=post('workspace',{})
        s=post('state',{'workspace_id':w['id'],'context':'235','bundle':None})
        m=post('report',{'workspace_id':w['id'],'revision':s['revision'],'result_id':None,'format':'json'})
        assert m==s['evidence'] and m['coordinate_provenance']['whole_json_sha256']==ORIGINAL_SHA256
        assert m['calculations']==[] and m['GLOBAL_DELTA']=='NOT_PROVEN'
        assert not any(e['event'].endswith('ENGINE_ENTERED') for e in server.application.events)
    finally:server.shutdown();server.server_close();t.join(5)
