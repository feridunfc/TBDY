# Column-R1 Q1P native wall Thickness source authority

Policy identifier: `COLUMN_R1_P1A_Q1P_PRESENT_WALL_THICKNESS_COMPATIBILITY_POLICY_V1`.
Version: `PROJECT_REVIEWED_V1_20261007;CSI_ETABSv1_GETWALL_THICKNESS_L`.

The supervisor's Q1P instruction accepts CSI-primary `cPropArea.GetWall`
Thickness semantics: membrane thickness [L], transported in PRESENT / DISPLAY
units. Current applicability is accepted through a narrowly scoped,
project-reviewed compatibility policy for ETABS **23.2.0**, OAPI **2.014**,
`SapModel.PropArea.GetWall`, output **Thickness**, dimension **L**, only.
This is not a claim that CSI supplied a literal ETABS 23.2.0 to ETABSv1.dll
2.14.0.0 mapping. Q1N's E/G policy identifier and authority are not reused.
No other PropArea output or native property getter is qualified by this policy.

The existing session-bound GetWall owner reads fresh active-model/application
identity and PRESENT units before and after one native acquisition, on the
existing verified gateway. The active path comes from those observations;
the cached protected-source path is not substituted for the owned scratch.
Session/PID and gateway remain the existing verified connection anchor.
The getter does not independently establish scratch ownership or source/result
lineage; those remain the responsibility of the existing upstream lifecycle.

Exactly one existing SourceUnitProvenance record binds Thickness to its own
property, raw response, capture, observed active model and verified session.
Raw thickness and the raw tuple are retained without acquisition-time scaling.
Conversion remains in the existing downstream source-unit converter. Units
are decoded only from fresh qualified PRESENT observations; database units,
table metadata, report/project defaults and numerical inference are not sources.
Existing safety/decoder/converter support is not expanded by this policy.
Missing observations, incompatible versions, drift, unsupported source units,
unsuccessful/absent returns and invalid/inapplicable Thickness fail closed.
Layered shell applicability is not broadened.

This policy does not requalify preserved anomalous tuples or prove A3 will
pass. Population closure, G12/material resolution, frame participation, B4B,
B5, sway, k, lambda and candidate selection remain outside its scope.
No live attempt, Q1O retry, latch reuse/deletion or scratch cleanup is authorized.
