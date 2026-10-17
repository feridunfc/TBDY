"""One typed offline product evaluation → HTML/PDF/JSON. No formulas here."""
from dataclasses import asdict
from tbdy_engine.product_reports.column_decision_presenter import present_decision, displayed
from hashlib import sha256
from html import escape
from pathlib import Path
from io import BytesIO
from types import SimpleNamespace
import json

from tbdy_engine.application.column_product_workspace import ColumnProductAuthority, ColumnProductEvaluation, FIELDS, canonical
from tbdy_engine.product_reports.column_v1_report import PINS
from tbdy_engine.product_reports.column_v2_report import column_235_manifest, section_svg
from tbdy_engine.application.column_235_coordinate_evidence import ADOPTION_NAME, ADOPTION_SHA256
from tbdy_engine.product_reports.slice_report_contribution import ReportField, ReportCalculation, SliceReportContribution


def product_authority(repo):
    evidence=column_235_manifest(repo);original={};adoptions={}
    for role in ('assignment','property'):
        name,pin=PINS[role];raw=(repo/'docs'/name).read_bytes()
        if sha256(raw).hexdigest()!=pin:raise ValueError('Kabul edilmiş adoption baytları farklı.')
        doc=json.loads(raw);o=doc['original']
        original[role]={'name':o['name'],'json_sha256':o['whole_json_sha256'],'sidecar_sha256':o['sidecar_bytes_sha256'],
            'HEAD':o['capture_HEAD'],'TREE':o['capture_TREE'],'finished_utc':o['finished_utc']}
        adoptions[role]={'name':name,'sha256':pin}
    o=evidence['coordinate_provenance']
    original['coordinates']={'name':o['name'],'json_sha256':o['whole_json_sha256'],'sidecar_sha256':o['sidecar_bytes_sha256'],
        'HEAD':o['capture_HEAD'],'TREE':o['capture_TREE'],'finished_utc':o['finished_utc']}
    adoptions['coordinates']={'name':ADOPTION_NAME,'sha256':ADOPTION_SHA256}
    epoch='accepted-factual-receipt:'+original['property']['json_sha256']
    return ColumnProductAuthority(evidence['candidate_sha256'],evidence['historical_sha256'],epoch,evidence,original,adoptions)


def product_drawing(packet, layout=None):
    v=packet['values']
    if 'geometry' not in packet['reviews']:return ''
    # Explicit reviewed dimensions only. This is the existing presentation helper.
    candidate=None if layout is None else SimpleNamespace(bars=tuple(SimpleNamespace(**b) for b in layout['bars']))
    return section_svg(SimpleNamespace(width_mm=v['width_mm'],depth_mm=v['depth_mm']),candidate).replace(f"b = {v['width_mm']:.6g} mm",f"b = {v['width_mm']/10:.6g} cm").replace(f"h = {v['depth_mm']:.6g} mm",f"h = {v['depth_mm']/10:.6g} cm").replace('Motorun donatı adayı; nihai donatı değildir','USER_PROVIDED_REBAR; beyan edilen çevre düzeni')




