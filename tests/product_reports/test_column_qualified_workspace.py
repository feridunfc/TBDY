"""Real existing engineering owners; native transport ONLY in existing tests."""
from dataclasses import replace
from pathlib import Path
import json
import os
import sys
import pytest

from tests.application import test_column_public_mixed_vertical as vertical
from tbdy_engine.application.column_qualified_workspace import (
    QualifiedColumnChannel, QualifiedColumnScope, exact_data, project_column_view,
)


@pytest.fixture(scope='module')
def qualified_runs():
    results = []
    for spacing in (100., 200.):
        with pytest.MonkeyPatch.context() as mp:
            h = vertical._install(mp)
            contexts = vertical._shear_contexts(h.setup.module)
            contexts['reviewed_column_final_cage_context'] = replace(
                contexts['reviewed_column_final_cage_context'], shear_spacing_mm=spacing,
                review_refs=(f'review:offline-final-cage-spacing:{spacing}',))
            calls = set()
            from functools import wraps
            for name in ('compose_column_longitudinal_runtime', 'run_vs5_column_axial',
                         'evaluate_column_transverse_confinement_bound',
                         'execute_source_bound_fnd_col_2_with_artifact', 'apply_reviewed_vc_to_transverse_input', 'compose_column_p7_runtime'):
                original = getattr(vertical.column, name)
                def instrument(fn):
                    @wraps(fn)
                    def observed(*args, **kwargs):
                        calls.add(fn.__module__+'.'+fn.__name__)
                        return fn(*args, **kwargs)
                    return observed
                mp.setattr(vertical.column, name, instrument(original))
            import tbdy_engine.application.column_vc_runtime as vc_owner
            import tbdy_engine.design.columns.column_longitudinal_production_composition as pmm_owner
            mp.setattr(vc_owner, 'qualify_column_vc', instrument(vc_owner.qualify_column_vc))
            mp.setattr(pmm_owner, 'select_canonical_column_longitudinal_rebar', instrument(pmm_owner.select_canonical_column_longitudinal_rebar))
            project = vertical.project.execute_project(vertical.population._two_column_request(),
                verified_session=h.setup.module._FakeSession(), column_design_basis=vertical._basis(),
                expected_combo_policy=vertical._policy(h.combos),
                reviewed_vs5_column_axial_context=vertical._axial_context(), **contexts)
            scope = QualifiedColumnScope('source-model-ref:public-a5', vertical.MODEL, vertical.EPOCH,
                                         'kN', 'm', project.columns[0].column_shear_evidence.evidence_epoch_id, 'OFFLINE_TEST_LIFECYCLE')
            channel = QualifiedColumnChannel()
            handles = channel.publish(project, scope=scope, label=f'OFFLINE TEST / shear spacing {spacing:g} mm')
            views = [channel.consume({'handle':handle, 'scope_identity':exact_data(scope)}) for handle in handles]
            results.append((project, scope, channel, handles, views, sorted(calls)))
    out = os.environ.get('COLUMN_QUALIFIED_EVIDENCE_DIR')
    if out:
        target = Path(out); target.mkdir(parents=True, exist_ok=True)
        for i, (_, _, _, _, views, calls) in enumerate(results):
            (target/f'owner-run-{i}.json').write_text(json.dumps({'views':views,'observed_owner_calls':calls,'transport':'EXISTING_TEST_TRANSPORT_ONLY','WORKER_ETABS':'NO'},ensure_ascii=False,allow_nan=False,indent=2))
    return results


def test_existing_qualified_full_path_is_consumed(qualified_runs):
    p, scope, channel, handles, views, calls = qualified_runs[0]
    positive, blocked = views
    assert positive['fnd2_status'] == 'READY'
    assert positive['selected_rebar']['authority'] == 'ENGINE_SELECTED_REBAR'
    assert positive['selected_rebar']['as_total_mm2'] == '5026.548245743669'
    assert positive['demand_states']
    assert set(positive['owner_outputs']) >= {'a23_demand_states','longitudinal_selection','longitudinal_runtime',
        'column_axial_vs5','column_shear_p7','transverse_confinement','final_transverse_cage'}
    assert positive['application_status'] == 'APPLICATION_BLOCKED'
    assert any('PROVIDED_ASH_NOT_AVAILABLE' in s for s in positive['application_blockers'])
    assert blocked['selected_rebar'] is None
    assert any('A18:' in s for s in blocked['application_blockers'])
    for owner in ('column_longitudinal_runtime.compose_column_longitudinal_runtime',
                  'vs5_column_axial_program.run_vs5_column_axial',
                  'column_transverse_confinement.evaluate_column_transverse_confinement_bound'):
        assert any(s.endswith(owner) for s in calls)


