"""Current 235 cannot acquire missing dimensions or design forces from accepted facts."""
from datetime import datetime, timezone
from pathlib import Path
from copy import deepcopy
from tbdy_engine.application.column_product_workspace import apply_review, evaluate_column_product, FIELDS
from tbdy_engine.product_reports.column_product_report import (
 product_authority, product_input_authority_matrix, product_manifest, render_product_html, render_product_pdf)
ROOT=Path(__file__).resolve().parents[2]

def test_native_facts_do_not_become_missing_geometry():
 a=product_authority(ROOT);p=a.packet();m=product_input_authority_matrix(p,a)
 assert len(m['rows'])==len(FIELDS)
 assert all(row['value'] is None for row in m['rows'])
 assert m['first_control']['missing_fields']==['width_mm','depth_mm','axis_basis']
 assert m['first_control']['source_qualification']=='BLOCKED_NOT_COMPUTED'
 assert m['accepted_native_facts'][0]['value']=='Column_80x80'
 assert m['accepted_native_facts'][1]['value']==0.03413333333333332
 assert m['accepted_native_facts'][-1]['value']['point_name']=='758'
 assert m['current_analysis_result_epoch'] is None and m['native_getters_executed']==0
 result=product_manifest(evaluate_column_product(p,a),a)
 assert result['input_authority_matrix']==m and not result['invoked_owners']

def test_project_review_source_and_existing_owner_recompute():
 a=product_authority(ROOT);p=a.packet()
 p['values'].update(width_mm=500.,depth_mm=800.,axis_basis='RECTANGULAR_LOCAL2_LOCAL3')
 p=apply_review(p,'geometry',dict(reviewer='OFFLINE FIXTURE',
     reference='SYNTHETIC-TEST-NOT-FACTUAL',
     reviewed_at=datetime.now(timezone.utc).isoformat(),origin='SYNTHETIC_TEST'),a)
 r=product_manifest(evaluate_column_product(p,a),a)
 first=r['input_authority_matrix']['first_control']
 assert first['computed_values']=={'emin_M2':39.0,'emin_M3':30.0}
 assert first['source_qualification']=='DECLARATION_ONLY'
 assert set(r['invoked_owners'])=={'ts500_minimum_eccentricity_mm'}
 assert not r['real_235_design_ready']
 assert 'İlk hesap için gereken gerçek veri' in render_product_html(r)
 assert render_product_pdf(r).startswith(b'%PDF')
 p2=deepcopy(p);p2['values']['width_mm']=800.;p2['reviews'].pop('geometry')
 r2=product_manifest(evaluate_column_product(p2,a),a)
 assert r2['result_id']!=r['result_id']
 assert r2['input_authority_matrix']['first_control']['computed_values'] is None

def test_project_document_review_not_native_promotion():
 a=product_authority(ROOT);p=a.packet()
 p['values'].update(width_mm=500.,depth_mm=800.,axis_basis='RECTANGULAR_LOCAL2_LOCAL3')
 p=apply_review(p,'geometry',dict(reviewer='OFFLINE TEST',reference='PROJECT-EXAMPLE',
      reviewed_at=datetime.now(timezone.utc).isoformat(),origin='PROJECT_DOCUMENT'),a)
 m=product_input_authority_matrix(p,a)
 assert m['first_control']['source_qualification']=='PROJECT_REVIEW_LEAF_ONLY'
 assert m['first_control']['minimum_user_request']==[]
 row=next(x for x in m['rows'] if x['field']=='width_mm')
 assert row['source_kind']=='PROJECT_REVIEWED_INPUT' and row['source_ref']=='PROJECT-EXAMPLE'
 assert row['source_sha256']==a.source_sha256
 assert m['accepted_native_facts'][0]['source_kind']=='ACCEPTED_NATIVE_FACT_LIMITED_SCOPE'
 assert m['real_235_full_design_ready'] is False
