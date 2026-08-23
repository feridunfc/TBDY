# VS-4A Status — RC Structural-System Baseline Policy

## Frozen identity

- Base: `f774726513a81edaadb2a5d897539575538e0cd0`
- Branch: `sprint/vs-4a-rc-system-baseline-policy`
- Scope: cast-in-place RC Table 4.1 A11–A33 baseline/pre-analysis policy only
- VS-4B post-analysis MDEV/Mo calculations: **not started**

## Acceptance obligations

The sprint is not auditable merely because code exists. The final branch must prove all of the following on the exact acceptance head before temporary acceptance artifacts are removed:

- shared RegulatoryQuantity pre-eligibility path; no CheckResult aggregation;
- no duplicate BYS/DTS/A31/A16 engineering calculation in formal CheckResult evaluators;
- `INELIGIBLE -> AnalysisBasisStatus.INVALID`;
- `BLOCKED -> AnalysisBasisStatus.UNRESOLVED`;
- BYS and DTS failures cannot leave a resolved baseline;
- A31 DTS failure is INVALID;
- A16 failed reviewed condition is INVALID;
- A16 `UNREVIEWED` roof connection is UNRESOLVED;
- empty system-declaration review refs rejected;
- empty DTS/BYS review refs rejected;
- exact analysis assumption cannot produce MATCH when eligibility fails;
- pending post-analysis qualification produces UNRESOLVED compatibility;
- eligible resolved exact assumption produces MATCH;
- eligible resolved mismatch produces REANALYSIS_REQUIRED;
- `vs4a_program.py` is the sole composition path;
- current F0.9 claims/reviews/implementation fingerprints validate;
- frozen F0 and full pytest regression matrix remains green.

## Finalization rule

`READY_FOR_SUPERVISOR_AUDIT` may be stated only after a fresh acceptance matrix is captured, the temporary `.github/workflows/vs4a_fingerprint_tmp.yml`, `.vs4a_acceptance_trigger`, and VS-4A temporary result artifacts are deleted, and the exact final branch HEAD is recorded.
