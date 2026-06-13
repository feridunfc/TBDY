# Engine Boundary Spec v1

## Permissions matrix

| Layer | May read table_registry | May read load_combo_policy | May read design_basis | May read section_state_policy | May read design_combo_matrix | May read ETABS table names | May read combo regex | May read actual combo names | May read Excel sheet names |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Provider | yes | no | no | no | no | yes | no | yes | no |
| Feature Resolver | yes | yes | yes | yes | yes | yes | yes | yes | no |
| Feature Snapshot | no | no | no | no | no | no | no | no | no |
| Check Catalog | no | no | no | no | no | no | no | no | no |
| Check Engine | no | no | no | no | no | no | no | no | no |
| Reports | no | no | no | no | no | no | no | no | output-only manifest |
| UI | no | no | no | no | no | no | no | no | no |

## Forbidden for CheckEngine

CheckEngine must not read table registry, combo policy, design basis, section-state policy, design combo matrix, ETABS table names, combo regex, actual combo names or Excel sheet names. It consumes FeatureSnapshot and CheckCatalog only.
