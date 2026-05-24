from pathlib import Path
import re

p = Path("tools/combo_alias_resolver_v1.py")
s = p.read_text(encoding="utf-8")

new_func = '''def normalize_combo_name(name: str) -> str:
    s = str(name or "").strip().upper()

    # Turkish / Unicode normalization.
    # Important: str.translate keys must be single Unicode codepoints.
    trans = str.maketrans({
        "İ": "I",
        "ı": "I",
        "Ş": "S",
        "Ğ": "G",
        "Ü": "U",
        "Ö": "O",
        "Ç": "C",
        "ş": "S",
        "ğ": "G",
        "ü": "U",
        "ö": "O",
        "ç": "C",
    })
    s = s.translate(trans)

    # Defensive cleanup for decomposed Turkish İ: I + combining dot above.
    s = s.replace(chr(0x0307), "")

    s = s.replace("×", "X")
    s = re.sub(r"\\bLOAD\\s*COMBO\\b", "", s)
    s = re.sub(r"\\bCOMBO\\b", "", s)
    s = re.sub(r"\\s+", "", s)
    s = s.replace("_", "")
    return s
'''

pattern = r'def normalize_combo_name\(name: str\) -> str:\n.*?\n(?=def _merge_unique)'
s2, n = re.subn(pattern, lambda m: new_func + "\n\n", s, count=1, flags=re.S)

if n != 1:
    raise SystemExit(f"normalize_combo_name replacement failed; replacements={n}")

p.write_text(s2, encoding="utf-8")
print("patched", p)