def test_cage_change_reaches_existing_owner(qualified_runs):
    base, changed = (r[4][0] for r in qualified_runs)
    assert base['result_id'] != changed['result_id']
    before = base['owner_outputs']['transverse_confinement']['data']
    after = changed['owner_outputs']['transverse_confinement']['data']
    assert before['shear_vr_by_direction_kn'] != after['shear_vr_by_direction_kn']
    # Independent fixture law: same cage steel/concrete, doubling shear spacing
    # halves Vs. Vc is retained by its actual existing owner, never this adapter.
    assert before['required_confinement_region_length_mm'] == after['required_confinement_region_length_mm']
    # Independent closed-form reference for this explicit existing fixture;
    # never used in production or supplied as an owner result.
    import math
    fctd = 0.35*math.sqrt(35)/(35/23.3333333333)
    for direction,bw,d in [('DIR2',800.,430.),('DIR3',500.,730.)]:
        vc = .8*.65*fctd*bw*d*(1+.07*3000000/400000)/1000
        asw = 4*math.pi*10**2/4
        assert dict(before['shear_vr_by_direction_kn'])[direction] == pytest.approx(vc+asw/100*365.2173913043*d/1000)
        assert dict(after['shear_vr_by_direction_kn'])[direction] == pytest.approx(vc+asw/200*365.2173913043*d/1000)



@pytest.mark.parametrize('key,value', [('source_model_ref','wrong'),('model_fingerprint','wrong'),
    ('evidence_epoch_id','wrong'),('force_unit','N'),('length_unit','mm'),('shear_evidence_epoch_id','wrong')])
def test_source_epoch_unit_mismatch_rejected(qualified_runs, key, value):
    p, scope, channel, handles, views, calls = qualified_runs[0]
    request = {'handle':handles[0], 'scope_identity':{**exact_data(scope),key:value}}
    with pytest.raises(ValueError): channel.consume(request)
    with pytest.raises(ValueError): channel.publish(p, scope=replace(scope, **{key:value}),label='wrong')


@pytest.mark.parametrize('bad', [{}, {'lineage':'QUALIFIED'}, {'design_ready':True}, {'handle':'missing','scope_identity':{}}])
def test_unsigned_client_authority_cannot_publish(qualified_runs, bad):
    _, scope, channel, _, _, _ = qualified_runs[0]
    with pytest.raises(ValueError): channel.publish(bad, scope=scope,label='unsigned')
    with pytest.raises(ValueError): channel.consume(bad)


def test_owner_selection_continuity_drift_rejected(qualified_runs):
    p, scope, channel, handles, _, _ = qualified_runs[0]
    c = p.columns[0]
    selection = replace(c.longitudinal_selection, selected_rebar=replace(c.selected_rebar, evidence_epoch_id='wrong'))
    broken = replace(c, longitudinal_selection=selection)
    with pytest.raises(ValueError): channel.publish(replace(p, columns=(broken,*p.columns[1:])),scope=scope,label='wrong')


def test_readiness_copy_is_not_owner_binding(qualified_runs):
    p, scope, channel, handles, _, _ = qualified_runs[0]
    c = p.columns[0]
    broken = replace(c,readiness_binding=replace(c.readiness_binding,readiness=replace(c.readiness_binding.readiness)))
    with pytest.raises(ValueError): channel.publish(replace(p, columns=(broken,*p.columns[1:])),scope=scope,label='copy')


def test_unknown_serializable_owner_type_and_nonfinite_rejected():
    for value in (object(), float('nan'), float('inf')):
        with pytest.raises((ValueError,TypeError)): exact_data(value)


