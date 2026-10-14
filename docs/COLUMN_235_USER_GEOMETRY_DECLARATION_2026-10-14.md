# Column 235 — User-supplied geometry, unreviewed import packet

The user supplied **80 × 80 cm** and **local-2 parallel to global X**. This does not assert a local-2 positive sign or local-3 positive global direction.

Download the full `docs/COLUMN_235_USER_GEOMETRY_DRAFT_2026-10-14.json` into the existing product's **235-product / Import packet** workflow. It contains canonical `width_mm=800.0`, `depth_mm=800.0`, `axis_basis=RECTANGULAR_LOCAL2_LOCAL3`, all other numeric inputs `null`, all accepted existing immutable authority fields, `result_epoch=null`, and **`reviews={}`**. This does not create or sign a project review; the user must complete the existing geometry review UI with their reviewer, reference, timezone and origin `USER_DECLARATION` (or supply actual project document evidence before selecting `PROJECT_DOCUMENT`).

Direction **local 2 ∥ Global X** is recorded in the separate sidecar `docs/COLUMN_235_USER_GEOMETRY_DECLARATION_2026-10-14.json`; this exact orientation does not fit inside the existing sealed packet schema and must not be appended as an unsupported packet field.

The existing canonical TS500 owner defines `e_min = 15 mm + 0.03 h`. With both declared dimensions 800 mm, the arithmetic is `e_min,M2=e_min,M3=39 mm=3.9 cm`. This is **UNREVIEWED NUMERICAL PREVIEW**, not a current 235 typed product result. The owner will be invoked by the existing workspace only after a valid geometry review; no `N_d×e_min` moment or qualified design force is calculated without current B5/B6 states.

Accepted coordinates remain original Global/m; neither end roles nor ln/k follow from them. M6_B OPEN, full 235 design NOT_GRANTED, no native getter or metadata calls, ABI7 R1–R6 closed-reuse, no merge or operator repin.
