"""Presentation of canonical owner output. No equations or authority issuance."""
from html import escape
from io import BytesIO
from pathlib import Path
import json


def summary_rows(manifest):
    rows = []
    for c in manifest['canonical_contributions']:
        values = {f['key']:f['value'] for f in c['summary_fields']}
        rows.append({'control': values.get('column_leaf_key', c['slice_id']),
                     'direction':values.get('direction'), 'status':c['status'],
                     'outcome':values.get('column_leaf_runtime_outcome'),
                     'source_ref':values.get('column_leaf_source_ref'), 'warnings':c['warnings'],
                     'fields':c['summary_fields']})
    return rows


def trace_rows(value, path=''):
    """All numerical and decision leaves, retaining owner paths and ordering."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {'store','assessment','target_topology','rebar_intent','ranking_key','regulatory_snapshot','structural_assessment'}:
                continue
            if key == 'evidence':
                for ref in child:
                    if isinstance(ref,str) and ref.startswith('QUALIFIED_VC:'):
                        yield (path+'.retained_owner_vc',ref)
                continue
            # References/metadata are preserved in full JSON and HTML technical
            # payload; keep the numerical report legible without 64-char hashes.
            if key != 'code_ref' and any(s in key for s in ('ref','provenance','fingerprint','identity','source','contract','artifact','policy','plan')):
                continue
            yield from trace_rows(child, path+'.'+key if path else key)
    elif isinstance(value, list):
        for i, child in enumerate(value): yield from trace_rows(child, f'{path}[{i}]')
    elif value is not None:
        yield (path, str(value))


def present_qualified_result(m):
    m = json.loads(json.dumps(m,ensure_ascii=False,allow_nan=False))
    m['control_summary'] = summary_rows(m)
    m['numerical_traces'] = {key:[list(row) for row in trace_rows(out['data'])] for key,out in m['owner_outputs'].items() if key != 'fnd_col_2_execution'}
    m['section_svg'] = ''
    runtime = m['owner_outputs'].get('longitudinal_runtime')
    if runtime:
        t = runtime['data']['target_topology']
        w, h = t['width_t2_m'], t['depth_t3_m']
        scale = 200/max(w,h)
        bars = m['selected_rebar']['selected_candidate']['bars'] if m['selected_rebar'] else []
        m['section_svg'] = ('<svg viewBox="0 0 360 300" role="img" aria-label="Owner geometri ve kanonik donatı">'
            f'<rect x="{160-w*scale/2}" y="{140-h*scale/2}" width="{w*scale}" height="{h*scale}" fill="#edf3f7" stroke="#183c53"/>'
            + ''.join(f'<circle cx="{160+b["x2_mm"]/1000*scale}" cy="{140-b["x3_mm"]/1000*scale}" r="{b["diameter_mm"]/2000*scale}" fill="#167969"/>' for b in bars)
            + f'<text x="12" y="270">yerel 2: {w:g} m · yerel 3: {h:g} m</text><path d="M160 140h120M160 140v-120" stroke="#5d768a"/><text x="290" y="145">2</text><text x="170" y="20">3</text></svg>')
    return m


def render_qualified_html(m):
    e = lambda v:escape(str(v))
    rows = ''.join('<tr><td>'+e(r['control'])+' '+e(r['direction'] or '')+'</td><td>'+e(r['status'])+'</td><td>'+e(r['outcome'])+'</td></tr>' for r in summary_rows(m))
    details = ''.join('<article><h2>'+e(key)+'</h2><p>'+e(output['owner'])+'</p><table>'+''.join('<tr><td>'+e(k)+'</td><td>'+e(v)+'</td></tr>' for k,v in trace_rows(output['data']))+'</table></article>' for key,output in m['owner_outputs'].items() if key != 'fnd_col_2_execution')
    return '<!doctype html><html lang="tr"><meta charset="UTF-8"><title>'+e(m['title'])+'</title><style>body{font:14px/1.6 system-ui;max-width:1000px;margin:32px auto;color:#183c53}table{border-collapse:collapse;width:100%}td{padding:8px;border-bottom:1px solid #dde5ec;overflow-wrap:anywhere}article{margin:32px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>'+e(m['title'])+'</h1><p>FND2: '+e(m['fnd2_status'])+' / Uygulama: '+e(m['application_status'])+'</p><p>'+e('; '.join(m['application_blockers']))+'</p>'+m.get('section_svg','')+'<h2>Kanonik kontrol özeti</h2><table>'+rows+'</table>'+details+'<h2>Kapsam</h2>'+''.join('<p>'+e(s)+'</p>' for s in m['scope'])+'<details><summary>Kesin typed çıktı / kaynak / governing kimlikleri</summary><pre>'+e(json.dumps(m,ensure_ascii=False,indent=2))+'</pre></details></html>'


def render_qualified_pdf(m):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pairs=[(Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')),
           (Path('C:/Windows/Fonts/arial.ttf'),Path('C:/Windows/Fonts/arialbd.ttf'))]
    found=next(((a,b) for a,b in pairs if a.is_file() and b.is_file()),None)
    if found is None: raise ValueError('PDF için Arial veya DejaVu gerekli.')
    if 'QualifiedColumn' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('QualifiedColumn',str(found[0])))
        pdfmetrics.registerFont(TTFont('QualifiedColumnBold',str(found[1])))
    body=ParagraphStyle('b',fontName='QualifiedColumn',fontSize=8,leading=11,spaceAfter=5)
    head=ParagraphStyle('h',parent=body,fontName='QualifiedColumnBold',fontSize=12,leading=16,spaceBefore=12,spaceAfter=7,keepWithNext=True)
    p=lambda x,s=body:Paragraph(escape(str(x)),s)
    def table(rows, widths):
        t=Table([[p(v) for v in row] for row in rows],colWidths=widths,repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf3f7')),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#dbe4eb')),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        return t
    story=[p(m['title'],head),p('FND2: '+m['fnd2_status']+' | Uygulama: '+m['application_status']),
           p('Project / population: '+str(m['project_status'])+' / '+str(m['population_state'])),
           *[p(s) for s in m['scope']], *[p(s) for s in m['application_blockers']],
           p('Kanonik owner kontrol ve coverage kararları',head),
           table([['Kontrol / yön','Durum','Owner outcome']]+[[r['control']+' '+str(r['direction'] or ''),r['status'],r['outcome']] for r in summary_rows(m)],[235,80,196])]
    runtime=m['owner_outputs'].get('longitudinal_runtime')
    if runtime:
        from reportlab.graphics.shapes import Drawing,Rect,Circle,Line,String
        t=runtime['data']['target_topology'];w,h=t['width_t2_m'],t['depth_t3_m'];scale=130/max(w,h)
        d=Drawing(500,200);d.add(Rect(100-w*scale/2,95-h*scale/2,w*scale,h*scale,fillColor=colors.HexColor('#edf3f7')))
        if m['selected_rebar']:
            for b in m['selected_rebar']['selected_candidate']['bars']:
                d.add(Circle(100+b['x2_mm']/1000*scale,95+b['x3_mm']/1000*scale,b['diameter_mm']/2000*scale,fillColor=colors.HexColor('#167969')))
        d.add(Line(100,95,190,95));d.add(Line(100,95,100,180))
        for x,y,text in [(195,95,'2'),(107,180,'3'),(220,130,f'local 2: {w:g} m'),(220,110,f'local 3: {h:g} m'),(220,90,'Kanonik owner geometri / secilen donati')]:
            d.add(String(x,y,text,fontName='QualifiedColumn',fontSize=9))
        story.insert(5,d)
    for key,output in m['owner_outputs'].items():
        if key == 'fnd_col_2_execution': continue
        rows=list(trace_rows(output['data']))
        story += [p(key,head),p(output['owner']),table([['Owner alanı / hesap izi','Kesin değer / karar']]+rows,[315,196])]
    story += [p('Kaynak ve sonuç kimliği',head),p(json.dumps(m['scope_identity'],ensure_ascii=False)),p(m['result_id'])]
    buf=BytesIO()
    def footer(canvas,doc):
        canvas.setFont('QualifiedColumn',7)
        canvas.drawString(42,22,'Kanonik owner çıktısı - offline test gerçek 235 tasarım yetkisi değildir')
        canvas.drawRightString(553,22,str(doc.page))
    SimpleDocTemplate(buf,pagesize=(595,842),leftMargin=42,rightMargin=42,topMargin=35,bottomMargin=38,
        title=m['title'],author='TBDY / canonical Column owners',invariant=1).build(story,onFirstPage=footer,onLaterPages=footer)
    return buf.getvalue()
