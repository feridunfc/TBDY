"""Numeric reference, source separation and real local backend regressions."""
from dataclasses import replace
from io import BytesIO
from pathlib import Path
import json
import threading
from urllib.request import Request, urlopen
import pytest
from pypdf import PdfReader
from tbdy_engine.application import column_reference_workspace as owner
from tbdy_engine.application.column_reference_workspace import ReferenceColumnInput, calculate_reference, REFERENCE_ID
from tbdy_engine.product_reports.column_v2_report import reference_manifest, column_235_manifest, render_reference_pdf
from apps.column_v2.server import ColumnWorkspace, make_server
REPO = Path(__file__).resolve().parents[2]

@pytest.fixture(scope='module')
def calculation(): return calculate_reference(ReferenceColumnInput().bundle())
@pytest.fixture(scope='module')
def changed(): return calculate_reference(replace(ReferenceColumnInput(), width_mm=800.0).bundle())

def test_regression_minimum_eccentricity_signed_moments(calculation):
    # Existing independent test_vs6_minimum_eccentricity: -39e6 / +30e6 N.mm.
    assert {(s.m2_nmm,s.m3_nmm) for s in calculation.engine_result.minimum_eccentricity.states} == {(-39000000.0,30000000.0)}
    assert calculation.engine_result.minimum_eccentricity.resolved

def test_regression_rectangular_radius_and_braced_limit(calculation):
    # Existing test_vs6_slenderness: h=800, ln=3000 -> i=240, lambda=12.5, limit=34.
    a=calculation.engine_result.slenderness.m2
    assert (a.radius_of_gyration_i_mm,a.effective_length_lk_mm,a.slenderness_ratio_lk_over_i,a.neglect_limit)==(240.0,3000.0,12.5,34.0)

def test_edit_width_uses_existing_independent_800mm_expectation(calculation,changed):
    assert calculation.engine_result.slenderness.m3.slenderness_ratio_lk_over_i==20.0
    assert changed.engine_result.slenderness.m3.slenderness_ratio_lk_over_i==12.5
    assert changed.engine_result.minimum_eccentricity.adjustments[0].required_abs_m3_nmm==39000000.0
    assert changed.changed_fields==('width_mm',)
    assert changed.input_sha256!=calculation.input_sha256
    assert changed.engine_result.rebar_design.selection.governing_utilization!=calculation.engine_result.rebar_design.selection.governing_utilization

def test_existing_engine_actually_called_once(monkeypatch):
    calls=[]; original=owner.evaluate_column_design
    def observe(**kwargs): calls.append(kwargs); return original(**kwargs)
    monkeypatch.setattr(owner,'evaluate_column_design',observe)
    actual=calculate_reference(ReferenceColumnInput().bundle())
    assert len(calls)==1 and actual.engine_result.status=='SELECTED_DESIGN_CANDIDATE_ONLY'
    assert calls[0]['component_id']==REFERENCE_ID
    assert 'EXPLICIT_REFERENCE_INPUT_NOT_ETABS' in calls[0]['constituent_case_demands'][0].source_identity

def test_capacity_ratio_is_actual_typed_evaluation_not_limit_ratio(calculation):
    selection=calculation.engine_result.rebar_design.selection;m=reference_manifest(calculation)
    g=next(e for e in selection.selected_evaluations if e.state.state_id==selection.governing_state_id)
    assert m['checks'][-1]['value']==g.utilization==pytest.approx(g.state.moment_magnitude_nmm/g.radial_capacity_nmm)
    assert selection.authority=='DESIGN_CANDIDATE_ONLY' and m['production_promotion'] is False

@pytest.mark.parametrize('key,value', [('width_mm',None),('nd_kn',True),('fcd_mpa',float('nan')),('fyd_mpa',0),('depth_mm',-1),('free_length_mm','3000'),('moment_ratio_m2',1.01),('k_m3',0),('fck_mpa',33),('clear_cover_mm',0),('aggregate_max_mm',float('inf'))])
def test_invalid_typed_inputs_no_fallback(key,value):
    b=ReferenceColumnInput().bundle();b['values'][key]=value
    with pytest.raises((ValueError,TypeError)): calculate_reference(b)

