from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
from pathlib import Path
import sys

import pytest
from pypdf import PdfReader
import pypdfium2 as pdfium

import tbdy_engine.product_reports.building_report_pdf as pdf_module
from tbdy_engine.product_reports.building_report_html import (
    HtmlRenderIntegrityError,
    HtmlRenderOptions,
)
from tbdy_engine.product_reports.building_report_pdf import (
    PdfRenderIntegrityError,
    PdfRenderOptions,
    SUPPORTED_PYDYF_VERSION,
    SUPPORTED_WEASYPRINT_VERSION,
    pdf_toolchain_identity,
    render_building_report_pdf,
)
from tbdy_engine.product_reports.building_report_projection import ReportView
from tbdy_engine.product_reports.report_artifact import ReportArtifact
from tbdy_engine.product_reports.report_presentation_selection import (
    ReportPresentationSelection,
)
from tbdy_engine.regulatory.contracts import ClosureExecutionStatus
from tbdy_engine.regulatory.kernel import AnalysisBasisStatus


_HELPER_MODULE_NAME = "_ur_1c_html_test_helpers_for_pdf"
_HELPER_PATH = Path(__file__).with_name("test_building_report_html.py")
_HELPER_SPEC = spec_from_file_location(_HELPER_MODULE_NAME, _HELPER_PATH)
if _HELPER_SPEC is None or _HELPER_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("could not load UR-1C HTML test helpers")
_HTML_HELPERS = module_from_spec(_HELPER_SPEC)
sys.modules[_HELPER_MODULE_NAME] = _HTML_HELPERS
_HELPER_SPEC.loader.exec_module(_HTML_HELPERS)
_model = _HTML_HELPERS._model
_pna_model = _HTML_HELPERS._pna_model
_projection = _HTML_HELPERS._projection
_resultless = _HTML_HELPERS._resultless


def _reader(artifact: ReportArtifact) -> PdfReader:
    return PdfReader(BytesIO(artifact.content))


def _text(artifact: ReportArtifact) -> str:
    return "\n".join(page.extract_text() or "" for page in _reader(artifact).pages)


def _engineering(model=None) -> ReportArtifact:
    return render_building_report_pdf(
        _projection(model or _model(), ReportView.ENGINEERING)
    )


def _audit(model=None) -> ReportArtifact:
    return render_building_report_pdf(
        _projection(model or _model(), ReportView.AUDIT)
    )


def test_engineering_projection_creates_valid_pdf_artifact() -> None:
    artifact = _engineering()
    reader = _reader(artifact)
    text = _text(artifact)

    assert artifact.format == "PDF"
    assert artifact.media_type == "application/pdf"
    assert artifact.view == "ENGINEERING"
    assert artifact.content.startswith(b"%PDF-")
    assert len(reader.pages) > 0
    assert "Unified Engineering Review" in text
    assert "ENGINEERING" in text
    assert "REPORT:1" in text


def test_audit_projection_creates_valid_pdf_artifact_and_trace() -> None:
    artifact = _audit()
    reader = _reader(artifact)
    text = _text(artifact)

    assert artifact.view == "AUDIT"
    assert artifact.content.startswith(b"%PDF-")
    assert len(reader.pages) > 0
    assert "AUDIT" in text
    assert "SourceManifest" in text
    assert "sha256:toy" in text
    assert "TOY §1" in text


@pytest.mark.parametrize("status", ["PASS", "FAIL"])
def test_executed_status_survives_pdf_exactly(status: str) -> None:
    artifact = _engineering(_model((("A", status),)))
    assert status in _text(artifact)


@pytest.mark.parametrize(
    ("closure", "status"),
    [
        (ClosureExecutionStatus.BLOCKED, "BLOCKED"),
        (ClosureExecutionStatus.NO_DATA, "NO_DATA"),
    ],
)
def test_resultless_status_survives_pdf_exactly(closure, status: str) -> None:
    artifact = _engineering(_resultless(closure, status))
    text = _text(artifact)
    assert status in text
    assert f"{status} stays" not in text


