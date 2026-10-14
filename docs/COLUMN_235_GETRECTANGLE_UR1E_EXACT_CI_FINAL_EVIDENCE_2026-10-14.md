# COLUMN 235 — Frozen operator source UR1E exact CI completed

Immutable software source checkpoint: `349e28f5ee7efe84d1242c78494c625f9dfd570c` / `e598efa24b1ede7d1c47a1ed324fb2de07595fe8`. This CI evidence is source-bound to that commit, **not** to a subsequently-created evidence-only branch HEAD.

[GitHub run #38555842097](https://github.com/feridunfc/TBDY/actions/runs/38555842097), original job **115824637565**, completed **SUCCESS**.

| Exact checkout | Passed | Failed (real) | Skipped |
| --- | ---: | ---: | ---: |
| Candidate 349e28f… | 1162 | 2 | 39 |
| Current PR base 1440df1… | 1147 | 2 | 39 |

Focused reporting: **167 PASS**; deterministic rendering, original current-PR hygiene and zero-new gate all **SUCCESS**. Exact original log reported `current_regression_base=1440df1b9300f75b1e604204438f5cada9ebd247`, `historical_base_used_as_current_pr_baseline=false`, `new_failures=[]`.

Both actual failures share the same normalized signatures: `tests/coverage/test_coverage_no_check_execution.py::test_coverage_builder_does_not_import_check_or_legacy_modules|AssertionError` and `tests/features/test_generic_resolver.py::test_generic_resolver_does_not_emit_ok_fail_or_import_forbidden_modules|AssertionError`. Do **not** report the broad profile as all PASS. Historical replay was skipped and does not constitute current-base evidence.

This closes **the final UR1E evidence edge only**. The full validation gate remains OPEN for original immutable 2445-ID ledger comparison, Python3.14.0 runtime, PowerShell ParseFile execution, and user's actual local Windows worktree CLEAN proof. Accepted R1–R6 code remains CLOSED–REUSE, no native ETABS/metadata/getter call, no merge, no ABI7 repin. M6_B remains OPEN. Supervisor offline validation review required before any live decision.
