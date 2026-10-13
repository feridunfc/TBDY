"""One typed offline product evaluation → HTML/PDF/JSON. No formulas here."""
from dataclasses import asdict
from hashlib import sha256
from html import escape
from pathlib import Path
from io import BytesIO
from types import SimpleNamespace
import json

from tbdy_engine.application.column_product_workspace import ColumnProductAuthority, ColumnProductEvaluation, FIELDS, canonical
from tbdy_engine.product_reports.column_v1_report import PINS
from tbdy_engine.product_reports.column_v2_report import column_235_manifest, section_svg
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
    epoch='accepted-factual-receipt:'+original['property']['json_sha256']
    return ColumnProductAuthority(evidence['candidate_sha256'],evidence['historical_sha256'],epoch,evidence,original,adoptions)


def product_drawing(packet):
    v=packet['values']
    if 'geometry' not in packet['reviews']:return ''
    # Explicit reviewed dimensions only. This is the existing presentation helper.
    return section_svg(SimpleNamespace(width_mm=v['width_mm'],depth_mm=v['depth_mm']))


def product_manifest(evaluation: ColumnProductEvaluation, authority):
    p=evaluation.input_packet;checks=[];contributions=[]
    for c in evaluation.controls:
        f=(ReportField('value','Sonuç',c.value,c.unit),ReportField('limit','Sınır',c.limit,c.unit,role='LIMIT'),ReportField('status','Motor / gate durumu',c.status,role='STATUS'))
        calc=() if c.value is None else (ReportCalculation(c.id,c.title,c.formula or None,
            inputs=(ReportField('input_sha256','Girdi kimliği',evaluation.input_sha256,role='IDENTITY'),),outputs=f,
            authority_refs=(c.source,) if c.source else (),evidence_refs=(evaluation.input_sha256,)),)
        contrib=SliceReportContribution('COLUMN-235-'+c.id,c.title,'COMPOSITE','BLOCKED' if c.status=='BLOCKED' else 'PARTIAL','COLUMN','235',summary_fields=f,calculations=calc,
            evidence_refs=(evaluation.input_sha256,),warnings=c.dependencies)
        contributions.append(contrib.as_dict())
        checks.append({**asdict(c),'display_status': 'ENGELLİ / HESAPLANMADI' if c.status=='BLOCKED' else 'PROJE REVIEW KOŞULLU',
            'reason':' · '.join(c.dependencies) if c.dependencies else 'Bağımsız mevcut owner değerlendirildi; tüm kolon readiness kanıtı değildir.',
            'governing_case':c.governing,'governing_end':None,'station_m':None})
    return {'schema_version':'column.product.235.result.v1','context':'B-BLOK-235','title':'B-BLOK / Kolon 235 çalışma raporu',
        'component_id':'235','section':authority.evidence['section'],'status':'OFFLINE_PARTIAL' if evaluation.invoked_owners else 'BLOCKED_MISSING_REVIEWED_INPUTS',
        'result_id':evaluation.result_id,'input_sha256':evaluation.input_sha256,'input_packet':p,
        'native_evidence':authority.evidence,'candidate_sha256':authority.source_sha256,'historical_sha256':authority.historical_sha256,
        'evidence_epoch':authority.evidence_epoch,'current_analysis_result_epoch':None,'session_connection':'NOT_OBSERVED',
        'checks':checks,'contributions':contributions,'section_svg':product_drawing(p),
        'invoked_owners':evaluation.invoked_owners,'typed_owner_outputs':{'slenderness':None if evaluation.slenderness is None else asdict(evaluation.slenderness),
            'material_basis':None if evaluation.material_basis is None else asdict(evaluation.material_basis)},
        'input_completeness':[{ 'field':k,'label':label,'unit':unit,'value':p['values'][k],'group':group,
            'provenance':'PROJECT_REVIEW_DECLARATION' if group in p['reviews'] else 'UNREVIEWED_USER_DRAFT' if p['values'][k] is not None else 'NOT_PROVIDED',
            'review':p['reviews'].get(group)} for k,label,unit,group,_ in FIELDS],
        'canonical_rebar_authority':'NOT_PROVIDED','user_cage_role':'USER_PROVIDED_REBAR' if 'cage' in p['reviews'] else 'NOT_PROVIDED',
        'real_235_design_ready':False,'global_delta':'NOT_PROVEN','M6_B':'OPEN','R2_RERUN_READY':False,
        'scope':[
            '235 native kesit ataması ve I22/I33 kabul edilmiş acquisition kapsamındadır. Güncel ETABS bağlantısı gözlenmedi.',
            'Geometri/narinlik/malzeme review girdileri proje beyanıdır; native olgu, current B5/B6 veya analiz doğrulaması yapılmaz.',
            'Minimum dışmerkezlik yalnız emin değeridir; kuvvet authority olmadan Nd×emin momenti veya PMM üretilmez.',
            'Narinlik motor sonucu beyan edilen ln/k/ötelenme sınıfı koşulludur; A17/M6-B/whole-system kapanışı değildir.',
            'Kuvvet adayları native I/J slotları için ayrı drafttır; bottom/top veya governing durumu üretilmedi.',
            'Donatı USER_PROVIDED_REBAR review olabilir; ENGINE_SELECTED_REBAR/final/as-built yapılmaz.',
            'FC09 historical sonuçlar 61FA current source’a taşınmaz. Global Δ NOT_PROVEN; M6-B OPEN; R2 hazır değil.',
        ]}


