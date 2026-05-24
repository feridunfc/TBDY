from pathlib import Path
import shutil
import yaml

root = Path.cwd()
path = root / "tbdy_engine" / "contracts" / "checks.yaml"
backup = root / "tbdy_engine" / "contracts" / "backup_scwb_activation" / "checks.yaml.before_eval_field_fix.bak"
backup.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(path, backup)

data = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
checks = data.get("checks", [])

mapping = {
    "column_capacity_hierarchy": "column_capacity_hierarchy",
    "beam_capacity_hierarchy": "beam_capacity_hierarchy",
}

def patch_check(chk, check_id, output_key):
    chk["evaluation"] = "SCWB_CHECK"
    chk["evaluation_field"] = output_key
    chk["output_key"] = output_key
    chk["runner_enabled"] = True

if isinstance(checks, list):
    found = set()
    for chk in checks:
        if isinstance(chk, dict) and chk.get("id") in mapping:
            cid = chk["id"]
            patch_check(chk, cid, mapping[cid])
            found.add(cid)
    for cid, out in mapping.items():
        if cid not in found:
            chk = {"id": cid}
            patch_check(chk, cid, out)
            checks.append(chk)

elif isinstance(checks, dict):
    for cid, out in mapping.items():
        chk = checks.setdefault(cid, {"id": cid})
        patch_check(chk, cid, out)
else:
    raise TypeError(f"Unsupported checks type: {type(checks).__name__}")

path.write_text(
    yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
    encoding="utf-8",
)

print("PATCHED", path)
print("BACKUP", backup)

for cid in mapping:
    if isinstance(checks, list):
        chk = next(x for x in checks if isinstance(x, dict) and x.get("id") == cid)
    else:
        chk = checks[cid]
    print("---", cid)
    print(yaml.safe_dump(chk, allow_unicode=True, sort_keys=False))
