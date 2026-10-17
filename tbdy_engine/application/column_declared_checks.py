"""Explicitly declared local-section checks; never native lineage or readiness.

Only this adapter constructs inputs. Numerical rules stay with their existing
owners. The two I/J rows share a declared case/step, not independently maximized
force envelopes. Each output retains its exact row and input source.
"""
from dataclasses import asdict
from math import hypot
from tbdy_engine.design.columns.rebar_layout import ColumnRebarGeometryInputs, build_rectangular_column_rebar_geometry_candidate
from tbdy_engine.design.columns.section_capacity import ColumnSectionCapacityError, ColumnSectionMaterial, build_interaction_envelope_at_axial_force, radial_moment_capacity
from tbdy_engine.regulatory.column_axial_dual_code import Ts500ColumnAxialExecutionInput, evaluate_ts500_column_axial, TS500_RULE_ID, TS500_RULE_VERSION
from tbdy_engine.regulatory.contracts import RuleInstanceId, Grain
from tbdy_engine.regulatory.kernel import RuleExecutionEnvelope
from tbdy_engine.regulatory.column_transverse_confinement import ColumnTransverseConfinementInput, TransverseDirectionFacts, evaluate_column_transverse_confinement


def evaluate_declared_checks(packet):
    v,r=packet['values'],packet['reviews'];out={}
    owners={
        'axial':'tbdy_engine.regulatory.column_axial_dual_code.evaluate_ts500_column_axial',
        'longitudinal':'tbdy_engine.design.columns.section_capacity.build_interaction_envelope_at_axial_force / radial_moment_capacity',
        'cage':'tbdy_engine.design.columns.rebar_layout.build_rectangular_column_rebar_geometry_candidate',
        'confinement':'tbdy_engine.regulatory.column_transverse_confinement.evaluate_column_transverse_confinement'}
    needs={'axial':('geometry','concrete','actions'),'cage':('geometry','cage'),
           'longitudinal':('geometry','concrete','longitudinal_steel','cage','actions'),
           'confinement':('geometry','concrete','transverse_steel','cage','transverse_cage','transverse','actions')}
    for key,groups in needs.items():
        missing=tuple(g+' review' for g in groups if g not in r)
        out[key]={'owner':owners[key],'status':'BLOCKED','dependencies':missing,
            'blocker_class':'DATA' if missing else None,'closure_owner':'Proje girdilerini sağlayan mühendis',
            'origins':tuple(dict.fromkeys(r[g]['origin'] for g in groups if g in r)),
            'trace':'Beyan esaslı kesit hesabı; USER_PROVIDED_REBAR; native/current analiz yetkisi değildir.'}
    states=[]
    if 'actions' in r:
        for end in ('I','J'):
            slot=end.lower()
            states.append({'state_id':end,'case':v['output_case'],'step_type':v['step_type'],'step_number':v['step_number'],
                'native_slot_label_only':end,'physical_end':None,'station_m':v['station_'+slot+'_m'],
                'nd_kn':v['nd_'+slot+'_kn'],'m2_knm':v['m2_'+slot+'_knm'],'m3_knm':v['m3_'+slot+'_knm'],
                'state_semantics':v['action_state_semantics'],'sign_basis':v['action_sign_basis'],'source_ref':v['action_source_ref'],
                'source_sha256':packet['source_sha256'],'analysis_result_epoch':None,
                'scope':'DECLARED_CASE_STEP_TWO_STATIONS_ONLY'})
        out['design_actions']={'owner':'column_declared_checks:explicit_concurrent_rows','status':'CALCULATED_PROJECT_REVIEW',
            'trace':'I ve J, aynı beyan edilen case/step içindeki ayrı eşzamanlı N-M2-M3 satırlarıdır. Proje geneli governing değildir.',
            'owner_output':{'states':states},'origins':(r['actions']['origin'],)}
    if not out['axial']['dependencies']:
        envelope=RuleExecutionEnvelope('DECLARED_235_ONLY',RuleInstanceId.build(rule_id=TS500_RULE_ID,grain=Grain.COMPONENT,scope_ref='235'),TS500_RULE_ID,TS500_RULE_VERSION,())
        rows=[]
        for state in states:
            if state['nd_kn']<0:
                rows.append({'state':state,'status':'NOT_APPLICABLE','reason':'TS500 compression bound; this declared state is tension.'});continue
            result=evaluate_ts500_column_axial(Ts500ColumnAxialExecutionInput(envelope,v['width_mm']/1000,v['depth_mm']/1000,v['fck_mpa'],state['nd_kn'],v['fck_mpa']/v['fcd_mpa'],'USER_DECLARED','USER_DECLARED_RECTANGLE',(r['concrete']['reference'],state['source_ref'])))
            rows.append({'state':state,**result.as_dict()})
        applicable=[x for x in rows if x['status']!='NOT_APPLICABLE']
        governing=max(applicable,key=lambda x:x['ratio']) if applicable else None
        out['axial'].update(status=governing['status'] if governing else 'NOT_APPLICABLE',value=governing['value'] if governing else None,
            limit=governing['limit'] if governing else None,unit='kN',governing=governing['state']['state_id'] if governing else None,
            decision_reason='TS500 beyan edilmiş basınç Nd sınırı: '+str(governing['value'])+' ≤ '+str(governing['limit'])+' kN; '+governing['status'] if governing else 'Beyan edilmiş iki durum da çekme; bu basınç sınırı uygulanmaz.',
            owner_output={'states':rows},source='TS500 7.4.1; TS500 Nd (TBDY Ndm değildir)',formula='Nd ≤ 0.90 Ac fcd',invoked_owners=(owners['axial'],))
    layout=None
    if not out['cage']['dependencies']:
        if any(not 2<=v[k]<=100 for k in ('n_bars_dir2','n_bars_dir3')):raise ValueError('Yüz adedi desteklenen [2,100] aralığında olmalı.')
        layout=build_rectangular_column_rebar_geometry_candidate(ColumnRebarGeometryInputs(v['width_mm'],v['depth_mm'],v['clear_cover_mm'],v['tie_diameter_mm']),diameter_mm=v['longitudinal_diameter_mm'],n_bars_dir2=v['n_bars_dir2'],n_bars_dir3=v['n_bars_dir3'])
        if layout.bar_count!=v['longitudinal_bar_count']:
            raise ValueError('Açık yüz adetleri ile toplam boyuna adet uyuşmuyor.')
        out['cage'].update(status='CALCULATED_PROJECT_REVIEW',value=layout.as_total_mm2,unit='mm2',owner_output={'role':'USER_PROVIDED_REBAR','layout':asdict(layout)},invoked_owners=(owners['cage'],))
    if not out['longitudinal']['dependencies']:
        try:
            material=ColumnSectionMaterial(v['fck_mpa'],v['fcd_mpa'],v['fyd_mpa'])
        except ColumnSectionCapacityError as exc:
            material=None
            out['longitudinal'].update(status='BLOCKED',blocker_class='ENGINE_CAPABILITY',decision_reason=str(exc),
                owner_output={'numerical_status':'UNSUPPORTED_SECTION_MATERIAL','error':str(exc)})
        if material is not None:
            rows=[]
            for state in states:
                envelope=build_interaction_envelope_at_axial_force(width_mm=v['width_mm'],depth_mm=v['depth_mm'],bars=layout.bars,material=material,target_n_compression_n=state['nd_kn']*1000)
                if envelope.status!='PROVEN':
                    rows.append({'state':state,'status':'BLOCKED','blocker_class':'ENGINE_CAPABILITY','numerical_status':envelope.status,'utilization':None,'capacity_knm':None});continue
                radial=radial_moment_capacity(envelope,demand_m2_nmm=state['m2_knm']*1e6,demand_m3_nmm=state['m3_knm']*1e6)
                demand=hypot(state['m2_knm'],state['m3_knm'])
                zero=radial.status=='ZERO_MOMENT_DEMAND'
                capacity=None if zero else radial.capacity_nmm/1e6
                ratio=0.0 if zero else demand/capacity if capacity and capacity>0 else None
                rows.append({'state':state,'status':'BLOCKED' if ratio is None else 'OK' if ratio<=1 else 'FAIL','numerical_status':radial.status,
                    'utilization':ratio,'capacity_knm':capacity,'demand_knm':demand,'angle_step_deg':envelope.angle_step_deg})
            worst=max(rows,key=lambda x:float('inf') if x['utilization'] is None else x['utilization'])
            out['longitudinal'].update(status=worst['status'],blocker_class='ENGINE_CAPABILITY' if worst['status']=='BLOCKED' else None,value=worst['utilization'],limit=1.,governing=worst['state']['state_id'],
                decision_reason='Yalnız girilen N-M2-M3 kümesi: η='+str(worst['utilization'])+'; sınır 1.0; sayısal durum '+worst['numerical_status'],
                owner_output={'states':rows,'layout':asdict(layout),'material':asdict(material),'role':'USER_PROVIDED_REBAR'},
                trace='Girilen işaretli N-M2-M3 için kesit kapasitesi; ikinci mertebe/minimum moment uygulanmış talep olarak kabul edilmez. Yalnız girilen iki durum yönetenidir.',
                source='Mevcut TS500 strain-compatibility / 72 açılı zarf / radyal owner',invoked_owners=(owners['longitudinal'],))
    if not out['confinement']['dependencies']:
        refs=tuple(dict.fromkeys(r[g]['reference'] for g in needs['confinement']))
        dirs=tuple(TransverseDirectionFacts(direction='DIR'+str(i),confined_core_width_bk_mm=v[f'bk{i}_mm'],provided_ash_mm2=v[f'ash{i}_mm2'],horizontal_leg_spacing_mm=v[f'leg_spacing{i}_mm'],source_refs=refs) for i in (2,3))
        request=ColumnTransverseConfinementInput(component_id='235',story='USER_DECLARED',section='USER_DECLARED_RECTANGLE',
            high_ductility_applies=v['high_ductility'],limited_ductility_applies=v['limited_ductility'],ts500_general_applies=v['ts500_general'],cantilever_column=v['cantilever'],
            clear_height_mm=v['transverse_clear_height_mm'],width_mm=v['width_mm'],depth_mm=v['depth_mm'],gross_area_ac_mm2=v['width_mm']*v['depth_mm'],confined_core_area_ack_mm2=v['core_area_mm2'],
            fck_mpa=v['fck_mpa'],fywk_mpa=v['fywk_mpa'],axial_design_force_nd_n=max(0.,max(x['nd_kn'] for x in states))*1000,
            transverse_diameter_mm=v['tie_diameter_mm'],confinement_spacing_mm=v['confinement_spacing_mm'],middle_spacing_mm=v['middle_spacing_mm'],provided_confinement_region_length_mm=v['confinement_length_mm'],
            directions=dirs,arrangement=None,source_refs=refs,restrained_longitudinal_bar_spacing_mm=v['restrained_bar_spacing_mm'],fywd_mpa=v['fywd_mpa'],shear_spacing_mm=v['shear_spacing_mm'])
        result=evaluate_column_transverse_confinement(request,selected_rebar=None)
        checks=[c.as_dict() for c in result.checks];statuses={x['status'] for x in checks}
        status='FAIL' if 'FAIL' in statuses else 'PARTIAL' if statuses.intersection({'BLOCKED','NOT_EVALUATED','NOT_CHECKED'}) else 'CALCULATED_PROJECT_REVIEW'
        out['confinement'].update(status=status,owner_output={'request':asdict(request),'checks':checks,'blocking_reasons':result.blockers},
            trace='Saf alt kontroller hesaplandı. Canonical selected rebar isteyen çap/nihai kesme alt kontrolleri kendi BLOCKED durumunu korur.',invoked_owners=(owners['confinement'],))
    return out
