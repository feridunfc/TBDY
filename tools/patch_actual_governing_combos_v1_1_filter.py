from __future__ import annotations

from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TARGET = PROJECT_ROOT / "tools" / "extract_actual_governing_combos_v1.py"

EXTRA = '''
# === ACTUAL_COMBO_V1_1_METADATA_FILTER_START ===
METADATA_COMBO_KEYS_EXCLUDE = {
    "combo_family",
    "combo_required_family",
    "combo_resolved_family",
    "combo_alias_summary",
    "combo_provenance_level",
    "combo_resolved_by",
    "combo_resolved_by_v1",
    "combo_resolution_confidence",
    "combo_matches_required_family",
    "combo_audit_source",
    "combo_alias_resolver",
    "combo_alias_resolver_applied_at",
    "available_families_from_raw_combos",
    "raw_combo_values_found_in_report",
    "mapped_combos",
    "unmapped_combos",
    "resolved_family",
    "resolved_by",
    "required_family",
}
PIPELINE_FALLBACK_FIELD_NAMES = {"raw_combo", "governing_combo"}
ACTUAL_COMBO_SOURCE_HINTS = (
    "design_summary",
    "beam_design_summary",
    "column_design_summary",
    "force_table",
    "frame_force",
    "frame_forces",
    "etabs_table",
    "ctx.tables",
    "ctx_tables",
    "database_tables",
    "table.",
    "tables.",
)
# === ACTUAL_COMBO_V1_1_METADATA_FILTER_END ===
'''

NEW_IS_CANDIDATE_KEY = '''def is_candidate_key(key: str) -> bool:
    nk = normalize_key(key)
    if nk in METADATA_COMBO_KEYS_EXCLUDE:
        return False
    if nk in CANDIDATE_KEY_TOKENS:
        return True
    if nk in {"case", "case_name", "output_case", "load_case"}:
        return True
    return False
'''

HELPER = '''def source_path_allows_actual_combo(path: str, key: str, source: str = "") -> bool:
    nk = normalize_key(key)
    text = f"{path} {source}".lower()

    if nk in METADATA_COMBO_KEYS_EXCLUDE:
        return False

    if nk in PIPELINE_FALLBACK_FIELD_NAMES:
        return any(h in text for h in ACTUAL_COMBO_SOURCE_HINTS)

    if "final_engine_report" in text and not any(h in text for h in ACTUAL_COMBO_SOURCE_HINTS):
        return False

    return True
'''

NEW_CANDIDATE_FROM_MAPPING = '''def candidate_from_mapping(mapping: Dict[str, Any], source_prefix: str) -> List[Dict[str, Any]]:
    out = []
    for k, v in flatten(mapping):
        key = k.split(".")[-1].split("[")[0]
        if is_candidate_key(key) and is_candidate_value(v) and source_path_allows_actual_combo(k, key, source_prefix):
            raw = str(v).strip()
            res = resolve_combo_family(raw)
            out.append({
                "candidate": raw,
                "field": key,
                "path": k,
                "source": source_prefix,
                "family": res.get("resolved_family") or "",
                "resolved_by": res.get("resolved_by") or "",
                "confidence": res.get("confidence", ""),
            })
    return out
'''

def replace_func(s: str, name: str, new: str, next_name: str) -> str:
    pattern = rf'def {name}\(.*?\n(?=def {next_name}\()'
    s2, n = re.subn(pattern, lambda m: new + "\n", s, count=1, flags=re.S)
    if n != 1:
        raise SystemExit(f"failed replacing {name}; replacements={n}")
    return s2

def main() -> int:
    if not TARGET.exists():
        raise SystemExit(f"target not found: {TARGET}")
    s = TARGET.read_text(encoding="utf-8")

    if "METADATA_COMBO_KEYS_EXCLUDE" not in s:
        marker = 'SKIP_VALUES_PREFIXES = ("UNEXPOSED_ETABS_COMBO::",)\n'
        if marker not in s:
            raise SystemExit("SKIP_VALUES_PREFIXES marker not found")
        s = s.replace(marker, marker + EXTRA + "\n", 1)

    s = replace_func(s, "is_candidate_key", NEW_IS_CANDIDATE_KEY, "is_candidate_value")

    if "def source_path_allows_actual_combo" not in s:
        marker = "\ndef candidate_from_mapping("
        if marker not in s:
            raise SystemExit("candidate_from_mapping marker not found")
        s = s.replace(marker, "\n" + HELPER + "\n" + marker.lstrip(), 1)

    s = replace_func(s, "candidate_from_mapping", NEW_CANDIDATE_FROM_MAPPING, "scan_report_rows")

    old = 'if is_candidate_key(k) and is_candidate_value(v):'
    new = 'if is_candidate_key(k) and is_candidate_value(v) and source_path_allows_actual_combo(f"row[{i}].{k}", k, str(path.relative_to(PROJECT_ROOT))):'
    if old in s and new not in s:
        s = s.replace(old, new, 1)

    s = s.replace("Genesis Actual ETABS Governing Combo Extraction v1", "Genesis Actual ETABS Governing Combo Extraction v1.1 Metadata Filter")
    s = s.replace('print("ACTUAL_ETABS_GOVERNING_COMBO_EXTRACTION_V1")', 'print("ACTUAL_ETABS_GOVERNING_COMBO_EXTRACTION_V1_1")')
    s = s.replace("GENESIS ACTUAL ETABS GOVERNING COMBO EXTRACTION V1", "GENESIS ACTUAL ETABS GOVERNING COMBO EXTRACTION V1.1")

    TARGET.write_text(s, encoding="utf-8")
    print("patched", TARGET)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
