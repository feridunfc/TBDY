# VS6 Legacy Reuse Register

Status: architectural record only. This file is not engineering authority.

The VS6 production implementation may reuse proven domain ideas from older code,
but old defaults, heuristics and approximate calculation paths are not promoted
without a fresh source-bound contract.

## Accepted ideas

- `tbdy_engine/design/columns/rebar_set.py`
  - Keep the domain separation between longitudinal reinforcement and transverse/
    confinement reinforcement as a useful modeling idea.
  - Keep deterministic derived quantities such as total bar area and reinforcement
    ratio when they are computed from an explicit selected/provided layout.
  - Do **not** use this module as the VS6 engineering authority.

- `tbdy_engine/design/rebar/provided_rebar.py`
  - Keep the fail-closed principle: absence of a provided/user reinforcement
    schedule means no provided reinforcement authority exists.
  - Keep the distinction between provided/user reinforcement and engine-selected
    reinforcement.
  - Future strict integration must bind provided reinforcement by exact component
    identity; label-prefix member-type guessing and label-only fallback aliases are
    not accepted for final authority.

- Existing reinforcement-role semantics from earlier project work
  - `TBDY_MIN_REQUIRED_REBAR`
  - `GOVERNING_REQUIRED_REBAR`
  - `ENGINE_SELECTED_REBAR`
  - `USER_PROVIDED_REBAR`
  - `FINAL_DETAILING_REQUIRED`
  These remain useful semantic roles. A role name never upgrades evidence by
  itself; each role must have its own source/derivation provenance.

## Rejected legacy behavior

The following behavior is explicitly not reused by VS6 production logic:

- hard-coded `BAR_LIBRARY` as project reinforcement availability;
- nearest-area bar selection without proving that the selected layout is adequate;
- default clear cover, tie diameter, aggregate size, bar count or tie spacing;
- ETABS-data fallback that invents reinforcement when factual data is absent;
- simplified/empirical PMM interaction as replacement for the source-bound
  strain-compatibility capacity kernel;
- member type inference from labels such as `B...` / `C...` for final authority;
- label-only aliases as final provided-rebar identity.

## Current VS6 promotion path

```text
ETABS factual rebar-size table
    -> reviewed field/unit binding
    -> FACTUAL_PROJECT_REBAR_CATALOG
    -> TBDY-eligible column longitudinal diameters
    -> symmetric feasible layout candidates
    -> source-bound N-M2-M3 section capacity
    -> ENGINE_SELECTED_REBAR
```

ETABS `ToBeDesigned=True` reinforcement remains design intent only. It is not
`USER_PROVIDED_REBAR`, final detailing, or as-built reinforcement.

## Boundary rule

Legacy code may be used as reference material, test inspiration, data-shape
knowledge or domain vocabulary. It must not become regulatory/design authority
unless its assumptions are re-derived from verified sources and expressed in the
current canonical engine/evidence contracts.
