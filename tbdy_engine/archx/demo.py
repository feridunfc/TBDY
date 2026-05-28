from __future__ import annotations

from .models import Beam, CanonicalSnapshot, Column, DesignBasis, Section, Story


def build_demo_snapshot() -> CanonicalSnapshot:
    return CanonicalSnapshot(
        sections={
            "S_BEAM_OK": Section(section_id="S_BEAM_OK", width_mm=300, depth_mm=500),
            "S_COLUMN_FAIL": Section(section_id="S_COLUMN_FAIL", width_mm=250, depth_mm=1000),
        },
        beams={
            "B101": Beam(element_id="B101", label="B101", story_id="5", section_id="S_BEAM_OK"),
        },
        columns={
            "C101": Column(element_id="C101", label="C101", story_id="5", section_id="S_COLUMN_FAIL"),
        },
        stories={
            "S1": Story(story_id="S1", height_mm=3000, drift_max_mm=75),
        },
        design_basis=DesignBasis(code="TBDY-2018", drift_limit=0.02),
    )
