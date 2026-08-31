# CURRENT CI BASELINE GOVERNANCE — R-CI-1

**Mode:** research / CI governance only
**Frozen base:** `6273c19030ab6ecb7ad2637e3bfc74f88b1da086`
**Frozen tree:** `8f6ef822b5ab26d22c859438689e7bb9aea9439a`
**Current main:** reverified at the frozen base immediately before writing.
**Write boundary:** documentation only. No workflow, production, or test expectation changes.

## Executive decision

The repository has three automatically triggered pull-request workflows:

1. **C13.4 Offline Product Acceptance** — currently red because current main contains registered inherited C13.5 debt.
2. **P2.10 Wall Pack A Kernel** — current main is green; absolute-green enforcement is correct.
3. **UR-1E Deterministic Report Package Validation** — focused/deterministic report checks are green, but the global broad gate compares modern code with historical `e98ed36...` and requires absolute zero failures.

Canonical governance rule:

```text
RED != CURRENT_SPRINT_REGRESSION

FAILURE_SIGNATURE debt
→ exact failed node + normalized exception match may classify an observed failure as inherited
→ NEW node/signature or materially changed inherited signature = BLOCKER until classified

WORKFLOW_GOVERNANCE debt
→ classifies stale baseline / wrong global gate semantics only
→ never acts as a failure-signature whitelist

historical frozen SHA
→ valid for immutable historical sprint acceptance
→ not automatically valid as current global regression baseline
```

Stable CI debt IDs are in `docs/audit/CURRENT_CI_DEBT_REGISTRY.yaml`.

### Debt-kind typing

The registry has two distinct debt kinds:

```text
CI-DEBT-001 .. CI-DEBT-006
→ debt_kind: FAILURE_SIGNATURE
→ actual currently observed failing test node/signature debt
→ eligible for exact failure-signature lookup

CI-DEBT-007 .. CI-DEBT-008
→ debt_kind: WORKFLOW_GOVERNANCE
→ stale/incorrect gate-policy semantics
→ NOT runtime/test failure signatures
→ NOT eligible for failure-signature lookup
```

In particular:

```text
CI-DEBT-007 / CI-DEBT-008
!= permission to ignore arbitrary failures in UR-1E / C13.4
```

Their only effect is classification of the workflow gate policy itself. Any actual UR-1E/C13.4 failed node still requires an exact `FAILURE_SIGNATURE` debt match or it remains a blocker until classified.

## 1. Workflow census

Current workflow count: **18**.

| Workflow | Trigger | Base model | Test / package assumptions | Delta / artifacts / hygiene | Governance disposition |
|---|---|---|---|---|---|
| `acq_ctx_1_validation.yml` — ACQ-CTX-1 | sprint branch + manual | `1789c814...` | broad deterministic toolchain; gateway/safety/integration | candidate/base exact failure delta; final hygiene | historical immutable sprint acceptance |
| `b1_beam_column.yml` — B1 Beam Column | sprint branch + manual | none | pytest/pyyaml/jsonschema; focused + offline acceptance | absolute historical gate | historical acceptance; retire after replacement |
| `c13_4_offline_acceptance.yml` — C13.4 | **PR main + push main** | none | installs pytest/pyyaml/jsonschema; does **not** install gateway package | 18-command absolute gate; uploads report | global; currently red; transitional zero-new or close debt |
| `cd_1_coverage_contract_debt.yml` — CD-1 | sprint branch + manual | `9ae83507...` | deterministic broad toolchain | candidate/base, explicit resolved failures, hygiene | valid immutable historical acceptance |
| `col_runtime_policy_input_validation.yml` | sprint branch + manual | `5256f40d...` | broad deterministic toolchain | candidate/base zero-new + no changed inherited | valid immutable historical acceptance |
| `fcr_1a_validation.yml` | sprint branch + manual | dynamic `origin/main` | pytest/pyyaml/jsonschema | candidate/current-main zero-new | **good current-sprint model** |
| `fnd_col_1_validation.yml` | sprint branch + manual | `362374d6...` named `CURRENT_MAIN` | broad deterministic toolchain | zero-new vs historical base | historical only; label is stale for global use |
| `fnd_col_2_validation.yml` | sprint branch + manual | `32f03ccf...` | broad deterministic toolchain | candidate/base zero-new, hygiene | valid immutable historical acceptance |
| `fnd_col_2x_validation.yml` | sprint branch + manual | `54834e0c...` | broad deterministic toolchain | zero-new + no missing inherited, hygiene | valid immutable historical acceptance |
| `p2_10_wall_pack_a.yml` | **PR main + push main** | none | narrow wall/C13 kernel, pytest/pyyaml | absolute green | **ABSOLUTE_GREEN_REQUIRED** |
| `p2_10_wall_pack_b.yml` | Pack B/C sprint branches | none | Pack A/B/C/inventory + C13.4 runner | absolute sprint acceptance | historical branch-only |
| `product_spine_col_1_validation.yml` | sprint branch + manual | `74d5b608...` | broad deterministic toolchain | full candidate/base zero-new, hygiene | valid immutable historical acceptance |
| `ur_1b_validation.yml` | sprint branch + manual | dynamic `origin/main` | report toolchain | candidate/current-main zero-new | **good current-sprint model** |
| `ur_1c_validation.yml` | sprint branch + manual | `02b72bf3...` | report toolchain | product-report candidate/base zero-new | valid immutable historical acceptance |
| `ur_1d_validation.yml` | sprint branch + manual | `95cef474...` | pinned PDF toolchain | determinism + candidate/base zero-new + hygiene | valid immutable historical acceptance |
| `ur_1e_validation.yml` | sprint branch + **PR main** + manual | `e98ed36c...` | pinned report toolchain; gateway package not installed | focused/determinism + candidate/base broad + **absolute zero-failure** gate | **STALE_FOR_GLOBAL_REGRESSION** |
| `ur_2_validation.yml` | sprint branch + manual | `2ae92083...` | pinned report toolchain | focused/product_reports absolute, demo artifact, hygiene | historical acceptance |
| `vs6_p8a_f0_validation.yml` | sprint branch + manual | `fce5509b...` | deterministic toolchain | focused absolute + import-safety + hygiene | historical acceptance |

