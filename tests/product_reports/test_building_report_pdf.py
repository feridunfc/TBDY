from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
import json
import os
from pathlib import Path
import re
import sys

import pytest
from pypdf import PdfReader
import pypdfium2 as pdfium

import tbdy_engine.product_reports.building_report_pdf as pdf_module
import tbdy_engine.product_reports.report_artifact as artifact_module
from tbdy_engine.product_reports.building_report_html import (
    HtmlRenderIntegrityError,
    HtmlRenderOptions,
)
from tbdy_engine.product_reports.building_report_pdf import (
    DETERMINISTIC_SOURCE_DATE_EPOCH,
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


def _normalized_text(artifact: ReportArtifact) -> str:
    """Normalize extractor-only whitespace without changing expected content."""

    return " ".join(_text(artifact).split())


def _compact_text(artifact: ReportArtifact) -> str:
    """Remove extractor-only whitespace for exact technical token assertions."""

    return "".join(_text(artifact).split())


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
    compact = _compact_text(artifact)

    assert artifact.format == "PDF"
    assert artifact.media_type == "application/pdf"
    assert artifact.view == "ENGINEERING"
    assert artifact.content.startswith(b"%PDF-")
    assert len(reader.pages) > 0
    assert "UNIFIEDENGINEERINGREVIEW" in compact.upper()
    assert "ENGINEERING" in compact
    assert "REPORT:1" in compact


def test_audit_projection_creates_valid_pdf_artifact_and_trace() -> None:
    artifact = _audit()
    reader = _reader(artifact)
    compact = _compact_text(artifact)

    assert artifact.view == "AUDIT"
    assert artifact.content.startswith(b"%PDF-")
    assert len(reader.pages) > 0
    assert "AUDIT" in compact
    assert "SourceManifest" in compact
    assert "sha256:toy" in compact
    assert "TOY§1" in compact


@pytest.mark.parametrize("status", ["PASS", "FAIL"])
def test_executed_status_survives_pdf_exactly(status: str) -> None:
    artifact = _engineering(_model((("A", status),)))
    assert status in _compact_text(artifact)


@pytest.mark.parametrize(
    ("closure", "status"),
    [
        (ClosureExecutionStatus.BLOCKED, "BLOCKED"),
        (ClosureExecutionStatus.NO_DATA, "NO_DATA"),
    ],
)
def test_resultless_status_survives_pdf_exactly(closure, status: str) -> None:
    artifact = _engineering(_resultless(closure, status))
    compact = _compact_text(artifact)
    assert status in compact
    assert f"{status}stays" not in compact


def test_reanalysis_required_remains_explicit() -> None:
    artifact = _engineering(
        _model(
            (("A", "REANALYSIS_REQUIRED"),),
            analysis={"A": AnalysisBasisStatus.REANALYSIS_REQUIRED},
        )
    )
    compact = _compact_text(artifact)
    assert "REANALYSIS_REQUIRED" in compact
    assert "rendererdoesnotmapittoPASSorFAIL" in compact


def test_pna_out_of_scope_is_not_mapped_to_pass() -> None:
    artifact = _engineering(_pna_model())
    text = _text(artifact)
    compact = "".join(text.split())
    assert "OUT_OF_SCOPE" in compact
    assert "proven_not_applicable_count" in compact
    assert re.search(r"(?<![A-Z_])PASS(?![A-Z_])", text) is None


def test_no_compliance_percentage_or_global_verdict_is_generated() -> None:
    lowered = _normalized_text(_engineering()).lower()
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
    compact = _compact_text(artifact)

    assert "FORMULA_TEXT_ONLY=DEMAND/CAPACITY" in compact
    assert "123.4567890123" in compact
    assert "kN" in compact
    assert "GOV:ROW:1" in compact


def test_presentation_selection_is_preserved_and_coverage_is_not_recomputed() -> None:
    projection = _projection(
        _model((("A", "PASS"), ("B", "FAIL"))),
        ReportView.ENGINEERING,
    )
    selection = ReportPresentationSelection(statuses=("FAIL",))
    artifact = render_building_report_pdf(projection, selection=selection)
    compact = _compact_text(artifact)

    assert "Presentationselection/filterapplied" in compact
    assert "Assessmentpopulation" in compact
    assert "Presentationscope" in compact
    assert "expectedmandatory:2" in compact
    assert "RuleB" in compact
    assert "RuleA" not in compact


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
    if first.content != second.content:
        limit = min(len(first.content), len(second.content))
        index = next(
            (i for i in range(limit) if first.content[i] != second.content[i]),
            limit,
        )
        window = slice(max(0, index - 40), index + 80)
        pytest.fail(
            "PDF bytes are not deterministic: "
            f"first_sha={first.sha256} second_sha={second.sha256} "
            f"first_diff={index} first={first.content[window]!r} "
            f"second={second.content[window]!r}"
        )
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
    identity = json.loads(pdf_toolchain_identity())
    assert identity["packages"]["weasyprint"] == SUPPORTED_WEASYPRINT_VERSION
    assert identity["packages"]["pydyf"] == SUPPORTED_PYDYF_VERSION
    assert identity["python"]
    assert identity["source_date_epoch"] == DETERMINISTIC_SOURCE_DATE_EPOCH


def test_reproducible_epoch_does_not_leak_caller_environment(monkeypatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "123456789")
    _engineering()
    assert os.environ["SOURCE_DATE_EPOCH"] == "123456789"


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


def test_production_pdf_modules_have_no_current_timestamp_random_or_engine_imports() -> None:
    sources = "\n".join(
        Path(module.__file__).read_text(encoding="utf-8")
        for module in (pdf_module, artifact_module)
    )
    lowered = sources.lower()
    assert "datetime.now" not in lowered
    assert "time.time" not in lowered
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
