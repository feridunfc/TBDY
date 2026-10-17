"""Finite public-product regressions for declared scope; no native lifecycle."""
from copy import deepcopy
from pathlib import Path
import json
import pytest
from apps.column_v2.server import ColumnWorkspace
from tbdy_engine.application.column_product_workspace import (
    apply_review, evaluate_column_product, invalidate_changed_reviews, known_user_draft,
    migrate_v1_packet, validate_packet, MATERIAL_GROUPS, FIELDS, digest,
)
from tbdy_engine.product_reports.column_product_report import product_authority, product_manifest
from tbdy_engine.product_reports.column_decision_presenter import present_decision

REPO=Path(__file__).resolve().parents[2]
DECLARATION=dict(reviewer='OFFLINE TEST',reference='SYNTHETIC PUBLIC INPUT / NOT REAL 235',reviewed_at='2026-10-17T08:00:00+03:00',origin='SYNTHETIC_TEST')


def declared_packet(authority, *, transverse=False):
    p=authority.packet()
    p['values'].update(width_mm=800.,depth_mm=800.,axis_basis='RECTANGULAR_LOCAL2_LOCAL3',
        concrete_name='TEST_C35',fck_mpa=35.,fcd_mpa=35/1.5,steel_name='TEST_S500',fyd_mpa=500/1.15,
        action_state_semantics='SIGNED_CONCURRENT_N_M2_M3',output_case='TEST_CONCURRENT_COMBO',action_source_ref='TEST_TWO_ROWS_SAME_CASE_STEP',step_type='Static',step_number=0.,action_sign_basis='COMPRESSION_POSITIVE_LOCAL_23',
        station_i_m=0.,station_j_m=4.45,nd_i_kn=1000.,nd_j_kn=1200.,m2_i_knm=100.,m3_i_knm=-60.,m2_j_knm=-120.,m3_j_knm=80.,
        clear_cover_mm=40.,longitudinal_diameter_mm=24.,longitudinal_bar_count=16,n_bars_dir2=5,n_bars_dir3=5,tie_diameter_mm=10.)
    groups=['geometry','concrete','longitudinal_steel','actions','cage']
    if transverse:
        p['values'].update(transverse_steel_name='TEST_TIE',fywk_mpa=500.,fywd_mpa=500/1.15,
            confinement_spacing_mm=100.,middle_spacing_mm=150.,shear_spacing_mm=100.,number_2_dir_tie_bars=4,number_3_dir_tie_bars=4,
            high_ductility=True,limited_ductility=False,ts500_general=True,cantilever=False,transverse_clear_height_mm=4450.,core_area_mm2=518400.,
            confinement_length_mm=1200.,restrained_bar_spacing_mm=180.,bk2_mm=720.,bk3_mm=720.,ash2_mm2=314.,ash3_mm2=314.,leg_spacing2_mm=180.,leg_spacing3_mm=180.)
        groups+=['transverse_steel','transverse_cage','transverse']
    for group in groups:p=apply_review(p,group,DECLARATION,authority)
    return p


def checks(packet, authority):
    return {c['id']:c for c in product_manifest(evaluate_column_product(packet,authority),authority)['checks']}


def test_declared_axial_and_coordinate_based_biaxial_pmm_require_only_their_own_inputs():
    a=product_authority(REPO);p=declared_packet(a);c=checks(p,a)
    assert c['axial']['status']=='OK' and c['axial']['limit']==pytest.approx(13440)
    assert c['longitudinal']['status']=='OK' and c['longitudinal']['value']==pytest.approx(.10773216688961827)
    layout=c['longitudinal']['owner_output']['layout']
    assert len(layout['bars'])==16 and len({(b['x2_mm'],b['x3_mm']) for b in layout['bars']})==16
    assert p['values']['v2_kn'] is None and p['values']['middle_spacing_mm'] is None
    assert c['longitudinal']['owner_output']['states'][0]['state']['m3_knm']==-60
    assert c['longitudinal']['owner_output']['states'][1]['state']['step_type']=='Static'
    assert c['material']['status']=='BLOCKED' and c['confinement']['status']=='BLOCKED'
    assert c['cage']['display_unit']=='cm²'
    assert c['longitudinal']['origins']==['SYNTHETIC_TEST']


def test_declared_force_change_changes_actual_capacity_decision_without_readiness():
    a=product_authority(REPO);p=declared_packet(a)
    p['values']['m2_j_knm']=3000.;p=invalidate_changed_reviews(p);p=apply_review(p,'actions',DECLARATION,a)
    c=checks(p,a);assert c['longitudinal']['status']=='FAIL' and c['longitudinal']['value']>1
    p['values']['nd_j_kn']=15000.;p=invalidate_changed_reviews(p);p=apply_review(p,'actions',DECLARATION,a)
    c=checks(p,a);assert c['axial']['status']=='FAIL' and c['axial']['value']==15000
    m=product_manifest(evaluate_column_product(p,a),a)
    assert m['current_analysis_result_epoch'] is None and not m['real_235_design_ready']