### Current PR workflows

| Workflow | Exact current evidence | Correct policy |
|---|---|---|
| C13.4 | **FAIL** — 18 commands / 4 failed command families | transitional exact current-base zero-new while registered debt exists; target absolute green after CI-D1/D2 |
| P2.10 Wall Pack A | **GREEN** — 59 passed locally; GitHub run green | **ABSOLUTE_GREEN_REQUIRED** |
| UR-1E | focused/upstream **166 passed**, deterministic render PASS; broad **1 failed / 911 passed**; historical base **616 passed** | replace historical global broad baseline with current-sprint/current-main zero-new; focused deterministic portion stays absolute green |

## 2. Hardcoded baseline census

There are **12** hardcoded SHA baselines in current workflow YAML.

| Workflow | SHA | Date / represented context | Relationship to current main | Classification |
|---|---|---|---|---|
| ACQ-CTX-1 | `1789c814f67c6dd8110714f26af7d30fd95acbd9` | 2026-08-29, post FND-COL-2X main / ACQ-CTX base | historical ancestor | `VALID_IMMUTABLE_HISTORICAL_ACCEPTANCE` |
| COL-RUNTIME | `5256f40d01a036b284e7b0af21577602bd1633d1` | 2026-08-29, merged ACQ-CTX-1 main | historical ancestor | `VALID_IMMUTABLE_HISTORICAL_ACCEPTANCE` |
| FND-COL-1 | `362374d6cd50eace3b6f37709690585ce50582cf` | 2026-08-27, merged FND-COL-2-era main | historical ancestor; no longer current | `STALE_FOR_GLOBAL_REGRESSION` if reused globally |
| FND-COL-2 | `32f03ccf5498061aa429adc71199c4bf66f01f2f` | 2026-08-27 era, sprint base | historical ancestor | `VALID_IMMUTABLE_HISTORICAL_ACCEPTANCE` |
| FND-COL-2X | `54834e0c85b356102e73d10b6341841ab5b71a61` | 2026-08-29, merged P8A-B main | historical ancestor | `VALID_IMMUTABLE_HISTORICAL_ACCEPTANCE` |
| CD-1 | `9ae835073ea9b05b5f8cf066feafdc1e3e9cee25` | 2026-08 era, CD-1 debt-closure base | historical ancestor | `VALID_IMMUTABLE_HISTORICAL_ACCEPTANCE` |
| PRODUCT-SPINE-COL-1 | `74d5b6083afed75e44b832336c31755aee482daa` | 2026-08-29 era | historical ancestor | `VALID_IMMUTABLE_HISTORICAL_ACCEPTANCE` |
| UR-1C | `02b72bf37ffb5cd9f32ee905f1a50eda51f9868b` | 2026-08-26, merged UR-1B main | historical ancestor | `VALID_IMMUTABLE_HISTORICAL_ACCEPTANCE` |
| UR-1D | `95cef47473037118566d5bd408c6b2745c03602e` | 2026-08-26 era | historical ancestor | `VALID_IMMUTABLE_HISTORICAL_ACCEPTANCE` |
| UR-1E | `e98ed36c13e8821f1e1a16a08eaee5b556b1dbce` | CD-1-era merge PR #152 / UR-1E historical base | historical ancestor far behind current main | **`STALE_FOR_GLOBAL_REGRESSION`**, `SHOULD_COMPARE_CURRENT_SPRINT_BASE` |
| UR-2 | `2ae920836649f1bab5c46b5ac38bf05a4353b35b` | 2026-08-27, merged VS6-P8A-F0 main | historical ancestor | `VALID_IMMUTABLE_HISTORICAL_ACCEPTANCE` |
| VS6-P8A-F0 | `fce5509bca335ee92e93db28ca7791a6d530e7d9` | 2026-08-27 era, VS6 sprint base | historical ancestor | `VALID_IMMUTABLE_HISTORICAL_ACCEPTANCE` |

