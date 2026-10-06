"""B-BLOK-COLUMN-A17-TOL-v1 binding for the existing acceptance load_inputs seam.

Project approval: docs/B-BLOK-COLUMN-A17-TOL-v1.md. This is not a default.
The accepted local inputs remain authoritative for every other dependency.
Use only with run_column_r1_public_acceptance.py's pinned B-BLOK model.
Importing this module does not read the reviewed inputs or access ETABS.
"""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sys
from types import ModuleType

from tbdy_engine.application.column_design_basis import ReviewedColumnDesignBasis
from tbdy_engine.design.columns.story_relative_translation import (
    ReviewedStoryTranslationTolerance,
)


ACCEPTED_INPUTS = Path(r"C:\tmp\column-r1-reviewed-inputs.py")
ACCEPTED_INPUTS_SHA256 = "9D7BAE7108C655751C018071E9B17D1D401A21904DAAD140BDBE81566AC9FBBC"
REVIEWED_TOLERANCE = ReviewedStoryTranslationTolerance(
    absolute_tolerance_mm=0.01,
    source_ref="B-BLOK-COLUMN-A17-TOL-v1",
)


def load_inputs():
    """Preserve the accepted inputs and bind only the explicitly approved field."""
    source = ACCEPTED_INPUTS.read_bytes()
    if sha256(source).hexdigest().upper() != ACCEPTED_INPUTS_SHA256:
        raise ValueError("B-BLOK accepted reviewed-input SHA256 mismatch")

    # Execute the verified bytes, avoiding a second read of a potentially changed file.
    module = ModuleType("_column_r1_bblok_accepted_inputs")
    module.__file__ = str(ACCEPTED_INPUTS)
    sys.modules[module.__name__] = module
    exec(compile(source, str(ACCEPTED_INPUTS), "exec"), module.__dict__)
    request, dependencies = module.load_inputs()
    if set(dependencies) != {
        "column_design_basis", "expected_combo_policy", "reviewed_vs5_column_axial_context",
    }:
        raise ValueError("B-BLOK accepted reviewed-input dependency scope mismatch")
    basis = dependencies["column_design_basis"]
    if not isinstance(basis, ReviewedColumnDesignBasis):
        raise TypeError("B-BLOK requires the existing ReviewedColumnDesignBasis")
    if basis.story_translation_tolerance not in (None, REVIEWED_TOLERANCE):
        raise ValueError("B-BLOK reviewed story-translation tolerance conflicts with v1")
    return request, {
        **dependencies,
        "column_design_basis": replace(basis, story_translation_tolerance=REVIEWED_TOLERANCE),
    }
