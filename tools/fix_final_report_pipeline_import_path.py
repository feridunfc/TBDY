from pathlib import Path

p = Path("tools/run_final_engine_report_v1.py")
s = p.read_text(encoding="utf-8")

needle = 'PROJECT_ROOT = Path(__file__).resolve().parents[1]\nREPORTS_OUT = PROJECT_ROOT / "reports_out"\n'
replacement = '''PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
REPORTS_OUT = PROJECT_ROOT / "reports_out"
'''

if needle not in s:
    raise SystemExit("needle not found; inspect tools/run_final_engine_report_v1.py manually")

p.write_text(s.replace(needle, replacement), encoding="utf-8")
print("patched", p)