def test_reanalysis_required_remains_explicit() -> None:
    artifact = _engineering(
        _model(
            (("A", "REANALYSIS_REQUIRED"),),
            analysis={"A": AnalysisBasisStatus.REANALYSIS_REQUIRED},
        )
    )
    text = _text(artifact)
    assert "REANALYSIS_REQUIRED" in text
    assert "renderer does not map it to PASS or FAIL" in text


def test_pna_out_of_scope_is_not_mapped_to_pass() -> None:
    artifact = _engineering(_pna_model())
    text = _text(artifact)
    assert "OUT_OF_SCOPE" in text
    assert "proven_not_applicable_count" in text
    assert "PASS" not in text


def test_no_compliance_percentage_or_global_verdict_is_generated() -> None:
    text = _text(_engineering())
    lowered = text.lower()
    assert "compliance percentage" not in lowered
    assert "project compliant" not in lowered
    assert "global compliance verdict" not in lowered
    assert "overall pass" not in lowered


def test_pdf_reuses_ur_1c_html_renderer(monkeypatch) -> None:
    projection = _projection(_model(), ReportView.ENGINEERING)
    calls: list[tuple[object, object, object]] = []

    def fake_html(projection_arg, *, options, selection):
        calls.append((projection_arg, options, selection))
        return "<!doctype html><html><body>canonical html</body></html>"

    monkeypatch.setattr(pdf_module, "render_building_report_html", fake_html)
    monkeypatch.setattr(pdf_module, "pdf_toolchain_identity", lambda: "toolchain")
    monkeypatch.setattr(
        pdf_module,
        "_render_pdf_bytes",
        lambda html_text, *, options, pdf_identifier: b"%PDF-1.7\ncanonical-stub",
    )

    artifact = render_building_report_pdf(projection)

    assert len(calls) == 1
    assert calls[0][0] is projection
    assert artifact.source_render_sha256 == sha256(
        b"<!doctype html><html><body>canonical html</body></html>"
    ).hexdigest()


def test_pdf_layer_does_not_evaluate_formula_or_transform_units_or_governing_ref() -> None:
    artifact = _engineering(
        _model(
            (("A", "PASS"),),
            formula_rule="A",
            formula="FORMULA_TEXT_ONLY = DEMAND / CAPACITY",
            value=123.4567890123,
            unit="kN",
        )
    )
    text = _text(artifact)

    assert "FORMULA_TEXT_ONLY" in text
    assert "123.4567890123" in text
    assert "kN" in text
    assert "GOV:ROW:1" in text


def test_presentation_selection_is_preserved_and_coverage_is_not_recomputed() -> None:
    projection = _projection(
        _model((("A", "PASS"), ("B", "FAIL"))),
        ReportView.ENGINEERING,
    )
    selection = ReportPresentationSelection(statuses=("FAIL",))
    artifact = render_building_report_pdf(projection, selection=selection)
    text = _text(artifact)

    assert "Presentation selection/filter applied" in text
    assert "Assessment population" in text
    assert "Presentation scope" in text
    assert "expected mandatory: 2" in text
    assert "Rule B" in text
    assert "Rule A" not in text


def test_same_inputs_options_toolchain_are_byte_identical() -> None:
    projection = _projection(
        _model((("A", "PASS"), ("B", "FAIL"))),
        ReportView.ENGINEERING,
    )
    html_options = HtmlRenderOptions(
        include_projection_json=False,
        enable_interactivity=False,
    )
    selection = ReportPresentationSelection(statuses=("PASS", "FAIL"))
    pdf_options = PdfRenderOptions()

    first = render_building_report_pdf(
        projection,
        html_options=html_options,
        selection=selection,
        pdf_options=pdf_options,
    )
    second = render_building_report_pdf(
        projection,
        html_options=html_options,
        selection=selection,
        pdf_options=pdf_options,
    )

    print(f"deterministic_pdf_sha256={first.sha256}")
    assert first.content == second.content
    assert first.sha256 == second.sha256
    assert first.artifact_id == second.artifact_id


def test_artifact_metadata_matches_pdf_bytes_and_is_deterministic() -> None:
    first = _engineering()
    second = _engineering()

    assert first.byte_length == len(first.content)
    assert first.sha256 == sha256(first.content).hexdigest()
    assert first.artifact_id == second.artifact_id
    assert first.filename == second.filename == "REPORT_1_engineering.pdf"
    assert first.source_report_id == "REPORT:1"
    assert first.source_project_id == "PROJECT:1"


