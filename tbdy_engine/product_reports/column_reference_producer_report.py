"""Projection of editable reference owner results; no second calculation."""
from dataclasses import asdict, fields
from hashlib import sha256
from html import escape

from tbdy_engine.application.column_reference_producer import ReferenceCageInput, ReferenceOwnerCalculation
from tbdy_engine.application.column_reference_workspace import canonical_bytes
from tbdy_engine.product_reports.column_v2_report import FIELDS, reference_manifest, render_manifest_pdf, fmt

CAGE_LABELS = (
    ("gross_area_ac_mm2", "Açık brüt alan Ac", "mm²"),
    ("confined_core_area_ack_mm2", "Açık çekirdek alanı Ack", "mm²"),
    ("fywk_mpa", "Enine çelik fywk", "MPa"), ("fywd_mpa", "Enine çelik fywd", "MPa"),
    ("confinement_spacing_mm", "Sargı aralığı", "mm"), ("middle_spacing_mm", "Orta bölge aralığı", "mm"),
    ("shear_spacing_mm", "Kesme hesabı aralığı s", "mm"),
    ("confinement_region_length_mm", "Sağlanan sargı bölgesi boyu", "mm"),
    ("restrained_bar_spacing_mm", "Tutulan boyuna çubuk aralığı", "mm"),
    ("bk_dir2_mm", "DIR2 çekirdek genişliği bk", "mm"), ("bk_dir3_mm", "DIR3 çekirdek genişliği bk", "mm"),
    ("ash_dir2_mm2", "DIR2 bağımsız Ash", "mm²"), ("ash_dir3_mm2", "DIR3 bağımsız Ash", "mm²"),
    ("asw_dir2_mm2", "DIR2 bağımsız Asw", "mm²"), ("asw_dir3_mm2", "DIR3 bağımsız Asw", "mm²"),
    ("leg_spacing_dir2_mm", "DIR2 etriye kolu aralığı", "mm"), ("leg_spacing_dir3_mm", "DIR3 etriye kolu aralığı", "mm"),
    ("effective_depth_dir2_mm", "DIR2 açık etkin derinlik d", "mm"), ("effective_depth_dir3_mm", "DIR3 açık etkin derinlik d", "mm"),
    ("reference_vc_dir2_kn", "DIR2 referans Vc varsayımı", "kN"), ("reference_vc_dir3_kn", "DIR3 referans Vc varsayımı", "kN"),
    ("reference_ve_dir2_kn", "DIR2 referans Ve varsayımı", "kN"), ("reference_ve_dir3_kn", "DIR3 referans Ve varsayımı", "kN"),
)
OWNER_FIELDS = FIELDS + tuple((key, label, unit, "Referans sargı / kesme") for key, label, unit in CAGE_LABELS)
assert {x[0] for x in CAGE_LABELS} == {f.name for f in fields(ReferenceCageInput)}


