# Streamlit BeamCore ETABS Diagnostic UI

Run:

```powershell
python -m streamlit run apps/streamlit_beam_design_app.py
```

or:

```powershell
streamlit run apps/streamlit_beam_design_app.py
```

This is a diagnostic UI only.

It can:

- show ETABS online/offline status
- list stories from open ETABS frame objects
- list ETABS response combinations and load cases
- list beams on the selected story
- select all beams or selected beams
- run accepted R7B BeamCore checks using ETABS FrameForce actions
- show JSON/XLSX/diagnostic output paths
- provide placeholder tabs for reports, diagnostics, and settings/about

It does not:

- validate ETABS
- validate the design engine
- prove TBDY compliance
- mark beams as final design
- claim production readiness

The app has no top-level COM import. If ETABS or Streamlit is unavailable, import remains safe and the app reports offline/placeholder status.

## Single-combo UI diagnostic runs

The UI supports one or multiple selected ETABS result combinations.

- If two or more combos are selected, the UI uses the accepted R7B story-batch runner.
- If exactly one combo is selected, the UI uses the accepted R7A single-beam FrameForce path for each selected beam.
- R7B live acceptance rules are not weakened; R7B acceptance still requires at least two combos.
- Single-combo UI output is interpreted only as `SINGLE_COMBO_FRAMEFORCE_CHECKS_EXECUTED`.
- Single-combo output must not claim multi-combo action envelope selection.

## R9B beam selection hardening

The Beam tab classifies ETABS frame objects with a diagnostic heuristic:

- labels starting with `C` or sections containing `Column` are probable columns
- labels starting with `B` or sections starting with `B` are probable beams
- other frame objects are unknown

This heuristic is intentionally limited. Future versions should classify by frame geometry/orientation from ETABS coordinates.

By default, probable columns and unknown frame objects are excluded from BeamCore beam checks. The UI can show them with a warning for diagnostics.

The combination selector supports one or multiple selected combinations. One selected combination means a single-combo diagnostic run and does not claim multi-combo envelope selection. Two or more combinations use the R7B batch route.

Sidebar values are diagnostic assumptions/overrides unless read from ETABS/model metadata.

## R16_REV mode split and ETABS evidence

The existing Streamlit diagnostic UI is upgraded with explicit modes:

- Connection/Input
- Demand
- Design
- Verification
- ETABS Crosscheck
- Reports/Evidence
- Settings/About

Sidebar evidence includes ETABS online/offline status, open model name/path, ETABS present/database units, canonical engine unit warning, provided reinforcement for verification, and output settings.

Claim boundaries:

- UI does not implement engineering formulas
- ETABS disagreement is diagnostic only and does not mutate engine/verification results
- COLUMN_LIKELY frame objects are not silently designed as beams
- ETABS units are evidence; conversion belongs in provider layer

## R19A Structural Workspace Sidebar Semantics

The sidebar is now framed as `TBDY Structural Design Workspace` rather than a beam-only design-input panel.

Sections:

- Workspace
- Analysis Source
- Current Pipeline
- Canonical Units
- Beam Context
- Beam Demand Set
- Verification Inputs
- Output Settings
- Workspace Status
- Run Workspace

Terminology:

- `Beam Context` aligns with `BeamModelContext`
- `Beam Demand Set` aligns with `BeamDemandSet`
- `Verification Inputs` contains element-specific provided reinforcement
- `Design Inputs` is intentionally removed from UI wording

Implementation boundary:

- Sidebar does not call live ETABS connection functions directly.
- ETABS connection status is passed from the main app flow or read from session state.
- Semantic provided keys are `top_provided_As_cm2` / `bottom_provided_As_cm2`.
- Legacy `top_selected_area_cm2` / `bottom_selected_area_cm2` keys are kept only as a compatibility layer for existing BeamCore diagnostic adapters.

Current R19A boundaries:

- Beam is the active element
- Column / Wall / Global Checks are preview / coming soon
- Manual design execution is deferred to R20
- ETABS Live keeps the existing BeamCore diagnostic flow
- Offline Demo keeps the existing R18 result-shaped fixture flow

## R20A Reporting / Evidence Workspace

The `Reports/Evidence` tab is split into two concepts:

- `Evidence`: claim boundaries, workspace evidence, canonical units, and ETABS unit evidence.
- `Generated Reports`: known diagnostic artifact paths and output settings.

R20A boundaries:

- Evidence only.
- No engineering formulas are calculated in UI.
- Reports are diagnostic artifacts.
- Reports are not TBDY compliance proof.
- PDF report is marked as coming soon.

## R21A ETABS Raw Signed Evidence

R21A preserves ETABS raw signed local-axis force evidence next to existing positive design/check magnitudes.

Examples:

- `Vd_left_kN` remains the positive magnitude used by checks.
- `Vd_left_raw_signed_kN` preserves ETABS signed `V2`.
- `Md_left_neg_kNm` remains the positive magnitude used by checks.
- `M3_left_raw_signed_kNm` preserves ETABS signed `M3`.

Evidence rows include:

- `etabs_raw_signed_value`
- `design_demand_magnitude`
- `etabs_local_axis_component`
- `sign_convention`

The sign convention text is: `ETABS raw signed local force is preserved; design/check demand uses positive magnitude.`