A hardcoded SHA is not wrong merely because it is old. Its correct meaning is immutable historical sprint acceptance. It becomes stale when used as perpetual global regression truth.

## 3. Current-main failure baseline

### C13.4 Offline Product Acceptance

Current exact tree: `8f6ef822b5ab26d22c859438689e7bb9aea9439a`.

```text
Offline product acceptance: FAIL
Commands: 18
Failed: 4
```

#### CI-DEBT-001 — C13.5-P2 — PACKAGING

```text
tests/c13_5_p2/test_live_etabs_geometry_probe_contract.py
::test_cli_refuses_live_probe_without_explicit_live_etabs_flag

expected subprocess exit 2
actual subprocess exit 1
ModuleNotFoundError: No module named 'etabs_gateway'
```

#### CI-DEBT-003 / CI-DEBT-004 — C13.5-P3

Current main has two failures:

```text
test_attach_module_has_no_top_level_com_imports
→ obsolete source-shape requirement; it expects COM import mechanics inside legacy facade

test_success_path_returns_attached_with_fake_sap_model
→ obsolete/raw-capability requirement; compatibility DTO intentionally exposes no SapModel
```

The earlier T1-specific “all historical strategies must execute” and exact COM-message assertions were already aligned before this audit and are not current-main debt.

#### CI-DEBT-005 — C13.5-P5

Five nodes fail because fixtures construct `EtabsAttachResult` with raw application/SapModel:

```text
test_assignment_table_fetch_failure_diagnostic
test_assignment_table_fetched_zero_rows_diagnostic
test_assignment_table_parse_empty_diagnostic
test_property_table_fetch_failure_diagnostic
test_summary_counts_for_live_table_read_results
```

Signature:

```text
ValueError: legacy compatibility result must not expose ETABS application/SapModel capability
```

#### CI-DEBT-006 — C13.5-P6

Three nodes fail with the same forbidden raw-capability fixture pattern:

```text
test_live_fake_database_component_type_source_consumes_spaced_design_type
test_live_fake_database_component_type_source_keeps_compact_design_type_alias
test_component_type_source_table_missing_produces_diagnostic
```

C13.4 is therefore **not green**. Its current red state contains known inherited debt and must not be called PASS.

### UR-1E Deterministic Report Package Validation

Global baseline:

```text
FROZEN_BASE = e98ed36c13e8821f1e1a16a08eaee5b556b1dbce
```

Current exact GitHub evidence:

```text
focused UR-1E/upstream: 166 passed
determinism double-render: PASS
candidate broad: 1 failed, 911 passed
historical e98ed36 broad: 616 passed
final exact zero-failure gate: FAIL
```

Node:

```text
tests/features/test_vs6_p8a_f0_column_design_evidence_authority.py
::test_design_evidence_authority_imports_without_regulatory_package

ModuleNotFoundError: No module named 'etabs_gateway'
```

This is `CI-DEBT-002`, same root cause as `CI-DEBT-001`. The report package itself is not the failing concern; the broad historical-baseline gate is.

### P2.10 Wall Pack A

```text
current main: 59 passed
GitHub PR run: success
```

No current debt registration is required.

