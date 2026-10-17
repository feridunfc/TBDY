"""Thin localhost transport for the offline typed reference application.

No native acquisition or engineering formulas belong in this adapter.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import RLock
from uuid import uuid4
import json
import sys
from importlib.metadata import version
from html import escape
from hashlib import sha256

from tbdy_engine.application.column_reference_workspace import ReferenceColumnInput, ReferenceCalculation, calculate_reference, canonical_bytes
from tbdy_engine.application.column_reference_producer import ReferenceOwnerInput, calculate_reference_owners
from tbdy_engine.product_reports.column_reference_producer_report import OWNER_FIELDS, owner_reference_manifest, render_owner_reference_pdf, render_owner_reference_html
from tbdy_engine.product_reports.column_v2_report import FIELDS, reference_manifest, column_235_manifest, section_svg, render_reference_pdf, render_manifest_pdf
from tbdy_engine.application.column_product_workspace import validate_packet, apply_review, evaluate_column_product, migrate_v1_packet, known_user_draft, FIELDS as PRODUCT_FIELDS
from tbdy_engine.application.column_qualified_workspace import QualifiedColumnChannel
from tbdy_engine.product_reports.column_qualified_report import render_qualified_html, render_qualified_pdf, present_qualified_result
from tbdy_engine.product_reports.column_product_report import product_authority, product_manifest, product_drawing, render_product_html, render_product_pdf, product_input_authority_matrix


@dataclass
class Workspace:
    context: str = 'reference'
    bundle: dict = field(default_factory=lambda: ReferenceColumnInput().bundle())
    revision: int = 0
    calculation: ReferenceCalculation | None = None
    running: bool = False
    product_calculation: object | None = None
    product_draft: dict | None = None
    run_envelope: dict | None = None


class ColumnWorkspace:
    def __init__(self, repo: Path, audit_path: Path | None = None, qualified_channel: QualifiedColumnChannel | None = None):
        self.qualified_channel = qualified_channel if qualified_channel is not None else QualifiedColumnChannel()
        if type(self.qualified_channel) is not QualifiedColumnChannel: raise TypeError("Original in-process result channel required.")
        self.repo = repo
        self.evidence = column_235_manifest(repo)
        self.product_authority = product_authority(repo)
        self.workspaces: dict[str, Workspace] = {}
        self.lock = RLock()
        self.events = []
        self.audit = None if audit_path is None else audit_path.open('x', encoding='utf-8')
        paths=sorted(set(repo.glob('tbdy_engine/**/*.py')) | set(repo.glob('apps/column_v2/*')) | set(repo.glob('packages/etabs_gateway/src/**/*.py')) | {repo/'requirements-column-v2.txt',repo/'tools/start_column_product.py',repo/'tools/serve_column_v2.py'})
        self.code_hashes={str(p.relative_to(repo)):sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file() and p.suffix in {'.py','.html','.txt'}}
        self.build_id=sha256(canonical_bytes(self.code_hashes)).hexdigest()
        self.runtime_profile={'python':sys.version.split()[0],'dependencies':{name:version(name) for name in ('reportlab','PyYAML','jsonschema')}}

    def verify_build(self):
        observed={name:sha256((self.repo/name).read_bytes()).hexdigest() for name in self.code_hashes}
        if observed!=self.code_hashes:raise ValueError('Çalışan build dosyaları değişti; sunucuyu yeniden başlatın.')

    def attach_run(self, manifest, w, workspace_id):
        envelope={'schema':'column.calculation-run.v1','workspace_id':workspace_id,'calculation_revision':w.revision,
            'result_id':manifest.get('result_id'),'input_sha256':manifest.get('input_sha256'),
            'build_sha256':self.build_id,'code_manifest_sha256':self.build_id,'runtime_profile':self.runtime_profile,
            'input_identity_kind':'QUALIFIED_ARTIFACT_SET' if w.context=='qualified' else 'DECLARED_INPUT_PACKET',
            'calculation_scope':w.context,'source_scope':manifest.get('scope_identity',{'component_id':manifest.get('component_id'),'candidate_sha256':manifest.get('candidate_sha256')}),
            'native_evidence_epoch':manifest.get('evidence_epoch'),'git_head':None}
        w.run_envelope=envelope
        manifest['run_envelope']=envelope
        return manifest

    def record(self, event: str, **facts):
        with self.lock:
            item = {'sequence':len(self.events)+1,'utc':datetime.now(timezone.utc).isoformat(),'event':event,**facts}
            self.events.append(item)
            if self.audit:
                self.audit.write(json.dumps(item, ensure_ascii=False, allow_nan=False)+'\n'); self.audit.flush()

    def create(self) -> dict:
        with self.lock:
            if len(self.workspaces) >= 32: raise ValueError('Yerel çalışma alanı sınırı doldu; sunucuyu yeniden başlatın.')
            key = uuid4().hex; self.workspaces[key] = Workspace(product_draft=known_user_draft(self.product_authority))
            self.record('WORKSPACE_CREATED', workspace_id=key)
            return {'id':key,'revision':0,'default_bundle':ReferenceColumnInput().bundle(),'fields':FIELDS,
                    'owner_reference_bundle':ReferenceOwnerInput.example().bundle(),'owner_reference_fields':OWNER_FIELDS,
                    'build_manifest':{'schema':'column.build.v1','build_sha256':self.build_id,'files':self.code_hashes},
                    'product_packet':self.workspaces[key].product_draft,'product_fields':PRODUCT_FIELDS,'qualified_catalog':self.qualified_channel.catalog()}

    def get(self, key: str) -> Workspace:
        if key not in self.workspaces: raise ValueError('Bilinmeyen çalışma alanı.')
        return self.workspaces[key]

    def state(self, body: dict) -> dict:
        if set(body) != {'workspace_id','context','bundle'} or body['context'] not in {'reference','reference-owners','235','235-product','qualified'}:
            raise ValueError('Bilinmeyen bağlam/girdi paketi.')
        if body['context'] == '235' and body['bundle'] is not None:
            raise ValueError('235 bağlamına referans girdi aktarılamaz.')
        with self.lock:
            w = self.get(body['workspace_id']); w.revision += 1; w.calculation = None; w.product_calculation = None; w.run_envelope = None
            w.context = body['context']; w.bundle = body['bundle']
            self.record('RESULT_INVALIDATED', workspace_id=body['workspace_id'], revision=w.revision, context=w.context)
            if w.context == 'reference-owners':
                try: inputs = ReferenceOwnerInput.from_bundle(w.bundle)
                except Exception:
                    w.bundle = None
                    raise
                return {'revision':w.revision,'section_svg':section_svg(inputs.longitudinal)}
            if w.context == 'qualified':
                try: view = present_qualified_result(self.qualified_channel.consume(w.bundle))
                except Exception:
                    w.bundle = None
                    raise
                return {'revision':w.revision,'qualified':view}
            if w.context == '235-product':
                try:
                    incoming=body['bundle']
                    if isinstance(incoming,dict) and incoming.get('schema')=='column.product.235.input.v1': incoming=migrate_v1_packet(incoming,self.product_authority)
                    w.bundle=validate_packet(incoming,self.product_authority)
                    w.product_draft=w.bundle
                except Exception:
                    w.bundle = None
                    raise
                return self.product_view(w)
            if w.context == '235': return {'revision':w.revision,'evidence':self.evidence}
            try: drawing = section_svg(ReferenceColumnInput.from_bundle(w.bundle))
            except (ValueError, TypeError): drawing = '<p>Geçerli ve tam girdi gerekli; kesit çizilmedi.</p>'
            return {'revision':w.revision,'section_svg':drawing}

    def calculate(self, body: dict) -> dict:
        self.verify_build()
        if set(body) != {'workspace_id','revision'}: raise ValueError('Hesap isteği kimliği farklı.')
        with self.lock:
            owner_reference = self.get(body['workspace_id']).context == 'reference-owners'
        if owner_reference: return self.calculate_reference_producer(body)
        with self.lock:
            w = self.get(body['workspace_id'])
            if w.context == 'qualified':
                if type(body['revision']) is not int or w.revision != body['revision']: raise ValueError('Eski nitelikli sonuç revizyonu.')
                w.product_calculation = None
                view = present_qualified_result(self.qualified_channel.consume(w.bundle))
                w.product_calculation = view
                self.record('QUALIFIED_OWNER_RESULT_CONSUMED', workspace_id=body['workspace_id'],revision=w.revision,
                    result_id=view['result_id'],scope_identity=view['scope_identity'],
                    owner_artifact_sha256={k:v['artifact_sha256'] for k,v in view['owner_outputs'].items()},
                    fnd2_status=view['fnd2_status'],application_status=view['application_status'],native_calls=0)
                return self.attach_run(view,w,body['workspace_id'])
            if w.context == '235-product': return self.calculate_product(body)
            if w.context != 'reference': raise ValueError('235 için hesap girdileri eksik; referans hesabı kullanılamaz.')
            if type(body['revision']) is not int or w.revision != body['revision']: raise ValueError('Eski girdi revizyonu.')
            if w.running: raise ValueError('Bu çalışma alanında hesap zaten çalışıyor; otomatik tekrar yok.')
            # Reject malformed input before recording an engine invocation.
            inputs = ReferenceColumnInput.from_bundle(w.bundle)
            w.running = True; w.calculation = None; revision = w.revision
            self.record('ENGINE_ENTERED', workspace_id=body['workspace_id'],revision=revision,
                function='tbdy_engine.design.columns.column_design_engine.evaluate_column_design',
                input_sha256=sha256(canonical_bytes(inputs.bundle())).hexdigest(),code_sha256=self.code_hashes)
        try:
            calculation = calculate_reference(inputs.bundle())
            manifest = reference_manifest(calculation)
            with self.lock:
                self.record('ENGINE_RETURNED',workspace_id=body['workspace_id'],revision=revision,
                    input_sha256=calculation.input_sha256,result_id=manifest['result_id'],engine_status=calculation.engine_result.status)
                if w.revision != revision or w.context != 'reference':
                    self.record('STALE_ENGINE_RESULT_REJECTED',workspace_id=body['workspace_id'],revision=revision)
                    raise ValueError('Hesap sırasında girdi/bağlam değişti; sonuç geçersiz.')
                w.calculation = calculation
                return self.attach_run(manifest,w,body['workspace_id'])
        except Exception as exc:
            self.record('CALCULATION_REJECTED',workspace_id=body['workspace_id'],revision=revision,exception_type=type(exc).__name__,message=str(exc))
            raise
        finally:
            with self.lock: w.running = False

    def report(self, body: dict) -> tuple[bytes,str,str]:
        self.verify_build()
        if set(body) != {'workspace_id','revision','result_id','format'} or body['format'] not in {'pdf','json','html'}:
            raise ValueError('Rapor isteği farklı.')
        with self.lock:
            w = self.get(body['workspace_id'])
            if type(body['revision']) is not int or body['revision'] != w.revision: raise ValueError('Eski rapor revizyonu.')
            if w.context == 'qualified':
                if w.product_calculation is None: raise ValueError('Aktif nitelikli sonuç yok; önce sonucu doğrulayın.')
                manifest = present_qualified_result(self.qualified_channel.consume(w.bundle))
                if body['result_id'] != manifest['result_id']: raise ValueError('Nitelikli sonuç kimliği farklı.')
                manifest['run_envelope']=w.run_envelope
                content = render_qualified_pdf(manifest) if body['format']=='pdf' else render_qualified_html(manifest).encode() if body['format']=='html' else canonical_bytes(manifest)
                name = 'Qualified_Column_Owner_Result'
            elif w.context == '235-product':
                if w.product_calculation is None: raise ValueError('Aktif 235 değerlendirmesi yok; önce Hesapla.')
                manifest = product_manifest(w.product_calculation,self.product_authority)
                if body['result_id'] != manifest['result_id']: raise ValueError('Aktif 235 sonuç kimliği farklı.')
                manifest['run_envelope']=w.run_envelope
                content = render_product_pdf(manifest) if body['format']=='pdf' else render_product_html(manifest).encode() if body['format']=='html' else canonical_bytes(manifest)
                name = 'B_BLOK_235_Calisma'
            elif w.context == 'reference-owners':
                if w.product_calculation is None: raise ValueError('Aktif owner hesabı yok; önce Hesapla.')
                manifest = owner_reference_manifest(w.product_calculation)
                if body['result_id'] != manifest['result_id']: raise ValueError('Aktif owner sonuç kimliği farklı.')
                manifest['run_envelope']=w.run_envelope
                content = render_manifest_pdf(manifest,input_fields=OWNER_FIELDS) if body['format']=='pdf' else render_owner_reference_html(manifest).encode() if body['format']=='html' else canonical_bytes(manifest)
                name = 'Editable_Reference_Owner_Calculation'
            elif w.context == 'reference':
                if body['format']=='html': raise ValueError('Referans HTML export bu endpoint kapsamında değil.')
                if w.calculation is None: raise ValueError('Aktif hesap yok; önce Hesapla.')
                manifest = reference_manifest(w.calculation)
                if body['result_id'] != manifest['result_id']: raise ValueError('Aktif sonuç kimliği farklı.')
                manifest['run_envelope']=w.run_envelope
                content = render_manifest_pdf(manifest) if body['format'] == 'pdf' else canonical_bytes(manifest)
                name = 'Referans_Kolon_Hesap'
            else:
                if body['format']=='html': raise ValueError('Kanıt HTML için teknik panel bağlantısı kullanın.')
                if body['result_id'] is not None: raise ValueError('235 için referans sonucu kabul edilmez.')
                # Passive accepted evidence is not a calculation run. Keep its
                # original projection exact; active calculations carry a run envelope.
                manifest = dict(self.evidence)
                content = render_manifest_pdf(manifest) if body['format'] == 'pdf' else canonical_bytes(manifest)
                name = 'B_BLOK_235_Kanit'
            self.record('REPORT_EXPORTED',workspace_id=body['workspace_id'],revision=w.revision,context=w.context,
                result_id=manifest.get('result_id'),content_sha256=sha256(content).hexdigest(),format=body['format'])
            return content,('application/pdf' if body['format'] == 'pdf' else 'text/html; charset=utf-8' if body['format']=='html' else 'application/json'),name+'.'+body['format']

    def calculate_reference_producer(self, body):
        with self.lock:
            w = self.get(body['workspace_id'])
            if w.context != 'reference-owners' or type(body['revision']) is not int or w.revision != body['revision']:
                raise ValueError('Eski/farklı owner referans revizyonu.')
            if w.running: raise ValueError('Owner hesabı zaten çalışıyor; otomatik tekrar yok.')
            inputs = ReferenceOwnerInput.from_bundle(w.bundle)
            revision = w.revision
            w.running = True; w.product_calculation = None
        def observe(phase, name, digest, value):
            facts = {}
            if phase == 'RETURNED':
                if hasattr(value, 'engine_result'): facts['engine_status'] = value.engine_result.status
                else:
                    facts['owner_checks'] = [c.as_dict() for c in value.checks]
                    facts['shear_vr_by_direction_kn'] = value.shear_vr_by_direction_kn
            self.record('REFERENCE_OWNER_'+phase, workspace_id=body['workspace_id'],revision=revision,
                        function=name,input_sha256=digest,native_calls=0,**facts)
        try:
            calculation = calculate_reference_owners(inputs.bundle(), observe=observe)
            manifest = owner_reference_manifest(calculation)
            with self.lock:
                if w.revision != revision or w.context != 'reference-owners':
                    self.record('STALE_OWNER_RESULT_REJECTED',workspace_id=body['workspace_id'],revision=revision)
                    raise ValueError('Owner hesabı sırasında girdi/bağlam değişti; sonuç geçersiz.')
                w.product_calculation = calculation
                self.record('REFERENCE_PRODUCER_RETURNED',workspace_id=body['workspace_id'],revision=revision,
                    input_sha256=calculation.input_sha256,result_id=manifest['result_id'],
                    invoked_owners=calculation.invoked_owners,engineering_complete=False,native_calls=0)
                return self.attach_run(manifest,w,body['workspace_id'])
        except Exception as exc:
            self.record('REFERENCE_PRODUCER_REJECTED',workspace_id=body['workspace_id'],revision=revision,
                        exception_type=type(exc).__name__,message=str(exc)); raise
        finally:
            with self.lock: w.running = False


    def product_view(self, w):
        return {'revision':w.revision,'product':{'packet':w.bundle,'fields':PRODUCT_FIELDS,
            'native_evidence':self.evidence,'section_svg':product_drawing(w.bundle),
            'input_authority_matrix':product_input_authority_matrix(w.bundle,self.product_authority),
            'result':None,'session_connection':'NOT_OBSERVED'}}

    def review_product(self, body):
        if set(body) != {'workspace_id','revision','group','declaration'}: raise ValueError('Review isteği farklı.')
        with self.lock:
            w=self.get(body['workspace_id'])
            if w.context!='235-product' or type(body['revision']) is not int or w.revision!=body['revision']: raise ValueError('Eski/farklı review revizyonu.')
            w.revision+=1;w.calculation=None;w.product_calculation=None;w.run_envelope=None
            self.record('PRODUCT_REVIEW_RESULT_INVALIDATED',workspace_id=body['workspace_id'],revision=w.revision)
            try: w.bundle=apply_review(w.bundle,body['group'],body['declaration'],self.product_authority)
            except Exception:
                # Never keep an old reviewed result after a rejected submission.
                raise
            self.record('PROJECT_DECLARATION_REVIEWED',workspace_id=body['workspace_id'],revision=w.revision,group=body['group'],origin=body['declaration']['origin'])
            w.product_draft=w.bundle
            return self.product_view(w)

    def calculate_product(self, body):
        # Called under the existing workspace RLock. Only pure offline owners.
        w=self.get(body['workspace_id'])
        if type(body['revision']) is not int or w.revision!=body['revision']: raise ValueError('Eski 235 hesap revizyonu.')
        if w.running: raise ValueError('Hesap zaten çalışıyor; otomatik tekrar yok.')
        packet=validate_packet(w.bundle,self.product_authority);revision=w.revision;w.running=True;w.product_calculation=None
        self.record('PRODUCT_ENGINE_ENTERED',workspace_id=body['workspace_id'],revision=revision,input_sha256=sha256(canonical_bytes(packet)).hexdigest(),code_sha256=self.code_hashes)
        try:
            evaluation=evaluate_column_product(packet,self.product_authority)
            if w.revision!=revision or w.context!='235-product': raise ValueError('Eski 235 hesap sonucu.')
            manifest=product_manifest(evaluation,self.product_authority)
            w.product_calculation=evaluation
            self.record('PRODUCT_ENGINE_RETURNED',workspace_id=body['workspace_id'],revision=revision,result_id=manifest['result_id'],invoked_owners=evaluation.invoked_owners,design_ready=False)
            return self.attach_run(manifest,w,body['workspace_id'])
        except Exception as exc:
            self.record('PRODUCT_CALCULATION_REJECTED',workspace_id=body['workspace_id'],revision=revision,exception_type=type(exc).__name__,message=str(exc));raise
        finally:w.running=False


def make_server(repo: Path, port: int = 8765, audit_path: Path | None = None, evidence_dir: Path | None = None, qualified_channel: QualifiedColumnChannel | None = None):
    application = ColumnWorkspace(repo,audit_path,qualified_channel)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def reply(self, code, content, media='application/json', filename=None):
            if not isinstance(content,bytes): content=canonical_bytes(content)
            self.send_response(code);self.send_header('Content-Type',media);self.send_header('Content-Length',str(len(content)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            if filename: self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
            self.end_headers();self.wfile.write(content)
        def do_GET(self):
            if self.path=='/': return self.reply(200,(repo/'apps/column_v2/index.html').read_bytes(),'text/html; charset=utf-8')
            if self.path.startswith('/evidence'):
                names={'/evidence':'Column_235_V1.html','/evidence/pdf':'Column_235_V1.pdf','/evidence/archive':'Column_235_V1_bundle.zip'}
                name=names.get(self.path)
                if name and evidence_dir and (evidence_dir/name).is_file():
                    return self.reply(200,(evidence_dir/name).read_bytes(),{'html':'text/html; charset=utf-8','pdf':'application/pdf','zip':'application/zip'}[name.rsplit('.',1)[-1]])
                return self.reply(200,('<html lang="tr"><meta charset="UTF-8"><title>235 kanıt kapsamı</title><h1>235 / kabul edilmiş kanıtlar</h1><p>Tarihsel modal arşiv bu sunucuya bağlanmadı. V1 arşivini --evidence-dir ile ayrı bağlayabilirsiniz; hesap için ön koşul değildir.</p><pre>'+escape(json.dumps(application.evidence,ensure_ascii=False,indent=2))+'</pre></html>').encode(),'text/html; charset=utf-8')
            self.reply(404,{'error':'Sayfa bulunamadı.'})
        def do_POST(self):
            # Local transport only. Cross-origin requests cannot mutate workspaces.
            origin=self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:
                return self.reply(403,{'error':'Yalnız aynı yerel origin kabul edilir.'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=(2097152 if self.path=='/api/state' else 16384) or self.headers.get('Content-Type')!='application/json': raise ValueError('Sınırlı JSON isteği gerekli.')
                body=json.loads(self.rfile.read(length))
                if type(body) is not dict: raise ValueError('JSON nesnesi gerekli.')
                if self.path=='/api/workspace':
                    if body: raise ValueError('Çalışma alanı isteği boş olmalı.')
                    return self.reply(200,application.create())
                if self.path=='/api/state': return self.reply(200,application.state(body))
                if self.path=='/api/product/review': return self.reply(200,application.review_product(body))
                if self.path=='/api/calculate': return self.reply(200,application.calculate(body))
                if self.path=='/api/report':
                    content,media,name=application.report(body);return self.reply(200,content,media,name)
                self.reply(404,{'error':'İşlem bulunamadı.'})
            except (ValueError,TypeError,KeyError) as exc: self.reply(422,{'error':str(exc)})
            except Exception as exc:
                application.record('ADAPTER_FAILURE',exception_type=type(exc).__name__,message=str(exc))
                self.reply(500,{'error':str(exc)})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.application=application
    return server


def main(repo: Path):
    parser=argparse.ArgumentParser(description='Column V3: offline 235 project inputs and reference workspace; no ETABS access.')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--audit-file',type=Path,help='New exclusive JSONL file outside the repository.')
    parser.add_argument('--evidence-dir',type=Path,help='Optional existing passive V1 artifact directory.')
    args=parser.parse_args()
    if args.audit_file and args.audit_file.resolve().is_relative_to(repo.resolve()): parser.error('Audit file must be outside the repository.')
    server=make_server(repo,args.port,args.audit_file,args.evidence_dir)
    print(f'Column V2: http://127.0.0.1:{server.server_port} / OFFLINE / ETABS NOT CALLED',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close()
        if server.application.audit: server.application.audit.close()
