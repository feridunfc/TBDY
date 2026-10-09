"""Explicit FC09 same-value project rebind for the canonical load_inputs seam.

Authority: docs/B-BLOK-COLUMN-FC09-REBIND-v1.md (supervisor review 2026-10-09).
The existing loader still verifies and executes the original exact 9D7 bytes.
Unchanged design-basis, exact combo policy, VS5 policy and Route-C W values are
now authorized for FC09 by this authority; their historical provenance remains
intact. Only A17's tolerance authority binding changes. No historical force,
result identity or epoch is injected. No P7/Vc/cage/short-column context is added.
Use only with the canonical FC09-pinned public-root live acceptance harness.
Importing this module reads no external file and performs no ETABS operation.
"""
from dataclasses import replace

from tools.column_r1_bblok_e1_reviewed_inputs import (
    ACCEPTED_INPUTS,
    ACCEPTED_INPUTS_SHA256,
    load_inputs as _load_historical_inputs,
)
from tbdy_engine.design.columns.story_relative_translation import (
    ReviewedStoryTranslationTolerance,
)


AUTHORITY_REF = "B-BLOK-COLUMN-FC09-REBIND-v1"
AUTHORITY_CLASSIFICATION = "REVIEWED_PROJECT_AUTHORITY / CURRENT_SOURCE_REBIND"
CURRENT_SOURCE_SHA256 = "FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F"
AUTHORIZED_DEPENDENCIES = (
    "column_design_basis", "expected_combo_policy", "reviewed_vs5_column_axial_context",
)
REVIEWED_TOLERANCE = ReviewedStoryTranslationTolerance(
    absolute_tolerance_mm=0.01,
    source_ref=AUTHORITY_REF,
)


def load_inputs():
    """Reuse verified historical values under explicit current-source authority."""
    request, dependencies = _load_historical_inputs()
    return request, {
        **dependencies,
        "column_design_basis": replace(
            dependencies["column_design_basis"],
            story_translation_tolerance=REVIEWED_TOLERANCE,
        ),
    }
