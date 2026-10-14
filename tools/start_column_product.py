"""Pinned local install/launch; no YAML/.env or native ETABS operation."""
from __future__ import annotations
from pathlib import Path
import argparse, os, socket, subprocess, sys, venv


def install_dependencies(python: Path, requirements: Path, runner=subprocess.run):
    previous=os.environ.get('PYYAML_FORCE_LIBYAML')
    try:
        os.environ['PYYAML_FORCE_LIBYAML']='0'
        # PyYAML 6.0.2 Distribution.ext_status / build_ext honor the numeric 0.
        # Force a fresh source-built pure wheel, never a cached native wheel.
        runner([str(python),'-m','pip','install','--no-cache-dir','--no-binary=PyYAML','-r',str(requirements)],check=True)
    finally:
        if previous is None:os.environ.pop('PYYAML_FORCE_LIBYAML',None)
        else:os.environ['PYYAML_FORCE_LIBYAML']=previous


def check_dependencies(python: Path):
    code="import importlib.metadata as m,yaml; assert m.version('reportlab')=='4.4.9'; assert m.version('PyYAML')=='6.0.2'; assert m.version('jsonschema')=='4.25.1'; assert not yaml.__with_libyaml__; assert yaml.safe_load('a: 1')=={'a':1}"
    return subprocess.run([str(python),'-c',code],capture_output=True).returncode==0


def launch(repo: Path, *, port=8765, install_only=False, audit_file: Path | None = None):
    if sys.version_info < (3,12):raise ValueError('Python 3.12+ gerekli. Linux 3.12 test edildi; Windows 3.14 native qualification henüz yok.')
    if not 1<=port<=65535:raise ValueError('Geçerli port gerekli.')
    if audit_file is not None and (audit_file.resolve().is_relative_to(repo.resolve()) or audit_file.exists()):
        raise ValueError('Audit için repo dışında yeni bir dosya gerekli; mevcut dosya korunuyor.')
    if not install_only:
        with socket.socket() as check:
            try:check.bind(('127.0.0.1',port))
            except OSError:raise ValueError(f'{port} portu kullanımda. Mevcut süreç değiştirilmeyecek; --port ile boş port seçin.') from None
    home=repo/'.column-product-venv';marker=home/'COLUMN_PRODUCT_OWNED_VENV'
    if home.exists() and (home.is_symlink() or not marker.is_file() or marker.read_text()!=str(repo.resolve())):
        raise ValueError('Mevcut .column-product-venv bu launcher’a ait değil; korunuyor. Yeni paket dizini kullanın.')
    if not home.exists():
        venv.EnvBuilder(with_pip=True).create(home);marker.write_text(str(repo.resolve()))
    python=home/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.is_file():raise ValueError('Launcher venv eksik; sunucu başlatılmadı.')
    if not check_dependencies(python):install_dependencies(python,repo/'requirements-column-v2.txt')
    if not check_dependencies(python):raise ValueError('Pinli bağımlılık/saf PyYAML kontrolü başarısız; sunucu başlatılmadı.')
    print('Pinler PASS: reportlab4.4.9 / PyYAML6.0.2 pure / jsonschema4.25.1. YAML/.env gerekli değil.',flush=True)
    if install_only:return 0
    command=[str(python),str(repo/'tools/serve_column_v2.py'),'--port',str(port)]
    if audit_file is not None:command.extend(['--audit-file',str(audit_file.resolve())])
    return subprocess.run(command,cwd=repo).returncode


def main():
    parser=argparse.ArgumentParser(description='Column ürün kurulumu ve yerel başlatma; ETABS çalıştırmaz.')
    parser.add_argument('--port',type=int,default=8765);parser.add_argument('--install-only',action='store_true')
    parser.add_argument('--audit-file',type=Path,help='Repo dışında yeni, özgün backend kayıt dosyası.')
    args=parser.parse_args()
    try:return launch(Path(__file__).resolve().parents[1],port=args.port,install_only=args.install_only,audit_file=args.audit_file)
    except (ValueError,OSError,subprocess.CalledProcessError) as exc:
        print('Kurulum/başlangıç durduruldu: '+str(exc)+'\nSunucu başlamadı; otomatik tekrar yok.',file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