## 4. Exact `etabs_gateway` subprocess root cause

`tests/conftest.py` inserts:

```text
<repo-root>
<repo-root>/packages/etabs_gateway/src
```

into **the current pytest interpreter's** `sys.path`. This makes in-process pytest imports work.

Affected tests then start fresh interpreters via `subprocess.run(...)` / `python -c`. A new interpreter does not inherit Python object-level `sys.path` mutations from its parent. At the same time C13.4/UR-1E install pytest/report dependencies but do not install `packages/etabs_gateway` as an editable package or wheel.

Thus a subprocess resolves repo-root `tbdy_engine`, reaches:

```text
tbdy_engine.etabs.safety
→ from etabs_gateway import ...
→ ModuleNotFoundError
```

### Repair options

**Preferred CI-D1:**

```text
python -m pip install -e packages/etabs_gateway
```

or build/install the gateway wheel, then prove fresh-process imports.

**Product packaging option:** declare/install the gateway through canonical repository/package dependency metadata.

**Test-only fallback:** explicitly pass a deterministic `PYTHONPATH` containing `packages/etabs_gateway/src` to subprocess tests. This proves source-layout behavior but does not close product packaging.

Do not rely on `conftest.py` mutation as a subprocess/product packaging solution.

## 5. Architecture-aware test debt

| Historical expectation | Current architecture | Disposition |
|---|---|---|
| legacy facade must contain `importlib.import_module` and literal `comtypes.client`/`win32com.client` | real COM ownership is gateway-only | **obsolete; rewrite around owner/reachability** |
| legacy attach success returns raw `SapModel` | raw capability is forbidden outside controlled gateway/safety/OAPI boundary | **obsolete; rewrite** |
| C13.5-P5/P6 fixtures inject raw SapModel into compatibility DTO | compatibility DTO is diagnostic-only | **obsolete fixture seam; migrate** |
| custom fake COM still falls through to default real COM / executes every historical strategy | T1 requires a closed fake dependency universe | **obsolete; never restore fallback** |
| attempt status, HRESULT, exception type, diagnostic provenance | still useful without raw capability | **meaningful compatibility negative test** |
| explicit live-opt-in refusal | still meaningful | **meaningful** |
| sole COM owner / no upper-layer raw capability | current architecture | **meaningful architecture test** |

## 6. Gate policy audit

### ABSOLUTE_GREEN_REQUIRED

Use when current main is green and the workflow is a current supported invariant.

**Now:** `P2.10 Wall Pack A Kernel`.
**Target state after debt closure:** `C13.4 Offline Product Acceptance`.

### EXACT_FROZEN_SPRINT_BASE_REQUIRED

Correct only for immutable historical sprint replay. Examples: ACQ-CTX-1, CD-1, FND-COL-2/2X, PRODUCT-SPINE-COL-1, UR-1C/1D, historical UR-1E replay, UR-2, VS6-P8A-F0.

### CURRENT_CANDIDATE_VS_CURRENT_SPRINT_BASE / ZERO-NEW-FAILURE

Correct for active migration while current main contains inherited debt. Existing good patterns are `FCR-1A` and `UR-1B`.

Recommended now for:

```text
UR-1E global broad regression
C13.4 global regression only transitionally while registered debt remains
```

### HISTORICAL ACCEPTANCE ONLY / SHOULD NOT RUN ON EVERY PR

The **historical `e98ed36...` broad-comparison form of UR-1E** should not be the perpetual global PR gate. Preserve it as branch/manual historical acceptance, and keep current focused/deterministic report-package tests in a current replacement global workflow.

## 7. Merge-blocker policy

Observed workflow failures and workflow-governance debt are classified on separate paths.

For actual runtime/test failures, a failure is a real current merge blocker when:

- P2.10 becomes red;
- current sprint focused/architecture tests become red;
- C13.4 or UR-1E produces a failed node/normalized exception that does not exactly match a `FAILURE_SIGNATURE` debt currently present on the exact sprint base;
- a registered `FAILURE_SIGNATURE` node materially changes exception signature;
- an architecture guard finds a new forbidden edge.

Only `CI-DEBT-001` through `CI-DEBT-006` are failure-signature debts. Exact unchanged matches may be classified as inherited failure debt rather than attributed to an unrelated candidate.

`CI-DEBT-007` and `CI-DEBT-008` are `WORKFLOW_GOVERNANCE` debts. They describe stale/incorrect gate-policy semantics only. They are not runtime/test failure signatures and cannot whitelist, excuse, or suppress arbitrary failures in UR-1E or C13.4.

