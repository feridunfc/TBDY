"""Real editable reference dispatch; no native or trusted issuer construction."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from threading import Event, Thread
import ast, json, os, shutil, subprocess
import pytest
from pypdf import PdfReader
from apps.column_v2.server import ColumnWorkspace, make_server
from tbdy_engine.application import column_reference_producer as app
from tbdy_engine.application import column_reference_workspace as longitudinal
from tbdy_engine.product_reports.column_reference_producer_report import owner_reference_manifest, render_owner_reference_pdf
REPO=Path(__file__).resolve().parents[2]

@pytest.fixture
def workspace():
    w=ColumnWorkspace(REPO);created=w.create();bundle=created['owner_reference_bundle']
    key=created['id'];rev=w.state(dict(workspace_id=key,context='reference-owners',bundle=bundle))['revision']
    return w,key,rev,bundle


def test_real_owner_dispatch_after_edit_same_workspace(monkeypatch,workspace):
    w,key,rev,bundle=workspace;calls=[]
    a=longitudinal.evaluate_column_design;b=app.transverse_owner.evaluate_column_transverse_confinement
    def spy_design(**kwargs):calls.append(('PMM',kwargs['rebar_inputs'].material));return a(**kwargs)
    def spy_transverse(request,**kwargs):calls.append(('TRANSVERSE',request.shear_spacing_mm));assert kwargs['selected_rebar'] is None;return b(request,**kwargs)
    monkeypatch.setattr(longitudinal,'evaluate_column_design',spy_design)
    monkeypatch.setattr(app.transverse_owner,'evaluate_column_transverse_confinement',spy_transverse)
    first=w.calculate(dict(workspace_id=key,revision=rev));bundle['values']['shear_spacing_mm']=200
    rev=w.state(dict(workspace_id=key,context='reference-owners',bundle=bundle))['revision']
    with pytest.raises(ValueError,match='Aktif owner hesabı'):w.report(dict(workspace_id=key,revision=rev,result_id=first['result_id'],format='json'))
    changed=w.calculate(dict(workspace_id=key,revision=rev))
    # Independent closed form, only in tests: 100+(200/s)*365*450/1000.
    assert first['typed_transverse_output']['shear_vr_by_direction_kn'][0][1]==428.5
    assert changed['typed_transverse_output']['shear_vr_by_direction_kn'][0][1]==264.25
    assert [x[0] for x in calls]==['PMM','TRANSVERSE','PMM','TRANSVERSE']
    assert calls[1][1]==100 and calls[3][1]==200
    assert first['result_id']!=changed['result_id']
    assert len([e for e in w.events if e['event']=='REFERENCE_OWNER_ENTERED'])==4
    assert len([e for e in w.events if e['event']=='REFERENCE_OWNER_RETURNED'])==4
    assert all(e.get('native_calls',0)==0 for e in w.events)


@pytest.mark.parametrize('field,value',[('shear_spacing_mm',None),('fywd_mpa',True),('ash_dir2_mm2',float('nan')),('effective_depth_dir2_mm',-1),('reference_vc_dir3_kn',-1),('gross_area_ac_mm2',1),('confined_core_area_ack_mm2',400000),('effective_depth_dir3_mm',900)])
def test_invalid_inputs_invalidate_without_dispatch(workspace,field,value):
    w,key,rev,bundle=workspace;first=w.calculate(dict(workspace_id=key,revision=rev));before=len(w.events)
    bundle['values'][field]=value
    with pytest.raises((ValueError,TypeError)):w.state(dict(workspace_id=key,context='reference-owners',bundle=bundle))
    assert w.get(key).product_calculation is None
    with pytest.raises((ValueError,TypeError)):w.calculate(dict(workspace_id=key,revision=w.get(key).revision))
    assert not any(e['event']=='REFERENCE_OWNER_ENTERED' for e in w.events[before:])


@pytest.mark.parametrize('mutation',['source','context','unit','missing','extra_B5','native_epoch','extra_selected_rebar'])
def test_no_reference_to_production_authority(mutation):
    b=app.ReferenceOwnerInput.example().bundle()
    if mutation=='source':b['source']='FC09_PRODUCTION'
    elif mutation=='context':b['context']='235'
    elif mutation=='unit':b['units']['force']='N'
    elif mutation=='missing':del b['values']['ash_dir2_mm2']
    else:b[mutation]='client invented authority'
    with pytest.raises(ValueError):app.calculate_reference_owners(b)


def test_exact_typed_owner_status_and_reference_limits():
    b=app.ReferenceOwnerInput.example().bundle();b['values']['reference_ve_dir2_kn']=500
    m=owner_reference_manifest(app.calculate_reference_owners(b))
    c=next(c for c in m['checks'] if c['id']=='COL_FINAL_SHEAR_VR_DIR2')
    assert c['status']=='FAIL' and c['value']==500 and c['limit']==428.5
    assert c['ratio']==500/428.5 and c['display_status']=='UYGUN DEĞİL'
    assert c['origins']==['SYNTHETIC_TEST'] and c['severity']=='danger'
    assert 'ENGINE_SELECTED_REBAR_REQUIRED_FOR_HD_SPACING' in m['transverse_blockers']
    assert m['B5'] is m['B6'] is None and not m['engineering_complete'] and not m['real_235_design_ready']
    assert m['authority']=='DESIGN_CANDIDATE_ONLY'
    assert m['typed_transverse_input']['model_fingerprint'] is None


def test_ash_is_not_asw():
    b=app.ReferenceOwnerInput.example().bundle();first=app.calculate_reference_owners(b)
    b['values']['ash_dir2_mm2']=0;changed=app.calculate_reference_owners(b)
    assert changed.transverse.shear_vr_by_direction_kn==first.transverse.shear_vr_by_direction_kn
    assert next(c for c in changed.transverse.checks if c.check_id=='COL_HD_CONFINEMENT_ASH_DIR2').status.value=='FAIL'


def test_n_and_material_edit_dispatches_longitudinal_owner(workspace):
    w,key,rev,b=workspace;first=w.calculate(dict(workspace_id=key,revision=rev))
    b['values']['nd_kn']=1200;b['values']['fywd_mpa']=300
    rev=w.state(dict(workspace_id=key,context='reference-owners',bundle=b))['revision'];new=w.calculate(dict(workspace_id=key,revision=rev))
    assert first['selected_evaluations']!=new['selected_evaluations']
    assert new['typed_transverse_output']['shear_vr_by_direction_kn'][0][1]==370
    assert new['input_sha256']!=first['input_sha256']


def test_pdf_json_html_share_active_result(workspace):
    w,key,rev,b=workspace;m=w.calculate(dict(workspace_id=key,revision=rev))
    outputs={fmt:w.report(dict(workspace_id=key,revision=rev,result_id=m['result_id'],format=fmt))[0] for fmt in ('json','pdf','html')}
    assert json.loads(outputs['json'])==json.loads(json.dumps(m))
    text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(outputs['pdf'])).pages).replace('\n','')
    assert m['result_id'] in text and m['input_sha256'] in text and '428.5' in text
    assert 'REFERANS / DEMO' in text and 'Kanonik' in text and 'Kesme hesabı aralığı s' in text
    assert m['result_id'] in outputs['html'].decode()


def test_context_switch_never_copies_reference_to_235(workspace):
    w,key,rev,b=workspace;w.calculate(dict(workspace_id=key,revision=rev))
    rev=w.state(dict(workspace_id=key,context='235-product',bundle=w.product_authority.packet()))['revision'];m=w.calculate(dict(workspace_id=key,revision=rev))
    assert m['invoked_owners']==() or m['invoked_owners']==[]
    assert all(c['status']=='BLOCKED' for c in m['checks']) and not m['real_235_design_ready']


def test_stale_while_owner_runs_cannot_restore_result(monkeypatch,workspace):
    w,key,rev,b=workspace;entered=Event();release=Event();errors=[]
    import apps.column_v2.server as server
    original=server.calculate_reference_owners
    def paused(*args,**kwargs):entered.set();assert release.wait(10);return original(*args,**kwargs)
    monkeypatch.setattr(server,'calculate_reference_owners',paused)
    def run():
        try:w.calculate(dict(workspace_id=key,revision=rev))
        except ValueError as e:errors.append(str(e))
    thread=Thread(target=run);thread.start();assert entered.wait(5)
    w.state(dict(workspace_id=key,context='235',bundle=None));release.set();thread.join(10)
    assert errors and w.get(key).product_calculation is None
    assert any(e['event']=='STALE_OWNER_RESULT_REJECTED' for e in w.events)


def test_first_owner_error_stops_no_transverse_fallback(monkeypatch):
    calls=[]
    def fail(*a,**kw):raise ValueError('original owner failure')
    def forbidden(*a,**kw):calls.append(1);raise AssertionError('must not reach')
    monkeypatch.setattr(app,'calculate_reference',fail)
    monkeypatch.setattr(app.transverse_owner,'evaluate_column_transverse_confinement',forbidden)
    with pytest.raises(ValueError,match='original owner failure'):app.calculate_reference_owners(app.ReferenceOwnerInput.example().bundle())
    assert calls==[]


def test_new_producer_has_no_tests_native_issuers_or_replacement_formula():
    tree=ast.parse((REPO/'tbdy_engine/application/column_reference_producer.py').read_text())
    forbidden={'RunAnalysis','StartDesign','Save','SaveAs','SetPresentUnits','GetPoints','QueryInterface','publish','execute_project'}
    assert not any(isinstance(n,ast.ImportFrom) and (n.module or '').startswith(('tests','tbdy_engine.integration')) for n in ast.walk(tree))
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden for n in ast.walk(tree))
    assert 'selected_rebar=None' in (REPO/'tbdy_engine/application/column_reference_producer.py').read_text()


def test_real_default_server_browser_single_context_edit(tmp_path):
    node=os.environ.get('COLUMN_V2_BROWSER_NODE') or shutil.which('node');binary=os.environ.get('COLUMN_V2_BROWSER_BINARY');module=os.environ.get('COLUMN_V2_PLAYWRIGHT_MODULE')
    if not node or not binary or not module:pytest.skip('Explicit delivery browser profile required.')
    capture=Path(os.environ.get('COLUMN_REFERENCE_PRODUCER_CAPTURE_DIR',tmp_path));capture.mkdir(parents=True,exist_ok=True)
    server=make_server(REPO,0,audit_path=capture/'Backend_Execution.jsonl');thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        p=subprocess.run([node,str(Path(__file__).with_name('column_reference_producer_browser.cjs')),json.dumps({'url':f'http://127.0.0.1:{server.server_port}','output_dir':str(capture)})],capture_output=True,text=True,env=os.environ.copy(),timeout=90)
        assert p.returncode==0,p.stdout+'\n'+p.stderr
        result=json.loads((capture/'Browser_Interaction.json').read_text());assert not result['page_errors'] and result['published_variants']==0
        returned=[e for e in server.application.events if e['event']=='REFERENCE_OWNER_RETURNED']
        assert len(returned)==6 and len({e['input_sha256'] for e in returned})==3
        assert len({e['workspace_id'] for e in returned})==1
        assert [e['shear_vr_by_direction_kn'][0][1] for e in returned if 'shear_vr_by_direction_kn' in e]==[428.5,264.25,264.25]
    finally:
        server.shutdown();server.server_close();thread.join(5);server.application.audit.close()


def test_standard_launch_entry_runs_editable_producer(tmp_path):
    """No make_server injection or pre-published typed variant in this proof."""
    import signal, socket, sys, time
    from urllib.request import Request, urlopen
    python=REPO/'.column-product-venv/bin/python'
    if not python.is_file():pytest.skip('Explicit pinned launch profile required for delivery.')
    capture=Path(os.environ.get('COLUMN_REFERENCE_LAUNCH_CAPTURE_DIR',tmp_path));capture.mkdir(parents=True,exist_ok=True)
    audit=capture/'Standard_Launch_Backend.jsonl';log=capture/'Standard_Launch.log'
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    command=[sys.executable,str(REPO/'tools/start_column_product.py'),'--port',str(port),'--audit-file',str(audit)]
    # The private pytest runner prepends a legacy testdeps site-packages path.
    # A normal user launch must use the launcher's own pinned environment.
    # Preserve the production pin check; remove only this test injection.
    runtime_env=dict(os.environ);runtime_env.pop('PYTHONPATH',None)
    stream=log.open('w');process=subprocess.Popen(command,cwd=REPO,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True,env=runtime_env)
    try:
        url=f'http://127.0.0.1:{port}'
        deadline=time.monotonic()+30
        while True:
            try:
                with urlopen(url,timeout=1) as r:assert r.status==200
                break
            except OSError:
                if process.poll() is not None or time.monotonic()>deadline:pytest.fail(log.read_text())
                time.sleep(.1)
        def post(path,body):
            req=Request(url+'/api/'+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
            with urlopen(req,timeout=15) as r:return r.read()
        w=json.loads(post('workspace',{}));assert w['qualified_catalog']==[]
        bundle=w['owner_reference_bundle'];key=w['id'];results=[]
        for spacing,expected in ((100,428.5),(200,264.25)):
            bundle['values']['shear_spacing_mm']=spacing
            rev=json.loads(post('state',dict(workspace_id=key,context='reference-owners',bundle=bundle)))['revision']
            m=json.loads(post('calculate',dict(workspace_id=key,revision=rev)));assert m['typed_transverse_output']['shear_vr_by_direction_kn'][0][1]==expected
            assert json.loads(post('report',dict(workspace_id=key,revision=rev,result_id=m['result_id'],format='json')))==m
            results.append(m)
        records=[json.loads(s) for s in audit.read_text().splitlines()];owner_returns=[r for r in records if r['event']=='REFERENCE_OWNER_RETURNED']
        assert len(owner_returns)==4 and len({r['input_sha256'] for r in owner_returns})==2
        assert not any(r.get('native_calls') for r in records)
        (capture/'Standard_Launch_Evidence.json').write_text(json.dumps({'command':command,'qualified_catalog':[], 'injected_channel':False,'results':results,'owner_returns':owner_returns},indent=2))
    finally:
        try:os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError:pass
        process.wait(timeout=10);stream.close()