@pytest.mark.parametrize('alteration', ['missing','extra','units','source','context','bars_duplicate','bars_string','bars_empty','bars_bool'])
def test_bundle_units_source_and_catalog_rejection(alteration):
    b=ReferenceColumnInput().bundle()
    if alteration=='missing':del b['values']['nd_kn']
    elif alteration=='extra': b['values']['unknown']=1
    elif alteration=='units': b['units']['force']='N'
    elif alteration=='source':b['source']='FC09_PRODUCTION'
    elif alteration=='context':b['context']='B-BLOK-235'
    elif alteration=='bars_duplicate':b['values']['bar_diameters_mm']=[20,20]
    elif alteration=='bars_string':b['values']['bar_diameters_mm']='14,20'
    elif alteration=='bars_empty':b['values']['bar_diameters_mm']=[]
    else:b['values']['bar_diameters_mm']=[True]
    with pytest.raises((ValueError,TypeError)):calculate_reference(b)

def test_both_zero_moments_keep_four_sign_branches():
    c=calculate_reference(replace(ReferenceColumnInput(),m2_knm=0,m3_knm=0).bundle())
    assert c.engine_result.minimum_eccentricity.output_state_count==8
    assert {(s.m2_nmm,s.m3_nmm) for s in c.engine_result.minimum_eccentricity.states}=={(-39000000,-30000000),(-39000000,30000000),(39000000,-30000000),(39000000,30000000)}

def test_second_order_required_is_blocked_not_fail():
    c=calculate_reference(replace(ReferenceColumnInput(),free_length_mm=6000,moment_ratio_m3=1).bundle());m=reference_manifest(c)
    assert c.engine_result.status=='REQUIRES_MOMENT_MAGNIFICATION'
    assert m['checks'][1]['display_status']=='MOMENT BÜYÜTME GEREKLİ' and m['checks'][-1]['value'] is None
    assert not any(check['status']=='FAIL' for check in m['checks'])

def test_report_projection_matches_engine_and_input(calculation):
    m=reference_manifest(calculation)
    assert m['input_bundle']==calculation.inputs.bundle() and m['engine_status']==calculation.engine_result.status
    assert m['typed_slenderness']['m2']['slenderness_ratio_lk_over_i']==m['checks'][0]['value']
    assert len(m['selected_candidate']['bars'])==calculation.engine_result.rebar_design.selection.selected_candidate.bar_count
    assert m['contributions'] and all(c['component_id']==REFERENCE_ID for c in m['contributions'])

def test_pdf_contains_same_exact_input_result_identity_and_trace(changed):
    m=reference_manifest(changed);content=render_reference_pdf(changed)
    text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(content)).pages)
    assert m['result_id'] in text.replace('\n','') and m['input_sha256'] in text.replace('\n','')
    assert m['engine_status'] in text and 'REFERANS / DEMO' in text and 'lambda = 3000 / 240 = 12.5' in text
    assert '39 kN.m' in text and 'Nihai donatı' in text
    assert content==render_reference_pdf(changed)

def test_235_keeps_accepted_facts_no_demo_geometry_or_result():
    m=column_235_manifest(REPO)
    assert m['context']=='B-BLOK-235' and m['section']=='Column_80x80'
    assert m['I22']['value']==m['I33']['value']==0.03413333333333332
    assert m['candidate_sha256']!=m['historical_sha256']
    assert m['calculations']==[] and 'input_bundle' not in m and 'selected_candidate' not in m
    assert m['FC09_PRODUCTION_GATE']=='UNCHANGED' and m['GLOBAL_DELTA']=='NOT_PROVEN'

