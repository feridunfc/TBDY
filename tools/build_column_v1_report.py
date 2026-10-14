"""Build the real 235 V1 report from accepted evidence offline. No ETABS path."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tbdy_engine.product_reports.column_v1_report import build_column_v1_report,build_column_v1_artifacts,persist_column_v1_artifacts

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical-modal-receipt',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.output.resolve().is_relative_to(ROOT):raise ValueError('delivery output must be outside Git worktree')
    report=build_column_v1_report(assignment_path=ROOT/'docs/COLUMN_R1_R3M_ABI4_LIVE_GETSECTION_ADOPTION_2026-10-12.json',property_path=ROOT/'docs/COLUMN_R1_R3M_ABI5_LIVE_GETSECTPROPS_ADOPTION_2026-10-12.json',gates_path=ROOT/'docs/COLUMN_R1_R3M_ABI6_OFFLINE_RECEIPT_2026-10-12.json',modal_path=args.historical_modal_receipt)
    artifacts=build_column_v1_artifacts(report);result=persist_column_v1_artifacts(artifacts,args.output)
    print(json.dumps({'report':'B-BLOK-COLUMN-235-V1','files':result,'new_ETABS_execution':False,'engineering_verdict':'NOT_EVALUATED','GLOBAL_DELTA':'NOT_PROVEN','R2_RERUN_READY':False}))
    return 0

if __name__=='__main__':raise SystemExit(main())
