from pathlib import Path

p = Path("tools/combo_alias_resolver_v1.py")
s = p.read_text(encoding="utf-8")

old = '''def normalize_combo_name(name: str) -> str:
    s = str(name or "").strip().upper()
    trans = str.maketrans({
        "İ": "I", "İ": "I", "ı": "I", "Ş": "S", "Ğ": "G", "Ü": "U", "Ö": "O", "Ç": "C",
        "ş": "S", "ğ": "G", "ü": "U", "ö": "O", "ç": "C",
    })
    s = s.translate(trans)
    s = s.replace("×", "X")
    s = re.sub(r"\\bLOAD\\s*COMBO\\b", "", s)
    s = re.sub(r"\\bCOMBO\\b", "", s)
    s = re.sub(r"\\s+", "", s)
    s = s.replace("_", "").replace("-", "-")
    return s
'''

new = '''def normalize_combo_name(name: str) -> str:
    s = str(name or "").strip().upper()
    # Turkish character normalization. Keep keys single-character for str.translate.
    trans = str.maketrans({
        "İ": "I", "I": "I", "ı": "I",
        "Ş": "S", "Ğ": "G", "Ü": "U", "Ö": "O", "Ç": "C",
        "ş": "S", "ğ": "G", "ü": "U", "ö": "O", "ç": "C",
    })
    s = s.translate(trans)
    s = s.replace("\\u0307", "")  # defensive: remove combining dot above if present
    s = s.replace("×", "X")
    s = re.sub(r"\\bLOAD\\s*COMBO\\b", "", s)
    s = re.sub(r"\\bCOMBO\\b", "", s)
    s = re.sub(r"\\s+", "", s)
    s = s.replace("_", "").replace("-", "-")
    return s
'''

if old not in s:
    raise SystemExit("target normalize_combo_name block not found")

p.write_text(s.replace(old, new), encoding="utf-8")
print("patched", p)