def product_input_authority_matrix(packet, authority):
    """Read-only source/owner/closure map for validated Column 235 packet.

    No section-name, I22/I33, coordinate, historical force or user draft is
    promoted to current native geometry/material/design authority.
    """
    need=('width_mm','depth_mm','axis_basis')
    own={
        'geometry':'tbdy_engine.design.columns.minimum_eccentricity.ts500_minimum_eccentricity_mm',
        'slenderness':'tbdy_engine.design.columns.slenderness.evaluate_ts500_column_slenderness',
        'materials':'tbdy_engine.application.column_design_basis.ReviewedColumnDesignBasis',
        'actions':'tbdy_engine.application.column_a23_design_demands / CURRENT_B5_B6_REQUIRED',
        'cage':'tbdy_engine.application.column_final_cage / ENGINE_SELECTED_REBAR_REQUIRED',
    }
    closure={
        'geometry':'Project drawing with reviewed b/h and explicit local2/local3 convention',
        'slenderness':'Project-reviewed independent ln/k/restraint/sway/moment-ratio and geometry',
        'materials':'Reviewed design strengths plus separate factual native section/material binding',
        'actions':'Current 61FA signed co-occurring case/combo/station N-M2-M3-V2-V3 + epoch/B5/B6',
        'cage':'User-provided cage is not ENGINE_SELECTED_REBAR or final detailing',
    }
    controls={
        'geometry':['emin_M2','emin_M3','slenderness_M2','slenderness_M3'],
        'slenderness':['slenderness_M2','slenderness_M3'],
        'materials':['material'], 'actions':['design_actions','longitudinal','axial','shear','vc'],
        'cage':['cage','confinement','detailing'],
    }
    for group in ('concrete','longitudinal_steel','transverse_steel','aggregate'):
        own[group]=own['materials'];closure[group]=closure['materials'];controls[group]=controls['materials']
    own['transverse']='tbdy_engine.regulatory.column_transverse_confinement.evaluate_column_transverse_confinement'
    closure['transverse']='Independent reviewed physical transverse dimensions and applicability'
    controls['transverse']=['confinement']
    for group,original in [('shear_actions','actions'),('transverse_cage','cage')]:
        own[group]=own[original];closure[group]=closure[original];controls[group]=controls[original]
    values,reviews=packet['values'],packet['reviews']
    rows=[]
    for name,label,unit,group,kind in FIELDS:
        review=reviews.get(group);value=values[name]
        source=({'PROJECT_DOCUMENT':'PROJECT_REVIEWED_INPUT',
                 'USER_DECLARATION':'USER_DECLARATION_NOT_PROJECT_VERIFIED',
                 'SYNTHETIC_TEST':'SYNTHETIC_TEST_ONLY'}[review['origin']]
                if review else 'UNREVIEWED_USER_DRAFT' if value is not None else 'NOT_PROVIDED')
        rows.append({
            'field':name,'label':label,'unit':unit,'value':value,'source_kind':source,
            'display_unit':displayed(value,unit)[1],
            'display_value':displayed(value,unit)[0],
            'source_ref':review['reference'] if review else None,
            'source_sha256':review['source_sha256'] if review else None,
            'input_sha256':review['input_sha256'] if review else None,
            'review_group':group,'reviewed':review is not None,
            'existing_owner':own[group],'owner_required_input':name,
            'required_for_controls':controls[group],
            'required_for_first_control':name in need,
            'missing_authority':None if review else closure[group],
            'closure':closure[group],
            'user_request':label+' (cm; mevcut kanonik giriş '+unit+')' if value is None and unit in {'mm','m'} else label+' ('+unit+')' if value is None else None,
        })
    facts=[]
    native=authority.evidence; pins=authority.adoption_pins
    for field,value,unit,role in [
        ('section_assignment',native['section'],'-','assignment'),
        ('I22',native['I22']['value'],'m^4','property'),
        ('I33',native['I33']['value'],'m^4','property'),
    ]:
        facts.append({'field':field,'value':value,'unit':unit,
             'source_kind':'ACCEPTED_NATIVE_FACT_LIMITED_SCOPE',
             'source_ref':pins[role]['name'],'source_sha256':pins[role]['sha256']})
    for point in native['current_point_coordinates']:
        facts.append({'field':point['native_slot']+'_Global_xyz',
            'value':{'point_name':point['point_name'],'X':point['X'],'Y':point['Y'],'Z':point['Z']},
            'unit':'m','source_kind':'ACCEPTED_NATIVE_FACT_LIMITED_SCOPE',
            'source_ref':pins['coordinates']['name'],
            'source_sha256':pins['coordinates']['sha256']})
    missing=[k for k in need if values[k] is None]
    review=reviews.get('geometry')
    requests=[next(row['user_request'] for row in rows if row['field']==k) for k in missing]
    if review is None:
        requests.append('Proje çizimi referansı, reviewer, timezone içeren review tarihi, PROJECT_DOCUMENT kökeni')
    elif review['origin']!='PROJECT_DOCUMENT':
        requests.append('Bu beyanı gerçek proje çizimine bağlayan PROJECT_DOCUMENT review gereklidir')
    first={'ids':['emin_M2','emin_M3'],
       'owner':own['geometry'],'required_field_names':list(need),
       'required_group_review':'geometry','missing_fields':missing,
       'missing_group_review':review is None,'minimum_user_request':requests,
       'source_qualification':('PROJECT_REVIEW_LEAF_ONLY'
            if review is not None and review['origin']=='PROJECT_DOCUMENT'
            else 'DECLARATION_ONLY' if review else 'BLOCKED_NOT_COMPUTED'),
       'computed_values':None,
       'not_authorized':['NATIVE_GETRECTANGLE','CURRENT_DESIGN_FORCES','FULL_235_DESIGN']}
    return {'schema':'column.product.235.input-authority-matrix.v1',
        'project_id':packet['project_id'],'component_id':packet['component_id'],
        'candidate_source_sha256':authority.source_sha256,
        'historical_source_sha256':authority.historical_sha256,
        'current_analysis_result_epoch':None,'rows':rows,'accepted_native_facts':facts,
        'first_control':first,
        'blocked_production':[
            {'id':'design_actions','reason':closure['actions']},
            {'id':'stability','reason':'M6-B full-story modal stability action authority OPEN'},
            {'id':'longitudinal','reason':'FND2/B6 and canonical ENGINE_SELECTED_REBAR missing'},
            {'id':'confinement','reason':'Canonical selection, qualified cage and lineage missing'}],
        'real_235_full_design_ready':False,'native_getters_executed':0,'selection':'NOT_READ'}

