"""Actual isolated Git checkout tests; no ETABS or COM access."""
import hashlib
import os
from pathlib import Path
import subprocess
import pytest

TARGET='docs/COLUMN_R1_R3M_ABI4_GETSECTION_TARGET_2026-10-12.json'
SHA='74fece6a6da2a460e6bf561c4c597ea177e7efae1bb3abb5ecb828df2aa441fb'

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
