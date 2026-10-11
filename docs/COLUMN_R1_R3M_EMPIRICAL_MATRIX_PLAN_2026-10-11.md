# COLUMN-R1 R3M empirical matrix experiment — prepared, not executed

R3D–R3L remain closed. R3M reuses the supervisor-accepted `1044 / LC_DL`
manual comparison. No CSI answer is awaited and no new general source search
is performed. The worker does not attach to ETABS or acquire native results.

## Reused observation and precise limit

Original `joint_global_crosscheck_20261011_140422.json`, Library
`libfile_c36ff6258248819182a035c233636fb5`, whole-file SHA256
`ef4bbadc3fb034f59533f6279c816cba8713ab3649950fce12018a8db4f82a29`,
binds PID 2072, protected FC09, R3K HEAD
`ab16c693c887ca383603ef3c372a098e05272706` and TREE
`a1f54bf3eb600b6929584fcf8483132b1448a51f`. Original bytes remain unchanged.

For Column 210, top endpoint Story `+0.00`, UniqueName `1044`, the actual
native PointElm matrix is identity. The LC_DL row is nonzero, with local
translations `(0.00006551988343712905, 0.000074312662822226,
-0.002343749593030482)` m. Both hypotheses therefore coincide exactly.
This cannot distinguish matrix direction or establish global semantics.
The receipt contains no original GUI comparison readings. Supervisor acceptance
is reused within its stated scope; no GUI values are manufactured.

The original native JointDispl call returned seven selected case rows, including
LC_DL and generated static response-spectrum cases. Its overall blocked status
and missing-modal warnings remain unchanged. R3M uses the successful LC_DL
subfact, and does not relabel the original receipt as a successful modal capture.

## Repo-external artifact and offline validation

`column_r1_r3m_matrix_probe.py` remains outside Git. Persistent identity:
`libfile_a261590cce848191bd9bf4493e01ec00`, version 1, SHA256
`3531a45013ab57dd6993ead7b1fa71117a690b3a0f22c14c296cced9e1cb391d`.
Git contains the explicit offline test suite and source-bound derived receipts,
not the script or copies of original native response arrays.

Run the committed suite explicitly after obtaining this exact external artifact:

```powershell
$env:COLUMN_R1_R3M_EXTERNAL_PROBE_PATH = 'C:\tmp\column_r1_r3m_matrix_probe.py'
python -m pytest -q tests/etabs/r3m_external_probe_regression.py
```

The suite requires the exact SHA and rejects a script placed inside the repository.
Its filename requires explicit invocation because an external operator artifact
is not assumed to exist in standard CI. Missing or altered artifact fails;
there are no conditional skips, live tests, or automatic downloads. Tests exercise
synthetic native declarations and fake STA reads, including complete 172-point
identity/nonidentity scans, source/session/selection drift, invalid native tuples,
duplicate LC_DL rows, ambiguous Elm mappings, ABI ordering, rounding separation,
immutable writes and absence of setters or alternate COM attach paths.

## Bounded native experiment

1. Operator verifies an existing PID and an idle, locked protected model. The
   only attachment uses the existing verified PID gateway with fallback disabled.
   The exact clean supervisor-reported R3M HEAD/TREE is required. No second
   COM owner or STA is introduced.
2. Verify original R3D SHA
   `83ce2ff7c3a6170e931d2869e212adde93b7c08b25bbf44e9f0c2c663f156b03`.
   Reuse R3L's existing offline physical resolver to derive 86 Columns and
   172 distinct physical endpoints. Use each endpoint's actual object story;
   bottom Base and top +0.00 both remain in the denominator. No nearest-point
   fallback, duplicate choice, or invented object=element equality.
3. Read native `PointElm.GetTransformationMatrix` for each R3D-retained actual
   Elm. Qualify generated parameter flags and exact native output ordering before
   invocation. Keep the full raw response and canonical JSON hash. Require ret=0,
   nine finite values, orthogonality defect <=1e-9 and determinant within 1e-9 of
   +1. No normalization or identity replacement. Identity classification uses
   a stated maximum component deviation tolerance of 1e-12.
4. For a nonidentity endpoint, evaluate LC_DL only if Results.Setup getter
   snapshots prove LC_DL is already the **sole selected case**, with no selected
   combos. Otherwise finish the matrix scan but block static acquisition and
   return no eligible GUI comparator. Do not change selection, or suggest a
   selection change under this experiment's authority. The original seven-row
   selection is a known limitation. A selection change would require a separate
   reviewed experiment, outside this task.
5. Bypass the existing `read_joint_displ_from_session` wrapper because it opens a
   selection-changing transaction. Invoke the factual getter directly inside
   the existing `_execute_verified_read` STA boundary. Require the exact native
   13-output generated ABI, ret=0, exactly one LC_DL row, equal array lengths,
   exact Obj and retained Elm identities, accepted static grain Single Value/0,
   and finite translations/rotations. Reject all other cases, modal rows,
   duplicate rows and generated-joint alternatives. Verify identical selection
   snapshots before/after each JointDispl call.
