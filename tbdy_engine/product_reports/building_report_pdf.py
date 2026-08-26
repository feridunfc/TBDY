"""Deterministic PDF export for the canonical UR-1C HTML read-model.

The PDF layer consumes only BuildingReportProjection through the accepted
UR-1C HTML renderer. It owns presentation/export mechanics only and performs
no engineering, regulatory, closure, coverage, governing, or compliance logic.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version as package_version
import json
import math
import platform
import re
from typing import Any

from tbdy_engine.product_reports.building_report_html import (
    HtmlRenderOptions,
    render_building_report_html,
)
from tbdy_engine.product_reports.building_report_projection import BuildingReportProjection
from tbdy_engine.product_reports.report_artifact import ReportArtifact
from tbdy_engine.product_reports.report_presentation_selection import (
    ReportPresentationSelection,
    resolve_presentation_selection,
)


SUPPORTED_WEASYPRINT_VERSION = "69.0"
SUPPORTED_PYDYF_VERSION = "0.12.1"

_TOOLCHAIN_PACKAGES = (
    "weasyprint",
    "pydyf",
    "tinycss2",
    "cssselect2",
    "tinyhtml5",
    "fonttools",
    "Pillow",
    "pyphen",
    "cffi",
)

_EXTERNAL_RESOURCE_RE = re.compile(
    r"(?is)(?:src|href)\s*=\s*[\"']\s*(?:https?:|file:|//)|"
    r"url\(\s*[\"']?\s*(?:https?:|file:|//)"
)
_SAFE_STEM_RE = re.compile(r"[^A-Za-z0-9._-]+")


class PdfRenderIntegrityError(ValueError):
    """Raised when deterministic truthful PDF export cannot be guaranteed."""


class PdfBackendUnavailableError(RuntimeError):
    """Raised when the supported deterministic PDF toolchain is unavailable."""


def _finite_nonnegative(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a finite nonnegative number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be a finite nonnegative number")
    return number


@dataclass(frozen=True, slots=True)
class PdfRenderOptions:
    """Immutable renderer-only options for the supported deterministic profile."""

    page_size: str = "A4"
    orientation: str = "portrait"
    margin_top_mm: float = 13.0
    margin_right_mm: float = 11.0
    margin_bottom_mm: float = 13.0
    margin_left_mm: float = 11.0
    print_background: bool = True
    filename_stem: str | None = None

    def __post_init__(self) -> None:
        if self.page_size != "A4":
            raise PdfRenderIntegrityError("UR-1D deterministic profile supports page_size='A4' only")
        if self.orientation not in {"portrait", "landscape"}:
            raise PdfRenderIntegrityError("orientation must be 'portrait' or 'landscape'")
        for name in (
            "margin_top_mm",
            "margin_right_mm",
            "margin_bottom_mm",
            "margin_left_mm",
        ):
            object.__setattr__(self, name, _finite_nonnegative(getattr(self, name), name))
        if not isinstance(self.print_background, bool):
            raise TypeError("print_background must be bool")
        if not self.print_background:
            raise PdfRenderIntegrityError(
                "UR-1D deterministic profile requires print_background=True"
            )
        if self.filename_stem is not None:
            if (
                not isinstance(self.filename_stem, str)
                or not self.filename_stem.strip()
                or self.filename_stem != self.filename_stem.strip()
            ):
                raise PdfRenderIntegrityError(
                    "filename_stem must be None or a nonblank exact string"
                )

    def as_dict(self) -> dict[str, object]:
        return {
            "page_size": self.page_size,
            "orientation": self.orientation,
            "margin_top_mm": self.margin_top_mm,
            "margin_right_mm": self.margin_right_mm,
            "margin_bottom_mm": self.margin_bottom_mm,
            "margin_left_mm": self.margin_left_mm,
            "print_background": self.print_background,
            "filename_stem": self.filename_stem,
        }


def _canonical_sha256(payload: object) -> str:
    return sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _TOOLCHAIN_PACKAGES:
        try:
            versions[name] = package_version(name)
        except PackageNotFoundError as exc:
            raise PdfBackendUnavailableError(
                f"required PDF toolchain package is not installed: {name}"
            ) from exc
    return versions


def pdf_toolchain_identity() -> str:
    """Return exact package-level identity for the supported render toolchain."""

    versions = _package_versions()
    if versions["weasyprint"] != SUPPORTED_WEASYPRINT_VERSION:
        raise PdfBackendUnavailableError(
            "unsupported WeasyPrint version: "
            f"{versions['weasyprint']} != {SUPPORTED_WEASYPRINT_VERSION}"
        )
    if versions["pydyf"] != SUPPORTED_PYDYF_VERSION:
        raise PdfBackendUnavailableError(
            "unsupported pydyf version: "
            f"{versions['pydyf']} != {SUPPORTED_PYDYF_VERSION}"
        )
    payload = {
        "profile": "tbdy-report-pdf-toolchain.v1",
        "python": platform.python_version(),
        "packages": versions,
    }
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _supported_backend() -> tuple[Any, Any]:
    toolchain = pdf_toolchain_identity()
    del toolchain
    try:
        from weasyprint import CSS, HTML
    except Exception as exc:  # pragma: no cover - import error detail is environment-specific
        raise PdfBackendUnavailableError("WeasyPrint PDF backend could not be imported") from exc
    return HTML, CSS


def _deny_url_fetcher(url: str, *args: object, **kwargs: object) -> object:
    del args, kwargs
    raise PdfRenderIntegrityError(
        "network/filesystem resource fetch is disabled for canonical PDF rendering: "
        + str(url)
    )


def _page_styles(options: PdfRenderOptions) -> str:
    return (
        "@page{size:"
        f"{options.page_size} {options.orientation};"
        f"margin:{options.margin_top_mm:g}mm {options.margin_right_mm:g}mm "
        f"{options.margin_bottom_mm:g}mm {options.margin_left_mm:g}mm;"
        "}"
    )


def _safe_filename_stem(value: str) -> str:
    stem = _SAFE_STEM_RE.sub("_", value).strip("._-")
    if not stem:
        stem = "report"
    return stem[:120]


def _artifact_filename(
    projection: BuildingReportProjection,
    options: PdfRenderOptions,
) -> str:
    raw_stem = options.filename_stem or projection.report_id
    stem = _safe_filename_stem(raw_stem)
    return f"{stem}_{projection.view.value.lower()}.pdf"


def _render_pdf_bytes(
    html_text: str,
    *,
    options: PdfRenderOptions,
    pdf_identifier: bytes,
) -> bytes:
    HTML, CSS = _supported_backend()
    if _EXTERNAL_RESOURCE_RE.search(html_text):
        raise PdfRenderIntegrityError(
            "UR-1C HTML contains an external resource reference; PDF rendering is offline-only"
        )
    document = HTML(
        string=html_text,
        base_url=None,
        url_fetcher=_deny_url_fetcher,
        media_type="print",
    )
    pdf_bytes = document.write_pdf(
        stylesheets=[CSS(string=_page_styles(options), media_type="print")],
        pdf_identifier=pdf_identifier,
        presentational_hints=False,
        custom_metadata=False,
        uncompressed_pdf=False,
        optimize_images=False,
        full_fonts=False,
        hinting=False,
        cache={},
    )
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF-"):
        raise PdfRenderIntegrityError("supported backend did not return a valid PDF byte stream")
    return pdf_bytes


def render_building_report_pdf(
    projection: BuildingReportProjection,
    *,
    html_options: HtmlRenderOptions | None = None,
    selection: ReportPresentationSelection | None = None,
    pdf_options: PdfRenderOptions | None = None,
) -> ReportArtifact:
    """Render one Engineering/Audit projection through UR-1C HTML into PDF."""

    if not isinstance(projection, BuildingReportProjection):
        raise TypeError("projection must be BuildingReportProjection")
    if html_options is None:
        html_options = HtmlRenderOptions(
            include_projection_json=False,
            enable_interactivity=False,
        )
    if not isinstance(html_options, HtmlRenderOptions):
        raise TypeError("html_options must be HtmlRenderOptions or None")
    if pdf_options is None:
        pdf_options = PdfRenderOptions()
    if not isinstance(pdf_options, PdfRenderOptions):
        raise TypeError("pdf_options must be PdfRenderOptions or None")

    resolved_selection = resolve_presentation_selection(projection, selection)
    html_text = render_building_report_html(
        projection,
        options=html_options,
        selection=resolved_selection,
    )
    if not isinstance(html_text, str) or not html_text:
        raise PdfRenderIntegrityError("UR-1C HTML renderer returned empty content")

    projection_sha256 = sha256(projection.to_json().encode("utf-8")).hexdigest()
    selection_sha256 = _canonical_sha256(resolved_selection.as_dict())
    html_sha256 = sha256(html_text.encode("utf-8")).hexdigest()
    options_sha256 = _canonical_sha256(
        {
            "html_options": {
                "include_projection_json": html_options.include_projection_json,
                "enable_interactivity": html_options.enable_interactivity,
            },
            "pdf_options": pdf_options.as_dict(),
        }
    )
    toolchain = pdf_toolchain_identity()
    identifier_seed = _canonical_sha256(
        {
            "projection_sha256": projection_sha256,
            "selection_sha256": selection_sha256,
            "html_sha256": html_sha256,
            "options_sha256": options_sha256,
            "toolchain": toolchain,
        }
    )
    pdf_bytes = _render_pdf_bytes(
        html_text,
        options=pdf_options,
        pdf_identifier=bytes.fromhex(identifier_seed),
    )

    return ReportArtifact(
        logical_role="UNIFIED_ENGINEERING_REVIEW",
        format="PDF",
        media_type="application/pdf",
        filename=_artifact_filename(projection, pdf_options),
        view=projection.view.value,
        content=pdf_bytes,
        source_report_id=projection.report_id,
        source_project_id=projection.project_id,
        source_projection_sha256=projection_sha256,
        presentation_selection_sha256=selection_sha256,
        source_render_sha256=html_sha256,
        options_sha256=options_sha256,
        renderer_toolchain_fingerprint=toolchain,
    )


__all__ = [
    "PdfBackendUnavailableError",
    "PdfRenderIntegrityError",
    "PdfRenderOptions",
    "SUPPORTED_PYDYF_VERSION",
    "SUPPORTED_WEASYPRINT_VERSION",
    "pdf_toolchain_identity",
    "render_building_report_pdf",
]
