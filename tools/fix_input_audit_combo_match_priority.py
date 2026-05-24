from pathlib import Path

p = Path("tools/run_input_audit_v1.py")
s = p.read_text(encoding="utf-8")

old = '''    for fid, spec in families.items():
        if not isinstance(spec, dict):
            continue
        aliases = spec.get("aliases") or []
        for alias in aliases:
            if normalize_name(alias) and normalize_name(alias) in norm:
                return fid, "alias_contains"

    for fid, spec in families.items():
        if not isinstance(spec, dict):
            continue
        for pat in spec.get("patterns") or []:
            try:
                if re.search(str(pat), str(raw_name), re.I):
                    return fid, "pattern"
            except re.error:
                pass

    return "", "unmapped"
'''

new = '''    # Pattern matching before loose alias_contains prevents generic aliases
    # such as "G" from stealing seismic combos like "G+0.3Q+Ex".
    for fid, spec in families.items():
        if not isinstance(spec, dict):
            continue
        for pat in spec.get("patterns") or []:
            try:
                if re.search(str(pat), str(raw_name), re.I):
                    return fid, "pattern"
            except re.error:
                pass

    for fid, spec in families.items():
        if not isinstance(spec, dict):
            continue
        aliases = spec.get("aliases") or []
        for alias in aliases:
            alias_norm = normalize_name(alias)
            if alias_norm and len(alias_norm) > 1 and alias_norm in norm:
                return fid, "alias_contains"

    return "", "unmapped"
'''

if old not in s:
    raise SystemExit("target block not found; inspect tools/run_input_audit_v1.py manually")

p.write_text(s.replace(old, new), encoding="utf-8")
print("patched", p)