def product_manifest(evaluation: ColumnProductEvaluation, authority):
    p=evaluation.input_packet;checks=[];contributions=[]
    matrix=product_input_authority_matrix(p,authority)
    numeric={c.id:c.value for c in evaluation.controls if c.id in {'emin_M2','emin_M3'} and c.value is not None}
    matrix['first_control']['computed_values']=numeric or None
    cage=next((c for c in evaluation.controls if c.id=='cage'),None)
    layout=None if cage is None or cage.owner_output is None else cage.owner_output.get('layout')
    synthetic=any(r['origin']=='SYNTHETIC_TEST' for r in p['reviews'].values())
    for c in evaluation.controls:
        f=(ReportField('value','Sonuç',c.value,c.unit),ReportField('limit','Sınır',c.limit,c.unit,role='LIMIT'),ReportField('status','Motor / gate durumu',c.status,role='STATUS'))
        calc=() if c.value is None else (ReportCalculation(c.id,c.title,c.formula or None,
            inputs=(ReportField('input_sha256','Girdi kimliği',evaluation.input_sha256,role='IDENTITY'),),outputs=f,
            authority_refs=(c.source,) if c.source else (),evidence_refs=(evaluation.input_sha256,)),)
        contrib=SliceReportContribution('COLUMN-235-'+c.id,c.title,'COMPOSITE','BLOCKED' if c.status=='BLOCKED' else 'PARTIAL','COLUMN','235',summary_fields=f,calculations=calc,
            evidence_refs=(evaluation.input_sha256,),warnings=c.dependencies)
        contributions.append(contrib.as_dict())
        states=(c.owner_output or {}).get('states',[])
        governing=next((x['state'] for x in states if isinstance(x,dict) and isinstance(x.get('state'),dict) and x['state'].get('state_id')==c.governing),{})
        subchecks=[]
        for raw in (c.owner_output or {}).get('checks',[]):
            subchecks.append({**raw,**present_decision(raw['status']),'display_value':displayed(raw.get('value'),raw.get('unit') or '-')[0],
                'display_limit':displayed(raw.get('limit'),raw.get('unit') or '-')[0],'display_unit':displayed(raw.get('value'),raw.get('unit') or '-')[1]})
        checks.append({'subchecks':subchecks,**asdict(c),**present_decision(c.status),
            'display_value':displayed(c.value,c.unit)[0],'display_limit':displayed(c.limit,c.unit)[0],'display_unit':displayed(c.value,c.unit)[1],
            'origins':list(c.origins),
            'reason':' · '.join(c.dependencies) if c.dependencies else c.decision_reason or c.trace or 'Mevcut owner değerlendirildi; tam kolon readiness değildir.',
            'governing_case':governing.get('case'),'governing_end':governing.get('native_slot_label_only'),'station_m':governing.get('station_m'),
            'governing_step_type':governing.get('step_type'),'governing_step_number':governing.get('step_number'),'governing_scope':'DECLARED_INPUT_STATES_ONLY' if governing else None})
    return {'schema_version':'column.product.235.result.v2','context':'B-BLOK-235','title':'SENTETİK TEST / gerçek 235 hesabı değildir' if synthetic else 'B-BLOK / Kolon 235 çalışma raporu',
        'data_provenance':'SYNTHETIC_TEST' if synthetic else 'ACCEPTED_NATIVE_FACTS_WITH_PROJECT_DECLARATIONS',
        'component_id':'235','section':authority.evidence['section'],'status':'OFFLINE_PARTIAL' if evaluation.invoked_owners else 'BLOCKED_MISSING_REVIEWED_INPUTS',
        'result_id':evaluation.result_id,'input_sha256':evaluation.input_sha256,'input_packet':p,
        'native_evidence':authority.evidence,'candidate_sha256':authority.source_sha256,'historical_sha256':authority.historical_sha256,
        'evidence_epoch':authority.evidence_epoch,'current_analysis_result_epoch':None,'session_connection':'NOT_OBSERVED',
        'checks':checks,'contributions':contributions,'section_svg':product_drawing(p,layout),
        'input_authority_matrix':matrix,
        'invoked_owners':evaluation.invoked_owners,'typed_owner_outputs':{'slenderness':None if evaluation.slenderness is None else asdict(evaluation.slenderness),
            'material_basis':None if evaluation.material_basis is None else asdict(evaluation.material_basis)},
        'input_completeness':[{ 'field':k,'label':label,'unit':unit,'value':p['values'][k],'group':group,
            'provenance':p['reviews'][group]['origin'] if group in p['reviews'] else 'UNREVIEWED_USER_DRAFT' if p['values'][k] is not None else 'NOT_PROVIDED',
            'review':p['reviews'].get(group)} for k,label,unit,group,_ in FIELDS],
        'canonical_rebar_authority':'NOT_PROVIDED','user_cage_role':'USER_PROVIDED_REBAR' if 'cage' in p['reviews'] else 'NOT_PROVIDED',
        'real_235_design_ready':False,'global_delta':'NOT_PROVEN','M6_B':'OPEN','R2_RERUN_READY':False,
        'scope':[
            '235 native kesit ataması ve I22/I33 kabul edilmiş acquisition kapsamındadır. Güncel ETABS bağlantısı gözlenmedi.',
            'Review girdileri kendi USER_DECLARATION / PROJECT_DOCUMENT / SYNTHETIC_TEST kökeniyle taşınır; native olgu, current B5/B6 veya imza doğrulaması değildir.',
            'Beyan edilen N-M2-M3 ve açık yerleşim yeterliyse mevcut kapasite owner PMM hesaplar. Bu hesap minimum moment/ikinci mertebe talebi veya native tasarım onayı değildir.',
            'Narinlik motor sonucu beyan edilen ln/k/ötelenme sınıfı koşulludur; A17/M6-B/whole-system kapanışı değildir.',
            'I/J satırları case/step/station ve işaret sözleşmesiyle ayrı tutulur. Yöneten sonuç yalnız girilen durum kümesine aittir; fiziksel alt/üst eşlemesi yapılmaz.',
            'Donatı USER_PROVIDED_REBAR review olabilir; ENGINE_SELECTED_REBAR/final/as-built yapılmaz.',
            'FC09 historical sonuçlar 61FA current source’a taşınmaz. Global Δ NOT_PROVEN; M6-B OPEN; R2 hazır değil.',
        ]}