6. Group the raw nine values by threes only to compute the two explicitly
   unqualified hypotheses `T × Ulocal` and `transpose(T) × Ulocal`.
   No ordering/direction interpretation is asserted. Require nonzero LC_DL
   translation and a component difference greater than `10^-d` m plus a stated
   floating-point margin, where d is the operator-verified existing GUI decimal
   precision. This separates two GUI half-quantum uncertainty intervals. Zero,
   identity, symmetric, axis-aligned or indistinguishable cases cannot qualify.
7. Rank distinct eligible endpoints by maximum candidate separation. Emit exact
   Story, UniqueName, Column, endpoint, retained Elm, OutputCase=LC_DL and both
   signed candidate vectors. Operator reads the existing Joint Displacements
   GUI table for that exact triple and records Ux/Uy/Uz, displayed units and
   precision, observed CaseType/StepType/StepNumber, time and original screenshot
   or export outside Git. Stop if the triple is not unique. Native JointDispl
   static grain is **not** silently equated with DatabaseTables table grain.
8. Verify fresh source/session/lock/units observations around every bounded
   point read, selection equality at the end and protected SHA before/after.
   All reads remain on the existing gateway STA, each at most 30 seconds, with
   a 900-second probe budget. On drift or any unsuccessful/malformed call,
   preserve raw evidence and invalidate FOUND/NOT_FOUND. Close only the gateway,
   never the ETABS application. Write a new exclusive read-only JSON and SHA
   sidecar outside Git, with no overwrite of original evidence.

## Operator prerequisites and command contract

The worker has not executed this command. Use the already reviewed Windows
Python/comtypes environment. Place the pinned script at
`C:\tmp\column_r1_r3m_matrix_probe.py`; retain original R3D and manual JSON at
their exact evidence paths. Prepare a clean checkout of the reported R3M branch
at `C:\Users\FCY\PycharmProjects\tbdy_engine_r3k_probe`. Existing PID 2072 must
still be ETABS 23.2.0/API 2.014, with the exact FC09 original loaded and locked,
present/database units 6 and raw force/length/temperature 4/6/2. If PID has
changed, stop for explicit PID re-verification; there is no instance fallback.

No concurrent operator model/analysis/unit/selection action is permitted.
Confirm the existing GUI table uses m and record its current decimal places;
do not adjust units or output selection. The exact PowerShell command artifact
delivered with the supervisor exit pins the final canonical R3M HEAD/TREE,
checks the external script SHA and PID, and passes this CLI contract:

```powershell
python 'C:\tmp\column_r1_r3m_matrix_probe.py' `
  --repo 'C:\Users\FCY\PycharmProjects\tbdy_engine_r3k_probe' `
  --expected-head $SupervisorR3MHead --expected-tree $SupervisorR3MTree `
  --pid 2072 --gui-decimal-places $VerifiedExistingGuiDecimalPlaces `
  --r3d-receipt 'C:\tmp\column-r1-r3d-modal_20261010_073229.json' `
  --manual-receipt 'C:\tmp\joint_global_crosscheck_20261011_140422.json' `
  --receipt $NewOutsideRepositoryReceipt
```

There is no RunAnalysis, StartDesign, Save, SetPresentUnits, Results.Setup setter,
DatabaseTables selection setter, modal recapture or global result-table capture.
This script is prepared for operator review; it does not authorize P2 or release.

## Exit law and next causal edge

Worker state: `NONIDENTITY_POINT_FOUND=NOT_OBSERVED_PENDING_OPERATOR_SCAN`.
Only one of 172 native endpoint matrices has been observed in the reused
original, and that one is identity. `NOT_FOUND` is reserved for a successful,
integrity-verified complete 172-matrix scan with all matrices identity within
the stated tolerance. `FOUND` denotes a native nonidentity matrix, not a GUI
match or engineering PASS. An eligible nonzero LC_DL point additionally requires
the safe current selection, unambiguous Elm binding and sufficient separation.

If the complete operator scan yields NOT_FOUND, close this population experiment
as NOT_FOUND. A separate follow-up can inspect already-existing nonidentity
points outside this population with explicit topology/source scope, or use an
owned scratch model with a deliberately rotated joint under separate mutation
authorization. Neither follow-up is executed or authorized here.

The next exact causal edge is the original operator-produced matrix scan receipt,
then (only for an eligible point) an original GUI comparison able to distinguish
the two hypotheses. Even a successful point comparison does not silently prove
all panel-zone mappings, signed modal/table grain or 172×100 global rows.
Global coordinate contract, global story delta and M6-B remain blocked/open;
current B5 is not provided, joint Δ/R/V remains a project decision, and R2 is
not ready. CSI request remains the existing unsent draft.