def test_filename_policy_is_deterministic_and_filesystem_safe() -> None:
    projection = _projection(_model(), ReportView.AUDIT)
    artifact = render_building_report_pdf(
        projection,
        pdf_options=PdfRenderOptions(filename_stem="Project / Report : 01"),
    )
    assert artifact.filename == "Project_Report_01_audit.pdf"
    assert "/" not in artifact.filename
    assert "\\" not in artifact.filename


def test_toolchain_identity_records_exact_supported_backend_versions() -> None:
    identity = pdf_toolchain_identity()
    assert f'"weasyprint":"{SUPPORTED_WEASYPRINT_VERSION}"' in identity
    assert f'"pydyf":"{SUPPORTED_PYDYF_VERSION}"' in identity
    assert '"python":' in identity


def test_html_integrity_error_is_not_swallowed(monkeypatch) -> None:
    projection = _projection(_model(), ReportView.ENGINEERING)

    def fail_html(*args, **kwargs):
        raise HtmlRenderIntegrityError("unreconciled")

    monkeypatch.setattr(pdf_module, "render_building_report_html", fail_html)
    with pytest.raises(HtmlRenderIntegrityError, match="unreconciled"):
        render_building_report_pdf(projection)


def test_generated_pdf_renders_to_nonblank_page_image() -> None:
    artifact = _engineering()
    document = pdfium.PdfDocument(artifact.content)
    assert len(document) > 0
    page = document[0]
    bitmap = page.render(scale=0.75)
    image = bitmap.to_pil()
    grayscale = image.convert("L")

    print(f"pdf_page_count={len(document)}")
    print(f"pdf_page_image={image.width}x{image.height}")
    assert image.width > 0
    assert image.height > 0
    minimum, maximum = grayscale.getextrema()
    assert minimum < 245
    assert maximum > minimum


def test_engineering_and_audit_use_same_export_path(monkeypatch) -> None:
    calls: list[str] = []
    real = pdf_module._render_pdf_bytes

    def record(html_text, *, options, pdf_identifier):
        calls.append(html_text)
        return real(html_text, options=options, pdf_identifier=pdf_identifier)

    monkeypatch.setattr(pdf_module, "_render_pdf_bytes", record)
    engineering = _engineering()
    audit = _audit()

    assert len(calls) == 2
    assert engineering.view == "ENGINEERING"
    assert audit.view == "AUDIT"


def test_supported_profile_rejects_non_a4_and_background_suppression() -> None:
    with pytest.raises(PdfRenderIntegrityError, match="A4"):
        PdfRenderOptions(page_size="Letter")
    with pytest.raises(PdfRenderIntegrityError, match="print_background=True"):
        PdfRenderOptions(print_background=False)


def test_production_pdf_modules_have_no_timestamp_random_or_engine_imports() -> None:
    sources = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (pdf_module.__file__, pdf_module.ReportArtifact.__module__.replace(".", "/") + ".py")
        if Path(path).exists()
    )
    if not sources:
        sources = Path(pdf_module.__file__).read_text(encoding="utf-8")
    lowered = sources.lower()
    assert "datetime.now" not in lowered
    assert "uuid4" not in lowered
    assert "random." not in lowered
    assert "etabs" not in lowered
    assert "featuresnapshot" not in lowered
    assert "regulatoryengine" not in lowered


def test_pdf_module_does_not_import_etabs_provider_or_regulatory_engine() -> None:
    source = Path(pdf_module.__file__).read_text(encoding="utf-8")
    assert "tbdy_engine.etabs" not in source
    assert "provider" not in source.lower()
    assert "RegulatoryEngine" not in source
    assert "AssessmentEngine" not in source


def test_product_reports_init_does_not_eagerly_import_ur_1d() -> None:
    init_path = Path(pdf_module.__file__).with_name("__init__.py")
    source = init_path.read_text(encoding="utf-8")
    assert "building_report_pdf" not in source
    assert "report_artifact" not in source
