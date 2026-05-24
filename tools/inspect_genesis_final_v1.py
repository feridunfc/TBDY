from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_JSON = PROJECT_ROOT / "reports_out" / "genesis_final_summary.json"
SUMMARY_TXT = PROJECT_ROOT / "reports_out" / "genesis_final_summary.txt"

def main() -> int:
    if not SUMMARY_JSON.exists():
        print(f"ERROR: summary not found: {SUMMARY_JSON}")
        print("Run first: python tools\\run_genesis_final_v1.py")
        return 2

    d = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))

    print("GENESIS_FINAL_INSPECT_V1")
    print("ok:", d.get("ok"))
    print("metadata:", d.get("metadata"))

    print("\noutputs:")
    for k, v in (d.get("outputs") or {}).items():
        print(f"  {k}: {v}")

    print("\nsteps:")
    for s in d.get("steps", []):
        print(f"  {'PASS' if s.get('ok') else 'FAIL'} {s.get('script')} returncode={s.get('returncode')}")

    for section in ["final_report", "provenance", "combo_alias", "input_audit_v1_1"]:
        print(f"\n{section}:")
        for k, v in (d.get(section) or {}).items():
            print(f"  {k}: {v}")

    if SUMMARY_TXT.exists():
        print("\nsummary_text:")
        print(SUMMARY_TXT.read_text(encoding="utf-8"))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
