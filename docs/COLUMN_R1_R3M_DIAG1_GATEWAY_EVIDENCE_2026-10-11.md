# R3M DIAG-1 — recover gateway failure evidence

DIAG-1 changes only repository-external receipt diagnostics. It does not repair a
guessed ABI failure or change the gateway, native getter signatures, source
authority, selection policy, physical comparisons, matrix interpretation or
engineering calculations. No worker ETABS execution or automatic operator retry
is performed.

## Accepted observation and its limit

The supervisor accepts one failed-closed operator execution at canonical HEAD
`79297185df4b363901aef90ccc74ff32533237fb`, TREE
`b0caca1b85ca7bfe487749c6f76713e88697054e`. Its original filename is
`column-r1-r3m-candidate_20261011_164303_783_1a31a36b45ff4fd399b703a373a10082.json`.
The original is not rewritten or reconstructed. Its complete original bytes and
sidecar were not available in this diagnostic workspace; no whole-receipt or
native-response hash is manufactured. The following facts are explicitly the
supervisor's accepted observation rather than an independent byte verification.

| Observation | Accepted value |
| --- | --- |
| Current candidate SHA before/after | `61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621`, unchanged |
| Identity / selection captured | TRUE / TRUE |
| Native facts / comparisons / matrices | 0 / 0 / 0 |
| Candidate stage | NOT_STARTED |
| Outer failure | ETABSCallError: Worker operation failed. |
| Bounded operation | r3m_candidate_fact_reconciliation |
| First expected getter | FrameObj.GetNameList |
| Exact underlying failure | NOT_PROVEN; requires original diagnostic receipt |

The gateway already exposes `ETABSGatewayError.code`, `operation`, `details` and
`as_dict()`. Its worker wraps an ordinary callback exception in ETABSCallError
with the original exception type/message and explicit chained cause. The prior
external probe retained only the outer type and string. DIAG-1 preserves the
available metadata without modifying that gateway behavior.

## Diagnostic receipt additions

All four existing error exits (primary operation, final identity/selection guards,
gateway close, and final file guards) now use the same exception-record function.
It retains the exact outer type/message, original unprefixed exception message,
gateway code and operation, complete JSON-compatible details, original args,
qualified Python type, and observed HRESULT/OS error attributes. Cause is preferred
over unsuppressed implicit context; relation and suppression are retained. Cycles
and chains beyond eight entries stop with explicit statuses. Non-JSON metadata
uses a labelled diagnostic Python representation without masking the failure or
inventing a native value. This does not promote exception text into source authority.

`diagnostics.first_getter` identifies FrameObj.GetNameList from initialization.
The generated ABI validation result is NOT_OBSERVED, CHECK_ENTERED, FAIL or PASS;
successful generated declarations are retained. Return code is recorded only
when the response has the ABI-qualified tuple length and an exact integer return
slot. Missing, malformed or boolean codes stay NOT_OBSERVED.

| Marker | Meaning |
| --- | --- |
| FACT_CENSUS_ENTERED | The factual callback body actually began; absent if gateway fails before callback entry |
| FIRST_GETTER_ABI_CHECK | The existing exact generated-ABI check began |
| FIRST_GETTER_INVOKED | ABI passed and the existing getter invocation was attempted; it does not claim native success |
| FIRST_GETTER_RETURNED | The invocation returned a Python response; it does not claim a successful return code |
| FIRST_GETTER_VALIDATED | Existing response/return-code checks and exact native name-list validation passed |

Markers are strictly ordered, at most five, and are written into the same evidence
object that the outer wrapper persists. An exception in owner access, ABI check,
invocation, native response validation or name-list validation is recorded and
re-raised. No other fact getter, matrix read or speculative signature is attempted
after that failure. Existing final getter-only integrity checks and session close
remain in place; those are not a census retry. If the first getter succeeds, the
pre-existing bounded read-only workflow continues unchanged.

## Source and execution boundaries

Historical production authority remains exactly FC09:
`FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F`.
The separately observed current candidate's full SHA above does not rebind it.
Original FC09 and pre-DIAG external Python artifacts remain byte-identical.
No historical receipt or test identity is relabelled as a new run.

The new Python artifact is `column_r1_r3m_diag1_probe.py`, kept outside Git.
The new operator command is `column_r1_r3m_diag1_operator.ps1`, also outside Git.
The command is based on the supervisor-reviewed operator file and retains its
actual Windows worktree `C:\Users\FCY\PycharmProjects\tbdy_engine_r3m_probe`,
explicit verified existing PID 2072, original receipt prerequisites and all
source/HEAD/TREE/units/selection guards. Its final Python SHA and exact checkout
pins are provided in the delivery. PowerShell is statically inspected only;
no Windows/ETABS execution is claimed by the worker.

Prepared manual command, requiring separate supervisor authorization to execute:

```powershell
& 'C:\tmp\column_r1_r3m_diag1_operator.ps1' `
  -CandidateSha256 '61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621' `
  -GuiDecimalPlaces <EXISTING_GUI_DECIMAL_PLACES>
```

No decimal precision is inferred. Do not change the existing GUI units or native
output selection. No automatic retry is included. No alternate attachment,
RunAnalysis, StartDesign, Save, SetPresentUnits, Results.Setup setter,
DatabaseTables selection setter, model mutation or P2 acquisition is added.

## Offline validation and next edge

The explicit external-artifact suite tests gateway error details, original cause,
implicit/suppressed context, bounded chains, COM metadata and every outer error
exit. Synthetic first-getter failures cover owner access, ABI rejection, invocation,
unsuccessful native return, malformed tuple/count and duplicate names. Full offline
run tests pass the exception through a synthetic gateway wrapper and inspect the
actual immutable receipt and sidecar; these do not attach to ETABS. Callback-entry
failure does not falsely claim FACT_CENSUS_ENTERED.

Native contract, selection, source/unit safety and engineering helper functions
are compared against the accepted pre-DIAG artifact. Fact comparisons remain
identical. Accepted 1732 test identities are preserved; fresh full diagnostics
must match the exact 79297185 baseline with no expanded violations or guard edits.
The permanent [DIAG-1 offline receipt](COLUMN_R1_R3M_DIAG1_OFFLINE_RECEIPT_2026-10-11.json)
records the final results and source-bound external artifact pin.

`LIVE_RETRY=NOT_EXECUTED`, `ROOT_CAUSE=PENDING_DIAGNOSTIC_RECEIPT`,
`FC09_PRODUCTION_GATE=UNCHANGED`, `GLOBAL_DELTA=NOT_PROVEN`,
`M6_B=OPEN`, `R2_RERUN_READY=NO`.

Next exact causal edge: a separately authorized original DIAG-1 operator receipt
with gateway code/operation/details/chain and the last observed first-getter phase.
Only then determine the underlying failure and review a specific fix. No inferred
COM/ABI correction is part of this checkpoint.
