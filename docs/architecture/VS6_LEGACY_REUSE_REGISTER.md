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

- Historical `forces.py` force-envelope work supplied during VS6 review
  - Keep the useful domain idea that force processing should be case-wise and
    end-aware rather than a single member-wide scalar envelope.
  - Keep the notion of a reusable frame-end force map for later beam/column shear
    and capacity workflows, but rebuild it on canonical `ColumnDemandState` /
    factual evidence contracts rather than pandas-only dictionaries.
  - Keep i/j end identity as first-class provenance in reports and governing
    selections.
  - Do **not** reuse absolute-value component envelopes as a concurrent PMM design
    state. `abs().max()` independently destroys sign/correlation information that
    VS6 now preserves through exact static vectors and response-spectrum sign
    permutations.
  - Do **not** reuse the historical 1% station-tolerance end detector as regulatory
    member-end authority. The current production path requires exact ETABS end
    normalization/provenance.
  - Do **not** reuse silent missing-force-column -> `0.0` fallbacks for design
    authority; missing required evidence must block.

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
- label-only aliases as final provided-rebar identity;
- independent absolute-value `P/M2/M3` envelopes as biaxial concurrent design
  vectors;
- heuristic station-end classification where exact ETABS end identity is
  available;
- zero-filling absent required force components in an authority-producing path.

## Current VS6 promotion path

```text
ETABS factual rebar-size table
    -> live-proven Name/Diameter schema + reviewed database length unit
    -> FACTUAL_PROJECT_REBAR_CATALOG
    -> TBDY-eligible column longitudinal diameters
    -> ETABS section rebar intent used only as layout seed (cover/tie identity)
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
