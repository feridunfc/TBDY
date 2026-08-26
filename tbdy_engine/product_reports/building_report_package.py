"""Deterministic UR-1E building report delivery/package assembly.

This module composes accepted canonical JSON, UR-1C HTML, UR-1D PDF, UR-1E
XLSX, manifest, and final ZIP artifacts. It owns delivery integrity only and
never introduces engineering/regulatory/coverage/compliance authority.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from typing import Sequence
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from tbdy_engine.product_reports.building_report_html import (
    HtmlRenderOptions,
    render_building_report_html,
)
from tbdy_engine.product_reports.building_report_json import (
    export_building_report_model_json,
)
from tbdy_engine.product_reports.building_report_pdf import (
    PdfRenderOptions,
    render_building_report_pdf,
)
from tbdy_engine.product_reports.building_report_projection import (
    BuildingReportProjection,
    ReportView,
    project_building_report_view,
)
from tbdy_engine.product_reports.building_report_xlsx import (
    XlsxRenderOptions,
    render_building_report_xlsx,
)
from tbdy_engine.product_reports.report_artifact import ReportArtifact
from tbdy_engine.product_reports.report_manifest import (
    DEFAULT_PAYLOAD_FILENAMES,
    MANIFEST_FILENAME,
    build_report_manifest,
)
from tbdy_engine.product_reports.report_presentation_selection import (
    ReportPresentationSelection,
    resolve_presentation_selection,
)
from tbdy_engine.product_reports.unified_building_report import (
    BuildingReportIntegrityError,
    BuildingReportModel,
)


DEFAULT_PACKAGE_FILENAME = "building_report_package.zip"
DEFAULT_PACKAGE_MEMBERS = tuple(
    sorted(DEFAULT_PAYLOAD_FILENAMES + (MANIFEST_FILENAME,))
)
_FIXED_ZIP_DT = (1980, 1, 1, 0, 0, 0)


class ReportPackageIntegrityError(ValueError):
    """Raised when final UR-1E package integrity cannot be proven."""


def _canonical_sha256(payload: object) -> str:
    content = (
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    return sha256(content).hexdigest()


def _copy_artifact_with_filename(
    artifact: ReportArtifact,
    filename: str,
) -> ReportArtifact:
    """Preserve accepted content/provenance while applying frozen delivery filename."""

    return ReportArtifact(
        logical_role=artifact.logical_role,
        format=artifact.format,
        media_type=artifact.media_type,
        filename=filename,
        content=artifact.content,
        view=artifact.view,
        source_report_id=artifact.source_report_id,
        source_project_id=artifact.source_project_id,
        source_model_sha256=artifact.source_model_sha256,
        source_projection_sha256=artifact.source_projection_sha256,
        presentation_selection_sha256=artifact.presentation_selection_sha256,
        source_render_sha256=artifact.source_render_sha256,
        options_sha256=artifact.options_sha256,
        renderer_toolchain_fingerprint=artifact.renderer_toolchain_fingerprint,
    )


def _html_artifact(
    projection: BuildingReportProjection,
    *,
    selection: ReportPresentationSelection | None,
    options: HtmlRenderOptions | None,
) -> ReportArtifact:
    if options is None:
        options = HtmlRenderOptions()
    if not isinstance(options, HtmlRenderOptions):
        raise TypeError("html_options must be HtmlRenderOptions or None")
    resolved = resolve_presentation_selection(projection, selection)
    html_text = render_building_report_html(
        projection,
        options=options,
        selection=resolved,
    )
    content = html_text.encode("utf-8")
    projection_sha256 = sha256(projection.to_json().encode("utf-8")).hexdigest()
    selection_sha256 = _canonical_sha256(resolved.as_dict())
    options_sha256 = _canonical_sha256(
        {
            "include_projection_json": options.include_projection_json,
            "enable_interactivity": options.enable_interactivity,
        }
    )
    return ReportArtifact(
        logical_role="UNIFIED_ENGINEERING_REVIEW",
        format="HTML",
        media_type="text/html; charset=utf-8",
        filename=f"{projection.view.value.lower()}.html",
        content=content,
        view=projection.view.value,
        source_report_id=projection.report_id,
        source_project_id=projection.project_id,
        source_projection_sha256=projection_sha256,
        presentation_selection_sha256=selection_sha256,
        options_sha256=options_sha256,
    )


def build_report_delivery_artifacts(
    model: BuildingReportModel,
    *,
    engineering_selection: ReportPresentationSelection | None = None,
    audit_selection: ReportPresentationSelection | None = None,
    html_options: HtmlRenderOptions | None = None,
    pdf_options: PdfRenderOptions | None = None,
    xlsx_options: XlsxRenderOptions | None = None,
) -> tuple[ReportArtifact, ...]:
    """Build the exact eight frozen default delivery members as ReportArtifacts."""

    if not isinstance(model, BuildingReportModel):
        raise TypeError("model must be BuildingReportModel")
    if model.report_integrity_status != "RECONCILED":
        raise BuildingReportIntegrityError(
            "report_integrity_status must be canonical RECONCILED before package assembly"
        )

    canonical_json = export_building_report_model_json(model)
    engineering = project_building_report_view(model, ReportView.ENGINEERING)
    audit = project_building_report_view(model, ReportView.AUDIT)

    engineering_html = _html_artifact(
        engineering,
        selection=engineering_selection,
        options=html_options,
    )
    audit_html = _html_artifact(
        audit,
        selection=audit_selection,
        options=html_options,
    )

    engineering_pdf_source = render_building_report_pdf(
        engineering,
        selection=engineering_selection,
        pdf_options=pdf_options,
    )
    audit_pdf_source = render_building_report_pdf(
        audit,
        selection=audit_selection,
        pdf_options=pdf_options,
    )
    engineering_pdf = _copy_artifact_with_filename(
        engineering_pdf_source,
        "engineering.pdf",
    )
    audit_pdf = _copy_artifact_with_filename(
        audit_pdf_source,
        "audit.pdf",
    )

    engineering_xlsx_source = render_building_report_xlsx(
        engineering,
        selection=engineering_selection,
        options=xlsx_options,
    )
    audit_xlsx_source = render_building_report_xlsx(
        audit,
        selection=audit_selection,
        options=xlsx_options,
    )
    engineering_xlsx = _copy_artifact_with_filename(
        engineering_xlsx_source,
        "engineering.xlsx",
    )
    audit_xlsx = _copy_artifact_with_filename(
        audit_xlsx_source,
        "audit.xlsx",
    )

    payloads = (
        canonical_json,
        engineering_html,
        audit_html,
        engineering_pdf,
        audit_pdf,
        engineering_xlsx,
        audit_xlsx,
    )
    manifest = build_report_manifest(payloads)
    members = tuple(sorted(payloads + (manifest,), key=lambda item: item.filename))
    if tuple(item.filename for item in members) != DEFAULT_PACKAGE_MEMBERS:
        raise ReportPackageIntegrityError(
            "default report delivery member population is not the frozen eight-file contract"
        )
    return members


def _package_zip_bytes(artifacts: Sequence[ReportArtifact]) -> bytes:
    members = tuple(artifacts)
    if any(not isinstance(item, ReportArtifact) for item in members):
        raise TypeError("artifacts must contain ReportArtifact")
    filenames = tuple(item.filename for item in members)
    if len(filenames) != len(set(filenames)):
        raise ReportPackageIntegrityError("ZIP member filenames must be unique")
    if tuple(sorted(filenames)) != DEFAULT_PACKAGE_MEMBERS:
        raise ReportPackageIntegrityError(
            "final ZIP must contain exactly the frozen eight default members"
        )

    output = BytesIO()
    with ZipFile(
        output,
        "w",
        compression=ZIP_DEFLATED,
        compresslevel=9,
        allowZip64=False,
    ) as archive:
        for artifact in sorted(members, key=lambda item: item.filename):
            filename = artifact.filename
            if filename.startswith("/") or ".." in filename.split("/"):
                raise ReportPackageIntegrityError("unsafe ZIP member path")
            info = ZipInfo(filename, date_time=_FIXED_ZIP_DT)
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            info.flag_bits = 0x800
            archive.writestr(
                info,
                artifact.content,
                compress_type=ZIP_DEFLATED,
                compresslevel=9,
            )
    return output.getvalue()


def build_building_report_package(
    model: BuildingReportModel,
    *,
    engineering_selection: ReportPresentationSelection | None = None,
    audit_selection: ReportPresentationSelection | None = None,
    html_options: HtmlRenderOptions | None = None,
    pdf_options: PdfRenderOptions | None = None,
    xlsx_options: XlsxRenderOptions | None = None,
) -> ReportArtifact:
    """Build the deterministic eight-member final report ZIP as one ReportArtifact."""

    members = build_report_delivery_artifacts(
        model,
        engineering_selection=engineering_selection,
        audit_selection=audit_selection,
        html_options=html_options,
        pdf_options=pdf_options,
        xlsx_options=xlsx_options,
    )
    content = _package_zip_bytes(members)
    canonical_json = next(
        item for item in members if item.filename == "building_report_model.json"
    )
    return ReportArtifact(
        logical_role="BUILDING_REPORT_PACKAGE",
        format="ZIP",
        media_type="application/zip",
        filename=DEFAULT_PACKAGE_FILENAME,
        content=content,
        view=None,
        source_report_id=model.report_id,
        source_project_id=model.project_id,
        source_model_sha256=canonical_json.source_model_sha256,
        renderer_toolchain_fingerprint="python-zipfile:deflate9:ur_1e.v1",
    )


def verify_building_report_package(package_artifact: ReportArtifact) -> None:
    """Reopen and cryptographically verify the final bounded delivery package."""

    if not isinstance(package_artifact, ReportArtifact):
        raise TypeError("package_artifact must be ReportArtifact")
    if package_artifact.filename != DEFAULT_PACKAGE_FILENAME:
        raise ReportPackageIntegrityError("package filename is not canonical")
    if package_artifact.format != "ZIP":
        raise ReportPackageIntegrityError("package artifact format must be ZIP")

    with ZipFile(BytesIO(package_artifact.content), "r") as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if names != list(DEFAULT_PACKAGE_MEMBERS):
            raise ReportPackageIntegrityError(
                "ZIP member ordering/population is not the frozen deterministic contract"
            )
        if len(names) != len(set(names)):
            raise ReportPackageIntegrityError("ZIP contains duplicate member names")
        for info in infos:
            if info.filename.startswith("/") or ".." in info.filename.split("/"):
                raise ReportPackageIntegrityError("ZIP contains unsafe member path")
            if info.date_time != _FIXED_ZIP_DT:
                raise ReportPackageIntegrityError("ZIP member timestamp is not canonical")
            if info.compress_type != ZIP_DEFLATED:
                raise ReportPackageIntegrityError("ZIP compression method is not canonical")
            if info.create_system != 3:
                raise ReportPackageIntegrityError("ZIP create_system is not canonical")
            if info.external_attr != (0o100644 & 0xFFFF) << 16:
                raise ReportPackageIntegrityError("ZIP external attributes are not canonical")

        content = {name: archive.read(name) for name in names}

    try:
        manifest = json.loads(content[MANIFEST_FILENAME].decode("utf-8"))
    except Exception as exc:
        raise ReportPackageIntegrityError("manifest.json is not valid JSON") from exc
    payloads = manifest.get("payloads")
    if not isinstance(payloads, list) or len(payloads) != 7:
        raise ReportPackageIntegrityError(
            "manifest must cryptographically account for seven non-manifest payloads"
        )
    manifest_names = [item.get("filename") for item in payloads if isinstance(item, dict)]
    if manifest_names != list(DEFAULT_PAYLOAD_FILENAMES):
        raise ReportPackageIntegrityError("manifest payload ordering/population is invalid")
    for entry in payloads:
        if not isinstance(entry, dict):
            raise ReportPackageIntegrityError("manifest payload entry is invalid")
        filename = entry.get("filename")
        if not isinstance(filename, str) or filename not in content:
            raise ReportPackageIntegrityError("manifest references unknown payload")
        payload = content[filename]
        if entry.get("byte_length") != len(payload):
            raise ReportPackageIntegrityError("manifest byte_length mismatch")
        if entry.get("sha256") != sha256(payload).hexdigest():
            raise ReportPackageIntegrityError("manifest SHA-256 mismatch")

    try:
        json.loads(content["building_report_model.json"].decode("utf-8"))
    except Exception as exc:
        raise ReportPackageIntegrityError(
            "building_report_model.json is not valid JSON"
        ) from exc
    for filename in ("engineering.html", "audit.html"):
        html = content[filename].decode("utf-8")
        if not html.startswith("<!doctype html>") or "<html" not in html or "</html>" not in html:
            raise ReportPackageIntegrityError(f"{filename} is not standalone HTML")
    for filename in ("engineering.pdf", "audit.pdf"):
        if not content[filename].startswith(b"%PDF-"):
            raise ReportPackageIntegrityError(f"{filename} is not a PDF byte stream")
    for filename in ("engineering.xlsx", "audit.xlsx"):
        try:
            with ZipFile(BytesIO(content[filename]), "r") as xlsx:
                if "[Content_Types].xml" not in xlsx.namelist():
                    raise ReportPackageIntegrityError(f"{filename} is not OOXML")
        except ReportPackageIntegrityError:
            raise
        except Exception as exc:
            raise ReportPackageIntegrityError(f"{filename} is not a readable XLSX ZIP") from exc

    if sha256(package_artifact.content).hexdigest() != package_artifact.sha256:
        raise ReportPackageIntegrityError("package ReportArtifact SHA-256 is inconsistent")


__all__ = [
    "DEFAULT_PACKAGE_FILENAME",
    "DEFAULT_PACKAGE_MEMBERS",
    "ReportPackageIntegrityError",
    "build_building_report_package",
    "build_report_delivery_artifacts",
    "verify_building_report_package",
]