def owner_reference_manifest(calculation: ReferenceOwnerCalculation):
    m = reference_manifest(calculation.longitudinal)
    m.update(schema="column.editable.reference.owner-calculation.v1",
             context=calculation.inputs.bundle()["context"], source=calculation.inputs.bundle()["source"],
             title="REFERANS / DEMO - Düzenlenebilir kolon owner hesabı",
             input_bundle=calculation.inputs.bundle(), input_sha256=calculation.input_sha256,
             input_fields=OWNER_FIELDS, invoked_owners=list(calculation.invoked_owners),
             source_authority="NUMERICAL_REFERENCE_ONLY", B5=None, B6=None,
             real_235_design_ready=False, engineering_complete=False,
             transverse_complete=calculation.transverse.complete,
             transverse_blockers=list(calculation.transverse.blockers),
             typed_transverse_input=asdict(calculation.transverse_input),
             typed_transverse_output={"checks": [c.as_dict() for c in calculation.transverse.checks],
                "shear_vr_by_direction_kn": list(calculation.transverse.shear_vr_by_direction_kn),
                "required_confinement_region_length_mm": calculation.transverse.required_confinement_region_length_mm})
    default = calculation.inputs.example().bundle()["values"]
    m["changed_fields"] = [k for k, v in m["input_bundle"]["values"].items() if v != default[k]]
    m["scope"] = [s for s in m["scope"] if not s.startswith("Nihai donatı")]
    m["scope"] += [
        "Bu işlem her Hesapla çağrısında mevcut Python owner'larını yeniden çalıştırır; hazır varyant tüketmez.",
        "HIGH, konsol değil ve açık DIR2/DIR3 eşleme yalnız bu sayısal referansın kabulleridir.",
        "Vc ve Ve açık örnek kabulleridir; gerçek P7/Vc sonucu veya güncel B5/B6 yetkisi değildir.",
        "PMM adayı kanonik seçilmiş donatıya yükseltilmedi. Enine owner'a selected_rebar=None verildi.",
        "Kanonik boyuna çap ve özel kanca geometrisi gereken kontroller BLOCKED kalır. Nihai cage/engineering readiness verilmez.",
        "B-BLOK/235 kaynak/geometry/topology/force/analysis-design lineage ve M6-B kararı açık; bu sonuç oraya taşınmaz.",
    ]
    for c in calculation.transverse.checks:
        titles = {
            "COL_LD_CONFINEMENT_APPLICABILITY": "Sınırlı süneklik dalı / referans kapsamı",
            "COL_HD_TRANSVERSE_MIN_DIAMETER": "Sargı etriyesi asgari çapı",
            "COL_HD_CONFINEMENT_REGION_LENGTH": "Sargı bölgesi boyu",
            "COL_HD_CONFINEMENT_SPACING": "Sargı aralığı / kanonik çap bağımlılığı",
            "COL_HD_CONFINEMENT_ASH_DIR2": "Sargı donatısı Ash / DIR2",
            "COL_HD_CONFINEMENT_ASH_DIR3": "Sargı donatısı Ash / DIR3",
            "COL_HD_TIE_LEG_SPACING_DIR2": "Etriye kolu aralığı / DIR2",
            "COL_HD_TIE_LEG_SPACING_DIR3": "Etriye kolu aralığı / DIR3",
            "COL_HD_MIDDLE_MIN_DIAMETER": "Orta bölge etriye çapı",
            "COL_HD_MIDDLE_SPACING": "Orta bölge etriye aralığı",
            "COL_HD_MIDDLE_TIE_LEG_SPACING_DIR2": "Orta bölge kol aralığı / DIR2",
            "COL_HD_MIDDLE_TIE_LEG_SPACING_DIR3": "Orta bölge kol aralığı / DIR3",
            "COL_SPECIAL_TIE_DETAILING": "Özel deprem etriyesi / kanca geometrisi",
            "COL_TS500_TRANSVERSE_DIAMETER": "TS500 etriye çapı / kanonik çap bağımlılığı",
            "COL_TS500_TRANSVERSE_SPACING": "TS500 etriye aralığı / kanonik çap bağımlılığı",
            "COL_TS500_RESTRAINED_BAR_SPACING": "Tutulan boyuna çubuk aralığı",
            "COL_FINAL_SHEAR_VR_DIR2": "Kesme talebi / Vr dayanımı - DIR2",
            "COL_FINAL_SHEAR_VR_DIR3": "Kesme talebi / Vr dayanımı - DIR3",
        }
        title = titles.get(c.check_id, c.check_id)
        value = c.value if type(c.value) in (float, int) else None
        limit = c.limit if type(c.limit) in (float, int) else None
        trace = f"Owner değer/sınır: {c.value!r} / {c.limit!r}; oran = {c.ratio!r}."
        if "FINAL_SHEAR" in c.check_id:
            direction = next(d for d in calculation.transverse_input.directions if d.direction in c.check_id)
            trace = (f"Örnek Vc={fmt(direction.qualified_vc_kn)} kN; Asw={fmt(direction.provided_asw_mm2)} mm²; "
                     f"s={fmt(calculation.inputs.cage.shear_spacing_mm)} mm; fywd={fmt(calculation.inputs.cage.fywd_mpa)} MPa; "
                     f"d={fmt(direction.effective_depth_mm)} mm. Mevcut owner çıktısı Vr={fmt(c.limit)} kN; "
                     f"referans Ve={fmt(c.value)} kN; Ve/Vr={fmt(c.ratio)}.") if c.limit is not None else trace
        m["checks"].append({"id": c.check_id, "title": title, "status": c.status.value,
            "display_status": {"OK": "UYGUN · REFERANS", "FAIL": "UYGUNSUZ · REFERANS", "BLOCKED": "EKSİK YETKİ / GİRDİ", "OUT_OF_SCOPE": "KAPSAM DIŞI"}.get(c.status.value, c.status.value),
            "value": value, "limit": limit, "unit": c.unit or "-", "ratio": c.ratio,
            "source": c.code_ref, "formula": c.pass_rule or "Owner bağımlılığı / uygulanabilirlik kararı",
            "trace": trace, "reason": " ".join(c.messages), "owner": calculation.invoked_owners[-1]})
    m["checks"] = [c for c in m["checks"] if c["id"].startswith("COL_FINAL_SHEAR")] + [c for c in m["checks"] if not c["id"].startswith("COL_FINAL_SHEAR")]
    m["result_id"] = sha256(canonical_bytes({k:v for k,v in m.items() if k != "result_id"})).hexdigest()
    return m


def render_owner_reference_pdf(calculation):
    return render_manifest_pdf(owner_reference_manifest(calculation), input_fields=OWNER_FIELDS)


def render_owner_reference_html(manifest):
    # Same manifest projection as the screen/PDF; no independent status logic.
    esc = lambda x: escape(str(x))
    sections = "".join(f"<section><h2>{esc(c['title'])}</h2><p>{esc(c['display_status'])} / {esc(c['status'])}</p><p>Değer: {esc(c['value'])}; sınır: {esc(c['limit'])} {esc(c['unit'])}</p><p>{esc(c['source'])}</p><pre>{esc(c['formula'])}</pre><p>{esc(c['trace'])}</p><p>{esc(c['reason'])}</p></section>" for c in manifest["checks"])
    return ("<!doctype html><html lang='tr'><meta charset='UTF-8'><title>Referans owner hesabı</title>"
            "<style>body{max-width:980px;margin:40px auto;font:16px/1.6 system-ui;color:#183c53}pre{white-space:pre-wrap;overflow-wrap:anywhere}section{border-top:1px solid #dbe4eb;padding:16px}svg{max-width:420px}</style>"
            f"<h1>{esc(manifest['title'])}</h1><p>Girdi kaynağı: {esc(manifest['source'])}</p>{manifest['section_svg']}"
            "<h2>Açık girdiler ve birimler</h2><ul>" + "".join(f"<li>{esc(label)}: {esc(manifest['input_bundle']['values'][key])} {esc(unit)}</li>" for key,label,unit,_ in OWNER_FIELDS) + "</ul>"
            + sections + "<h2>Kalan kapsam</h2><ul>" + "".join("<li>"+esc(s)+"</li>" for s in manifest["scope"]) + "</ul>"
            + f"<p>Sonuç kimliği: {esc(manifest['result_id'])}</p><p>Girdi SHA256: {esc(manifest['input_sha256'])}</p></html>")