def render_product_html(manifest):
    e=lambda v:escape(str(v),quote=True)
    rows=''.join('<tr><td>'+e(c['title'])+'</td><td>'+e('—' if c['value'] is None else format(c['display_value'],'.7g'))+' '+e(c['display_unit'])+'</td><td>'+e(c['display_status']+' · '+c['status']+' · '+', '.join(c['origins']))+'</td></tr>' for c in manifest['checks'])
    def shown_input(f):return displayed(f['value'],f['unit'])
    inputs=''.join('<tr><td>'+e(f['label'])+'</td><td>'+e(shown_input(f)[0])+'</td><td>'+e(shown_input(f)[1])+'</td><td>'+e(f['provenance'])+'</td></tr>' for f in manifest['input_completeness'])
    first=manifest['input_authority_matrix']['first_control']
    request_html='<h2>İlk hesap için gereken gerçek veri</h2><p>Owner: '+e(first['owner'])+'; durum '+e(first['source_qualification'])+'</p><ul>'+''.join('<li>'+e(r)+'</li>' for r in first['minimum_user_request'])+'</ul>'
    details=''.join('<article><h2>'+e(c['title'])+'</h2><p>'+e(c['display_status']+' · '+c['status']+' · '+', '.join(c['origins']))+'</p><p>'+e(c['source'])+'</p><code>'+e(c['formula'])+'</code><p>'+e(c['trace'])+'</p><p>Sınır: '+e(c['display_limit'])+' '+e(c['display_unit'])+'</p><p>'+e(c['reason'])+'</p><p>'+e(c['next_action'])+'</p><p>Owner: '+e(c['owner'])+'</p><p>Çözüm: '+e(c['closure_owner'])+'</p></article>' for c in manifest['checks'])
    points=''.join('<p>'+e(p['native_slot'])+' → '+e(p['point_name'])+': X='+e(p['X'])+' m; Y='+e(p['Y'])+' m; Z='+e(p['Z'])+' m</p>' for p in manifest['native_evidence']['current_point_coordinates'])
    points='<h2>Güncel aday native koordinatları / Global / m</h2>'+points+'<p>Özgün ABI7; native slot sırası, fiziksel alt/üst veya ln değildir.</p>'
    run='<p>Koşu zarfı: '+e(json.dumps(manifest.get('run_envelope',{}),ensure_ascii=False))+'</p>'
    return '<!doctype html><html lang="tr"><meta charset="UTF-8"><title>'+e(manifest['title'])+'</title><style>body{font:14px/1.6 system-ui;color:#183c53;max-width:1000px;margin:40px auto;padding:20px}table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #dbe4eb;text-align:left}h1{font-size:28px}article{border:1px solid #dbe4eb;padding:16px;margin:16px 0;break-inside:avoid}svg{max-width:420px}pre{white-space:pre-wrap;overflow-wrap:anywhere}code{background:#eef3f7}</style><h1>'+e(manifest['title'])+'</h1>'+run+'<p>Durum: '+e(manifest['status'])+' · Tam tasarım hazır: HAYIR · ETABS bağlantısı: gözlenmedi</p>'+manifest['section_svg']+points+request_html+'<h2>Kontrol özeti</h2><table>'+rows+'</table><h2>Girdi / birim / köken</h2><table>'+inputs+'</table>'+details+'<h2>Kapsam</h2>'+''.join('<p>'+e(s)+'</p>' for s in manifest['scope'])+'<details><summary>Girdi + sonuç + kanıt kimliği</summary><pre>'+e(json.dumps(manifest,ensure_ascii=False,indent=2))+'</pre></details></html>'


