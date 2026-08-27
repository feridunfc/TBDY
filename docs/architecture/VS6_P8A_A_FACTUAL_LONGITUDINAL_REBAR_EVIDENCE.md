# VS6-P8A-A — Factual Longitudinal Column Rebar Evidence Boundary

Status: bounded implementation slice. Building-level/full TBDY compliance remains `NOT_EVALUATED`.

## Scope

P8A-A ends at factual `ETABS_REQUIRED_REBAR` evidence:

`existing ETABS concrete-column design results -> exact factual result population -> exact F0 identity/combo/model/epoch binding -> row-wise ETABS_REQUIRED_REBAR`

It does **not** authorize `ENGINE_SELECTED_REBAR`.

The accepted factual acquisition path is read-only and uses `DesignConcrete.GetSummaryResultsColumn` only for the strict canonical column topology. It reuses the accepted `GetDesignSection` population, exact F0 concrete-design combo reconciliation, canonical Story + ColumnLabel + UniqueName identity, model fingerprint, `EvidenceEpoch`, and explicit `GetPresentUnits_2` unit provenance.

No `StartDesign`, analysis, model mutation, property/rebar mutation, model save, unit guessing, name/regex rebinding, first/last/max reduction, PMM absolute envelope, zero fill, or `(Sp)` normalization is permitted.

## Row eligibility

Every `MyOption=2` design row remains accounted for.

A row is promoted to `ETABS_REQUIRED_REBAR` only when:

- the global factual result population is complete;
- model fingerprint and EvidenceEpoch match the accepted F0 reconciliation;
- F0 combo/definition/drift/analysis-basis reconciliation is closed;
- exact component/section binding is eligible;
- `ErrorSummary` is empty;
- `WarningSummary` is empty;
- `PMMCombo` resolves exactly once to an accepted F0 matched combo identity.

Rows that fail one of the row-local gates are retained as explicit blocked factual rows with exact source row id, PMMCombo, PMMArea, ErrorSummary, WarningSummary and deterministic blocker reason. In particular, non-empty `WarningSummary` is fail-closed until a reviewed warning eligibility policy exists.

`(Sp)` is never stripped or normalized. If an `(Sp)` PMMCombo is not an exact accepted F0 combo identity, the row is reported as `BLOCKED_UNBINDABLE_PMM_COMBO`.

## Population accounting

The promotion result carries:

- canonical expected component count;
- exact source result-row count;
- exact source design-row count;
- promoted `ETABS_REQUIRED_REBAR` count;
- blocked design-row count;
- explicit blocked rows/reasons.

Invariant:

`source_design_row_count == promoted_requirement_count + blocked_requirement_count`

No design row may disappear from the accounting.

## Quarantined P8A shortcut

The P8A prototype path that joined an arbitrary caller-supplied TBDY minimum scalar to factual ETABS requirements and could feed a caller-manufactured resolved demand basis to selection is removed from P8A-A. The canonical pre-existing column design modules are not declared source-bound by this slice and are not extended to emit new P8A production authority.

## Foundation debt before P8A-B

The following are explicitly outside P8A-A and require a separate source-bound foundation cutover before design-informed `ENGINE_SELECTED_REBAR` can be authorized:

- source-bound longitudinal minimum reinforcement;
- source-bound layout eligibility requirements;
- section-capacity authority;
- minimum eccentricity authority;
- slenderness authority;
- sway/stability authority;
- retirement/quarantine of legacy PMM / `ColumnDesignModuleV2` authority.

P8A-A must not silently solve or bypass these items.

## Live acceptance contract

Local ETABS acceptance is read-only and must report:

- canonical target column count;
- exact design-result captured count and zero missing canonical components;
- unique PMMCombo values;
- exact base-combo values and count;
- `(Sp)` values and count;
- ErrorSummary population;
- WarningSummary population;
- accepted `ETABS_REQUIRED_REBAR` count;
- blocked rows/count/reasons;
- exact model fingerprint;
- exact EvidenceEpoch;
- units before/after, proving unchanged units;
- proof that no `StartDesign`, analysis, save or model mutation was invoked.

No live `ENGINE_SELECTED_REBAR` claim is permitted in this slice.
