
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = PROJECT_ROOT / "reports_out" / "engine_report_enriched.json"

NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
ASH_FAIL_RE = re.compile(
    rf"Ash\s*=\s*({NUMBER})\s*mm2\s*<\s*required\s*=\s*({NUMBER})\s*mm2",
    re.I,
)
PROVIDED_RE = re.compile(
    rf"provided\s*=\s*Phi\s*({NUMBER})\s*@\s*({NUMBER})\s*mm",
    re.I,
)
LEGS_RE = re.compile(r"legs\s*=\s*(\d+)\s*/\s*(\d+)", re.I)
PROPOSAL_RE = re.compile(r"Proposal\s*:\s*(.+?)(?:$|\. source=| source=)", re.I)

FINAL_SOURCE_TOKENS = {
    "user",
    "provided",
    "provided_rebar",
    "final",
    "section_rebar_defs",
    "column_rebar_defs",
}

NON_FINAL_SOURCE_TOKENS = {
    "etabs_design_summary",
    "auto_confinement",
    "screening",
    "proposal",
    "default",
    "fallback",
}

def _msg(row):
    return str(row.get("message") or row.get("description") or "")

def _source(row):
    return str(row.get("source") or "").strip()

def _level(row):
    return str(row.get("evaluation_level") or "").upper().strip()

def _status(row):
    return str(row.get("status") or "").upper().strip()

def _has_any(text, tokens):
    t = str(text or "").lower()
    return any(tok in t for tok in tokens)

def extract_confinement_fields(row):
    msg = _msg(row)
    out = {}

    m = ASH_FAIL_RE.search(msg)
    if m:
        out["Ash_provided"] = float(m.group(1))
        out["Ash_required"] = float(m.group(2))

    p = PROVIDED_RE.search(msg)
    if p:
        out["tie_dia_mm"] = float(p.group(1))
        out["spacing_mm"] = float(p.group(2))

    l = LEGS_RE.search(msg)
    if l:
        out["legs_x"] = int(l.group(1))
        out["legs_y"] = int(l.group(2))

    prop = PROPOSAL_RE.search(msg)
    if prop:
        out["proposal_text"] = prop.group(1).strip()

    return out

def is_non_final_confinement_proposal(row):
    if str(row.get("check_id") or "") != "column_confinement":
        return False

    source = _source(row)
    msg = _msg(row)
    level = _level(row)
    status = _status(row)
    source_or_msg = f"{source} {msg}"

    if _has_any(source, FINAL_SOURCE_TOKENS) and not _has_any(source, NON_FINAL_SOURCE_TOKENS):
        return False

    has_proposal = "proposal" in msg.lower() or "auto proposal" in msg.lower()
    has_non_final_source = _has_any(source_or_msg, NON_FINAL_SOURCE_TOKENS)
    has_screening_level = level in {"SCREENING", "APPROXIMATE"}

    return status == "FAIL" and (has_proposal or has_non_final_source or has_screening_level)

def apply_policy_to_row(row):
    if str(row.get("check_id") or "") != "column_confinement":
        return row, False

    fields = extract_confinement_fields(row)
    for k, v in fields.items():
        row.setdefault(k, v)

    if not is_non_final_confinement_proposal(row):
        if fields:
            row.setdefault("confinement_policy", "evidence_extracted_only")
        return row, False

    row["original_status"] = row.get("status")
    row["original_evaluation_level"] = row.get("evaluation_level")
    row["original_source"] = row.get("source")
    row["original_reason_code"] = row.get("reason_code")

    row["status"] = "WARNING"
    row["evaluation_level"] = "SCREENING"
    row["source"] = "confinement_proposal"
    row["reason_code"] = "non_final_confinement_proposal"
    row["confinement_policy"] = "FAIL_to_WARNING_non_final_proposal"

    row["message"] = (
        "Confinement screening warning: transverse reinforcement data is derived from "
        "ETABS design summary / automatic proposal, not final user-provided detailing. "
        f"{_msg(row)}"
    )
    row["action"] = (
        "Enter final/user-provided confinement detailing "
        "(tie diameter, spacing, legs_x, legs_y) and rerun DESIGN_LEVEL confinement check. "
        "Do not treat automatic proposal such as '12 legs Phi8' as final design."
    )

    return row, True

