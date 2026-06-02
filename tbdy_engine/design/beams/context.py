"""
BeamModelContext — Canonical beam design input.
Sadece geometri + malzeme + metadata.
Reinforcement ve demand bilgisi içermez.
Birim standardı: mm, kN, kNm, MPa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class BeamGeometryInput:
    """Kiriş geometrisi — mm cinsinden"""
    bw_mm: float
    h_mm: float
    d_mm: float
    cover_mm: float
    Ln_mm: float


@dataclass(frozen=True)
class BeamMaterialInput:
    """Beton ve donatı malzeme — MPa cinsinden"""
    fck_mpa: float
    fcd_mpa: float
    fctd_mpa: float
    fyk_mpa: float
    fyd_mpa: float
    fywd_mpa: float


@dataclass(frozen=True)
class BeamMetadata:
    """Kaynak, kimlik ve izlenebilirlik bilgileri"""
    label: str = ""
    story: str = ""
    section_name: str = ""
    source: str = ""
    evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BeamModelContext:
    """
    Kiriş tasarımı için canonical input.
    Birim standardı: mm, kN, kNm, MPa.

    Design Engine sadece bu context + BeamDemandSet tüketir.
    ETABS, provided reinforcement, combo/station bilgisi içermez.
    """
    beam_id: str
    geometry: BeamGeometryInput
    material: BeamMaterialInput
    metadata: BeamMetadata = field(default_factory=BeamMetadata)

    @property
    def label(self) -> str:
        return self.metadata.label

    @property
    def story(self) -> str:
        return self.metadata.story

    @property
    def section_name(self) -> str:
        return self.metadata.section_name


def validate_beam_model_context(ctx: BeamModelContext) -> tuple[str, ...]:
    """BeamModelContext alanlarını doğrula, eksik alanları döndür."""
    invalid: list[str] = []

    if not ctx.beam_id:
        invalid.append("beam_id")
    if not ctx.metadata.label:
        invalid.append("metadata.label")

    for name in ("bw_mm", "h_mm", "d_mm", "cover_mm", "Ln_mm"):
        if getattr(ctx.geometry, name, 0.0) <= 0.0:
            invalid.append(f"geometry.{name}")

    for name in ("fck_mpa", "fcd_mpa", "fctd_mpa", "fyk_mpa", "fyd_mpa", "fywd_mpa"):
        if getattr(ctx.material, name, 0.0) <= 0.0:
            invalid.append(f"material.{name}")

    return tuple(invalid)


def is_valid_beam_model_context(ctx: BeamModelContext) -> bool:
    return len(validate_beam_model_context(ctx)) == 0

def _read_context_value(data: object, name: str, default: object = None) -> object:
    if isinstance(data, dict):
        return data.get(name, default)
    return getattr(data, name, default)


def build_beam_model_context(data: object | None = None, **overrides: object) -> BeamModelContext:
    """Backward-compatible context builder for legacy BeamCore callers.

    R9C+ preferred usage is constructing BeamModelContext explicitly from
    BeamGeometryInput, BeamMaterialInput, and BeamMetadata.

    This compatibility layer accepts either:
    - a mapping/object with legacy flat fields
    - keyword overrides
    """
    source_data = data or {}

    def value(name: str, default: object = None) -> object:
        return overrides.get(name, _read_context_value(source_data, name, default))

    beam_id = str(value("beam_id", value("label", "")) or "")
    label = str(value("label", beam_id) or beam_id)
    story = str(value("story", "") or "")
    section_name = str(value("section_name", value("section", "")) or "")
    source = str(value("source", "legacy_builder") or "legacy_builder")

    return BeamModelContext(
        beam_id=beam_id,
        geometry=BeamGeometryInput(
            bw_mm=float(value("bw_mm", 0.0) or 0.0),
            h_mm=float(value("h_mm", 0.0) or 0.0),
            d_mm=float(value("d_mm", 0.0) or 0.0),
            cover_mm=float(value("cover_mm", 0.0) or 0.0),
            Ln_mm=float(value("Ln_mm", value("ln_mm", 0.0)) or 0.0),
        ),
        material=BeamMaterialInput(
            fck_mpa=float(value("fck_mpa", 0.0) or 0.0),
            fcd_mpa=float(value("fcd_mpa", 0.0) or 0.0),
            fctd_mpa=float(value("fctd_mpa", 0.0) or 0.0),
            fyk_mpa=float(value("fyk_mpa", 0.0) or 0.0),
            fyd_mpa=float(value("fyd_mpa", 0.0) or 0.0),
            fywd_mpa=float(value("fywd_mpa", 0.0) or 0.0),
        ),
        metadata=BeamMetadata(
            label=label,
            story=story,
            section_name=section_name,
            source=source,
        ),
    )