def test_count_and_diameter_without_face_layout_never_execute_pmm():
    a=product_authority(REPO);p=declared_packet(a);p['values']['n_bars_dir2']=None;p=invalidate_changed_reviews(p)
    c=checks(p,a);assert c['longitudinal']['status']=='BLOCKED' and c['cage']['owner_output'] is None
    with pytest.raises(ValueError):apply_review(p,'cage',DECLARATION,a)


def test_layout_total_count_mismatch_and_unsupported_size_are_rejected():
    a=product_authority(REPO)
    for change in ({'longitudinal_bar_count':20},{'n_bars_dir2':10000000}):
        p=declared_packet(a);p['values'].update(change);p=invalidate_changed_reviews(p);p=apply_review(p,'cage',DECLARATION,a)
        with pytest.raises(ValueError):evaluate_column_product(p,a)


def test_pure_transverse_owner_keeps_canonical_dependent_subchecks_blocked_and_recomputes():
    a=product_authority(REPO);p=declared_packet(a,transverse=True);before=checks(p,a)['confinement']
    statuses={c['status'] for c in before['owner_output']['checks']}
    assert 'OK' in statuses and 'BLOCKED' in statuses and before['status']=='PARTIAL'
    p['values']['confinement_spacing_mm']=300.;p=invalidate_changed_reviews(p);p=apply_review(p,'transverse_cage',DECLARATION,a)
    after=checks(p,a)['confinement']
    assert after['owner_output']!=before['owner_output'] and after['status']=='FAIL'
    assert after['owner_output']['request']['design_result_ref'] is None


@pytest.mark.parametrize('length,status',[(4450.,'SLENDERNESS_EFFECTS_NEGLIGIBLE'),(6000.,'SIGNED_END_MOMENT_RATIO_REQUIRED_FOR_SLENDERNESS_DECISION'),(12000.,'MOMENT_MAGNIFICATION_REQUIRED'),(25000.,'GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED')])
def test_slenderness_decision_and_next_action_match_owner(length,status):
    a=product_authority(REPO);p=a.packet();p['values'].update(width_mm=800.,depth_mm=800.,axis_basis='RECTANGULAR_LOCAL2_LOCAL3',free_length_mm=length,k_m2=1.,k_m3=1.,sway_classification='SWAY_PREVENTED')
    for group in ('geometry','slenderness'):p=apply_review(p,group,DECLARATION,a)
    c=checks(p,a)['slenderness_M2'];assert c['status']==status and c['value']==pytest.approx(length/240)
    assert c['display_status']==present_decision(status)['display_status'] and c['next_action']
    assert c['severity']=='success' if length==4450 else c['severity']=='warning'


@pytest.mark.parametrize('origin',['USER_DECLARATION','PROJECT_DOCUMENT','SYNTHETIC_TEST'])
def test_origin_is_distinct_and_never_implies_native_signature(origin):
    a=product_authority(REPO);p=a.packet();p['values'].update(width_mm=800.,depth_mm=800.,axis_basis='RECTANGULAR_LOCAL2_LOCAL3')
    p=apply_review(p,'geometry',{**DECLARATION,'origin':origin},a);m=product_manifest(evaluate_column_product(p,a),a)
    c=next(c for c in m['checks'] if c['id']=='emin_M2')
    assert c['value']==39 and c['origins']==[origin]
    assert next(x for x in m['input_completeness'] if x['field']=='width_mm')['provenance']==origin
    assert m['canonical_rebar_authority']=='NOT_PROVIDED' and not m['real_235_design_ready']


def test_unknown_status_is_not_green():
    assert present_decision('FUTURE_UNKNOWN_OWNER_STATUS')['severity']=='warning'
    assert present_decision('FAIL')['severity']=='danger'