def aggregate_column_design_full(rows):
    changed = 0

    real_confinement_fail_exists = any(
        r.get("check_id") == "column_confinement"
        and str(r.get("status")).upper() == "FAIL"
        and not is_non_final_confinement_proposal(r)
        for r in rows
    )

    if real_confinement_fail_exists:
        return 0

    for row in rows:
        if row.get("check_id") != "column_design_full":
            continue
        if str(row.get("status") or "").upper() != "FAIL":
            continue

        row["original_status"] = row.get("status")
        row["status"] = "WARNING"
        row["evaluation_level"] = "SCREENING"
        row["source"] = row.get("source") or "column_module_summary"
        row["reason_code"] = "non_final_confinement_proposal_controls_summary"
        row["confinement_policy"] = "summary_FAIL_to_WARNING_no_real_confinement_FAIL"
        row["message"] = (
            "Column design summary warning: no final/provided DESIGN_LEVEL confinement FAIL "
            "remains after policy normalization. Original summary was controlled by "
            "non-final confinement proposal/screening data. " + _msg(row)
        )
        row["action"] = (
            "Provide final confinement detailing and rerun. Keep summary as FAIL only when "
            "a real user/provided/final DESIGN_LEVEL confinement failure exists."
        )
        changed += 1

    return changed

def recalc_distributions(rows):
    def c(key):
        return dict(Counter(str(r.get(key) or "<empty>") for r in rows if isinstance(r, dict)))
    return {
        "by_status": c("status"),
        "by_check_id": c("check_id"),
        "by_evaluation_level": c("evaluation_level"),
        "by_source": c("source"),
        "by_reason_code": c("reason_code"),
        "by_category": c("category"),
    }

def apply_policy(report):
    rows = [r for r in report.get("checks", []) if isinstance(r, dict)]
    changed_conf = 0
    evidence_only = 0

    for row in rows:
        _, changed = apply_policy_to_row(row)
        if changed:
            changed_conf += 1
        elif row.get("check_id") == "column_confinement" and row.get("confinement_policy") == "evidence_extracted_only":
            evidence_only += 1

    changed_summary = aggregate_column_design_full(rows)

    report["checks"] = rows
    report["distributions"] = recalc_distributions(rows)

    meta = dict(report.get("report_metadata") or {})
    meta["schema"] = "engine_report.v1.2+confinement_policy.v1.1"
    meta["confinement_policy"] = "Column Confinement Cleanup v1.1"
    meta["confinement_policy_applied_at"] = datetime.now().isoformat(timespec="seconds")
    report["report_metadata"] = meta

    report["confinement_policy_summary"] = {
        "column_confinement_rows": sum(1 for r in rows if r.get("check_id") == "column_confinement"),
        "column_confinement_fail_to_warning": changed_conf,
        "column_confinement_evidence_only": evidence_only,
        "column_design_full_fail_to_warning": changed_summary,
        "remaining_column_confinement_FAIL": sum(
            1 for r in rows if r.get("check_id") == "column_confinement" and str(r.get("status")).upper() == "FAIL"
        ),
        "remaining_column_design_full_FAIL": sum(
            1 for r in rows if r.get("check_id") == "column_design_full" and str(r.get("status")).upper() == "FAIL"
        ),
    }
    return report

def main(argv=None):
    argv = argv or sys.argv[1:]
    in_path = Path(argv[0]) if argv else DEFAULT_REPORT
    in_path = in_path if in_path.is_absolute() else PROJECT_ROOT / in_path

    if not in_path.exists():
        print(f"ERROR: report not found: {in_path}")
        return 2

    report = json.loads(in_path.read_text(encoding="utf-8"))
    out = apply_policy(report)

    out_dir = in_path.parent
    out_path = out_dir / "engine_report_confinement_policy.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    hist_dir = out_dir / "history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    hist_path = hist_dir / f"{stamp}_engine_report_confinement_policy.json"
    hist_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print("COLUMN_CONFINEMENT_POLICY_V1_1")
    print("input:", in_path)
    print("output:", out_path)
    print("snapshot:", hist_path)
    for k, v in out["confinement_policy_summary"].items():
        print(f"{k}: {v}")

    print("\nby_status:")
    for k, v in out["distributions"]["by_status"].items():
        print(f"  {k}: {v}")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
