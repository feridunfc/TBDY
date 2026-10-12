"""Actual isolated Git checkout tests; no ETABS or COM access."""
import hashlib
import os
from pathlib import Path
import subprocess
import pytest

TARGET='docs/COLUMN_R1_R3M_ABI6_GETPOINTS_TARGET_2026-10-12.json'
SHA='bb660a45059af6d5d8d93581527092b83c6e159998225ec6ae75c32f5e220d79'

@pytest.mark.parametrize('autocrlf',['true','false'])
def test_checkout_preserves_pinned_target_and_clean_tree_under_git_eol_settings(tmp_path,autocrlf):
    source=Path(os.environ['COLUMN_R1_ABI4_REPO'])
    def git(*args):
        return subprocess.check_output(['git','-C',str(tmp_path),*args],stderr=subprocess.PIPE)
    git('init','-q');git('config','user.name','Offline checkout regression')
    git('config','user.email','offline@example.invalid');git('config','core.autocrlf',autocrlf)
    git('config','core.safecrlf','false')
    (tmp_path/'.gitattributes').write_bytes((source/'.gitattributes').read_bytes())
    p=tmp_path/TARGET;p.parent.mkdir(parents=True);p.write_bytes((source/TARGET).read_bytes())
    other=tmp_path/'other.json';other.write_bytes(b'{"unrelated": true}\n')
    git('add','.gitattributes',TARGET,'other.json');git('commit','-qm','isolated checkout fixture')
    p.unlink();other.unlink()
    git('checkout-index','-u','--force','--',TARGET,'other.json')
    assert hashlib.sha256(p.read_bytes()).hexdigest()==SHA and b'\r' not in p.read_bytes()
    assert git('status','--porcelain')==b''
    assert git('check-attr','eol','--',TARGET).decode().strip()==TARGET+': eol: lf'
    assert git('check-attr','eol','--','other.json').decode().strip()=='other.json: eol: unspecified'
    assert other.read_bytes()==(b'{"unrelated": true}\r\n' if autocrlf=='true' else b'{"unrelated": true}\n')
    assert git('rev-parse','HEAD:'+TARGET).strip()==git('hash-object','--no-filters',str(p)).strip()
    p.write_bytes((source/TARGET).read_bytes());git('update-index','--refresh')
    assert git('status','--porcelain')==b'' and hashlib.sha256(p.read_bytes()).hexdigest()==SHA
