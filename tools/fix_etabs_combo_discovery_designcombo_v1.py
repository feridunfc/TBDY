from pathlib import Path

p = Path("tools/discover_etabs_combo_columns_v1.py")
s = p.read_text(encoding="utf-8")

old = '''    "design_combo", "designcombination", "design_combo_name", "designcomb",
    "output_case", "outputcase", "load_case", "loadcase",
'''

new = '''    "design_combo", "designcombo", "designcombination", "design_combo_name", "designcomb",
    "output_case", "outputcase", "load_case", "loadcase",
'''

if old not in s:
    raise SystemExit("target combo column block not found")

p.write_text(s.replace(old, new), encoding="utf-8")
print("patched", p)
