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
