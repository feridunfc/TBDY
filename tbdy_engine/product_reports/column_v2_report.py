"""Render the typed reference calculation; no engineering decisions here."""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from html import escape
from io import BytesIO
from pathlib import Path

from tbdy_engine.application.column_reference_workspace import ReferenceCalculation, ReferenceColumnInput, canonical_bytes
from tbdy_engine.product_reports.vs6_column_design_engine_report import build_vs6_column_design_engine_reports
from tbdy_engine.product_reports.column_v1_report import PINS, CANDIDATE, HISTORICAL
import json

FIELDS = (
    ("width_mm", "Genişlik / yerel 2", "mm", "Geometri"),
    ("depth_mm", "Derinlik / yerel 3", "mm", "Geometri"),
    ("free_length_mm", "Düzenleyici serbest boy ln", "mm", "Geometri"),
    ("k_m2", "Etkin boy katsayısı k / M2", "-", "Narinlik"),
    ("k_m3", "Etkin boy katsayısı k / M3", "-", "Narinlik"),
    ("moment_ratio_m2", "İşaretli M1/M2 / M2 düzlemi", "-", "Narinlik"),
    ("moment_ratio_m3", "İşaretli M1/M2 / M3 düzlemi", "-", "Narinlik"),
    ("fck_mpa", "Beton karakteristik dayanımı fck", "MPa", "Malzeme"),
    ("fcd_mpa", "Beton tasarım dayanımı fcd", "MPa", "Malzeme"),
    ("fyd_mpa", "Donatı tasarım dayanımı fyd", "MPa", "Malzeme"),
    ("nd_kn", "Basınç kuvveti Nd", "kN", "Yük"),
    ("m2_knm", "İşaretli moment M2", "kN.m", "Yük"),
    ("m3_knm", "İşaretli moment M3", "kN.m", "Yük"),
    ("clear_cover_mm", "Net beton örtüsü", "mm", "Donatı"),
    ("tie_diameter_mm", "Etriye çapı / yerleşim girdisi", "mm", "Donatı"),
    ("aggregate_max_mm", "En büyük agrega çapı", "mm", "Donatı"),
    ("bar_diameters_mm", "Referans çap kataloğu", "mm", "Donatı"),
)
SCOPE = (
    "REFERANS / DEMO: ETABS gözlemi veya B-BLOK üretim hesabı değildir.",
    "REFERENCE_ULS = 1.0 x REFERENCE_D. İki referans uçta aynı açık N/M girdisi kullanılır.",
    "Ötelenmesi önlenmiş sistem; ln, k ve işaretli uç moment oranları açık referans kabulleridir. Kuvvetlerden türetilmez.",
    "fck, fcd, fyd ayrı açık girdilerdir; bu ekran malzeme güvenlik katsayısı üretmez.",
    "36 yönlü mevcut TS500 şekil değiştirme uyumu ve radyal kapasite denemesi: yalnız DESIGN_CANDIDATE_ONLY.",
    "Nihai donatı seçimi, sargı/etriye uygunluğu, kesme, deprem yük kapsamı ve proje onayı hesaplanmadı.",
)


def fmt(value: float) -> str:
    return f"{value:.6g}"


