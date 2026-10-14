"""Actual UI import/review/edit/calculate/source-switch/export/error regressions."""
from pathlib import Path
from threading import Thread
import os,json,subprocess,shutil
import pytest
from apps.column_v2.server import make_server
REPO=Path(__file__).resolve().parents[2]
SCENARIOS=('actual_empty','review_recompute_export','import_source','import_units','import_component','import_epoch','import_result_epoch','missing_review_error','product_delayed_context')

@pytest.mark.parametrize('scenario',SCENARIOS)
def test_actual_product_browser(scenario,tmp_path):
    node=os.environ.get('COLUMN_V2_BROWSER_NODE') or shutil.which('node');binary=os.environ.get('COLUMN_V2_BROWSER_BINARY');module=os.environ.get('COLUMN_V2_PLAYWRIGHT_MODULE')
    if not node or not binary or not module:pytest.skip('Explicit browser profile required; supplied for full private delivery.')
    if not Path(binary).is_file() or not Path(module).is_dir():pytest.fail('Configured browser profile missing.')
    capture=Path(os.environ['COLUMN_PRODUCT_CAPTURE_DIR'])/scenario if os.environ.get('COLUMN_PRODUCT_CAPTURE_DIR') else tmp_path
    capture.mkdir(parents=True,exist_ok=True);audit=capture/'Backend_Execution.jsonl'
    server=make_server(REPO,0,audit_path=audit);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        args=dict(url=f'http://127.0.0.1:{server.server_port}',scenario=scenario,output=str(capture/'Browser_Evidence.json'),screenshot=str(capture/'Screen.png'),artifact_dir=str(capture))
        p=subprocess.run([node,str(Path(__file__).with_name('column_product_browser.cjs')),json.dumps(args)],capture_output=True,text=True,env=os.environ.copy(),timeout=45)
        assert p.returncode==0,p.stdout+'\n'+p.stderr
        result=json.loads((capture/'Browser_Evidence.json').read_text());assert not result['page_errors'] and result['scenario']==scenario
        if scenario=='actual_empty':
            assert any(e['event']=='PRODUCT_ENGINE_RETURNED' and not e['invoked_owners'] for e in server.application.events)
        if scenario=='review_recompute_export':
            assert len([e for e in server.application.events if e['event']=='PRODUCT_ENGINE_RETURNED'])==2
    finally:
        server.shutdown();server.server_close();thread.join(5);server.application.audit.close()
