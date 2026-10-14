"""No native calls: source guard for external GetRectangle metadata package."""
import hashlib
import json
import os
from pathlib import Path
import re
import pytest

ROOT = Path(__file__).resolve().parents[2]
EXPECT = ROOT / 'docs/COLUMN_235_GETRECTANGLE_METADATA_OFFLINE_EXPECTATION_2026-10-14.json'

def fact():
    return json.loads(EXPECT.read_text(encoding='utf-8'))

def test_exact_reviewed_parent_pin():
    d=fact()
    assert d['start_head']=='a16a9865c93c5b64f91f1571247f42088b233e01'
    assert d['start_tree']=='0cc9adef749c231bd656630e63c01bb539467b7b'

def test_source_audit_pin_integrity():
    d=fact();audit=d['audit_source_sha256']
    assert len(audit)==9
    assert all(re.fullmatch('[0-9a-f]{64}',v) for v in audit.values())
    files={n:ROOT/n for n in audit}
    if not all(p.is_file() for p in files.values()):
        pytest.skip('isolated offline fixture lacks complete exact Git source')
    for name,p in files.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest()==audit[name],name

def test_explicitly_unobserved_and_no_live_authority():
    d=fact()
    assert d['status']=='OFFLINE_DERIVED_NO_LIVE'
    assert d['native_declaration']=='PENDING_LIVE'
    assert d['native_getter_attempts']==0
    assert d['live_metadata_authorized'] is False
    assert d['current_235_design_ready'] is False
    assert d['M6_B']=='OPEN'
    assert d['original_abi7']=='CLOSED_REUSE_UNCHANGED'

def test_external_artifact_pins_have_byte_sha256_shape():
    d=fact()
    for k in ('external_python_sha256','external_operator_ps_sha256','external_prepare_ps_sha256','member_spec_sha256','dependency_ast_sha256'):
        assert re.fullmatch('[0-9a-f]{64}',d[k])

def test_pinned_external_scripts_if_explicitly_provided():
    folder=os.environ.get('COLUMN235_GETRECTANGLE_EXTERNAL_DIR')
    if not folder:pytest.skip('external operator package intentionally outside Git')
    d=fact()
    names={'external_python_sha256':'column235_getrectangle_metadata_only.py',
           'external_operator_ps_sha256':'operator_metadata_only.ps1',
           'external_prepare_ps_sha256':'prepare_metadata_only.ps1'}
    for k,n in names.items():
        assert hashlib.sha256((Path(folder)/n).read_bytes()).hexdigest()==d[k]