def test_235_source_drift_rejected(tmp_path):
    from tbdy_engine.product_reports.column_v1_report import PINS
    (tmp_path/'docs').mkdir()
    for key in ('assignment','property','gates'):
        name,_=PINS[key];(tmp_path/'docs'/name).write_bytes((REPO/'docs'/name).read_bytes())
    path=tmp_path/'docs'/PINS['property'][0];path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError,match='hash'):column_235_manifest(tmp_path)

@pytest.fixture
def backend():
    server=make_server(REPO,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def post(path,body):
        request=Request(f'http://127.0.0.1:{server.server_port}/api/'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
        with urlopen(request,timeout=20) as response:return response.read(),response.headers
    yield post,server.application
    server.shutdown();server.server_close();thread.join()

def test_real_http_backend_numeric_stale_context_report(backend):
    post,app=backend;raw,_=post('workspace',{});w=json.loads(raw);b=w['default_bundle'];key=w['id']
    rev=json.loads(post('state',dict(workspace_id=key,context='reference',bundle=b))[0])['revision']
    initial=json.loads(post('calculate',dict(workspace_id=key,revision=rev))[0])
    b['values']['width_mm']=800
    newrev=json.loads(post('state',dict(workspace_id=key,context='reference',bundle=b))[0])['revision']
    from urllib.error import HTTPError
    with pytest.raises(HTTPError):post('report',dict(workspace_id=key,revision=newrev,result_id=initial['result_id'],format='json'))
    changed=json.loads(post('calculate',dict(workspace_id=key,revision=newrev))[0]);assert changed['checks'][1]['value']==12.5
    report=json.loads(post('report',dict(workspace_id=key,revision=newrev,result_id=changed['result_id'],format='json'))[0]);assert report==changed
    rev235=json.loads(post('state',dict(workspace_id=key,context='235',bundle=None))[0])['revision']
    with pytest.raises(HTTPError):post('calculate',dict(workspace_id=key,revision=rev235))
    with pytest.raises(HTTPError):post('report',dict(workspace_id=key,revision=rev235,result_id=changed['result_id'],format='json'))
    evidence=json.loads(post('report',dict(workspace_id=key,revision=rev235,result_id=None,format='json'))[0]);assert evidence['calculations']==[]
    assert len([e for e in app.events if e['event']=='ENGINE_ENTERED'])==2
    assert len([e for e in app.events if e['event']=='ENGINE_RETURNED'])==2

def test_input_changes_while_engine_runs_reject_completed_result(monkeypatch):
    app=ColumnWorkspace(REPO);w=app.create();key=w['id'];entered=threading.Event();release=threading.Event();errors=[]
    import apps.column_v2.server as server
    original=server.calculate_reference
    def paused(bundle):entered.set();release.wait(5);return original(bundle)
    monkeypatch.setattr(server,'calculate_reference',paused)
    def run():
        try:app.calculate(dict(workspace_id=key,revision=0))
        except ValueError as e:errors.append(str(e))
    t=threading.Thread(target=run);t.start();assert entered.wait(5)
    app.state(dict(workspace_id=key,context='235',bundle=None));release.set();t.join(10)
    assert errors and app.get(key).calculation is None
    assert any(e['event']=='STALE_ENGINE_RESULT_REJECTED' for e in app.events)

def test_native_boundary_and_no_test_fixture_imports():
    import ast
    paths=['tbdy_engine/application/column_reference_workspace.py','tbdy_engine/product_reports/column_v2_report.py','apps/column_v2/server.py','tools/serve_column_v2.py']
    forbidden={'RunAnalysis','StartDesign','Save','SaveAs','SetPresentUnits','GetPoints','JointDispl','GetSectProps','GetSection','GetTransformationMatrix','GetTableForDisplayArray'}
    for name in paths:
        tree=ast.parse((REPO/name).read_text())
        assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden for n in ast.walk(tree))
        assert not any(isinstance(n,ast.ImportFrom) and (n.module or '').startswith('tests') for n in ast.walk(tree))
