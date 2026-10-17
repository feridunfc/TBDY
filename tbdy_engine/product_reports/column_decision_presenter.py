"""Decision and provenance are independent; unknown statuses are never success."""
DECISIONS = {
    'DETAILING_PROVEN':('DETAY KAPSAMI KANITLANDI','success','Yalnız A35 kanıt ve uygulanabilirlik kapsamı.'),
    'DETAILING_FAILED':('DETAY UYGUN DEĞİL','danger','Başarısız detay hükümlerini düzeltin.'),
    'FINAL_DETAILING_REQUIRED':('DETAY KANITI EKSİK','warning','Eksik detay popülasyonlarını tamamlayın.'),
    'OUT_OF_SCOPE':('KAPSAM DIŞI','neutral','Owner tarafından belirtilen kapsamı inceleyin.'),
    'SELECTED':('KANONİK DONATI SEÇİLDİ','neutral','Detaylandırma ve diğer kolon kontrolleri ayrıca değerlendirilir.'),
    'READY_LOCAL_AXIS_SWAY_BINDING':('YEREL ÖTELENME BAĞI TAMAM','neutral','Beyan kapsamını ve alt owner sonuçlarını inceleyin.'),
    'PROVEN_SWAY_PREVENTED_BY_TS500_STABILITY_INDEX':('ÖTELENME ÖNLENMİŞ / KARARLILIK İNDİSİ','success','Yalnız belirtilen kat, yön ve kombinasyon kapsamı.'),
    'APPLIED':('UYGULANDI','neutral','Yalnız belirtilen hesap adımı uygulandı.'),
    'SELECTED_DESIGN_CANDIDATE_ONLY':('DONATI ADAYI BULUNDU','neutral','Nihai donatı veya proje kabulü değildir.'),
    'READY':('OWNER YÜRÜTÜLEBİLİR','neutral','Bu owner kararı tam kolon tasarım kabulü değildir.'),
    'OK':('UYGUN','success','Girilen kapsam için uygunluk sağlandı.'),
    'PASS':('UYGUN','success','Girilen kapsam için uygunluk sağlandı.'),
    'PROVEN':('KANITLANDI','success','Yalnız belirtilen kanıt kapsamı.'),
    'FAIL':('UYGUN DEĞİL','danger','Uygunsuz girdiyi veya tasarımı düzeltin.'),
    'NOT_APPLICABLE':('UYGULANAMAZ','neutral','Kanıtlı uygulanabilirlik kapsamı.'),
    'SLENDERNESS_EFFECTS_NEGLIGIBLE':('NARİNLİK ETKİSİ İHMAL EDİLEBİLİR','success','Beyan edilen ln/k/ötelenme koşulları için.'),
    'MOMENT_MAGNIFICATION_REQUIRED':('MOMENT BÜYÜTME GEREKLİ','warning','Kaynak bağlı ikinci mertebe girdilerini tamamlayın.'),
    'SIGNED_END_MOMENT_RATIO_REQUIRED_FOR_SLENDERNESS_DECISION':('İŞARETLİ MOMENT ORANI GEREKLİ','warning','İlgili eksen için eşzamanlı işaretli M1/M2 sağlayın.'),
    'GENERAL_SECOND_ORDER_ANALYSIS_REQUIRED':('GENEL İKİNCİ MERTEBE GEREKLİ','warning','Genel ikinci mertebe analizini sağlayın.'),
    'CALCULATED_PROJECT_REVIEW':('KOŞULLU HESAPLANDI','neutral','Hesap yapılması uygunluk veya native yetki değildir.'),
    'REVIEWED_PROJECT_DECLARATION':('BEYAN TEMELİ TAMAMLANDI','neutral','Native malzeme eşlemesi ayrıca gerekir.'),
    'PARTIAL':('ALT KONTROLLER HESAPLANDI','warning','Eksik alt kontrol girdilerini tamamlayın.'),
    'BLOCKED':('HESAPLANMADI / EKSİK GİRDİ','warning','Kontrolün eksik girdi ve yetki listesini tamamlayın.'),
    'UNRESOLVED':('ÇÖZÜMLENMEDİ','warning','Kaynak bağlı kanıtı tamamlayın.'),
}


def present_decision(status):
    label,severity,action=DECISIONS.get(status,('TANINMAYAN / ÇÖZÜMLENMEMİŞ DURUM','warning','Ham owner durumunu inceleyin: '+str(status)))
    return {'display_status':label,'severity':severity,'next_action':action,'raw_status':status}


def displayed(value, unit):
    factor,target={'mm':(.1,'cm'),'m':(100.,'cm'),'mm2':(.01,'cm²'),'kN.m':(1.,'kN·m')}.get(unit,(1.,unit))
    return (None if value is None else value*factor if type(value) in {int,float} else value),target