def test_independent_material_reviews_keep_names_draft_and_require_strength_tuple():
    a=product_authority(REPO);p=known_user_draft(a)
    assert p['values']['steel_name']=='S500' and p['values']['concrete_name']=='C35/45' and p['reviews']=={}
    with pytest.raises(ValueError):apply_review(p,'longitudinal_steel',DECLARATION,a)
    p['values']['fcd_mpa']=35/1.5;p['values']['fck_mpa']=35.
    p=apply_review(p,'concrete',DECLARATION,a)
    assert set(p['reviews'])=={'concrete'} and evaluate_column_product(p,a).material_basis is None
    p['values'].update(fyd_mpa=500/1.15);p=apply_review(p,'longitudinal_steel',DECLARATION,a)
    assert set(p['reviews'])=={'concrete','longitudinal_steel'}
    p['values']['aggregate_max_mm']=25.;p=apply_review(p,'aggregate',DECLARATION,a)
    p['values'].update(transverse_steel_name='TEST_TIE',fywk_mpa=500.,fywd_mpa=500/1.15);p=apply_review(p,'transverse_steel',DECLARATION,a)
    assert evaluate_column_product(p,a).material_basis is not None
    p['values']['fcd_mpa']=24.;p=invalidate_changed_reviews(p)
    assert set(p['reviews'])=={'longitudinal_steel','transverse_steel','aggregate'}


def test_geometry_change_invalidates_dependent_cage_review_but_keeps_strengths():
    a=product_authority(REPO);p=declared_packet(a,transverse=True);p['values']['width_mm']=900.
    with pytest.raises(ValueError):validate_packet(p,a)
    p=invalidate_changed_reviews(p)
    assert 'geometry' not in p['reviews'] and 'cage' not in p['reviews'] and 'transverse' not in p['reviews']
    assert 'concrete' in p['reviews'] and 'longitudinal_steel' in p['reviews']


def test_explicit_v1_migration_drops_old_reviews_and_preserves_source_and_values():
    a=product_authority(REPO);p=declared_packet(a)
    old=deepcopy(p);old['schema']='column.product.235.input.v1';old.pop('draft_notes');old.pop('migration')
    new_fields={'action_state_semantics','action_source_ref','step_type','step_number','action_sign_basis','n_bars_dir2','n_bars_dir3'} | {f[0] for f in FIELDS if f[3]=='transverse'}
    for k in new_fields:old['values'].pop(k);old['units'].pop(k)
    old['reviews']={'geometry':old['reviews']['geometry']}
    q=migrate_v1_packet(old,a)
    assert q['reviews']=={} and q['migration']['requires_new_reviews'] and q['values']['width_mm']==800
    assert q['accepted_native_coordinates']==p['accepted_native_coordinates'] and q['values']['n_bars_dir2'] is None
    with pytest.raises(ValueError):migrate_v1_packet({**old,'fake_authority':True},a)
    with pytest.raises(ValueError):migrate_v1_packet({**old,'source_sha256':'WRONG'},a)


def test_run_envelope_is_shared_across_formats_and_stale_revision_rejected():
    app=ColumnWorkspace(REPO);w=app.create();p=declared_packet(app.product_authority)
    s=app.state(dict(workspace_id=w['id'],context='235-product',bundle=p));m=app.calculate(dict(workspace_id=w['id'],revision=s['revision']))
    request=dict(workspace_id=w['id'],revision=s['revision'],result_id=m['result_id'])
    payload=json.loads(app.report({**request,'format':'json'})[0]);html=app.report({**request,'format':'html'})[0].decode();pdf=app.report({**request,'format':'pdf'})[0]
    assert payload['run_envelope']==m['run_envelope'] and payload['result_id']==evaluate_column_product(p,app.product_authority).result_id
    assert m['run_envelope']['workspace_id']==w['id'] and m['run_envelope']['calculation_revision']==s['revision']
    assert m['run_envelope']['build_sha256'] in html and w['id'] in html and pdf.startswith(b'%PDF')
    assert m['run_envelope']['git_head'] is None
    app.state(dict(workspace_id=w['id'],context='reference',bundle=w['default_bundle']))
    assert app.get(w['id']).product_draft==p
    with pytest.raises(ValueError):app.report({**request,'format':'json'})
    s2=app.state(dict(workspace_id=w['id'],context='235-product',bundle=p));m2=app.calculate(dict(workspace_id=w['id'],revision=s2['revision']))
    assert m2['result_id']==m['result_id'] and m2['run_envelope']['calculation_revision']!=m['run_envelope']['calculation_revision']


def test_unsupported_pmm_material_keeps_independent_axial_and_cage_results():
    a=product_authority(REPO);p=declared_packet(a);p['values']['fck_mpa']=37.;p=invalidate_changed_reviews(p);p=apply_review(p,'concrete',DECLARATION,a)
    c=checks(p,a)
    assert c['axial']['status']=='OK' and c['cage']['owner_output']['layout']
    assert c['longitudinal']['status']=='BLOCKED' and c['longitudinal']['blocker_class']=='ENGINE_CAPABILITY'
    assert c['longitudinal']['owner_output']['numerical_status']=='UNSUPPORTED_SECTION_MATERIAL'
