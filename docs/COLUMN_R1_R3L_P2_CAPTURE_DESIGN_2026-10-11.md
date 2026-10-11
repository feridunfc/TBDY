# COLUMN-R1 R3L — P2 result acquisition design

**PREPARED / BLOCKED BEFORE AUTHORIZATION. P2_EXECUTION_AUTHORIZED=NO.**
This separately reviewable design contains no executable acquisition command.
The coordinate contract must close before P2 authorization is proposed. R3L
does not execute GetTableForDisplayArray, a selection setter, or any ETABS call.

## Preconditions

Archive an applicable CSI contract establishing global translations in the exact
ETABS 23.2/API 2.014 Joint Displacements API table, including rotated point axes,
signed direct modal grain, exact CaseType token and the panel-zone result-joint
selection rule. Adopt original P1 hashes and schema; reconfirm schema/version
and units in the prospective source session without promoting changed metadata.
Review complete endpoint panel-zone assignments and exact table-row to
column-connected analysis-joint mapping. Obtain only facts absent from the
accepted R3D/P1 evidence. Unknown native method/table identities or ABIs require
source qualification before a bounded getter implementation; no speculative names.

Bind a clean separately authorized capture HEAD/TREE, independently verified
existing PID, exact loaded `C:\tmp\B-BLOK_Revised.EDB`, ETABS 23.2.0/API 2.014,
protected FC09 SHA and observable lock state. PID 2072 is the historical P1 PID;
it must not be assumed to identify a future process. Attach without fallback.
Verify present/database raw unit identities and return codes independently;
require m translation units and exact unchanged unit state. Reuse the existing
session-bound gateway and DatabaseTables owners. No parallel COM attachment,
direct public SapModel escape or new safety owner is proposed.

## Selection safety transaction and restoration law

This capture is a result **read with reviewed temporary output-selection state**,
not getter-only P1. Review and separately authorize every selection/options setter
before execution. If no setters are authorized, read only a natively verified
already-correct selection/range; otherwise stop. Do not call the existing generic
output selector merely because it accepts a preferred name.

The existing DatabaseTablesReadTransaction snapshots native selected cases,
combinations, optional patterns and output options under its acquisition lock.
Its generic select_output first tries a combination and preserves the opposite
domain: it explicitly records VERIFIED_SUPERSET_SELECTION. It **does not guarantee
Modal-only output**, and can select a same-named combination. This is a material
implementation limit; R3L changes no safety code and grants no execution approval.

Preferred prospective transaction: a separately reviewed typed exact-case
operation within the existing owner, with native case/combination classification
first. Target state must be selected cases=(existing Modal case,), combinations=(),
patterns exactly unchanged. No combo-first attempt, automatic fallback, combo
creation or assumed CaseType token. Snapshot/readbacks must use exact native ABI
and return code 0; compare complete ordered selections, not just containment.
If this exact-case operation is unavailable, P2 remains blocked pending its review.
The generic owner's core restoration writes cases then combinations in one try;
a failed case setter can prevent the combination write. A prospective exact-case
implementation must attempt both domain restorations independently and report
every failure. The existing option-versus-selection restoration independence is
reused, but does not remove this additional review requirement.

Reuse the existing subordinate modal-output option transaction. The reviewed
GetOutputOptionsForDisplay ABI has 15 values plus return code. Preserve all other
values; change only the modal all-modes flag to False and inclusive modal start/end
to 1/100 (existing reviewed owner's positions 4,5,6). Verify the exact 15-value tuple.
Do not change Results.Setup selections, units, patterns or other output options.

Restoration law: on success, acquisition error, parse error, setter failure or
validation failure, attempt restoration of the original full output-option tuple
and original case/combination selections independently, even if one restoration
fails. Restore options first, selections second, and re-read both. Optional
patterns must equal the original snapshot without a pattern setter. Require
exact final equality of all snapshots and unchanged source/session/units/lock.
Report restoration failure separately and block release of rows as usable
evidence; retain immutable error evidence. Do not hide it behind acquisition
failure, retry another instance, save, rerun analysis, or claim rollback from
disk SHA alone. Process-local locking does not prevent outside operator actions;
require an exclusive operator observation window and explicit before/after checks.

## One bounded table read

Only after the preconditions and separately authorized transaction are satisfied,
request the exact `Joint Displacements` table through
`DatabaseTables.GetTableForDisplayArray("Joint Displacements", ...)`. Freeze the
applicable actual generated ABI before the call. Existing permissive generic
reader signature retries/shape inference are not sufficient for this package;
require one reviewed signature, exact success code, full returned FieldKeys,
version and complete record count. Do not substitute the Absolute table.
Prefer an already-existing group whose native membership proves exactly the 172
endpoint objects, if this result table's GroupName scope is source-qualified.
Do not invent/create a group or change point selections. If no exact existing
group can be qualified, explicitly review whether an all-point transport read of
this single table is the minimal feasible API operation; do not silently enlarge
the proposed scope. Such a scope needs separate authorization, a native model-wide
bound and offline exact endpoint filtering. If the minimal scope or ABI cannot be
established, stop before reading results.

Minimum result columns are Story, UniqueName, OutputCase, CaseType, StepType,
StepNumber, StepLabel and Ux/Uy/Uz. Retain all original returned raw fields/rows
as immutable evidence, including Label and rotations if the API returns them;
requesting a reduced set requires an actual qualified native FieldKeyList ABI.
No extra result tables or modal recapture are part of this plan. Do not clip to
17,200 raw records: the model may contain other points. Bound total raw bytes and
record count using a separately reviewed model-wide denominator; exceeding the
bound is BLOCKED, never truncation labeled complete. Parse the full raw response
and record `NumberRecords × field_count == flattened data length`; reject unknown
or repeated keys, malformed tuples, nonzero codes, partial reads and nonfinite
translation values. Preserve signed values with no abs, spectrum scaling or
normalization guess. No CQC or top-minus-bottom displacement calculation in P2.

## Binding and release checks

After a qualified Story/object/element bridge, use each endpoint's own story and
the exact six-part key described in the R3L physical plan. Case name/type, Mode,
integral 1–100 number and blank StepLabel must agree. Keep unrelated raw identities
but reject unexpected rows within the target subset. Require 172 distinct endpoint
objects ×100 modes=17,200 target rows and 86 columns ×100 modes=8,600 exact paired
identities. Duplicate rows block even when equal. Confirm per-endpoint panel-zone
assignment absence or exact column-connected generated-joint selection and table
binding through the archived native mapping authority. No nearest-coordinate
fallback, object=element assumption, first-row selection or synthetic Elm field.

Capture evidence outside Git with exclusive new receipt/sidecar files, original
raw hashes and before/after protected EDB SHA, source/session identities, units,
case classification, schema/version, selection snapshots, temporary readbacks,
restoration diagnostics and exact physical binding references. Failures retain
their own immutable receipt; never overwrite an original. A validated capture
would establish factual global endpoint rows only. Global common-story Delta,
current B5, joint Delta/R/V project decision and M6-B still need their own gates.

Prohibited throughout: RunAnalysis, StartDesign, Save/SaveAs, SetPresentUnits,
model mutation, analysis-state mutation, combo creation, unreviewed selections,
another ETABS instance and any execution by the worker under this task.
Next action is CSI contract recovery and plan review; no P2 command is proposed.
