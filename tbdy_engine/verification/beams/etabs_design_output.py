"""
ETABSDesignOutput — external ETABS design output container.
Does not read ETABS. Only holds externally-provided values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ETABSDesignOutput:
    """ETABS tasarım çıktısı — manuel veya provider tarafından doldurulur"""
    beam_id: str
    label: str
    source: str = "manual_etabs_design_output"

    top_left_As_required_cm2: float | None = None
    bottom_mid_As_required_cm2: float | None = None
    top_right_As_required_cm2: float | None = None

    shear_spacing_required_mm: float | None = None

    evidence: Mapping[str, object] = field(default_factory=dict)