@pytest.mark.parametrize('transition', ['context','source','epoch','units','unsigned','edit'])
def test_workspace_invalidates_qualified_result_before_transition(qualified_runs, transition):
    from apps.column_v2.server import ColumnWorkspace
    p, scope, channel, handles, _, _ = qualified_runs[0]
    app=ColumnWorkspace(Path(__file__).resolve().parents[2],qualified_channel=channel)
    w=app.create();request={'handle':handles[0],'scope_identity':exact_data(scope)}
    state=app.state(dict(workspace_id=w['id'],context='qualified',bundle=request))
    result=app.calculate(dict(workspace_id=w['id'],revision=state['revision']))
    if transition=='context': app.state(dict(workspace_id=w['id'],context='235',bundle=None))
    else:
        bad=json.loads(json.dumps(request))
        if transition=='source':bad['scope_identity']['source_model_ref']='wrong'
        elif transition=='epoch':bad['scope_identity']['evidence_epoch_id']='wrong'
        elif transition=='units':bad['scope_identity']['force_unit']='N'
        elif transition=='unsigned':bad['lineage']={'qualified':True}
        else:bad['values']={'nd_n':999.}
        with pytest.raises(ValueError):app.state(dict(workspace_id=w['id'],context='qualified',bundle=bad))
    assert app.get(w['id']).product_calculation is None
    with pytest.raises(ValueError):app.report(dict(workspace_id=w['id'],revision=state['revision'],result_id=result['result_id'],format='json'))


def test_actual_qualified_browser_and_downloads(qualified_runs,tmp_path):
    from threading import Thread
    import subprocess
    from apps.column_v2.server import make_server
    from tbdy_engine.product_reports.column_qualified_report import present_qualified_result
    binary=os.environ.get('COLUMN_V2_BROWSER_BINARY');module=os.environ.get('COLUMN_V2_PLAYWRIGHT_MODULE');node=os.environ.get('COLUMN_V2_BROWSER_NODE')
    if not all((binary,module,node)):pytest.skip('Explicit actual browser profile required.')
    out=Path(os.environ.get('COLUMN_QUALIFIED_CAPTURE_DIR',str(tmp_path)));out.mkdir(parents=True,exist_ok=True)
    channel=QualifiedColumnChannel();handles=[]
    for i,(p,scope,_,_,views,calls) in enumerate(qualified_runs):
        handles.extend(channel.publish(p,scope=scope,label=f'OFFLINE TEST / shear spacing {100 if i==0 else 200} mm'))
    audit=out/'Backend_Execution.jsonl'
    server=make_server(Path(__file__).resolve().parents[2],0,audit_path=audit,qualified_channel=channel)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        args={'url':f'http://127.0.0.1:{server.server_port}','output_dir':str(out),'handles':handles}
        completed=subprocess.run([node,str(Path(__file__).with_name('column_qualified_browser.cjs')),json.dumps(args)],capture_output=True,text=True,timeout=90)
        assert completed.returncode==0,completed.stdout+'\n'+completed.stderr
        for name,index in [('Baseline',0),('Changed_Cage',2),('Owner_Blocked',1)]:
            downloaded=json.loads((out/(name+'.json')).read_text())
            view=channel.consume({'handle':handles[index],'scope_identity':exact_data(qualified_runs[1 if index==2 else 0][1])})
            envelope=downloaded.pop('run_envelope')
            assert envelope['result_id']==view['result_id'] and envelope['calculation_scope']=='qualified'
            assert envelope['input_sha256']==view['input_sha256']
            assert downloaded==present_qualified_result(view)
        events=server.application.events
        assert len([e for e in events if e['event']=='QUALIFIED_OWNER_RESULT_CONSUMED'])==3
        assert all(e['native_calls']==0 for e in events if e['event']=='QUALIFIED_OWNER_RESULT_CONSUMED')
        (out/'Observed_Owner_Calls.json').write_text(json.dumps([{'variant':i,'calls':r[5],'selected_artifact_id':r[4][0]['result_id']} for i,r in enumerate(qualified_runs)],indent=2))
    finally:
        server.shutdown();server.server_close();thread.join(5);server.application.audit.close()


@pytest.mark.parametrize('drift',['demand','snapshot','component'])
def test_causal_owner_payload_drift_rejected(qualified_runs, drift):
    p,scope,channel,_,_,_=qualified_runs[0];c=p.columns[0]
    if drift=='demand':broken=replace(c,a23_demand_states=(replace(c.a23_demand_states[0],nd_compression_n=99.),*c.a23_demand_states[1:]))
    elif drift=='component':broken=replace(c,transverse_confinement=replace(c.transverse_confinement,component_id='other'))
    else:
        execution=c.fnd_col_2_execution
        broken=replace(c,fnd_col_2_execution=replace(execution,snapshot=replace(execution.snapshot,plan_identity='wrong')))
    with pytest.raises(ValueError):channel.publish(replace(p,columns=(broken,*p.columns[1:])),scope=scope,label='wrong')


