"""Synthetic declarations test wiring; never qualify actual 235 readiness."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import base64,json,os,subprocess
import pytest
from apps.column_v2.server import ColumnWorkspace
from tbdy_engine.application.column_product_workspace import apply_review,validate_packet,evaluate_column_product
from tbdy_engine.product_reports.column_product_report import product_authority,product_manifest,render_product_html,render_product_pdf
from tools.start_column_product import install_dependencies

REPO=Path(__file__).resolve().parents[2]


def synthetic_packet(authority):
    p=authority.packet();p['values'].update(width_mm=500.,depth_mm=800.,axis_basis='RECTANGULAR_LOCAL2_LOCAL3',free_length_mm=3000.,k_m2=1.,k_m3=1.,sway_classification='SWAY_PREVENTED',moment_ratio_m2=0.,moment_ratio_m3=0.,concrete_name='TEST_CONCRETE',steel_name='TEST_STEEL',transverse_steel_name='TEST_TIE',fck_mpa=35.,fcd_mpa=35/1.5,fyd_mpa=500/1.15,fywk_mpa=500.,fywd_mpa=500/1.15,aggregate_max_mm=25.)
    for group in ('geometry','slenderness','materials'):
        p=apply_review(p,group,dict(reviewer='SYNTHETIC TEST',reference='Synthetic wiring / not factual 235',reviewed_at=datetime.now(timezone.utc).isoformat(),origin='SYNTHETIC_TEST'),authority)
    return p


def test_actual_accepted_235_has_no_filled_geometry_or_native_results():
    a=product_authority(REPO);m=product_manifest(evaluate_column_product(a.packet(),a),a)
    assert all(f['value'] is None for f in m['input_completeness'])
    assert all(c['status']=='BLOCKED' and c['value'] is None for c in m['checks'])
    assert not m['invoked_owners'] and not m['real_235_design_ready']
    assert m['native_evidence']['I22']['value']==0.03413333333333332 and m['section_svg']==''
    assert m['current_analysis_result_epoch'] is None and m['session_connection']=='NOT_OBSERVED'


def test_existing_independent_owner_recompute_and_typed_reports():
    a=product_authority(REPO);p=synthetic_packet(a);r=evaluate_column_product(p,a);m=product_manifest(r,a)
    by={c['id']:c for c in m['checks']}
    # Independent TS500 regression expectation reused from accepted VS6 tests.
    assert by['slenderness_M3']['value']==20 and by['emin_M3']['value']==30
    assert r.material_basis.concrete_strengths[0].fcd_mpa==35/1.5
    assert set(r.invoked_owners)=={'ts500_minimum_eccentricity_mm','evaluate_ts500_column_slenderness','ReviewedColumnDesignBasis'}
    q=deepcopy(p);q['values']['width_mm']=800.;del q['reviews']['geometry']
    q=apply_review(q,'geometry',dict(reviewer='TEST',reference='Synthetic edited geometry',reviewed_at=datetime.now(timezone.utc).isoformat(),origin='SYNTHETIC_TEST'),a)
    n=product_manifest(evaluate_column_product(q,a),a);changed={c['id']:c for c in n['checks']}
    assert changed['slenderness_M3']['value']==12.5 and changed['emin_M3']['value']==39
    assert n['result_id']!=m['result_id'] and not n['real_235_design_ready']
    assert all(c['status']=='BLOCKED' for c in n['checks'] if c['id'] in {'longitudinal','design_actions','stability','confinement','readiness'})
    html=render_product_html(n);assert n['result_id'] in html and 'ENGINE_SELECTED_REBAR' in html
    assert render_product_pdf(n).startswith(b'%PDF')
    assert n['contributions'][0]['calculations'][0]['outputs'][0]['value']==39


@pytest.mark.parametrize('field,value',[('source_sha256','FC09'),('historical_sha256','61FA'),('component_id','1044'),('project_id','OTHER'),('schema','UNKNOWN'),('evidence_epoch','stale'),('result_epoch','fake-B5')])
def test_source_component_epoch_mismatch_rejects(field,value):
    a=product_authority(REPO);p=a.packet();p[field]=value
    with pytest.raises(ValueError):validate_packet(p,a)


@pytest.mark.parametrize('alteration',['unit','original_pin','adoption_pin','extra_authority','receipt_bytes','receipt_missing_sidecar','review_stale','review_unknown_origin','review_missing_reference','review_wrong_source','review_wrong_epoch','review_unzoned_time','wrong_type','negative_dimension','ratio','integer','unknown_field'])
def test_fail_closed_packet_and_review(alteration):
    a=product_authority(REPO);p=synthetic_packet(a)
    if alteration=='unit':p['units']['width_mm']='m'
    elif alteration=='original_pin':p['original_receipt_pins']['assignment']['json_sha256']='0'*64
    elif alteration=='adoption_pin':p['adoption_pins']['assignment']['sha256']='0'*64
    elif alteration=='extra_authority':p['TrustedLiveAcquisitionContext']={'fake':True}
    elif alteration=='receipt_bytes':p['original_pairs']['assignment']={'json_base64':base64.b64encode(b'{}').decode(),'sidecar_base64':base64.b64encode(b'bad').decode()}
    elif alteration=='receipt_missing_sidecar':p['original_pairs']['assignment']={'json_base64':'e30='}
    elif alteration=='review_stale':p['values']['width_mm']=600.
    elif alteration=='review_unknown_origin':p['reviews']['geometry']['origin']='NATIVE'
    elif alteration=='review_missing_reference':p['reviews']['geometry']['reference']=''
    elif alteration=='review_wrong_source':p['reviews']['geometry']['source_sha256']='wrong'
    elif alteration=='review_wrong_epoch':p['reviews']['geometry']['evidence_epoch']='old'
    elif alteration=='review_unzoned_time':p['reviews']['geometry']['reviewed_at']='2026-10-13T00:00:00'
    elif alteration=='wrong_type':p['values']['width_mm']=True
    elif alteration=='negative_dimension':p['values']['width_mm']=-1
    elif alteration=='ratio':p['values']['moment_ratio_m2']=1.1
    elif alteration=='integer':p['values']['longitudinal_bar_count']=4.5
    elif alteration=='unknown_field':p['values']['end_bottom']='guessed'
    with pytest.raises(ValueError):validate_packet(p,a)


def test_material_validation_does_not_create_production_bound_identity():
    a=product_authority(REPO);r=evaluate_column_product(synthetic_packet(a),a)
    assert r.material_basis and not hasattr(r,'design_lineage') and not hasattr(r,'acquisition_context')
    m=product_manifest(r,a);assert m['canonical_rebar_authority']=='NOT_PROVIDED'


def test_no_group_review_means_no_owner_dispatch():
    a=product_authority(REPO);p=synthetic_packet(a);p['reviews']={};r=evaluate_column_product(p,a)
    assert r.invoked_owners==() and all(c.status=='BLOCKED' for c in r.controls)


def test_import_error_invalidates_old_backend_result():
    app=ColumnWorkspace(REPO);w=app.create();p=synthetic_packet(app.product_authority);s=app.state(dict(workspace_id=w['id'],context='235-product',bundle=p));m=app.calculate(dict(workspace_id=w['id'],revision=s['revision']))
    bad=deepcopy(p);bad['source_sha256']='wrong'
    with pytest.raises(ValueError):app.state(dict(workspace_id=w['id'],context='235-product',bundle=bad))
    assert app.get(w['id']).product_calculation is None and app.get(w['id']).bundle is None
    with pytest.raises(ValueError):app.report(dict(workspace_id=w['id'],revision=s['revision'],result_id=m['result_id'],format='json'))


@pytest.mark.parametrize('change',['edit','source_switch','review_failure'])
def test_workspace_change_invalidates_export_and_result(change):
    app=ColumnWorkspace(REPO);w=app.create();p=synthetic_packet(app.product_authority);s=app.state(dict(workspace_id=w['id'],context='235-product',bundle=p));m=app.calculate(dict(workspace_id=w['id'],revision=s['revision']))
    if change=='edit':p['values']['width_mm']=800.;p['reviews'].pop('geometry');app.state(dict(workspace_id=w['id'],context='235-product',bundle=p))
    elif change=='source_switch':app.state(dict(workspace_id=w['id'],context='235',bundle=None))
    else:
        with pytest.raises(ValueError):app.review_product(dict(workspace_id=w['id'],revision=s['revision'],group='geometry',declaration={}))
    assert app.get(w['id']).product_calculation is None
    with pytest.raises(ValueError):app.report(dict(workspace_id=w['id'],revision=s['revision'],result_id=m['result_id'],format='pdf'))


@pytest.mark.parametrize('previous',[None,'1','custom'])
@pytest.mark.parametrize('fail',[False,True])
def test_pure_yaml_install_env_restored_and_pins_not_changed(monkeypatch,previous,fail):
    if previous is None:monkeypatch.delenv('PYYAML_FORCE_LIBYAML',raising=False)
    else:monkeypatch.setenv('PYYAML_FORCE_LIBYAML',previous)
    def run(args,check):
        assert os.environ['PYYAML_FORCE_LIBYAML']=='0' and '--no-binary=PyYAML' in args and '--no-cache-dir' in args
        assert args[-1].endswith('requirements-column-v2.txt')
        if fail:raise subprocess.CalledProcessError(1,args)
    if fail:
        with pytest.raises(subprocess.CalledProcessError):install_dependencies(Path('python'),Path('requirements-column-v2.txt'),run)
    else:install_dependencies(Path('python'),Path('requirements-column-v2.txt'),run)
    assert os.environ.get('PYYAML_FORCE_LIBYAML')==previous


def test_launcher_refuses_foreign_venv_before_install(tmp_path,monkeypatch):
    from tools.start_column_product import launch
    (tmp_path/'.column-product-venv').mkdir()
    with pytest.raises(ValueError,match='ait değil'):launch(tmp_path,install_only=True)


def test_launcher_install_failure_never_runs_server(tmp_path,monkeypatch):
    from tools import start_column_product as launcher
    home=tmp_path/'.column-product-venv';(home/'bin').mkdir(parents=True);(home/'bin/python').write_text('stub')
    (home/'COLUMN_PRODUCT_OWNED_VENV').write_text(str(tmp_path.resolve()))
    monkeypatch.setattr(launcher,'check_dependencies',lambda p:False)
    def fail(*a):raise subprocess.CalledProcessError(1,['pip'])
    monkeypatch.setattr(launcher,'install_dependencies',fail)
    with pytest.raises(subprocess.CalledProcessError):launcher.launch(tmp_path,install_only=True)


def test_launcher_used_port_is_preserved(tmp_path):
    import socket
    from tools.start_column_product import launch
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1',0));occupied.listen()
        with pytest.raises(ValueError,match='kullanımda'):launch(tmp_path,port=occupied.getsockname()[1])
        assert occupied.getsockname()[1]>0 and not (tmp_path/'.column-product-venv').exists()
