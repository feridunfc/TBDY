# C13.4-P2 Modular Catalog Loader + Master Catalog Validation

## Goal

C13.4-P2 adds a deterministic modular catalog loader before adding any new engineering checks.

The architectural flow is:

```text
catalog fragments
-> catalog loader
-> merged MasterCatalog
-> validation
-> future validated contract artifacts
```

## Added module

`tbdy_engine/catalogs/loader.py` provides:

- `load_single_file_master(catalog_dir)` for existing single-file catalogs.
- `load_single_file_catalog(path)` for single YAML catalog files.
- `load_modular_catalog(root)` for directory-based modular fragments.
- `validate_master_catalog(master)` for merged master validation.
- `summarize_master_catalog(master)` for deterministic reporting.

## Modular fragment structure

Representative fragments were added under:

```text
tbdy_engine/catalogs/modular/checks/beam_geometry.yaml
tbdy_engine/catalogs/modular/checks/column_geometry.yaml
tbdy_engine/catalogs/modular/features/beam_geometry.yaml
tbdy_engine/catalogs/modular/features/column_geometry.yaml
```

The subset covers C13.4-P1 geometry-only contracts:

- `column_geometry_min_dimension`
- `beam_geometry_min_width`
- `beam_geometry_min_depth`
- `beam_depth_width_ratio`

and required geometry features:

- `beam_width_mm`
- `beam_depth_mm`
- `column_width_mm`
- `column_depth_mm`

## Deterministic merge

The loader sorts YAML fragment paths before reading. Merge order never depends on OS glob order.

Fragment rules:

- top-level `checks:` contributes to master `checks`.
- top-level `features:` contributes to master `features`.
- top-level `policies:` contributes to master `policies`.
- duplicate ids are blockers.
- unknown top-level keys are blockers.

## Validation rules

The merged MasterCatalog validation blocks:

- duplicate check ids
- duplicate feature ids
- invalid fragment shape
- missing engineering-sensitive fields
- nested `required_features` lists from YAML alias mistakes
- required feature references missing from merged features
- absence of the C13.4-P1 geometry checks

The loader does not invent engineering-sensitive defaults such as component type, required features, source units, unit conversion, pass rule, or code reference.

## Existing catalog compatibility

Existing single-file `check_catalog.yaml` and `feature_catalog.yaml` remain in place. They are not moved and continue to be loadable with `load_single_file_master()`.

## Explicitly not implemented

- No beam flexure.
- No beam shear.
- No rebar adequacy.
- No capacity design.
- No governing combo selection.
- No force envelope selection.
- No SCWB.
- No PMM.
- No Streamlit.
- No Excel production path.
- No ETABS live fetching.
- No legacy beam/design/runtime execution.

## Acceptance commands

```bash
python -m compileall -q tbdy_engine tools tests
python tbdy_engine/tools/validate_contract_constitution.py
python tools/audit_legacy_boundary.py
pytest -q tests/c13_4_p1
pytest -q tests/c13_4_p2
```

The implementation worker could not run these commands in the connector environment. Run them locally before merge and paste exact outputs into the PR body.

## Known implementation note

C13.4-P2 adds modular MasterCatalog validation through the new loader module and direct tests. The existing constitution validator remains the final single-file contract gate. Full CLI output integration into `validate_contract_constitution.py` should be completed before treating this sprint as fully accepted.