def render_product_pdf(manifest):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.graphics.shapes import Drawing,Rect,Circle,Line,String
    pairs=[(Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')),(Path('C:/Windows/Fonts/arial.ttf'),Path('C:/Windows/Fonts/arialbd.ttf'))]
    found=next(((a,b) for a,b in pairs if a.is_file() and b.is_file()),None)
    if found is None:raise ValueError('PDF için Arial veya DejaVu fontları bulunamadı.')
    if 'ColumnV3' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('ColumnV3',str(found[0])));pdfmetrics.registerFont(TTFont('ColumnV3Bold',str(found[1])))
    body=ParagraphStyle('body',fontName='ColumnV3',fontSize=8.5,leading=12,spaceAfter=6,textColor=colors.HexColor('#183c53'))
    heading=ParagraphStyle('head',parent=body,fontName='ColumnV3Bold',fontSize=13,leading=18,spaceBefore=12,spaceAfter=8,keepWithNext=True)
    para=lambda v,style=body:Paragraph(escape(str(v)),style)
    def table(rows,widths):
        t=Table([[para(v) for v in row] for row in rows],colWidths=widths,repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf3f7')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#dbe4eb')),('BOTTOMPADDING',(0,0),(-1,-1),6)]));return t
    display=lambda value:'Verilmedi' if value is None else format(value,'.7g') if type(value) in {int,float} else str(value)
    story=[para(manifest['title'],heading),para('Durum: '+manifest['status']+' | Tam tasarım hazır: HAYIR | ETABS bağlantısı gözlenmedi.'),para('Kesit: '+manifest['section']+'; kabul edilmiş I22/I33 = '+repr(manifest['native_evidence']['I22']['value'])+' m4; ölçü native olarak doğrulanmadı.'),para('Bağımsız proje review kontrolleri; güncel üretim readiness veya final donatı hükmü değildir.')]
    story += [para('Koşu zarfı'),para(json.dumps(manifest.get('run_envelope',{}),ensure_ascii=False))]
    story += [para('Güncel aday / Global / m — özgün ABI7 koordinatları',heading)]
    story += [para(p['native_slot']+' → '+p['point_name']+'; X='+repr(p['X'])+' m; Y='+repr(p['Y'])+' m; Z='+repr(p['Z'])+' m') for p in manifest['native_evidence']['current_point_coordinates']]
    story += [para('Native slot sırası; fiziksel alt/üst veya ln türetilmedi.'),para('Özgün receipt SHA256: '+manifest['native_evidence']['coordinate_provenance']['whole_json_sha256'])]
    if manifest['section_svg']:
        v=manifest['input_packet']['values'];scale=140/max(v['width_mm'],v['depth_mm']);w=v['width_mm']*scale;h=v['depth_mm']*scale
        d=Drawing(490,195);d.add(Rect(100-w/2,95-h/2,w,h,fillColor=colors.HexColor('#edf3f7')));d.add(Line(100,95,205,95));d.add(Line(100,95,100,180))
        for x,y,s in [(210,95,'2'),(107,180,'3'),(230,135,f"b={v['width_mm']/10:g} cm"),(230,115,f"h={v['depth_mm']/10:g} cm"),(230,90,'Proje review kesiti; native ölçü değil'),(230,70,'Donatı seçimi/yerleşimi nitelikli değil')]:d.add(String(x,y,s,fontName='ColumnV3',fontSize=8))
        cage=next((c for c in manifest['checks'] if c['id']=='cage'),None)
        layout=None if cage is None or cage['owner_output'] is None else cage['owner_output'].get('layout')
        if layout:
            for bar in layout['bars']:d.add(Circle(100+bar['x2_mm']*scale,95+bar['x3_mm']*scale,bar['diameter_mm']*scale/2,fillColor=colors.HexColor('#167969')))
        story.append(d)
    first=manifest['input_authority_matrix']['first_control']
    story+=[para('İlk hesap / eksik gerçek veri',heading),para('Owner: '+first['owner']),para('Durum: '+first['source_qualification'])]
    story += [para(request) for request in first['minimum_user_request']]
    story+=[para('Kontrol özeti',heading),table([['Kontrol','Sonuç / sınır','Durum']]+[[c['title'],display(c['display_value'])+' / '+display(c['display_limit'])+' '+c['display_unit'],c['display_status']+' / '+c['status']] for c in manifest['checks']],[185,150,160]),para('Girdi / birim / köken',heading),table([['Girdi','Değer / birim','Provenance']]+[[f['label'],display(displayed(f['value'],f['unit'])[0])+' '+displayed(f['value'],f['unit'])[1],f['provenance']] for f in manifest['input_completeness']],[185,130,180])]
    for c in manifest['checks']:
        story.append(KeepTogether([para(c['title'],heading),para(c['display_status']+' · '+c['status']+' · '+', '.join(c['origins'])),para(c['next_action']),*[para(c[k]) for k in ('source','formula','trace','reason') if c[k]],para('Owner: '+c['owner']),para('Çözüm sahibi: '+c['closure_owner'])]))
    for c in manifest['checks']:
        if c.get('owner_output'):
            story.append(para(c['title']+' / exact owner output',heading))
            story.append(para(json.dumps(c['owner_output'],ensure_ascii=False,sort_keys=True)))
    story+=[para('Kapsam ve kesin kaynak kimliği',heading),*[para(s) for s in manifest['scope']],para('Aday SHA256: '+manifest['candidate_sha256']),para('Tarihsel SHA256: '+manifest['historical_sha256']),para('Girdi SHA256: '+manifest['input_sha256']),para('Sonuç kimliği: '+manifest['result_id'])]
    for group,review in manifest['input_packet']['reviews'].items():story.append(para(group+' review: '+json.dumps(review,ensure_ascii=False,sort_keys=True)))
    buffer=BytesIO()
    def footer(canvas,doc):
        canvas.setFont('ColumnV3',7);canvas.drawString(42,22,'Kolon 235 / koşullu offline kontrol · tam tasarım hazır değil');canvas.drawRightString(552,22,str(doc.page))
    SimpleDocTemplate(buffer,pagesize=(595,842),leftMargin=42,rightMargin=42,topMargin=36,bottomMargin=38,title=manifest['title'],author='TBDY / Column V3',invariant=1).build(story,onFirstPage=footer,onLaterPages=footer)
    return buffer.getvalue()