def test_all_fourteen_product_cards_project_actual_retained_owners(qualified_runs):
    from tbdy_engine.product_reports.column_qualified_report import present_qualified_result, QUALIFIED_CONTROL_PATHS
    m=present_qualified_result(qualified_runs[0][4][0]);cards={c['id']:c for c in m['product_controls']}
    assert set(cards)==set(QUALIFIED_CONTROL_PATHS) and len(cards)==14
    for name in ('topology','design_actions','stability','local_sway','second_order','longitudinal','detailing','cage','confinement','axial','shear','vc','readiness'):
        assert cards[name]['output'] is not None, name
        assert cards[name]['owner_path']
    assert cards['limited_shear']['status']=='BLOCKED' and cards['limited_shear']['blocker_class']=='DATA'
    assert cards['detailing']['status']=='FINAL_DETAILING_REQUIRED'
    assert cards['stability']['output'][0]['stability_result'] is not None
    assert m['input_sha256'] and cards['readiness']['status']=='READY'
    blocked=present_qualified_result(qualified_runs[0][4][1])
    assert next(c for c in blocked['product_controls'] if c['id']=='topology')['output'] is not None


def test_actual_canonical_selection_accepts_source_bound_a35_review_without_native_call(qualified_runs):
    from tbdy_engine.application.column_longitudinal_detailing import ReviewedColumnDetailingEvidence, detailing_facts_digest, materialize_selected_column_longitudinal_detailing, DETAILING_FAILED
    from tbdy_engine.regulatory.column_detailing_checks import SOURCE_HASHES
    from tbdy_engine.integration.etabs_design_lineage import DESIGN_RESULT_REF_PREFIX, DESIGN_LINEAGE_REF_PREFIX
    from tests.regulatory.test_column_detailing_checks import complete_facts
    c=qualified_runs[0][0].columns[0];s=c.selected_rebar;material=c.longitudinal_runtime.bound_design_basis.material_context
    candidate=s.selected_candidate
    facts=complete_facts(candidate,float(candidate.as_total_mm2)/float(candidate.rho))
    height=c.free_length.free_length_ln_mm
    facts=replace(facts,lap=replace(facts.lap,clear_height_mm=height,min_dimension_mm=500.,rows=tuple(replace(row,start_mm=height/3,end_mm=2*height/3) for row in facts.lap.rows),bond=replace(facts.lap.bond,fyd_mpa=material.material.fyd_mpa)),
        anchorage=replace(facts.anchorage,bond=replace(facts.anchorage.bond,fyd_mpa=material.material.fyd_mpa)),
        continuity=replace(facts.continuity,clear_height_mm=height,covered_height_mm=height))
    evidence=ReviewedColumnDetailingEvidence(s.component_id,s.selected_rebar_ref,s.model_fingerprint,s.evidence_epoch_id,s.material_context_ref,
        next(x for x in s.provenance_refs if x.startswith(DESIGN_RESULT_REF_PREFIX)),next(x for x in s.provenance_refs if x.startswith(DESIGN_LINEAGE_REF_PREFIX)),SOURCE_HASHES,
        'TBDY_HIGH_DUCTILITY_RECTANGULAR_SINGLE_DEFORMED_BARS','OFFLINE TEST REVIEW','2026-10-17T08:00:00+03:00',('SYNTHETIC_DETAIL_DRAWING_NOT_PROJECT_ACCEPTANCE',),facts,detailing_facts_digest(facts),material)
    result=materialize_selected_column_longitudinal_detailing(s,reviewed_evidence=evidence)
    # The actual PMM owner selected four 40-mm corner bars. Their wide
    # perimeter gaps do not satisfy A35 continuity; selection is not detailing.
    assert not result.complete and result.status==DETAILING_FAILED
    assert all(x.resolved for x in result.outcomes)
    assert result.outcomes[-1].status=='FAIL'
    assert result.engine_selected_rebar is s
    if os.environ.get('COLUMN_QUALIFIED_EVIDENCE_DIR'):
        dest=Path(os.environ['COLUMN_QUALIFIED_EVIDENCE_DIR'])/'A35_Canonical_Selected_Detailing.json'
        dest.write_text(json.dumps({'origin':'OFFLINE_TEST_LIFECYCLE','WORKER_ETABS':'NO','result':exact_data(result),'reviewed_evidence':exact_data(evidence),'real_235_design_acceptance':False},ensure_ascii=False,indent=2))
