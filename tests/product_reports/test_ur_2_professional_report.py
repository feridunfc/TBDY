from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
from pathlib import Path
import inspect
import json
import sys
from zipfile import ZipFile

from tbdy_engine.product_reports.building_report_html import HtmlRenderOptions, render_building_report_html
from tbdy_engine.product_reports.building_report_package import build_building_report_package, build_report_delivery_artifacts, verify_building_report_package
from tbdy_engine.product_reports.building_report_projection import ReportView, project_building_report_view
from tbdy_engine.product_reports.building_report_pdf import render_building_report_pdf
from tbdy_engine.product_reports.building_report_xlsx import render_building_report_xlsx


def _demo_module():
    path = Path("tools/build_ur2_demo_report.py")
    spec = spec_from_file_location("_ur2_demo_builder_for_tests", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _model():
    return _demo_module().build_demo_model()


def test_public_html_facade_imports_and_keeps_ur1_signature_compatible():
    signature = inspect.signature(render_building_report_html)
    assert list(signature.parameters) == ["projection", "options", "selection"]
    assert signature.parameters["options"].kind is inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["selection"].kind is inspect.Parameter.KEYWORD_ONLY
    options = HtmlRenderOptions()
    assert options.include_projection_json is True
    assert options.enable_interactivity is True


def test_projection_adds_presentation_metadata_without_changing_canonical_truth():
    model = _model(); payload = project_building_report_view(model, ReportView.ENGINEERING).as_dict()
    assert payload["coverage_summary"] == model.reconciliation.as_dict()["summary"]
    assert all(item["value"] == payload["coverage_summary"][item["canonical_key"]] for item in payload["coverage_display"])
    assert [item["status"] for item in payload["contributions"]] == [item.status for item in model.contributions]
    contract = payload["presentation_contract"]
    assert contract["engineering_recalculation_allowed"] is False
    assert contract["status_reinterpretation_allowed"] is False
    assert contract["governing_selection_change_allowed"] is False
    assert contract["remediation_synthesis_allowed"] is False
    assert contract["global_compliance_verdict_emitted"] is False
    assert contract["compliance_percentage_emitted"] is False
    assert payload["report_context"]["data_classification"] == "DEMO DATA"
    assert all(item["status"] == "REPORT_INPUT_GAP" for item in payload["report_input_gaps"])


def test_exact_component_type_domain_grouping_never_uses_titles_or_ids():
    payload = project_building_report_view(_model(), ReportView.ENGINEERING).as_dict()
    domains = {item["domain_id"]: item for item in payload["presentation_domains"]}
    refs_by_type = {item["component_type"]: item["contribution_ref"] for item in payload["contributions"]}
    assert refs_by_type["COLUMN"] in domains["columns"]["contribution_refs"]
    assert refs_by_type["BEAM"] in domains["beams"]["contribution_refs"]
    assert refs_by_type["SCWB_JOINT"] in domains["scwb-joints"]["contribution_refs"]
    assert refs_by_type["FOUNDATION"] in domains["foundation-geotechnical"]["contribution_refs"]


def test_engineering_and_audit_html_are_professional_standalone_demo_documents():
    model = _model()
    for view in (ReportView.ENGINEERING, ReportView.AUDIT):
        html = render_building_report_html(project_building_report_view(model, view), options=HtmlRenderOptions(include_projection_json=True, enable_interactivity=True))
        assert html.startswith("<!doctype html><html") and html.endswith("</html>\n")
        assert '<div class="shell">' in html
        for marker in ("UNIFIED ENGINEERING REVIEW V2", "Engineering executive summary", "Critical findings / blockers / reanalysis", "Project and seismic design basis", "Coverage by engineering domain", "Engineering domain navigation", "Required actions / remediation register", "REPORT_INPUT_GAP register", "DEMO DATA - ILLUSTRATIVE PRODUCT PACKAGE - NOT LIVE ENGINEERING TRUTH"):
            assert marker in html
        assert "no compliance percentage is calculated" in html
        assert "no renderer remediation is generated" in html


def test_formula_text_is_displayed_literally_and_never_evaluated():
    html = render_building_report_html(project_building_report_view(_model(), ReportView.ENGINEERING))
    assert "DEMO_UPSTREAM_EXPRESSION - DISPLAY ONLY - NOT EVALUATED BY RENDERER" in html


def test_pdf_and_xlsx_render_for_both_views():
    model = _model()
    for view in (ReportView.ENGINEERING, ReportView.AUDIT):
        projection = project_building_report_view(model, view)
        pdf = render_building_report_pdf(projection); xlsx = render_building_report_xlsx(projection)
        assert pdf.content.startswith(b"%PDF-"); assert xlsx.content.startswith(b"PK")
        with ZipFile(BytesIO(xlsx.content), "r") as archive:
            assert "[Content_Types].xml" in archive.namelist()


def test_deterministic_package_and_required_nine_visible_artifacts(tmp_path: Path):
    module = _demo_module(); first_paths = module.write_demo_package(tmp_path / "run1"); second_paths = module.write_demo_package(tmp_path / "run2")
    first = {path.name: path.read_bytes() for path in first_paths}; second = {path.name: path.read_bytes() for path in second_paths}
    expected = {"engineering.html", "engineering.pdf", "engineering.xlsx", "audit.html", "audit.pdf", "audit.xlsx", "building_report_model.json", "manifest.json", "building_report_package.zip"}
    assert set(first) == expected and set(second) == expected and first == second
    package = build_building_report_package(_model()); verify_building_report_package(package)
    assert package.content == first["building_report_package.zip"]
    with ZipFile(BytesIO(package.content), "r") as archive:
        assert set(archive.namelist()) == expected - {"building_report_package.zip"}
    model_json = json.loads(first["building_report_model.json"].decode("utf-8"))
    assert model_json["title"] == "Unified Engineering Review - DEMO DATA"


def test_delivery_members_remain_the_accepted_ur1_eight_member_contract():
    artifacts = build_report_delivery_artifacts(_model())
    assert {item.filename for item in artifacts} == {"engineering.html", "engineering.pdf", "engineering.xlsx", "audit.html", "audit.pdf", "audit.xlsx", "building_report_model.json", "manifest.json"}


def test_renderer_source_contains_no_engineering_or_etabs_authority_calls():
    import tbdy_engine.product_reports.building_report_html_v2 as renderer
    source = inspect.getsource(renderer)
    for token in ("RunAnalysis", "StartDesign", "GetSummaryResultsColumn", "PMMArea", "SetPresentUnits", "SetComboStrength", "SetDesignSection", "CheckEngine", "ETABS_REQUIRED_REBAR", "ENGINE_SELECTED_REBAR", "eval(", "exec("):
        assert token not in source
    assert "project_compliant" not in source
    assert "compliance_percentage" not in source