All debt still requires an owner repair sprint; debt typing changes classification mechanics, not the obligation to repair it.

## 8. Smallest safe repair sequence

### CI-D1 — etabs_gateway subprocess packaging closure

One concern: make gateway importable in fresh subprocesses through real package installation. Expected closures: `CI-DEBT-001`, `CI-DEBT-002`.

### CI-D2 — C13.5 legacy architecture-contract retirement

One concern: migrate P3/P5/P6 source-shape/raw-SapModel test expectations to current bounded factual architecture. Expected closures: `CI-DEBT-003` through `CI-DEBT-006`.

Do **not** restore raw capability or real-COM fallback.

After CI-D1 + CI-D2, rerun C13.4. If green, keep it globally absolute-green.

### CI-D3 — UR-1E baseline governance modernization

One concern: stop treating `e98ed36...` as perpetual global main truth. Preserve immutable historical UR-1E replay separately; global broad regression compares against exact current sprint/base. Expected closure: `CI-DEBT-007`.

### CI-D4 — C13.4 gate governance (conditional)

Only if C13.4 remains red after CI-D1/CI-D2. Introduce current-base/registry zero-new governance while debt remains. If CI-D1/D2 make C13.4 green, skip CI-D4 and preserve absolute green. Expected closure: `CI-DEBT-008`.

## 9. Required final answers

1. **Which red CI checks are real merge blockers?** New/changed runtime/test signatures are blockers. P2.10 is green now, so any P2.10 failure is a blocker. Current exact C13.4/UR-1E failures are inherited only when the failed node + normalized exception exactly match a `FAILURE_SIGNATURE` debt (`CI-DEBT-001..006`).
2. **Which are inherited?** Failure-signature debt: C13.4 `CI-DEBT-001`, `003`, `004`, `005`, `006`; UR-1E `CI-DEBT-002`. Separately, workflow-governance debt: C13.4 `CI-DEBT-008`; UR-1E `CI-DEBT-007`. Governance debt does not whitelist failures.
3. **Which use stale baselines?** Active problem: UR-1E `e98ed36...` as a global baseline. FND-COL-1 also calls a historical SHA `CURRENT_MAIN`, but its workflow is branch-historical, not a current global PR gate.
4. **Which tests contradict current architecture?** P3 source-shape/raw-SapModel expectations, P5/P6 raw-capability fixtures, and any fake-COM test demanding fallback to real/default COM or all historical strategies.
5. **Why does `etabs_gateway` fail in subprocesses?** Process-local pytest `sys.path` injection plus no actual gateway package installation; fresh subprocesses cannot resolve the src-layout package.
6. **Which workflow should require absolute green?** P2.10 now; C13.4 after CI-D1/D2.
7. **Which workflow should use exact zero-new-failure delta?** UR-1E global broad now; C13.4 transitionally only if debt remains.
8. **Which workflow should no longer run globally?** The historical `e98ed36...` UR-1E broad-baseline form.
9. **Smallest safe sequence?** `CI-D1 → CI-D2 → CI-D3 → CI-D4 only if needed`.
10. **Can supervisors use CI-DEBT IDs?** Yes, but by debt kind: actual failed node/exception lookup uses only `FAILURE_SIGNATURE`; gate-policy audit uses `WORKFLOW_GOVERNANCE` separately.

## 10. Supervisor lookup procedure

### A. Failure-signature classification

```text
observe workflow failure
→ identify failed node + normalized exception
→ lookup only debts where debt_kind = FAILURE_SIGNATURE
→ exact node + normalized exception match?
   YES → inherited failure; verify candidate-vs-current-sprint-base delta
   NO  → blocker until classified
→ route matched debt to expected_owner_sprint
```

A `WORKFLOW_GOVERNANCE` entry must never satisfy this lookup.

### B. Workflow-governance classification

```text
inspect workflow gate policy
→ lookup debts where debt_kind = WORKFLOW_GOVERNANCE
→ classify stale baseline / wrong global gate semantics
→ route gate-policy debt to expected_owner_sprint
```

This second path classifies the workflow policy, not the runtime/test failure population.

Therefore:

```text
CI-DEBT-007 / CI-DEBT-008
!= permission to ignore arbitrary failures in UR-1E / C13.4
```

This replaces repeated manual archaeology without weakening fail-closed regression policy.
