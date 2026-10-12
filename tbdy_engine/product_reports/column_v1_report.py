"""Source-bound single-column report projection. No engineering or ETABS execution.

This is a factual review product, not a fabricated BuildingReportModel/FCR
closure or a replacement for the accepted Column-R1 design composition.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
from hashlib import sha256
from html import escape
from io import BytesIO, StringIO
import json
import math
from pathlib import Path
from typing import Mapping
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from tbdy_engine.product_reports.report_artifact import ReportArtifact
from tbdy_engine.product_reports.slice_report_contribution import ReportField, ReportTable, SliceReportContribution
from tbdy_engine.product_reports.unified_building_report import ReportSourceKind, SourceManifest, SourceManifestEntry

COMPONENT = '235'
MAIN_HEAD = '810f93159bc2207b3d0280ac85e9930b7aaf6586'
MAIN_TREE = '54af7aa7a314dfc0a80aa6766684a49150f452b6'
CANDIDATE = '61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621'
HISTORICAL = 'FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F'
PINS = {
    'assignment': ('COLUMN_R1_R3M_ABI4_LIVE_GETSECTION_ADOPTION_2026-10-12.json', 'b0cdb95c434c9f9ab3c8fb6cfcbfb3c529aa9b981578081ceb935a7b3a644278'),
    'property': ('COLUMN_R1_R3M_ABI5_LIVE_GETSECTPROPS_ADOPTION_2026-10-12.json', '79ba4dc212c6b39283362d292152acb77003467f1b620a13e2790f6be221ea2e'),
    'gates': ('COLUMN_R1_R3M_ABI6_OFFLINE_RECEIPT_2026-10-12.json', '3b0c77976b8c813627603585b9558d649d7b6590c26991a0d339fd339c2484e3'),
    'modal': ('column-r1-r3d-modal_20261010_073229.json', '83ce2ff7c3a6170e931d2869e212adde93b7c08b25bbf44e9f0c2c663f156b03'),
}
FORCE_KEYS = ('object_name','object_station','element_name','element_station','load_case','step_type','step_number','p','v2','v3','t','m2','m3')
POINT_KEYS = ('point_object','element_name','load_case','step_type','step_number','u1','u2','u3','r1','r2','r3')


def _require(test, message):
    if not test: raise ValueError(message)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',',':'))+'\n'


def _load(path, key):
    data=Path(path).read_bytes();digest=sha256(data).hexdigest()
    _require(digest==PINS[key][1], 'accepted source bytes differ: '+key)
    return json.loads(data)


@dataclass(frozen=True, slots=True)
class ColumnV1Report:
    sources: SourceManifest
    contributions: tuple[SliceReportContribution, ...]
    capture_times: tuple[tuple[str,str], ...]

    def as_dict(self):
        return {'schema_version':'column_v1.source_bound_review.v1','report_id':'B-BLOK-COLUMN-235-V1','project_id':'B-BLOK',
            'component_id':COMPONENT,'title':'Kolon 235 - Column V1','report_scope':'ACCEPTED_FACTS_AND_HISTORICAL_RAW_RESULTS_ONLY',
            'current_engine_result':'NOT_PROVIDED','current_B5':'NOT_PROVIDED','engineering_verdict':'NOT_EVALUATED',
            'source_authority_rebound':False,'global_delta':'NOT_PROVEN','M6_B':'OPEN','R2_RERUN_READY':False,
            'matrix_scan':'NOT_STARTED','live_GetPoints_authorized':False,'new_getter_is_report_prerequisite':False,
            'delivery_basis':{'MAIN_HEAD':MAIN_HEAD,'MAIN_TREE':MAIN_TREE},'capture_times':dict(self.capture_times),
            'source_manifest':self.sources.as_dict(),'contributions':[c.as_dict() for c in self.contributions],
            'presentation_contract':{'engineering_recalculation_allowed':False,'renderer_may_change_status':False,
                'renderer_may_change_governing_selection':False,'global_compliance_verdict_emitted':False}}

    def to_json(self): return _json(self.as_dict())


def build_column_v1_report(*, assignment_path, property_path, gates_path, modal_path):
    """Project the exact accepted evidence; no getter, solver, envelope or gate promotion."""
    a=_load(assignment_path,'assignment');p=_load(property_path,'property');g=_load(gates_path,'gates');m=_load(modal_path,'modal')
    _require(a['native_call']['named_arguments']=={'Name':COMPONENT} and a['single_assignment_derived']['candidate_PropName']=='Column_80x80', 'exact accepted frame assignment required')
    _require(a['integrity']['candidate_sha256']==p['integrity']['candidate_before_after_sha256']==CANDIDATE, 'candidate source binding required')
    _require(p['property_scope']['Name']=='Column_80x80' and p['ABI5']=='CLOSED_ACCEPTED_ORIGINAL_NATIVE_RECEIPT'
        and p['native_call']['application_pRetVal']==0 and not p['native_errors'], 'closed accepted named section required')
    _require(g['safety']['execution_authorized'] is False and g['safety']['LIVE_GETPOINTS']=='NOT_EXECUTED', 'GetPoints is not observed or authorized')
    _require(m['source_sha256_before']==m['source_sha256_after']==HISTORICAL and m['identity_before']==m['identity_after']
        and m['source_unchanged'] is True and m['output_state_restored'] is True and not m['errors'], 'historical source/capture integrity required')
    _require(m['current_b5_qualified'] is False and m['factual_capture_binding']['is_analysis_result_epoch'] is False, 'historical raw capture must not become a B5 epoch')
    match=[r for r in m['story_columns'] if r['UniqueName']==COMPONENT];_require(len(match)==1,'one exact historical frame; no duplicate/nearest fallback')
    geometry=match[0];facts=m['facts'];names=(geometry['UniquePtI'],geometry['UniquePtJ']);_require(len(set(names))==2,'two distinct historical native slots required')
    selected=[('Modal:FrameForce:'+COMPONENT,FORCE_KEYS)]+[('Modal:JointDispl:'+n,POINT_KEYS) for n in names]
    for key,keys in selected:
        fact=facts[key];payload=fact['payload'];digest=sha256(json.dumps(payload,sort_keys=True,allow_nan=False,separators=(',',':')).encode()).hexdigest()
        _require(fact['capture_payload_ref']=='modal-read:sha256:'+digest and type(payload['return_code']) is int and payload['return_code']==0,'original raw payload digest/status required')
        rows=payload['rows'];_require(rows and all(set(row)==set(keys) for row in rows),'exact original result field set required')
        _require(all(r['load_case']=='Modal' and r['step_type']=='Mode' and type(r['step_number']) is float and r['step_number'].is_integer() for r in rows),'exact original modal grain required')
        _require({r['step_number'] for r in rows}==set(range(1,101)),'complete accepted 100-mode population required')
        _require(all(math.isfinite(v) for r in rows for v in r.values() if type(v) is float),'finite native data required')
    force=facts[selected[0][0]]['payload']['rows'];_require(len(force)==300 and all(r['object_name']==COMPONENT for r in force),'exact accepted 235 frame rows required')
    _require(len({(r['step_number'],r['object_station'],r['element_name'],r['element_station']) for r in force})==300,'ambiguous frame result grain')
    points=[]
    for n in names:
        rows=facts['Modal:JointDispl:'+n]['payload']['rows']
        _require(len(rows)==100 and len({r['step_number'] for r in rows})==100 and all(r['point_object']==n for r in rows),'exact endpoint modal grain required')
        points.extend(rows)  # Keep original native per-point order; no bottom/top, sorting or averaging.
    refs=lambda key:('sha256:'+PINS[key][1],)
    sources=SourceManifest(tuple(SourceManifestEntry(key,ReportSourceKind.ETABS_EVIDENCE,title,
        fingerprint=PINS[key][1],locator=PINS[key][0],evidence_refs=refs(key)) for key,title in (
        ('assignment','ABI4 - güncel aday kesit ataması'),('property','ABI5 - güncel aday I22/I33'),
        ('modal','R3D - FC09 tarihsel ham modal sonuçları'),('gates','Kabul edilmiş açık mühendislik kapıları'))))
    current=SliceReportContribution('COLUMN-V1-CURRENT-FACTS','Güncel aday kaynaktan doğrulanan bilgiler','FACTUAL','PROVEN','COLUMN',COMPONENT,
        summary_fields=(ReportField('source_sha','Kaynak SHA256',CANDIDATE,role='IDENTITY'),ReportField('section','Atanmış kesit','Column_80x80',role='IDENTITY'),
            *(ReportField(k,k,p['property_scope'][k]['value'],unit='m4',note='ABI5; exact binary64 MATCH; yalnız bu kesit özelliği') for k in ('I22','I33'))),
        evidence_refs=refs('assignment')+refs('property'),warnings=('Kesit adından geometrik ölçü veya kesit formülü çıkarılmadı.','Diğer on kesit alanı NOT_COMPARABLE / NOT_PROVEN.'))
    historic=SliceReportContribution('COLUMN-V1-HISTORICAL-RAW','FC09 arşivindeki mevcut sonuçlar','FACTUAL','PARTIAL','COLUMN',COMPONENT,
        summary_fields=(ReportField('source_sha','Tarihsel kaynak SHA256',HISTORICAL,role='IDENTITY'),ReportField('story','Tarihsel Story',geometry['Story'],role='IDENTITY'),
            ReportField('label','Tarihsel kolon etiketi',geometry['ColumnBay'],role='IDENTITY'),ReportField('native_I','Tarihsel I slotu',names[0],role='IDENTITY'),
            ReportField('native_J','Tarihsel J slotu',names[1],role='IDENTITY'),ReportField('native_length_text','Connectivity Length ham metni',geometry['Length'],role='NOTE',note='Alan birimi/offset yorumu V1 tarafından genişletilmedi.'),
            ReportField('frame_rows','FrameForce ham satır',len(force)),ReportField('joint_rows','JointDispl ham satır',len(points)),ReportField('modes','Modal mod nüfusu',100)),
        tables=(ReportTable('frame_force','Modal FrameForce - 235',FORCE_KEYS,tuple(force)),ReportTable('joint_displ','Modal JointDispl - tarihsel I/J slotları',POINT_KEYS,tuple(points))),
        evidence_refs=refs('modal')+tuple(facts[key]['capture_payload_ref'] for key,_ in selected),
        warnings=('Bu sonuçlar FC09 arşivine aittir; 61FA aday kaynağının güncel tasarım sonuçlarına bağlanmadı.',
            'Ham Modal sonuçlar tasarım kombinasyonu, CQC/envelope veya kapasite sonucu değildir.',
            'U1/U2/U3 ham API bileşenleridir; global dönüşüm ve global Δ nitelendirilmedi.',
            'I/J slot sırasından bottom/top veya panel-zone/analiz-joint kimliği çıkarılmadı.'))
    missing_rows=(
        {'Alan':'Güncel fiziksel uçlar','Durum':'NOT_PROVEN','Eksik':'235 için güncel native uç/analiz-joint bağlamı yok.','Etkisi':'FC09 I/J adları 61FA uç kimliği yerine kullanılamaz.'},
        {'Alan':'Global modal Δ','Durum':'NOT_PROVEN','Eksik':'Global koordinat/binding/panel-zone sözleşmesi ve tam nitelikli sonuç nüfusu.','Etkisi':'Global kat ötelemesi ve buna bağlı mühendislik hükmü üretilemez.'},
        {'Alan':'B5 sonuç dönemi','Durum':'NOT_PROVIDED','Eksik':'Kaynakla bağlı güncel nitelikli analysis-result epoch.','Etkisi':'Ham arşiv sonuçları güncel B5 sonucu değildir.'},
        {'Alan':'M6-B / TS500 stabilite','Durum':'OPEN','Eksik':'Kaynak yetkili modal stabilite/ortak Δ-R-V kararı.','Etkisi':'Tam stabilite ve R2 yeniden çalıştırma hazır değil.'},
        {'Alan':'Tasarım kuvvetleri / kapasite / donatı','Durum':'NOT_PROVIDED','Eksik':'235 için güncel kontrollü tasarım sonucu.','Etkisi':'N-Ed/M-Ed, kapasite oranı, seçilmiş donatı ve nihai metraj yayımlanmadı.'},
        {'Alan':'Diğer on kesit alanı','Durum':'NOT_COMPARABLE','Eksik':'Alan bazında kabul edilmiş tarihsel birim yetkisi.','Etkisi':'I22/I33 eşleşmesi tüm kesit/model eşdeğerliği değildir.'})
    gaps=SliceReportContribution('COLUMN-V1-OPEN-GATES','Tam kolon tasarımı için açık bilgiler','COMPOSITE','BLOCKED','COLUMN',COMPONENT,
        tables=(ReportTable('missing','Eksikler ve sonuç üzerindeki etkileri',('Alan','Durum','Eksik','Etkisi'),missing_rows),),evidence_refs=refs('gates'),
        summary_fields=(ReportField('current_engine_result','Güncel kontrollü tasarım sonucu','NOT_PROVIDED',role='STATUS'),
            ReportField('global_delta','Global Δ','NOT_PROVEN',role='STATUS'),ReportField('M6_B','M6-B','OPEN',role='STATUS'),
            ReportField('R2_RERUN_READY','R2 yeniden çalıştırma hazır',False,role='STATUS')),
        warnings=('Rapor için yeni getter hazırlığı veya canlı çalışma ön koşul değildir.','Bu V1 mevcut kanıtı gösterir; TBDY/TS500 uygunluk belgesi üretmez.'))
    return ColumnV1Report(sources,(current,historic,gaps),(('candidate',p['original']['finished_utc']),('historical',m['finished_utc'])))


def _table(columns, rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+escape(str(k))+'</th>' for k in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+escape(str(r.get(k,'')))+'</td>' for k in columns)+'</tr>' for r in rows)+'</tbody></table></div>'


def render_column_v1_html(report):
    data=report.as_dict();current,historical,gaps=data['contributions'];e=lambda x:escape(str(x),quote=True)
    fields=_table(('Bilgi','Değer','Birim'),[{'Bilgi':f['label'],'Değer':f['value'],'Birim':f['unit'] or ''} for f in current['summary_fields'] if f['key']!='source_sha'])
    force_table=historical['tables'][0];point_table=historical['tables'][1]
    initial_force=_table(('Obj','ObjSta (ham)','Elm','P [kN]','V2 [kN]','V3 [kN]','T (ham)','M2 (ham)','M3 (ham)'),[dict(zip(('Obj','ObjSta (ham)','Elm','P [kN]','V2 [kN]','V3 [kN]','T (ham)','M2 (ham)','M3 (ham)'),[r[k] for k in ('object_name','object_station','element_name','p','v2','v3','t','m2','m3')])) for r in force_table['rows'] if r['step_number']==1])
    initial_points=_table(('Obj','Elm','U1 [m]','U2 [m]','U3 [m]'),[dict(zip(('Obj','Elm','U1 [m]','U2 [m]','U3 [m]'),[r[k] for k in ('point_object','element_name','u1','u2','u3')])) for r in point_table['rows'] if r['step_number']==1])
    payload=report.to_json().replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    provenance=_table(('Kaynak','Dosya','SHA256'),[{'Kaynak':s['title'],'Dosya':s['locator'],'SHA256':s['fingerprint']} for s in data['source_manifest']['entries']])
    return '''<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Kolon 235 | Column V1</title>
<style>
:root{--navy:#173548;--blue:#256b89;--green:#237356;--amber:#946b20;--ink:#223844;--muted:#647681;--line:#d8e2e6;--paper:#fff}*{box-sizing:border-box}body{margin:0;background:#edf2f4;color:var(--ink);font:15px/1.6 system-ui,sans-serif}main{max-width:1160px;margin:32px auto;padding:0 24px}header{background:var(--navy);color:white;border-radius:18px;padding:32px 38px;position:relative}h1{font-size:36px;line-height:1.2;margin:10px 0}h2{font-size:23px;margin:0 0 16px}h3{font-size:17px}p{margin:8px 0}.eyebrow{letter-spacing:.15em;font-size:12px;text-transform:uppercase}.chips{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.chip{font-size:12px;padding:5px 12px;border-radius:30px;background:#e6f4ec;color:var(--green)}.chip.open{background:#fff0cc;color:#78571c}button,select{font:inherit;border:1px solid var(--line);border-radius:8px;padding:8px 14px;background:white;color:var(--ink);cursor:pointer}header button{position:absolute;right:30px;top:28px}section{background:white;border:1px solid var(--line);border-radius:14px;padding:26px 30px;margin-top:20px}.notice{background:#fff8e9;border-left:4px solid #c49a42;padding:16px 20px;border-radius:8px;margin:18px 0}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.card{border:1px solid var(--line);border-radius:10px;padding:18px}.metric{font-size:26px;font-weight:650;line-height:1.3}.sub,.muted{color:var(--muted);font-size:13px}.mono{font-family:ui-monospace,monospace;overflow-wrap:anywhere;font-size:12px}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}td,th{padding:11px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#f0f5f7;font-weight:650}td{font-variant-numeric:tabular-nums}#facts table td:nth-child(2){font-size:16px;font-weight:600}details{margin-top:12px}summary{cursor:pointer;font-weight:600}.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}footer{text-align:center;color:var(--muted);font-size:12px;padding:24px}a{color:var(--blue)}.source-tag{font-size:12px;background:#eef3f5;padding:6px 10px;display:inline-block;border-radius:5px}.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}@media(max-width:700px){main{margin:16px auto;padding:0 12px}header,section{padding:22px}header button{position:static}.grid,.two{grid-template-columns:1fr}h1{font-size:30px}}@media print{body{background:white}main{margin:0;padding:0}button,select{display:none}header{border-radius:0}section{break-inside:avoid}details{display:block}.scroll{overflow:visible}}
</style><main><header><div class="eyebrow">B-BLOK / Tek kolon raporu / V1</div><h1>Kolon 235</h1><p>Doğrulanmış bilgiler, mevcut sonuçlar ve tamamlanması gerekenler.</p><button onclick="window.print()">Yazdır / PDF</button><div class="chips"><span class="chip">Kesit ataması ve I22/I33 doğrulandı</span><span class="chip open">Tam tasarım sonucu henüz yok</span></div><div class="sub" style="color:#c9d9e2">Kabul edilmiş kayıtların offline raporu · 12 Ekim 2026</div></header>
<section id="facts"><h2>Güncel aday kaynaktan doğrulanan bilgiler</h2><span class="source-tag">61FA aday kaynağı · ABI4 + ABI5</span>'''+fields+'''<p class="sub">I22 ve I33 tarihsel yetkili değerlerle tam binary64 eşleşmiştir. Kesit adındaki “80x80” bir geometrik ölçü kanıtı olarak kullanılmadı. Diğer on alan NOT_COMPARABLE / NOT_PROVEN.</p><details><summary>Kaynak kimliği ve yakalama tarihi</summary><p class="mono">'''+e(CANDIDATE)+'''</p><p>'''+e(data['capture_times']['candidate'])+'''</p></details></section>
<section><h2>Mevcut sonuçlar: FC09 arşivi</h2><div class="notice"><strong>Bu sonuçların kaynağı FC09’dur.</strong><br>61FA kaynağına güncel tasarım sonucu olarak bağlanmadı. Global Δ, kontrollü tasarım kuvveti veya kapasite hükmü üretilmedi.</div><div class="grid"><div class="card"><div class="metric">100</div><div>Modal mod</div></div><div class="card"><div class="metric">300</div><div>235 / FrameForce satırı</div></div><div class="card"><div class="metric">200</div><div>955 ve 758 / JointDispl satırı</div></div></div><p class="sub">Tarihsel Story: +0.00 · Etiket: C1 · Native I/J slotları: 955 / 758. Bu slotlardan güncel bottom/top eşlemesi çıkarılmadı.</p>
<h3>Mod bazında ham sonuçları inceleyin</h3><div class="toolbar"><label for="mode">Modal mod</label><select id="mode">'''+''.join('<option value="'+str(n)+'">'+str(n)+'</option>' for n in range(1,101))+'''</select><button id="force-csv">300 FrameForce satırını indir</button><button id="point-csv">200 JointDispl satırını indir</button></div>
<h3>FrameForce / 235</h3><p class="sub">P, V2, V3: capture kuvvet birimi kN. İstasyon, T ve M alanları ham API alanları olarak korunur; fiziksel uç, offset veya tasarım büyütmesi yorumu yapılmadı.</p><div id="force-results">'''+initial_force+'''</div><h3>JointDispl / tarihsel native noktalar</h3><p class="sub">U1/U2/U3: capture birimi m. Global koordinat dönüşümü nitelendirilmemiştir; bu değerlerden global Δ hesaplanmadı.</p><div id="point-results">'''+initial_points+'''</div><details><summary>Tarihsel kayıt kapsamı</summary><p class="mono">'''+e(HISTORICAL)+'''</p><p>'''+e(data['capture_times']['historical'])+'''</p><p class="sub">300 FrameForce ve 200 JointDispl satırının tamamı JSON/CSV’de kaynak alanlarıyla korunur. Hiçbir mod governing seçilmedi veya birleştirilmedi. Native connectivity Length metni 5.15 ile FrameForce istasyonu aynı fiziksel büyüklük kabul edilmedi. Ham capture güncel nitelikli B5 epoch değildir.</p></details></section>
<section><h2>Tam kolon tasarımı için açık bilgiler</h2>'''+_table(gaps['tables'][0]['columns'],gaps['tables'][0]['rows'])+'''<p class="notice">Bu V1 raporunu açmak için yeni getter gerekmez. Global Δ: NOT_PROVEN · M6-B: OPEN · R2_RERUN_READY: NO. Donatı seçimi, nihai metraj ve uygunluk hükmü yayımlanmadı.</p></section><section><h2>Kaynak izi</h2><p class="sub">Her bölüm kendi kaynak kimliğini taşır. Aynı model yolu, farklı SHA256’ları eşdeğer yapmaz. FC09 üretim kapısı değişmedi.</p><details><summary>Kanıt dosyaları ve kesin hashler</summary>'''+provenance+'''</details><details><summary>Raporun kapsamı</summary><p class="sub">Gerçek kabul edilmiş kayıtlardan üretilmiş tek kolon bilgi/sonuç raporudur. Yeni analiz, tasarım veya ETABS çağrısı yapılmadı. Tam TBDY/TS500 uygunluk raporu veya tamamlanmış Column-R1 tasarım sonucu değildir.</p></details></section><footer>Column V1 · 235 · Kanıt kapsamı korunarak üretildi</footer></main><script id="report-data" type="application/json">'''+payload+'''</script><script>
const report=JSON.parse(document.getElementById('report-data').textContent), tables=report.contributions[1].tables;
function tableInto(id,rows,columns){const container=document.getElementById(id);container.replaceChildren();const wrap=document.createElement('div');wrap.className='scroll';const table=document.createElement('table'),head=document.createElement('thead'),tr=document.createElement('tr');for(const [key,label] of columns){const th=document.createElement('th');th.textContent=label;tr.append(th);}head.append(tr);table.append(head);const body=document.createElement('tbody');for(const row of rows){const tr=document.createElement('tr');for(const [key] of columns){const td=document.createElement('td');td.textContent=String(row[key]);tr.append(td);}body.append(tr);}table.append(body);wrap.append(table);container.append(wrap);}
function show(){const mode=Number(document.getElementById('mode').value);tableInto('force-results',tables[0].rows.filter(r=>r.step_number===mode),[['object_name','Obj'],['object_station','ObjSta (ham)'],['element_name','Elm'],['element_station','ElmSta (ham)'],['p','P [kN]'],['v2','V2 [kN]'],['v3','V3 [kN]'],['t','T (ham)'],['m2','M2 (ham)'],['m3','M3 (ham)']]);tableInto('point-results',tables[1].rows.filter(r=>r.step_number===mode),[['point_object','Obj'],['element_name','Elm'],['u1','U1 [m]'],['u2','U2 [m]'],['u3','U3 [m]']]);}
function download(table){const quote=v=>'"'+String(v).replaceAll('"','""')+'"';const csv=[table.columns.map(quote).join(','),...table.rows.map(r=>table.columns.map(k=>quote(r[k])).join(','))].join('\\r\\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='Column_235_V1_'+table.table_id+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
document.getElementById('mode').addEventListener('change',show);document.getElementById('force-csv').addEventListener('click',()=>download(tables[0]));document.getElementById('point-csv').addEventListener('click',()=>download(tables[1]));show();
</script></html>'''


def render_column_v1_pdf(report):
    """Print review of the same projection; full 500 rows remain in JSON/HTML/CSV."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    font_root=Path('/usr/share/fonts/truetype/dejavu')
    for name,file in [('ColumnV1','DejaVuSans.ttf'),('ColumnV1Bold','DejaVuSans-Bold.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(name,str(font_root/file)))
    color=colors.HexColor;navy=color('#173548');muted=color('#647681');line=color('#d8e2e6')
    body=ParagraphStyle('body',fontName='ColumnV1',fontSize=9,leading=14,textColor=navy,spaceAfter=7)
    small=ParagraphStyle('small',parent=body,fontSize=7.4,leading=11,textColor=muted)
    h1=ParagraphStyle('h1',parent=body,fontName='ColumnV1Bold',fontSize=27,leading=34,spaceAfter=14)
    h2=ParagraphStyle('h2',parent=body,fontName='ColumnV1Bold',fontSize=14,leading=20,spaceBefore=10,spaceAfter=12)
    h3=ParagraphStyle('h3',parent=body,fontName='ColumnV1Bold',fontSize=10,leading=15,spaceBefore=8)
    para=lambda s,style=body:Paragraph(escape(str(s)),style)
    def table(headers,rows,widths):
        data=[[para(v,small) for v in headers]]+[[para(v,body) for v in row] for row in rows]
        t=Table(data,colWidths=[v*mm for v in widths],repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),color('#edf3f5')),('LINEBELOW',(0,0),(-1,-1),.5,line),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]));return t
    data=report.as_dict();current,hist,gaps=data['contributions'];story=[para('B-BLOK / COLUMN V1 / 12 EKİM 2026',small),para('Kolon 235',h1),para('Doğrulanmış bilgiler, mevcut sonuçlar ve açık mühendislik kapsamı.'),Spacer(1,8*mm),para('01 / Güncel aday kaynaktan doğrulananlar',h2)]
    story.append(table(['Bilgi','Değer','Birim'],[[f['label'],f['value'],f['unit'] or ''] for f in current['summary_fields'] if f['key']!='source_sha'],[64,85,25]))
    story.extend([Spacer(1,5*mm),para('I22/I33 tam binary64 MATCH. Yalnız Column_80x80 kesit özelliği kapsamında. Kesit adından geometrik ölçü çıkarılmadı; diğer on alan NOT_COMPARABLE / NOT_PROVEN.',small),para('Aday kaynak SHA256: '+CANDIDATE,small),para('Yakalama: '+data['capture_times']['candidate'],small),Spacer(1,6*mm),para('Tasarım durumu',h2),para('Güncel kontrollü kolon tasarım sonucu ve B5 dönemi verilmedi. Bu V1, kapasite/donatı seçimi veya TBDY/TS500 uygunluk hükmü üretmez.'),para('Global Δ: NOT_PROVEN | M6-B: OPEN | R2_RERUN_READY: NO'),para('Rapor için yeni getter veya canlı çalışma ön koşul değildir.',small),PageBreak(),para('02 / Mevcut tarihsel sonuçlar',h2),para('FC09 arşivi: 100 mod, 300 FrameForce ve 200 JointDispl satırı. Bu sonuçlar 61FA aday kaynağının güncel tasarım sonuçlarına bağlanmadı.'),para('Tarihsel Story +0.00 / C1. Native I/J slotları 955 ve 758; bottom/top veya güncel uç eşlemesi yapılmadı.',small),para('Modal mod 1 - ham kuvvet alanları',h3)])
    force=hist['tables'][0]['rows'];points=hist['tables'][1]['rows'];fmt=lambda v:format(v,'.10g') if type(v) is float else str(v)
    story.append(table(['Obj','ObjSta (ham)','Elm','P [kN]','V2 [kN]','V3 [kN]'],[[r['object_name'],fmt(r['object_station']),r['element_name'],fmt(r['p']),fmt(r['v2']),fmt(r['v3'])] for r in force if r['step_number']==1],[16,28,16,38,38,38]))
    story.extend([para('Signed native Modal satırlarıdır; kombinasyon, governing seçim, CQC veya tasarım büyütmesi uygulanmadı. T/M2/M3 dahil tam 300 satır HTML/JSON/CSV’de korunur.',small),para('Modal mod 1 - ham JointDispl bileşenleri',h3)])
    story.append(table(['Obj','Elm','U1 [m]','U2 [m]','U3 [m]'],[[r['point_object'],r['element_name'],fmt(r['u1']),fmt(r['u2']),fmt(r['u3'])] for r in points if r['step_number']==1],[20,20,45,45,44]))
    story.extend([para('U1/U2/U3 ham API alanlarıdır. Global koordinat sözleşmesi nitelendirilmedi; bu değerlerden global Δ üretilmedi. R1/R2/R3 dahil tam 200 satır JSON/CSV’de korunur.',small),para('Capture güncel nitelikli analysis-result/B5 epoch değildir. Connectivity Length ham metni 5.15 ile FrameForce istasyonu aynı fiziksel büyüklük kabul edilmedi.',small),para('Tarihsel kaynak SHA256: '+HISTORICAL,small),para('Yakalama: '+data['capture_times']['historical'],small),PageBreak(),para('03 / Eksikler ve sonuç üzerindeki etkileri',h2)])
    story.append(table(['Alan / durum','Eksik ve etkisi'],[[r['Alan']+' / '+r['Durum'],r['Eksik']+' '+r['Etkisi']] for r in gaps['tables'][0]['rows']],[57,117]))
    story.extend([para('FC09 üretim kapısı değişmedi. Matris taraması başlamadı. Yeni ETABS getter/analiz/tasarım çalıştırılmadı.',small),PageBreak(),para('04 / Kaynak izi',h2),para('Her kaynak kendi kimliğini taşır. Aynı model yolu, farklı SHA256 kaynaklarını eşdeğer yapmaz. Aşağıdaki SHA256’lar kullanılan kabul edilmiş kanıt dosyalarını bağlar.',small)])
    for s in data['source_manifest']['entries']:story.extend([para(s['title'],h3),para(s['locator'],small),para('SHA256 '+s['fingerprint'],small)])
    story.extend([Spacer(1,5*mm),para('Rapor içeriği kaynaklara bağlı bir tek-kolon factual review projeksiyonudur. Tam BuildingReportModel/FCR kapsamı veya yeni formal CheckResult üretilmedi. Kabul edilmiş mevcut rapor katkı/artifact sözleşmeleri kullanıldı.',small),para('Kaynak kod tabanı: '+MAIN_HEAD,small)])
    output=BytesIO()
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('ColumnV1',7);canvas.setFillColor(muted);canvas.drawString(18*mm,12*mm,'Column V1 / 235 / Kaynak kapsamı korunmuştur');canvas.drawRightString(192*mm,12*mm,str(doc.page));canvas.restoreState()
    doc=SimpleDocTemplate(output,pagesize=(210*mm,297*mm),leftMargin=18*mm,rightMargin=18*mm,topMargin=18*mm,bottomMargin=22*mm,title='Kolon 235 - Column V1',author='TBDY / Column V1')
    def deterministic_canvas(*args,**kwargs):
        kwargs['invariant']=1
        return Canvas(*args,**kwargs)
    doc.build(story,onFirstPage=footer,onLaterPages=footer,canvasmaker=deterministic_canvas)
    return output.getvalue()