def render_product_html(manifest):
    e=lambda v:escape(str(v),quote=True)
    rows=''.join('<tr><td>'+e(c['title'])+'</td><td>'+e('—' if c['value'] is None else format(c['value'],'.7g'))+' '+e(c['unit'])+'</td><td>'+e(c['status'])+'</td></tr>' for c in manifest['checks'])
    inputs=''.join('<tr><td>'+e(f['label'])+'</td><td>'+e(f['value'])+'</td><td>'+e(f['unit'])+'</td><td>'+e(f['provenance'])+'</td></tr>' for f in manifest['input_completeness'])
    details=''.join('<article><h2>'+e(c['title'])+'</h2><p>'+e(c['status'])+'</p><p>'+e(c['source'])+'</p><code>'+e(c['formula'])+'</code><p>'+e(c['trace'])+'</p><p>Sınır: '+e(c['limit'])+' '+e(c['unit'])+'</p><p>'+e(c['reason'])+'</p><p>Owner: '+e(c['owner'])+'</p><p>Çözüm: '+e(c['closure_owner'])+'</p></article>' for c in manifest['checks'])
    return '<!doctype html><html lang="tr"><meta charset="UTF-8"><title>'+e(manifest['title'])+'</title><style>body{font:14px/1.6 system-ui;color:#183c53;max-width:1000px;margin:40px auto;padding:20px}table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #dbe4eb;text-align:left}h1{font-size:28px}article{border:1px solid #dbe4eb;padding:16px;margin:16px 0;break-inside:avoid}svg{max-width:420px}pre{white-space:pre-wrap;overflow-wrap:anywhere}code{background:#eef3f7}</style><h1>'+e(manifest['title'])+'</h1><p>Durum: '+e(manifest['status'])+' · Tam tasarım hazır: HAYIR · ETABS bağlantısı: gözlenmedi</p>'+manifest['section_svg']+'<h2>Kontrol özeti</h2><table>'+rows+'</table><h2>Girdi / birim / köken</h2><table>'+inputs+'</table>'+details+'<h2>Kapsam</h2>'+''.join('<p>'+e(s)+'</p>' for s in manifest['scope'])+'<details><summary>Girdi + sonuç + kanıt kimliği</summary><pre>'+e(json.dumps(manifest,ensure_ascii=False,indent=2))+'</pre></details></html>'


def render_product_pdf(manifest):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.graphics.shapes import Drawing,Rect,Line,String
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
    story=[para(manifest['title'],heading),para('Durum: '+manifest['status']+' | Tam tasarım hazır: HAYIR | ETABS bağlantısı gözlenmedi.'),para('Kesit: '+manifest['section']+'; kabul edilmiş I22/I33 = '+repr(manifest['native_evidence']['I22']['value'])+' m4; ölçü native olarak doğrulanmadı.'),para('Bağımsız proje review kontrolleri; güncel üretim readiness veya final donatı hükmü değildir.')]
    if manifest['section_svg']:
        v=manifest['input_packet']['values'];scale=140/max(v['width_mm'],v['depth_mm']);w=v['width_mm']*scale;h=v['depth_mm']*scale
        d=Drawing(490,195);d.add(Rect(100-w/2,95-h/2,w,h,fillColor=colors.HexColor('#edf3f7')));d.add(Line(100,95,205,95));d.add(Line(100,95,100,180))
        for x,y,s in [(210,95,'2'),(107,180,'3'),(230,135,f"b={v['width_mm']:g} mm"),(230,115,f"h={v['depth_mm']:g} mm"),(230,90,'Proje review kesiti; native ölçü değil'),(230,70,'Donatı seçimi/yerleşimi nitelikli değil')]:d.add(String(x,y,s,fontName='ColumnV3',fontSize=8))
        story.append(d)
    story+=[para('Kontrol özeti',heading),table([['Kontrol','Sonuç / sınır','Durum']]+[[c['title'],str(c['value'])+' / '+str(c['limit'])+' '+c['unit'],c['status']] for c in manifest['checks']],[185,150,160]),para('Girdi / birim / köken',heading),table([['Girdi','Değer / birim','Provenance']]+[[f['label'],str(f['value'])+' '+f['unit'],f['provenance']] for f in manifest['input_completeness']],[185,130,180])]
    for c in manifest['checks']:
        story += [para(c['title'],heading),para(c['status']),para(c['source']),para(c['formula']),para(c['trace']),para(c['reason']),para('Owner: '+c['owner']),para('Çözüm sahibi: '+c['closure_owner'])]
    story+=[para('Kapsam ve kesin kaynak kimliği',heading),*[para(s) for s in manifest['scope']],para('Aday SHA256: '+manifest['candidate_sha256']),para('Tarihsel SHA256: '+manifest['historical_sha256']),para('Girdi SHA256: '+manifest['input_sha256']),para('Sonuç kimliği: '+manifest['result_id'])]
    for group,review in manifest['input_packet']['reviews'].items():story.append(para(group+' review: '+json.dumps(review,ensure_ascii=False,sort_keys=True)))
    buffer=BytesIO()
    def footer(canvas,doc):
        canvas.setFont('ColumnV3',7);canvas.drawString(42,22,'Kolon 235 / koşullu offline kontrol · tam tasarım hazır değil');canvas.drawRightString(552,22,str(doc.page))
    SimpleDocTemplate(buffer,pagesize=(595,842),leftMargin=42,rightMargin=42,topMargin=36,bottomMargin=38,title=manifest['title'],author='TBDY / Column V3',invariant=1).build(story,onFirstPage=footer,onLaterPages=footer)
    return buffer.getvalue()