def section_svg(inputs: ReferenceColumnInput, selected=None) -> str:
    scale = 230 / max(inputs.width_mm, inputs.depth_mm)
    w, h = inputs.width_mm * scale, inputs.depth_mm * scale
    x, y = (360-w)/2, (310-h)/2
    bars = "" if selected is None else "".join(
        f'<circle cx="{180+b.x2_mm*scale}" cy="{155-b.x3_mm*scale}" r="{max(2.5,b.diameter_mm*scale/2)}" fill="#11665b"/>' for b in selected.bars)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 350" role="img" aria-label="Açık referans girdilerinden ölçülü kesit">
    <defs><marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="none" stroke="#65778b"/></marker></defs>
    <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#eef3f7" stroke="#183c53" stroke-width="2"/>{bars}
    <path d="M{x},{y+h+17} H{x+w} M{x-17},{y} V{y+h}" stroke="#65778b" fill="none"/>
    <path d="M180,155 H{min(338,x+w+28)} M180,155 V{max(12,y-24)}" stroke="#65778b" marker-end="url(#arr)"/>
    <g fill="#183c53" font-family="sans-serif" font-size="12"><text x="180" y="{y+h+36}" text-anchor="middle">b = {fmt(inputs.width_mm)} mm</text>
    <text x="{max(7,x-29)}" y="155" text-anchor="middle" transform="rotate(-90 {max(7,x-29)} 155)">h = {fmt(inputs.depth_mm)} mm</text>
    <text x="{min(340,x+w+25)}" y="148">2</text><text x="187" y="{max(16,y-18)}">3</text>
    <text x="180" y="337" text-anchor="middle">{('Motorun donatı adayı; nihai donatı değildir' if selected else 'Donatı yerleşimi hesap sonrası gösterilir')}</text></g></svg>'''


def reference_manifest(calculation: ReferenceCalculation) -> dict:
    result = calculation.engine_result
    checks = []
    for axis in (result.slenderness.m2, result.slenderness.m3):
        checks.append({"id": "slenderness_"+axis.axis, "title": "Narinlik / "+axis.axis,
            "status": axis.status, "display_status": "HESAPLANDI" if axis.status == "SLENDERNESS_EFFECTS_NEGLIGIBLE" else "EK HESAP GEREKLİ",
            "value": axis.slenderness_ratio_lk_over_i, "limit": axis.neglect_limit, "unit": "-",
            "reason": "İkinci mertebe etkileri ihmal edilebilir." if axis.status == "SLENDERNESS_EFFECTS_NEGLIGIBLE" else "Bu eksende ihmal kararı tamamlanmadı; büyütme/ikinci mertebe yolu gerekli. Hesaplanmış FAIL değildir.",
            "source": "TS500 7.6.1, 7.6.2.3 / Denklem 7.17",
            "formula": "i = 0.30 h; lk = k ln; lambda = lk/i; sınır = min(40, 34 - 12 M1/M2)",
            "trace": f"i = 0.30 x {fmt(axis.section_dimension_mm)} = {fmt(axis.radius_of_gyration_i_mm)} mm; lk = {fmt(axis.effective_length_factor_k)} x {fmt(axis.free_length_ln_mm)} = {fmt(axis.effective_length_lk_mm)} mm; lambda = {fmt(axis.effective_length_lk_mm)} / {fmt(axis.radius_of_gyration_i_mm)} = {fmt(axis.slenderness_ratio_lk_over_i)}; sınır = min(40, 34 - 12 x {fmt(axis.moment_ratio_m1_over_m2)}) = {fmt(axis.neglect_limit)}"})
    adjustment = result.minimum_eccentricity.adjustments[0]
    for axis, h, emin, original, required in (
        ("M2", calculation.inputs.depth_mm, adjustment.emin_for_m2_mm, adjustment.original_m2_nmm, adjustment.required_abs_m2_nmm),
        ("M3", calculation.inputs.width_mm, adjustment.emin_for_m3_mm, adjustment.original_m3_nmm, adjustment.required_abs_m3_nmm)):
        states = sorted(set(getattr(s, axis.lower()+"_nmm") / 1e6 for s in result.minimum_eccentricity.states))
        checks.append({"id": "eccentricity_"+axis, "title": "Minimum dışmerkezlik / "+axis,
            "status": result.minimum_eccentricity.status, "display_status": "UYGULANDI",
            "value": required/1e6, "limit": None, "unit": "kN.m", "source": "TS500 6.3.10 / Denklem 6.16",
            "reason": "Moment alt sınırı uygulandı; kapasite veya PMM oranı değildir.",
            "formula": "emin = 15 + 0.03 h; |M|min = Nd emin; işaret korunur, sıfır momentte iki işaret dallanır",
            "trace": f"emin = 15 + 0.03 x {fmt(h)} = {fmt(emin)} mm; |M|min = {fmt(adjustment.nd_compression_n/1000)} x {fmt(emin)} / 1000 = {fmt(required/1e6)} kN.m; giriş = {fmt(original/1e6)} kN.m; motor çıkışı = {', '.join(fmt(v) for v in states)} kN.m"})
    selection = result.rebar_design.selection
    selected = None if selection is None else selection.selected_candidate
    evaluations = [] if selection is None else [asdict(e) for e in selection.selected_evaluations]
    if selected is not None:
        governing = next(e for e in selection.selected_evaluations if e.state.state_id == selection.governing_state_id)
        checks.append({"id": "candidate_capacity", "title": "Donatı adayı / radyal kapasite",
            "status": result.rebar_design.status, "display_status": "ADAY BULUNDU",
            "value": selection.governing_utilization, "limit": 1.0, "unit": "-",
            "source": "TS500 7.1, 7.5; mevcut VS6 / 36 yönlü şekil değiştirme uyumu",
            "formula": "u = sqrt(M2² + M3²) / M_radyal(Nd); mevcut motor kapasite zarfı",
            "trace": f"Nd = {fmt(governing.state.nd_compression_n/1000)} kN; M2 = {fmt(governing.state.m2_nmm/1e6)} kN.m; M3 = {fmt(governing.state.m3_nmm/1e6)} kN.m; |M| = {fmt(governing.state.moment_magnitude_nmm/1e6)} kN.m; radyal kapasite = {fmt(governing.radial_capacity_nmm/1e6)} kN.m; u = {fmt(governing.utilization)} <= 1; As = {fmt(selected.as_total_mm2)} mm²; rho = {fmt(selected.rho_pct)} %",
            "reason": f"{selected.bar_count} adet Ø{fmt(selected.bar_diameter_mm)} aday. Yöneten referans durum: {governing.state.output_case} / {governing.state.end_tag}. Nihai donatı değildir."})
    else:
        checks.append({"id": "candidate_capacity", "title": "Donatı adayı / radyal kapasite", "status": result.rebar_design.status,
            "display_status": "TAMAMLANMADI", "value": None, "limit": None, "unit": "-", "source": "Mevcut VS6 motoru",
            "formula": "Kapasite/aday sonucu mevcut motorun bağımlılık kararına tabidir.", "trace": "Sayısal kapasite sonucu yayımlanmadı.",
            "reason": "Narinlik bağımlılığı veya uygun aday tamamlanmadı; otomatik PASS/FAIL üretilmedi."})
    contributions = [c.as_dict() for c in build_vs6_column_design_engine_reports(result, section_name="Açık referans dikdörtgen kesit")]
    data = {"schema": "column_v2.reference_calculation.v1", "context": calculation.inputs.bundle()["context"],
        "title": "REFERANS / DEMO - Kolon hesabı", "source": calculation.inputs.bundle()["source"],
        "input_bundle": calculation.inputs.bundle(), "input_sha256": calculation.input_sha256,
        "changed_fields": list(calculation.changed_fields), "engine_status": result.status,
        "engine_function": "tbdy_engine.design.columns.column_design_engine.evaluate_column_design",
        "authority": result.rebar_design.authority, "checks": checks, "scope": list(SCOPE),
        "typed_slenderness": asdict(result.slenderness), "typed_minimum_eccentricity": asdict(result.minimum_eccentricity),
        "selected_candidate": None if selected is None else asdict(selected),
        "selected_evaluations": evaluations, "contributions": contributions,
        "section_svg": section_svg(calculation.inputs, selected), "production_promotion": False}
    data["result_id"] = sha256(canonical_bytes(data)).hexdigest()
    return data


def column_235_manifest(repo: Path) -> dict:
    accepted = {}
    for key in ("assignment", "property", "gates"):
        name, digest = PINS[key]
        content = (repo/"docs"/name).read_bytes()
        if sha256(content).hexdigest() != digest:
            raise ValueError("235 kabul edilmiş kanıt hash'i farklı: "+key)
        accepted[key] = json.loads(content)
    assignment, prop = accepted["assignment"], accepted["property"]
    if assignment["integrity"]["candidate_sha256"] != CANDIDATE or prop["integrity"]["candidate_before_after_sha256"] != CANDIDATE:
        raise ValueError("235 kaynak kimliği farklı.")
    return {"context": "B-BLOK-235", "title": "B-BLOK / Kolon 235", "status": "EKSİK GİRDİ / HESAPLANMADI",
        "section": assignment["single_assignment_derived"]["candidate_PropName"],
        "I22": prop["property_scope"]["I22"], "I33": prop["property_scope"]["I33"],
        "candidate_sha256": CANDIDATE, "historical_sha256": HISTORICAL,
        "unavailable": ["Aday modele bağlı açık kesit ölçüleri", "Düzenleyici ln/k ve sistem kararlılığı", "Malzeme tasarım dayanımları", "Yönetmelik kapsamlı tasarım N/M/V ve güncel sonuç dönemi", "Donatı ve sargı bilgileri", "Güncel uç nokta/fiziksel bağlama", "Global deplasman sözleşmesi"],
        "calculations": [], "engineering_verdict": "NOT_EVALUATED", "FC09_PRODUCTION_GATE": "UNCHANGED",
        "GLOBAL_DELTA": "NOT_PROVEN", "M6_B": "OPEN", "R2_RERUN_READY": False,
        "evidence_refs": {k: {"name": PINS[k][0], "sha256": PINS[k][1]} for k in accepted},
        "scope": ["Kesit adından boyut üretilmedi.", "I22/I33 yalnız kabul edilmiş m⁴ özelliğini kapsar; tüm model eşdeğerliği değildir.", "Referans sonuçları bu kolona aktarılmadı.", "FC09 tarihsel sonuçları ayrı kanıttır; güncel tasarım yükü değildir."]}


def render_reference_pdf(calculation: ReferenceCalculation) -> bytes:
    return render_manifest_pdf(reference_manifest(calculation))


def render_manifest_pdf(manifest: dict) -> bytes:
    """Both reference and evidence reports project their own immutable manifest."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from reportlab.graphics.shapes import Drawing, Rect, Circle, String, Line
    fonts = ((Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
             (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")))
    regular, bold = next((a,b) for a,b in fonts if a.is_file() and b.is_file())
    if "ColumnV2" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("ColumnV2", str(regular)))
        pdfmetrics.registerFont(TTFont("ColumnV2Bold", str(bold)))
        pdfmetrics.registerFontFamily("ColumnV2", normal="ColumnV2", bold="ColumnV2Bold")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("V2", fontName="ColumnV2", fontSize=9, leading=12, spaceAfter=5))
    styles.add(ParagraphStyle("V2H", fontName="ColumnV2Bold", fontSize=13, leading=17, spaceBefore=10, spaceAfter=6, keepWithNext=True, textColor=colors.HexColor("#183c53")))
    styles.add(ParagraphStyle("V2Title", fontName="ColumnV2Bold", fontSize=21, leading=25, spaceAfter=14))
    p = lambda text: Paragraph(escape(str(text)), styles["V2"])
    story = [Paragraph(escape(manifest["title"]), styles["V2Title"]), p("Kaynak: "+("REFERANS / kullanıcı girdisi; ETABS gözlemi değildir." if "input_bundle" in manifest else "Kabul edilmiş aday / ayrı tarihsel FC09")), p("Durum: "+("Hesaplandı - tasarım adayı" if manifest.get("engine_status") == "SELECTED_DESIGN_CANDIDATE_ONLY" else manifest.get("engine_status", manifest.get("status", ""))))]
    if "input_bundle" in manifest:
        v = manifest["input_bundle"]["values"]
        story += [Paragraph("Kontrol özeti", styles["V2H"])]
        summary_rows = [[p("Kontrol"),p("Sonuç / sınır"),p("Durum")]]
        for check in manifest["checks"]:
            summary_rows.append([p(check["title"]),p(("YOK" if check["value"] is None else fmt(check["value"]))+" "+check["unit"]+("" if check["limit"] is None else " / "+fmt(check["limit"]))),p(check["display_status"])])
        summary=Table(summary_rows,colWidths=[240,140,110],repeatRows=1)
        summary.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#e8eff5")),("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,-1),0.3,colors.HexColor("#dae3eb"))]))
        story.append(summary)
        d = Drawing(490, 190)
        s = 145/max(v["width_mm"], v["depth_mm"])
        w,h = v["width_mm"]*s,v["depth_mm"]*s
        d.add(Rect(110-w/2,95-h/2,w,h,fillColor=colors.HexColor("#eef3f7"),strokeColor=colors.HexColor("#183c53")))
        selected = manifest["selected_candidate"]
        if selected:
            for b in selected["bars"]: d.add(Circle(110+b["x2_mm"]*s,95+b["x3_mm"]*s,max(2,b["diameter_mm"]*s/2),fillColor=colors.HexColor("#11665b")))
        d.add(Line(110,95,210,95)); d.add(Line(110,95,110,183))
        for x,y,t in ((211,98,"2"),(116,180,"3"),(50,10,f'b={fmt(v["width_mm"])} mm'),(230,160,f'h={fmt(v["depth_mm"])} mm'),(230,130,"Açık referans kesiti"),(230,108,"Donatı: motor adayı" if selected else "Donatı: hesaplanmadı")):
            d.add(String(x,y,t,fontName="ColumnV2",fontSize=9))
        story += [d, Paragraph("Girdi özeti", styles["V2H"])]
        rows = [[p("Girdi"),p("Değer"),p("Birim / kaynak")]]
        for key,label,unit,_ in FIELDS:
            value = v[key]; display = ", ".join(fmt(x) for x in value) if isinstance(value,list) else fmt(value)
            rows.append([p(label),p(display),p(unit+" / "+("kullanıcı referansı" if key in manifest["changed_fields"] else "referans"))])
        t=Table(rows,colWidths=[245,95,150],repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#e8eff5")),("VALIGN",(0,0),(-1,-1),"TOP"),("LINEBELOW",(0,0),(-1,-1),0.3,colors.HexColor("#dae3eb")),("BOTTOMPADDING",(0,0),(-1,-1),3)]))
        story += [t,Paragraph("Kontroller ve sayısal hesap izi", styles["V2H"])]
        for check in manifest["checks"]:
            story.append(KeepTogether([Paragraph(escape(check["title"]), styles["V2H"]), p(check["display_status"]+" / "+check["status"]),
                p("Sonuç: "+("YOK" if check["value"] is None else fmt(check["value"]))+" "+check["unit"]+"; sınır: "+("uygulanmaz" if check["limit"] is None else fmt(check["limit"]))),
                p(check["source"]),p(check["formula"]),p(check["trace"]),p(check["reason"])]))
    else:
        story += [p("Kesit: "+manifest["section"]), p("I22 = "+repr(manifest["I22"]["value"])+" m⁴; I33 = "+repr(manifest["I33"]["value"])+" m⁴"),p("Aday SHA256: "+manifest["candidate_sha256"]),p("Tarihsel SHA256: "+manifest["historical_sha256"]),Paragraph("Eksik hesap kapsamı",styles["V2H"])]
        story.extend(p(item) for item in manifest["unavailable"])
    story.append(Paragraph("Kapsam ve kaynak sınırları", styles["V2H"]))
    story.extend(p(item) for item in manifest["scope"])
    story.append(Paragraph("Kanıt / Teknik kimlik", styles["V2H"]))
    if "input_bundle" in manifest:
        story.extend([p("Kaynak kimliği: "+manifest["source"]),p("Motor: "+manifest["engine_status"]),p("Sonuç kimliği: "+manifest["result_id"]),p("Girdi SHA256: "+manifest["input_sha256"])])
    else:
        story.extend(p(key+": "+value["sha256"]) for key,value in manifest["evidence_refs"].items())
    buffer = BytesIO()
    def footer(canvas,doc):
        canvas.setFont("ColumnV2",8); canvas.setFillColor(colors.HexColor("#65778b"))
        canvas.drawString(42,24,manifest["context"]+" / "+str(doc.page)); canvas.drawRightString(552,24,"TBDY - Column V2 / offline")
    SimpleDocTemplate(buffer,pagesize=(595,842),rightMargin=42,leftMargin=42,topMargin=36,bottomMargin=40,title=manifest["title"],author="TBDY / offline",invariant=1).build(story,onFirstPage=footer,onLaterPages=footer)
    return buffer.getvalue()
