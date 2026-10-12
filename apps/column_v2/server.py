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
from html import escape
from hashlib import sha256

from tbdy_engine.application.column_reference_workspace import ReferenceColumnInput, ReferenceCalculation, calculate_reference, canonical_bytes
from tbdy_engine.product_reports.column_v2_report import FIELDS, reference_manifest, column_235_manifest, section_svg, render_reference_pdf, render_manifest_pdf


@dataclass
class Workspace:
    context: str = 'reference'
    bundle: dict = field(default_factory=lambda: ReferenceColumnInput().bundle())
    revision: int = 0
    calculation: ReferenceCalculation | None = None
    running: bool = False


class ColumnWorkspace:
    def __init__(self, repo: Path, audit_path: Path | None = None):
        self.repo = repo
        self.evidence = column_235_manifest(repo)
        self.workspaces: dict[str, Workspace] = {}
        self.lock = RLock()
        self.events = []
        self.audit = None if audit_path is None else audit_path.open('x', encoding='utf-8')
        self.code_hashes = {str(p.relative_to(repo)): sha256(p.read_bytes()).hexdigest() for p in (
            repo/'tbdy_engine/application/column_reference_workspace.py',
            repo/'tbdy_engine/design/columns/column_design_engine.py',
            repo/'tbdy_engine/product_reports/column_v2_report.py',
            repo/'apps/column_v2/server.py',repo/'apps/column_v2/index.html')}

    def record(self, event: str, **facts):
        with self.lock:
            item = {'sequence':len(self.events)+1,'utc':datetime.now(timezone.utc).isoformat(),'event':event,**facts}
            self.events.append(item)
            if self.audit:
                self.audit.write(json.dumps(item, ensure_ascii=False, allow_nan=False)+'\n'); self.audit.flush()

    def create(self) -> dict:
        with self.lock:
            if len(self.workspaces) >= 32: raise ValueError('Yerel çalışma alanı sınırı doldu; sunucuyu yeniden başlatın.')
            key = uuid4().hex; self.workspaces[key] = Workspace()
            self.record('WORKSPACE_CREATED', workspace_id=key)
            return {'id':key,'revision':0,'default_bundle':ReferenceColumnInput().bundle(),'fields':FIELDS}

    def get(self, key: str) -> Workspace:
        if key not in self.workspaces: raise ValueError('Bilinmeyen çalışma alanı.')
        return self.workspaces[key]

    def state(self, body: dict) -> dict:
        if set(body) != {'workspace_id','context','bundle'} or body['context'] not in {'reference','235'}:
            raise ValueError('Bilinmeyen bağlam/girdi paketi.')
        if body['context'] == '235' and body['bundle'] is not None:
            raise ValueError('235 bağlamına referans girdi aktarılamaz.')
        with self.lock:
            w = self.get(body['workspace_id']); w.revision += 1; w.calculation = None
            w.context = body['context']; w.bundle = body['bundle']
            self.record('RESULT_INVALIDATED', workspace_id=body['workspace_id'], revision=w.revision, context=w.context)
            if w.context == '235': return {'revision':w.revision,'evidence':self.evidence}
            try: drawing = section_svg(ReferenceColumnInput.from_bundle(w.bundle))
            except (ValueError, TypeError): drawing = '<p>Geçerli ve tam girdi gerekli; kesit çizilmedi.</p>'
            return {'revision':w.revision,'section_svg':drawing}

    def calculate(self, body: dict) -> dict:
        if set(body) != {'workspace_id','revision'}: raise ValueError('Hesap isteği kimliği farklı.')
        with self.lock:
            w = self.get(body['workspace_id'])
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
                return manifest
        except Exception as exc:
            self.record('CALCULATION_REJECTED',workspace_id=body['workspace_id'],revision=revision,exception_type=type(exc).__name__,message=str(exc))
            raise
        finally:
            with self.lock: w.running = False

    def report(self, body: dict) -> tuple[bytes,str,str]:
        if set(body) != {'workspace_id','revision','result_id','format'} or body['format'] not in {'pdf','json'}:
            raise ValueError('Rapor isteği farklı.')
        with self.lock:
            w = self.get(body['workspace_id'])
            if type(body['revision']) is not int or body['revision'] != w.revision: raise ValueError('Eski rapor revizyonu.')
            if w.context == 'reference':
                if w.calculation is None: raise ValueError('Aktif hesap yok; önce Hesapla.')
                manifest = reference_manifest(w.calculation)
                if body['result_id'] != manifest['result_id']: raise ValueError('Aktif sonuç kimliği farklı.')
                content = render_reference_pdf(w.calculation) if body['format'] == 'pdf' else canonical_bytes(manifest)
                name = 'Referans_Kolon_Hesap'
            else:
                if body['result_id'] is not None: raise ValueError('235 için referans sonucu kabul edilmez.')
                manifest = self.evidence
                content = render_manifest_pdf(manifest) if body['format'] == 'pdf' else canonical_bytes(manifest)
                name = 'B_BLOK_235_Kanit'
            self.record('REPORT_EXPORTED',workspace_id=body['workspace_id'],revision=w.revision,context=w.context,
                result_id=manifest.get('result_id'),content_sha256=sha256(content).hexdigest(),format=body['format'])
            return content,('application/pdf' if body['format'] == 'pdf' else 'application/json'),name+'.'+body['format']


def make_server(repo: Path, port: int = 8765, audit_path: Path | None = None, evidence_dir: Path | None = None):
    application = ColumnWorkspace(repo,audit_path)
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
                if not 0<length<=16384 or self.headers.get('Content-Type')!='application/json': raise ValueError('Sınırlı JSON isteği gerekli.')
                body=json.loads(self.rfile.read(length))
                if type(body) is not dict: raise ValueError('JSON nesnesi gerekli.')
                if self.path=='/api/workspace':
                    if body: raise ValueError('Çalışma alanı isteği boş olmalı.')
                    return self.reply(200,application.create())
                if self.path=='/api/state': return self.reply(200,application.state(body))
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
    parser=argparse.ArgumentParser(description='Column V2: offline reference calculation; no ETABS access.')
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
