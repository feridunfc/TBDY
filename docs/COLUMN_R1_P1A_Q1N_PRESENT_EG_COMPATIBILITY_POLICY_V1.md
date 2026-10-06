# Column-R1 Q1N native E/G source authority

Policy identifier: `COLUMN_R1_P1A_Q1N_PRESENT_EG_COMPATIBILITY_POLICY_V1`.
Version: `PROJECT_REVIEWED_V1_20261006;CSI_ETABSv1_PRESENT_F_L2`.

The supervisor's Q1N instruction explicitly accepts the CSI-primary E/G
stress dimension F/L² and present/display source-unit rule for this existing
native acquisition path, through a reviewed project version-compatibility
policy. This is project-reviewed applicability, not a claim that CSI supplied
a literal ETABS 23.2.0 / OAPI 2.014 version mapping. Q1L/Q1M's historical
non-proof receipts remain unchanged.

Primary sources: CSI API ETABS v1.pdf, GetMPIsotropic page 3936 and API unit
rule page 4203; preserved CSI help extraction `1_extracted.txt`,
GetMPIsotropic and InitializeNewModel topics under ETABSv1.dll 2.14.0.0.
The policy's current installed scope is ETABS 23.2.0 / implemented OAPI 2.014.

The getter uses fresh active-model/session/present-unit observations before
and after exactly one native GetMPIsotropic call. E and G receive separate
existing SourceUnitProvenance records tied to that material, raw response,
capture, model and session. Source units come exclusively from verified
present force/length identities. Owned-scratch facts additionally bind the
factory-issued existing trusted acquisition and ownership context, retaining
the observed scratch identity in the evidence. Raw E/G are never rescaled.
Unknown observations, identity/unit drift and nonzero getter returns do not
issue qualified E/G authority. Canonical conversion remains downstream.

This policy does not qualify preserved anomalous historical tuples, table
E1/Fc, other native property getters, analysis epochs, sway, k, lambda or any
Column candidate. It authorizes no live attempt. Existing Q1K/Q1J latches and
scratch remain preserved; the Q1N patch must be merged before a separately
authorized live attempt.