def build_column_v1_artifacts(report):
    projection=report.to_json().encode();digest=sha256(projection).hexdigest()
    def artifact(format,name,media,content):return ReportArtifact('COLUMN_SINGLE_COMPONENT_EVIDENCE_REVIEW',format,media,name,content,source_report_id='B-BLOK-COLUMN-235-V1',source_project_id='B-BLOK',source_projection_sha256=digest)
    artifacts=[artifact('JSON','Column_235_V1.json','application/json',projection),artifact('HTML','Column_235_V1.html','text/html; charset=utf-8',render_column_v1_html(report).encode()),artifact('PDF','Column_235_V1.pdf','application/pdf',render_column_v1_pdf(report))]
    for table in report.contributions[1].tables:
        text=StringIO(newline='');writer=csv.DictWriter(text,fieldnames=table.columns);writer.writeheader();writer.writerows(dict(r) for r in table.rows)
        artifacts.append(artifact('CSV','Column_235_V1_'+table.table_id+'.csv','text/csv; charset=utf-8',text.getvalue().encode()))
    manifest={'report_id':'B-BLOK-COLUMN-235-V1','source_projection_sha256':digest,'source_manifest':report.sources.as_dict(),'files':[{'name':a.filename,'sha256':a.sha256,'bytes':a.byte_length} for a in artifacts],'engineering_verdict':'NOT_EVALUATED','new_ETABS_execution':False,'source_authority_rebound':False}
    artifacts.append(artifact('JSON','Column_235_V1_provenance.json','application/json',_json(manifest).encode()))
    output=BytesIO()
    with ZipFile(output,'w',compression=ZIP_DEFLATED) as zip:
        for a in artifacts:
            entry=ZipInfo(a.filename,(1980,1,1,0,0,0));entry.compress_type=ZIP_DEFLATED;entry.external_attr=0o100644<<16;zip.writestr(entry,a.content)
    artifacts.append(artifact('ZIP','Column_235_V1.zip','application/zip',output.getvalue()))
    return tuple(artifacts)


def persist_column_v1_artifacts(artifacts, output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    _require(all(not (output/a.filename).exists() for a in artifacts),'output exists; preserve original delivery')
    for artifact in artifacts:
        with (output/artifact.filename).open('xb') as f:f.write(artifact.content)
    return tuple({'name':a.filename,'sha256':a.sha256,'bytes':a.byte_length} for a in artifacts)
