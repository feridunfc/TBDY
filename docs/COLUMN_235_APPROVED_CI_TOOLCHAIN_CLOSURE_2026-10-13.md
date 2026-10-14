# Column 235 — bounded CI toolchain correction closed

The supervisor-authorized Python 3.12 and ReportLab 4.4.9 setup changes passed the original UR-1E zero-new gate. No production, test expectation, baseline selection, guard, allowlist or ABI operator change was made.

Validated source HEAD: `16d88ea1b0f7b4cb22921f8aa7608f591a719e1d`
Validated source TREE: `eca477dc7fcf9553d59cfb5dc50f3388fc9c2bf0`
Exact PR base: `810f93159bc2207b3d0280ac85e9930b7aaf6586`
[Actual GitHub run](https://github.com/feridunfc/TBDY/actions/runs/38450118453) — **SUCCESS**. Candidate and exact base use the same new toolchain; no historical replay base substituted.

| Profile | Candidate PASS / FAIL / SKIP | Exact base PASS / FAIL / SKIP | Zero-new |
| --- | --- | --- | --- |
| Actual GitHub | 1147 / 2 / 39 | 1022 / 2 / 0 | PASS |
| Local cold Python 3.12, same pinned report dependencies | 1148 / 2 / 38 | 1022 / 2 / 0 | PASS |

Two shared broad-regression failures remain **real FAIL** (coverage import isolation and generic-resolver import isolation). They were not skipped or waived. The six previously introduced failures pass. Local qualified owner module: **24 PASS / 1 existing browser-profile SKIP**. Counts from different runtime profiles are not combined.

All **2404 accepted identities** freshly collected: 2326 prior plus 78 accepted ABI7; missing/extra 0. All 524 test source files unchanged from the reviewed fixture-import checkpoint. New tests 0. This collection preserves identities; it is **not a fresh full 2404 PASS run**.

Architecture: 31 PASS / same 6 real FAIL against both exact PR base and previous worker. Full guard sets and mutation callsites equal; new/expanded violations 0. Protected ledger remains original: **1 explicitly authorized / 0 unauthorized drift**, other 44 exact hashes preserved.

Workflow before SHA256: `a9254d8a7014907982e311fd897ba4f5b511154d0eec6984e519e3eabe390fd4`
Approved/actual after SHA256: `12719cf429c5073f4e4d2591d3699528f8945f9ca42090076a8a367645db7b0f`
Original zero-new gate SHA256: `172aa495c59c1827e03d7d42ab74be40353b8b3441a61fd57d172c57b3c185bb`.

Compile/import/diff checks PASS. The closing commit changes derived evidence documents only; the actual Actions verdict is explicitly bound to the source HEAD above. No green verdict is manufactured for any later docs-only commit.

Original ABI7 operator HEAD `9f426f5b6376b9c6da984270171556d2e3b2c496` / TREE `c557a517d07fa973a8ea5c2aabb3fbb8d65d34fb` and pins are unchanged. Original moving-branch prepare still fails closed on a newer worker HEAD. No repin or native execution authorized. PR208 remains draft/open/unmerged.

WORKER_ETABS=NO; NEW_NATIVE_GETTERS=0; LIVE_AUTHORIZATION=NONE; MATRIX_SCAN=NOT_STARTED; RESULT_CAPTURE=NO. FC09_PRODUCTION_GATE=UNCHANGED; GLOBAL_DELTA=NOT_PROVEN; M6_B=OPEN; R2_RERUN_READY=NO.

Evidence and individual proof hashes: `COLUMN_235_APPROVED_CI_TOOLCHAIN_RECEIPT_2026-10-13.json`. Stop for supervisor review; no merge or live getter follows this CI correction.
