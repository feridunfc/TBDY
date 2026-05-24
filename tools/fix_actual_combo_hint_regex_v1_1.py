from pathlib import Path
import re

p = Path("tools/extract_actual_governing_combos_v1.py")
s = p.read_text(encoding="utf-8")

old = r'''COMBO_HINT_RE = re.compile(
    r"(?:\b(?:G|D|Q|L|E|EX|EY|EQ|RS|SPEC|K_E|KE|DRIFT|DEPREM|CAPACITY|KAPASITE)\b|[+\-*/]|\d\.\d)",
    re.I,
)
'''

new = r'''COMBO_HINT_RE = re.compile(
    r"(?:\b(?:G|D|Q|L|E|EX|EY|EQ|RS|SPEC|KE|DRIFT|DEPREM|CAPACITY|KAPASITE)\b|K[_\-\s]?E(?:[_\-\s]?[XY])?|[+\-*/]|\d\.\d)",
    re.I,
)
'''

if old not in s:
    raise SystemExit("COMBO_HINT_RE block not found")

p.write_text(s.replace(old, new), encoding="utf-8")
print("patched", p)
