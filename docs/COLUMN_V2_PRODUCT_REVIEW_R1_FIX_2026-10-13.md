# Column V2 - supervisor R1 asynchronous context correction

Review: `REVISION_REQUESTED` against HEAD2e00b3ab43d9a34322f5702b2311f21e40e911a8,
treefcf01d78619d46af68f373150c282ef43ad7cc65. The accepted numerical reference
slice and all engineering/source/server guards are reused without change.

## Defect and bounded fix

The original JavaScript applied a delayed235 state success after the user had
already returned to reference. The header/dropdown could say reference while
inputs, section name and technical manifest belonged to235. The unchanged
checkpoint was reproduced in real Chromium153 against actual Python HTTP
responses. Its rejected observation is preserved separately from the new capture.

Every context/input/calculation/export operation now captures an immutable
context+epoch token and the applicable server revision. After each asynchronous
boundary, success/error rendering requires that token to remain active. Returning
to the same context creates a new epoch. Obsolete acknowledgements do not update
current UI revision/readiness; backend state transactions remain ordered.

A context switch immediately clears the former inputs/drawing/results/technical
manifest/export controls.235 shows a loading shell until its active evidence
arrives. All controls derive from the latest context readiness and the current
calculation/export snapshot. A late calculation releases only its in-flight lock;
it cannot restore an old result or overwrite current messages. If context changes
while calculation awaits state, the obsolete calculation is never dispatched.
Exports pin context/revision/result identity; late blobs and failures are discarded
without downloading a mismatched file or placing an old error in the new context.

No backend, renderer, numerical kernel, regulatory rule, source-authority, native
ABI or architecture-policy implementation changed.

## Deterministic regression profile

`tests/product_reports/test_column_v2_async_frontend.py` invokes actual Chromium
and the delivered frontend against the real local Python server. The accompanying
`.cjs` harness deliberately holds actual `/api/state`, `/api/calculate` and
`/api/report` responses. Failure tests send a deliberately unknown workspace ID
to the real backend and hold its actual422 response; no native/engineering response
is manufactured.12 focused browser scenarios cover235->reference, repeated
context transitions ending in either context, delayed/active state failures,
no obsolete calculation dispatch, context changes during calculation/export,
and late input/calculation/export failures. Browser dependency paths are an
explicit test profile, never production imports. Missing profile is reported
as SKIP outside the private delivery environment; configured missing files FAIL.
The full delivery run supplies the profile and requires zero skipped identities.

The four normal product flows are rerun separately in actual Chromium with the
clean Python dependency profile. Width500->800 mm still gives M3 lambda20->12.5
and minimum M3 moment30->39 kN.m. The original numerical input/result identities
remain historical; new browser/backend captures have new workspace/time identities
and the corrected frontend code hash.

## Installation and boundaries

The user has not installed or run the package. Worker browser records and
supervisor audit records are separate observations; no user installation receipt
or independent supervisor Chromium replay is claimed. Deliver the corrected
exact-LF archive before requesting any user installation.

Python3.12+, `python -m pip install -r requirements-column-v2.txt`; from the
extracted package root launch with `python tools/serve_column_v2.py` and open
`http://127.0.0.1:8765`. Optional passive V1 archive binding is not required.

Original App ZIP, original supervisor upload archive/delivery, original worker
receipts, PDFs and original rejected reproduction remain immutable and separate.
Final identity/architecture/byte ledgers are recorded in the R1 offline receipt.

WORKER_ETABS=NO;NEW_NATIVE_GETTERS=0;LIVE_GETPOINTS=NOT_AUTHORIZED;
172_MATRIX_SCAN=NOT_STARTED;RESULT_CAPTURE=NO;FC09_PRODUCTION_GATE=UNCHANGED;
GLOBAL_DELTA=NOT_PROVEN;M6_B=OPEN;R2_RERUN_READY=NO.
REFERENCE_REBAR=DESIGN_CANDIDATE_ONLY;235=NOT_EVALUATED.
STOP: revised supervisor product review. No automatic next getter work.
