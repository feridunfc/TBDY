# Column V1 - real single-column235 report delivery

Base main `810f93159bc2207b3d0280ac85e9930b7aaf6586`, tree
`54af7aa7a314dfc0a80aa6766684a49150f452b6`, merged PR207 independently verified.
Operator pin98f15e0 is unchanged. No ETABS/native getter or new getter preparation.

## Delivered product

A real, openable offline report for235, with accepted current-source facts,
existing historical results and explicit missing engineering outputs:

- `Column_235_V1.html`: self-contained Turkish report, native mode1 visible with
  JavaScript disabled;100-mode selector and full CSV downloads with JavaScript.
- `Column_235_V1.pdf`: four visually inspected A4 pages: current facts, existing
  FC09 result example, missing engineering scope, source trace.
- `Column_235_V1.json`: immutable render-neutral truth projection.
- `Column_235_V1_frame_force.csv`: all300 original signed native FrameForce rows.
- `Column_235_V1_joint_displ.csv`: all200 original native rows for955/758.
- `Column_235_V1_provenance.json`: sources, exact projection/file hashes.
- `Column_235_V1.zip`: deterministic complete six-file review package.

Artifacts live outside Git and are separately delivered. The Git receipt records
exact hashes. The existing `SliceReportContribution`, `ReportField`, `ReportTable`,
`SourceManifest` and `ReportArtifact` contracts are reused. No fabricated FCR,
BuildingReportModel, formal CheckResult, design result or compliance denominator.
This is a source-bound factual single-component review product; the accepted
Column-R1 production composition and its engineering authorities are unchanged.

## Source and engineering scope

Latest accepted candidate61FA: original ABI4 Name235 assignment and ABI5 named
Column_80x80 property. I22/I33 each0.03413333333333332m4, exact binary64 MATCH
within existing per-output authority. Other ten properties NOT_COMPARABLE /
NOT_PROVEN; no geometry/inertia formulas from the section name.

FC09 original R3D file SHA
`83ce2ff7c3a6170e931d2869e212adde93b7c08b25bbf44e9f0c2c663f156b03`:
frame235 historical Story+0.00/C1; native connectivity I/J955/758;300 FrameForce
rows and200 JointDispl rows,100 modes, exact Modal/Mode grain, payload hashes
independently checked. Tables retain native Obj/Elm/station/mode/sign identities;
no averaging, modal combination, governing selection or raw-result repair.

This historical source is not rebound to current candidate61FA. Native I/J
slot order does not become bottom/top or candidate endpoint identity. Global
coordinate/Δ, panel-zone and column-connected analysis-joint binding remain
unqualified. FrameForce P/V2/V3 show the recorded kN force context; U1/U2/U3 show
recorded m context. Moment/station fields remain raw; no missing per-field unit,
offset or physical-endpoint authority is inferred. Connectivity Length raw
5.15 and FrameForce stations0/2.225/4.45 are not treated as identical physical
quantities. The factual capture is not a qualified current B5 result epoch.

Current controlled design result/B5 not provided; globalΔ NOT_PROVEN; M6-B OPEN;
R2_RERUN_READY NO. Design N/M demands, capacity ratio, selected reinforcement,
final quantity and global TBDY/TS500 compliance are not issued. Missing data and
its consequence are visible in the report rather than replaced by numbers.
New GetPoints preparation/execution is not a report prerequisite.

## Reproduction and validation

Run offline, with the exact unchanged accepted R3D original outside Git:

```bash
python tools/build_column_v1_report.py \
  --historical-modal-receipt /absolute/path/column-r1-r3d-modal_20261010_073229.json \
  --output /absolute/path/new_column_v1_delivery
```

The tool reads pinned adopted ABI4/ABI5/gate documents from this repository and
pinned historical bytes. Any source hash/binding/grain failure stops. Delivery
refuses pre-existing filenames. ReportLab4.4.9, DejaVuSans regular/bold in the
Linux rendering profile, Node for syntax tests, pypdf for PDF checks; no live
ETABS or Python/comtypes operator environment required to open the artifacts.

Focused offline regressions exercise source drift/rebinding, false B5 promotion,
wrong/duplicate modal grain, complete raw-value preservation, deterministic
HTML/PDF/JSON/CSV/ZIP, PDF reopening/text, manifest/ZIP hashes, output preservation,
HTML static fallback/script injection and actual rendered JavaScript syntax.

HTML JavaScript executed in jsdom: native mode1/2/50/100 populations3+2, exact
mode100 raw P,100 options and both CSV download events PASS. No network resources.
Headless Chromium binary download failed in this environment; a native-browser
screenshot is not claimed. HTML visual print reviewed through WeasyPrint69.0;
four final PDF pages visually reviewed and exact PDF bytes pinned. Engineering
and source qualification do not depend on browser availability.

Fresh integrated/architecture evidence and preserved2162 identities are in
`COLUMN_V1_235_OFFLINE_RECEIPT_2026-10-12.json`. Six inherited architecture
failures remain real FAIL; no guard/allowlist or protected source changes.

## Continuing boundaries

FC09_PRODUCTION_GATE UNCHANGED. Current candidate only. GetPoints live authority
NO; worker ETABS NO; no analysis/design/save/units/selection/model mutation;
operator artifacts unchanged; matrix scan NOT_STARTED; GLOBAL_DELTA NOT_PROVEN;
M6_B OPEN; R2_RERUN_READY NO. ABI2-6/old engineering research not reopened.

NEXT EXACT CAUSAL EDGE: review/open the delivered Column235 V1 product. Further
engineering/gateway authority remains separate from report delivery.
