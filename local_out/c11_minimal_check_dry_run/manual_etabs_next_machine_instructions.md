# Manual ETABS next-machine instructions for C11

C11 itself does not run ETABS. It consumes C10 JSON artifacts and executes only the three controlled RUNNABLE readiness rows.

Suggested later sequence on the ETABS machine:

1. Run C8 feature resolver smoke in manual live mode.
2. Build C9 coverage matrix from that live C8 output.
3. Build C10 readiness slice from live C8/C9 outputs plus explicit design_context.json.
4. Only if the same three rows are RUNNABLE, run C11 dry-run against those artifacts.
5. Do not run rebar, flexure, shear, force-demand, full beam checks, or live ETABS-backed checks unless a later sprint explicitly unlocks them.

Boundary: C11 does not mutate the ETABS model, does not run a design, and does not import legacy runner/runtime/archx or old beam modules.
