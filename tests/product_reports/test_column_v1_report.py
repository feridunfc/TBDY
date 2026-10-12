"""Real accepted evidence, real HTML/PDF/CSV delivery; no fake ETABS execution."""
import ast,csv,hashlib,json,os
from dataclasses import replace
from io import BytesIO,StringIO
from pathlib import Path
from zipfile import ZipFile
import pytest
from pypdf import PdfReader
from tbdy_engine.product_reports import column_v1_report as v1

@pytest.fixture(scope='module')
def inputs():
    root=Path(__file__).resolve().parents[2]
    return {'assignment_path':root/'docs'/v1.PINS['assignment'][0],'property_path':root/'docs'/v1.PINS['property'][0],
        'gates_path':root/'docs'/v1.PINS['gates'][0],'modal_path':Path(os.environ['COLUMN_V1_MODAL_RECEIPT'])}

@pytest.fixture(scope='module')
def report(inputs):return v1.build_column_v1_report(**inputs)


def test_real_sources_keep_candidate_and_historical_populations_separate(report,inputs):
    p=report.as_dict();m=json.loads(inputs['modal_path'].read_text());a,h,g=p['contributions']
    assert a['status']=='PROVEN' and h['status']=='PARTIAL' and g['status']=='BLOCKED'
    assert a['summary_fields'][0]['value']==v1.CANDIDATE and h['summary_fields'][0]['value']==v1.HISTORICAL
    assert h['tables'][0]['rows']==m['facts']['Modal:FrameForce:235']['payload']['rows']
    assert h['tables'][1]['rows']==m['facts']['Modal:JointDispl:955']['payload']['rows']+m['facts']['Modal:JointDispl:758']['payload']['rows']
    assert p['current_engine_result']==p['current_B5']=='NOT_PROVIDED' and p['engineering_verdict']=='NOT_EVALUATED'
    assert p['source_authority_rebound'] is False and p['new_getter_is_report_prerequisite'] is False
    assert p['live_GetPoints_authorized'] is False and p['global_delta']=='NOT_PROVEN' and p['R2_RERUN_READY'] is False
    assert all(not c['calculations'] for c in p['contributions'])

@pytest.mark.parametrize('key',['assignment_path','property_path','gates_path','modal_path'])
def test_any_changed_source_bytes_stop_before_report_delivery(inputs,tmp_path,key):
    original=inputs[key];q=tmp_path/original.name;q.write_bytes(original.read_bytes()+b' ')
    with pytest.raises(ValueError,match='accepted source bytes differ'):v1.build_column_v1_report(**(inputs|{key:q}))

@pytest.mark.parametrize('fault',['candidate_rebind','false_b5','bad_mode','duplicate_frame','wrong_component','payload_digest'])
def test_semantic_drift_cannot_be_hidden_by_a_replaced_pin(inputs,monkeypatch,tmp_path,fault):
    data=json.loads(inputs['modal_path'].read_text())
    if fault=='candidate_rebind':data['source_sha256_before']=data['source_sha256_after']=v1.CANDIDATE
    if fault=='false_b5':data['current_b5_qualified']=True
    if fault=='bad_mode':data['facts']['Modal:FrameForce:235']['payload']['rows'][0]['step_type']='Step'
    if fault=='duplicate_frame':data['story_columns'].append(next(x for x in data['story_columns'] if x['UniqueName']=='235'))
    if fault=='wrong_component':data['facts']['Modal:FrameForce:235']['payload']['rows'][0]['object_name']='236'
    if fault=='payload_digest':data['facts']['Modal:JointDispl:955']['capture_payload_ref']='modal-read:sha256:'+'0'*64
    q=tmp_path/'changed.json';q.write_text(json.dumps(data));pins=dict(v1.PINS);pins['modal']=(q.name,hashlib.sha256(q.read_bytes()).hexdigest());monkeypatch.setattr(v1,'PINS',pins)
    with pytest.raises(ValueError):v1.build_column_v1_report(**(inputs|{'modal_path':q}))


