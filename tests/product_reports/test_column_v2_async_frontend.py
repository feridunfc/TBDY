"""Browser response-order regressions against the unchanged real HTTP backend."""
from pathlib import Path
from threading import Thread
import json, os, shutil, subprocess
import pytest
from apps.column_v2.server import make_server

REPO=Path(__file__).resolve().parents[2]
SCENARIOS=('race_235_reference','repeated_reference_final','repeated_235_final','delayed_state_failure','active_state_failure','calculation_state_obsolete_no_dispatch','calculation_context_change','calculation_repeated_contexts','calculation_delayed_failure','export_context_change','export_delayed_failure','input_delayed_failure')

@pytest.mark.parametrize('scenario',SCENARIOS)
def test_real_frontend_delayed_response_keeps_latest_context(scenario,tmp_path):
    node=os.environ.get('COLUMN_V2_BROWSER_NODE') or shutil.which('node')
    binary=os.environ.get('COLUMN_V2_BROWSER_BINARY')
    module=os.environ.get('COLUMN_V2_PLAYWRIGHT_MODULE')
    if not node or not binary or not module:
        pytest.skip('Native browser test profile not supplied; private delivery validation supplies all three pins.')
    if not Path(binary).is_file() or not Path(module).is_dir():
        pytest.fail('Configured native browser test profile missing.')
    server=make_server(REPO,0);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    output=tmp_path/'browser.json'
    try:
        run=subprocess.run([node,str(Path(__file__).with_name('column_v2_async_browser.cjs')),json.dumps({'base_url':f'http://127.0.0.1:{server.server_port}','scenario':scenario,'output':str(output)})],env=os.environ.copy(),capture_output=True,text=True,timeout=40)
        assert run.returncode==0,run.stdout+'\n'+run.stderr
        evidence=json.loads(output.read_text());assert evidence['scenario']==scenario and not evidence['page_errors']
        assert evidence['records'] and all(r['actual_status'] in {200,422} for r in evidence['records'] if 'actual_status' in r)
        if scenario=='calculation_state_obsolete_no_dispatch':
            assert not any(event['event']=='ENGINE_ENTERED' for event in server.application.events)
    finally:
        server.shutdown();server.server_close();thread.join(5)
