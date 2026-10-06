# B-BLOK-COLUMN-A17-TOL-v1

## Explicit reviewed project authority

Source: user/project reviewer approval supplied in this task on 2026-09-27,
followed by: “Treat the supplied B-BLOK-COLUMN-A17-TOL-v1 as explicit reviewed project authority.”

```text
absolute_tolerance_mm = 0.01
model-equivalent = 1.0E-5 m
scope = signed Column-end relative translation equality
        for the current reviewed B-BLOK Column-R1 A17 path
universal default = NO
```

Classification: REVIEWED_PROJECT_AUTHORITY. This explicit approval supersedes
the earlier E1 NO_AUTHORITY finding. Test values are not its source.
This approval establishes equality tolerance only; it does not approve
uncracked stiffness, an analysis state, Eq.7.13 readiness, or a design result.

## Exact project scope and binding

- Accepted E0 commit: `9a9511b13ff93f451c8610217f48fdaaf81b59cc`.
- Protected model: `C:\tmp\B-BLOK_Revised.EDB`.
- Accepted model SHA256: `5AA83947C46AE886DD43E8BD2270DAEAC6117AE60BAD1F8CB9ED9874CD3E2A44`.
- Accepted local reviewed inputs: `C:\tmp\column-r1-reviewed-inputs.py`.
- Accepted input SHA256: `9D7BAE7108C655751C018071E9B17D1D401A21904DAAD140BDBE81566AC9FBBC`.
- Model/input identities are from the accepted live receipt, not newly measured here.

`tools/column_r1_bblok_e1_reviewed_inputs.py` implements the existing
`load_inputs()` contract. It checks the accepted input hash before execution,
preserves the request and all other reviewed fields/dependencies, and binds
`ReviewedStoryTranslationTolerance(0.01, "B-BLOK-COLUMN-A17-TOL-v1")`
through `ReviewedColumnDesignBasis.story_translation_tolerance`.
Unexpected dependencies or conflicting tolerance fail closed.

The existing acceptance harness independently pins the B-BLOK model hash.
This configuration is restricted to that harness and model; it is not a generic
project policy. Other projects retain `None` and the existing missing-authority gate.
No public request DTO or engineering consumer is changed.

## Offline preparation and next live gate

On the supervisor's accepted Windows checkout, this check reads only the
reviewed Python inputs and invokes no ETABS operation:

```powershell
python -c "from tools.column_r1_bblok_e1_reviewed_inputs import load_inputs; r,d=load_inputs(); t=d['column_design_basis'].story_translation_tolerance; print(r.column.component_id, t.absolute_tolerance_mm, t.source_ref)"
```

For a separately authorized future acceptance run, use the existing harness
with `--reviewed-inputs tools/column_r1_bblok_e1_reviewed_inputs.py` and the
persisted E1 SHA/tree. No live run is authorized or performed by this change.
The original input file and protected EDB are not modified.
Offline fixture success is not a new live result for any of the 142 A17 columns.