def test_real_deterministic_package_pdf_csv_json_and_manifest(report,tmp_path):
    before=report.to_json();artifacts=v1.build_column_v1_artifacts(report);repeat=v1.build_column_v1_artifacts(report)
    assert [a.content for a in artifacts]==[a.content for a in repeat] and report.to_json()==before
    byname={a.filename:a for a in artifacts};assert len(byname)==7
    assert len(PdfReader(BytesIO(byname['Column_235_V1.pdf'].content)).pages)==4
    text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(byname['Column_235_V1.pdf'].content)).pages)
    assert 'Kolon 235' in text and 'I22' in text and 'NOT_PROVEN' in text and '0.03413333333333332' in text
    manifest=json.loads(byname['Column_235_V1_provenance.json'].content)
    for entry in manifest['files']:assert byname[entry['name']].sha256==entry['sha256']
    for suffix,count in [('frame_force',300),('joint_displ',200)]:
        rows=list(csv.DictReader(StringIO(byname['Column_235_V1_'+suffix+'.csv'].content.decode())));assert len(rows)==count
        assert {float(r['step_number']) for r in rows}==set(range(1,101))
    with ZipFile(BytesIO(byname['Column_235_V1.zip'].content)) as z:
        assert len(z.namelist())==6
        for name in z.namelist():assert z.read(name)==byname[name].content
    v1.persist_column_v1_artifacts(artifacts,tmp_path)
    with pytest.raises(ValueError,match='preserve original delivery'):v1.persist_column_v1_artifacts(artifacts,tmp_path)
    assert all((tmp_path/a.filename).read_bytes()==a.content for a in artifacts)


def test_html_is_standalone_static_fallback_and_complete_modal_data(report):
    html=v1.render_column_v1_html(report)
    assert 'cdn.' not in html and 'src="http' not in html and 'href="http' not in html
    assert 'id="force-results"><div class="scroll"><table>' in html and 'id="point-results"><div class="scroll"><table>' in html
    payload=html.split('<script id="report-data" type="application/json">')[1].split('</script>')[0]
    assert json.loads(payload)==report.as_dict() and html.count('<option value=')==100
    assert 'r.step_number===mode' in html and 'NOT_PROVEN' in html


def test_html_content_is_escaped_and_can_never_close_embedded_data_script(report):
    fields=report.contributions[0].summary_fields
    dangerous=replace(fields[1],value='</script><script>alert(1)</script>')
    contribution=replace(report.contributions[0],summary_fields=(fields[0],dangerous,*fields[2:]))
    html=v1.render_column_v1_html(replace(report,contributions=(contribution,*report.contributions[1:])))
    assert '&lt;/script&gt;' in html and '<script>alert(1)</script>' not in html and '\\u003c/script\\u003e' in html


def test_projection_module_has_no_acquisition_setter_solver_or_engineering_calls():
    tree=ast.parse(Path(v1.__file__).read_text());attrs={n.attr for n in ast.walk(tree) if isinstance(n,ast.Attribute)}
    assert attrs.isdisjoint({'GetPoints','GetSectProps','GetSection','JointDispl','RunAnalysis','StartDesign','Save','SetPresentUnits','QueryInterface'})
    imports={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
    assert not any(n and n.startswith(('etabs_gateway','tbdy_engine.etabs','tbdy_engine.design','tools')) for n in imports)


def test_rendered_javascript_is_syntactically_valid_in_node(report,tmp_path):
    import re,subprocess
    html=v1.render_column_v1_html(report)
    scripts=re.findall(r'<script>(.*?)</script>',html,re.S)
    assert len(scripts)==1
    p=tmp_path/'rendered.cjs';p.write_text(scripts[0])
    result=subprocess.run(['node','--check',str(p)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
