# COLUMN-R1 R3K — getter-only native schema probe

Prepared 2026-10-11. **LIVE_EXECUTION = NOT_AUTHORIZED.** This document proposes
one operator execution for supervisor authorization. The worker has not attached
to ETABS or run the probe against a live model.

## Scope

Only the exact `Joint Displacements` schema is queried. Reuse the accepted
[R3J source-route report](COLUMN_R1_R3J_GLOBAL_DISPLACEMENT_SOURCE_ROUTE_2026-10-11.md)
and its machine receipt; no exhausted general CSI search is repeated.

The implementation uses `tbdy_engine.etabs.oapi.database_tables` and the existing
verified session/gateway STA. `GetAllFieldsInTable` uses the already-reviewed
eight-output ABI: TableVersion, NumberFields, FieldKey, FieldName, Description,
UnitsString, IsImportable, pRetVal. The cache authority reference remains unchanged.
All FieldKeys, descriptions and native unit strings are retained, including
unfamiliar spellings or blank dimensionless metadata. No translation FieldKey,
axis, unit dimension or result meaning is invented.

For optional `GetAvailableTables`, the actual local generated cDatabaseTables
declaration must establish named outputs and their ordering before one native
call is attempted. Pointer-interface IID and parameter flags are retained. An
absent member or unqualified generated ABI is recorded as NOT_OBSERVED; it does
not trigger a guessed signature or retry. If the call is made, nonzero/invalid
return codes, shape/count/type errors and duplicate table identities block.
Native presence or IsEmpty is a factual observation only. Field metadata remains
an independent query; a native not-listed table does not grant result availability.

The probe calls neither `GetTableForDisplayArray` nor any result getter. It never
uses output-selection transactions, modal ranges or setters. It issues no B5
epoch or engineering provider result. Exact source/session/capture bindings,
fresh identity observations surrounding each query, and pre/post original EDB
SHA256 must agree. Existing unit-observation support is limited to reviewed enum
relationships; if current observations are unqualified, stop without changing
units. Lock state must be observable and unchanged.

## Operator prerequisites

1. Obtain explicit supervisor authorization for this single schema-discovery
   execution and its exact R3K repository HEAD. This preparation is not permission.
2. On Windows, use the existing compatible Python/comtypes and ETABS gateway
   environment. Check out the authorized R3K commit in a clean checkout; do not
   reset, discard, rebase or force-push existing work. Keep evidence outside it.
3. Identify and independently verify the already-running ETABS PID. Confirm it
   has the protected original `C:\tmp\B-BLOK_Revised.EDB` loaded, not scratch or
   another model. Program/API must be ETABS 23.2.0 / 2.014.
4. Original disk SHA256 must be
   `FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F`.
5. Keep the model, lock state, analysis state, selections, session and units
   unchanged while the probe runs. Do not interact with ETABS concurrently.
6. Use an existing outside-repository evidence directory. Receipt and `.sha256`
   sidecar must both be new. The probe writes them exclusively and marks them
   read-only. This is filesystem read-only protection plus byte hashes, not WORM
   storage. Preserve both original files; do not edit a failed receipt.

## Proposed Windows PowerShell command

Run from the authorized repository root **only after supervisor authorization**.
`$authorizedHead` and `$etabsPid` are operator inputs copied from the explicit
authorization and independently verified PID; neither is automatically selected.
The final worker exit contract supplies the exact remote HEAD.

```powershell
$ErrorActionPreference = 'Stop'
$authorizedHead = Read-Host 'Supervisor-authorized exact R3K HEAD (40 lowercase hex)'
if ($authorizedHead -notmatch '^[0-9a-f]{40}$') { throw 'Exact authorized HEAD required' }
if ((git rev-parse HEAD).Trim() -ne $authorizedHead) { throw 'Repository HEAD mismatch' }
if (git status --porcelain) { throw 'Clean authorized checkout required; preserve existing work' }
[int]$etabsPid = Read-Host 'Independently verified existing ETABS PID'
if ($etabsPid -le 0) { throw 'Positive verified PID required' }
$process = Get-Process -Id $etabsPid -ErrorAction Stop
if ($process.ProcessName -ne 'ETABS') { throw 'Verified PID is not ETABS' }
$source = 'C:\tmp\B-BLOK_Revised.EDB'
$expectedSha = 'FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F'
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $expectedSha) { throw 'Protected source SHA mismatch' }
$evidenceDir = 'C:\tmp\column-r1-r3k-schema-evidence'
if (-not (Test-Path -LiteralPath $evidenceDir -PathType Container)) { throw 'Create the authorized outside-repository evidence directory first' }
$receipt = Join-Path $evidenceDir ('column-r1-r3k-schema_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff') + '.json')
python .\tools\column_r1_r3k_schema_read_only.py `
  --source $source `
  --pid $etabsPid `
  --expected-head $authorizedHead `
  --receipt $receipt
if ($LASTEXITCODE -ne 0) { throw ('Schema probe blocked; preserve original receipt: ' + $receipt) }
Get-FileHash -LiteralPath $receipt -Algorithm SHA256
Get-Content -LiteralPath ($receipt + '.sha256')
```

No command here launches ETABS, saves the model, runs analysis/design, changes
units or changes output selections. The receipt is schema evidence only. A
successful schema extraction still leaves all post-schema engineering gates open.

## CSI escalation and post-schema gate

The focused [R3J support draft](COLUMN_R1_R3J_GLOBAL_DISPLACEMENT_SOURCE_ROUTE_2026-10-11.md)
remains DRAFT / NOT SENT. It covers coordinate basis, exact translation fields,
signed modal case/mode grain, panel-zone generated joints and the PointElm
matrix order/direction/applicability. No response is claimed. Any positive reply
must be archived with its date, complete original text and authority reference.

Before global Delta, independently establish: TABLE FIELD SEMANTICS; COORDINATE
BASIS; MODAL ROW GRAIN; POINT OBJECT / RESULT ELEMENT BINDING; PANEL ZONE
APPLICABILITY; and exact 172 endpoints × 100 modes. Field names alone cannot
close any engineering gate. Preserve the PointElm alternative without identity
or transpose assumptions if the table route cannot qualify.

Retain GLOBAL_MODAL_DELTA NOT_PROVEN; CURRENT_B5 NOT_PROVIDED;
JOINT_DELTA_R_V PROJECT_DECISION_REQUIRED; M6-B OPEN; R2_RERUN_READY NO;
Column-R1 software CLOSED; B-BLOK engineering OPEN.

## Offline validation

The fresh integrated run passed all 1543 distinct identities: all 1489 accepted
identities preserved plus 54 new offline synthetic probe identities, with zero
failures/errors/skips. The focused getter/safety/metadata package passed 202.
Exact post-PR203 main and R3K canonical negative suites each have 17 PASS /
5 actual FAIL, with identical full diagnostics/guard hashes/allowlist. An added
legacy OAPI guard suite each has 14 PASS / 1 actual FAIL: the existing StartDesign
callsite expectation mismatch is byte/callsite-identical in the exact base and
candidate. It is supplemental existing debt, not one of the canonical five;
no failure is relabeled PASS. Zero new/expanded violations. Compile/import, CLI
help and diff-check PASS. No architecture guard, baseline or allowlist changed.
See [offline receipt](COLUMN_R1_R3K_SCHEMA_PROBE_RECEIPT_2026-10-11.json).

All safety PASS claims are offline preparation/test evidence. Native availability,
field metadata, live unit/session observations and raw COM response hashes are
NOT_OBSERVED until an authorized operator supplies the original probe receipt.
