# Column: supervisor sonuç görüntüleyici incelemesine devam

Başlangıç: `65828b932c4368b2794a870e653bb9204b158b0f` / `e7769eb175769e23ed1031e56d84ee26ab7a2cf2`.
Özgün supervisor incelemesi: `COLUMN_QUALIFIED_PRODUCT_SUPERVISOR_REVIEW_2026-10-13(2).md` (orijinali değiştirilmedi).

**Tam gerçek235 ürün kabulü: BLOCKED / VERİLMEDİ.** Bu kapanış yalnız kullanıcı tarafından başlatılabilir, düzenlenebilir referans producer yazılım dilimidir. Eski qualified kanalın hazır sonuç tüketimi yeni hesap gibi sunulmaz. 100/200 mm için iki önceden yayınlanmış varyantın seçim testi gerçek kullanıcı düzenlemesi kanıtı değildir; eski kayıtlar bu sınırlamayla korunur.

## Gerçek kullanıcı yolu

`python tools/start_column_product.py` -> aynı çalışma ekranında **REFERANS / DEMO - N/M + sargı/kesme hesabı** seç -> açık girdiyi düzenle -> **Hesapla** -> yeni Python owner değerlendirmeleri -> typed sonuç -> ekran/PDF/JSON.

Standart launcher hiçbir qualified artifact yayınlamaz, test modülü import etmez, native lifecycle çalıştırmaz. Gerekli producer/consumer artık sadece test fixture'ında veya uygulanmamış host tarifinde kalmaz. `reference-owners` application işlemi standart `make_server` tarafından bağlanmıştır; kanalın boş olması bu referans hesabını engellemez. Eski `reference` PMM adayı yolu korunur.

`column_reference_producer.calculate_reference_owners` her çağrıda:

1. Tam bağlam/kaynak/birim/alan şemasını ve sonlu değerleri doğrular; eksik girdide default/fallback yoktur.
2. Mevcut `column_reference_workspace.calculate_reference` üzerinden **özgün `evaluate_column_design`** owner'ını çalıştırır. Minimum dışmerkezlik/narinlik kapanışları, mevcut PMM radyal kapasite ve donatı **DESIGN_CANDIDATE_ONLY** sonucu yeniden üretilir.
3. Açık ve ayrı Ash/Asw, etkin derinlik, fywd, aralık ve sayısal örnek Vc/Ve değerleriyle **özgün `evaluate_column_transverse_confinement`** owner'ını çalıştırır. Hiçbir mühendislik formülü yeniden uygulanmaz.
4. Kanonik `ENGINE_SELECTED_REBAR` üretmez veya PMM adayını ona dönüştürmez: enine owner'a **selected_rebar=None** gider. Bağımlı TS500/HD çap-aralık kontrolleri ve özel kanca geometrisi engine BLOCKED olarak korunur.

HIGH, konsol değil, DIR2/DIR3 eşleme, Vc/Ve bu örneğin açık sayısal kabulleridir. API DTO'sunun `qualified_vc_kn` / `p7_ve_kn` alanlarına taşınmaları native qualification/P7/Vc authority edinildiği anlamına gelmez. Model fingerprint, evidence epoch ve design result ref **None**; B5/B6 **None**. Ekran/rapor **NUMERICAL_REFERENCE_ONLY**, engineering_complete=False, real_235_design_ready=False kimliğini taşır.

Örnek veri: açık b=500, h=800 mm ve mevcut referans PMM girdileri; mevcut enine regresyondaki Asw=200 mm², d=450 mm, fywd=365 MPa, Vc=100 kN, Ve=200 kN. Kesit adından boyut/atalet, endpoint sırasından bottom/top veya ham modlardan governing yük oluşturulmadı.

## Artık gerçek düzenleme ile doğrulanan davranış

Aynı workspace ve aynı `reference-owners` bağlamında s=100 mm -> **alanı 200 mm yap** -> eski sonuç/indirme geçersiz -> Hesapla -> iki yeni owner çağrısı -> **Vr 428.5 -> 264.25 kN** (iki yön için aynı açık örnek değerleri). Bağımsız kapalı form yalnız testte bulunur: 100+(200/s)*365*450/1000. Ürün kodunda yeni Vw/Vr formülü yoktur.

Ayrıca referans Ve=300 kN düzenlemesi gerçek **FAIL** (300>264.25) üretir; boş aralık dispatch edilmez. N/malzeme değişimi yeni typed PMM değerlendirmesi ve değişmiş Vr üretir. Kanonik donatı/kanca bağımlılıkları gerçek BLOCKED kalır. `235-product` bağlamına geçiş referans sonucunu temizler; 235 alanları boş ve bütün tam tasarım bağımlılıkları açık kalır.

Backend olayları `REFERENCE_OWNER_ENTERED`, `REFERENCE_OWNER_RETURNED`, `REFERENCE_PRODUCER_RETURNED` ile aynı input SHA/revizyon/result ID'yi bağlar. Tarayıcı testi normal boş kanallı sunucuda gerçek HTTP, alan düzenleme, üç yeniden hesap, stale/error ve PDF/HTML/JSON indirmeleri kullanır. Ayrı test **teslim edilen launcher subprocess'ini** başlatır; host/channel injection yoktur. Başlatma isteğe bağlı `--audit-file <repo-dışında-yeni-dosya>` kabul eder; mevcut kayıtlar overwrite edilmez.

Eski qualified bağlamda düğme **Sonucu doğrula ve göster** olarak adlandırılır; bu davranışın tasarım yeniden hesabı olmadığı açıkça söylenir. Bu düğme B5/B6 kaynağı veya authority üretmez.

## Gerçek235 için ayrı acquisition / proje gate'i

Önceki `COLUMN_PRODUCT_QUALIFIED_HANDOFF_2026-10-13.md` veri-owner-kanıt tablosu yeniden kullanılacaktır. Bu belge hiçbir canlı işleme yetki vermez.

| Gereken veri / karar | Eldeki gerçek kapsam | Tam hesabın owner gereği ve ayrı kapanış |
|---|---|---|
| Current-source geometry / topology | Column_80x80 ataması; I22/I33=0.03413333333333332 m⁴. Açık b/h, yerel eksenler, offsets, uç bağlantı/beam restraint yok. | Kaynak bağlı strict topology ve düzenleyici ln/k/end-restraint kanıtı. ABI6 orijinal GetPoints paketi ayrı review/izinle yalnız iki ismi okuyabilir; bottom/top, boyut veya analysis-joint eşliği kanıtlamaz. |
| Current material / cage | Onaylı güncel fcd/fyd/fywd, agrega, ductility/cantilever/short-column, gerçek Ash/Asw/kanca tasarımı yok. | Proje review girdileri mevcut typed basis/cage owner'larına gönderilmeli; kullanıcı beyanı/native olgu ve kanonik selected rebar ayrı kalmalı. |
| Current analysis force lineage | Tarihsel FC09 modal kayıtları güncel adayın tasarım N/M/V sonucu değildir. | Özgün B4B/B5 source/input/result/units continuity gerekir. Mevcut yetkili artifact bulunamazsa controlled analysis **ayrı yetki** gerektirir; bu worker çalıştırmaz. |
| Current design lineage / selection | Original qualified 235 B6/kanonik longitudinal selection yok. | Geçerli B6/combo/rebar/catalog sürekliliği ve canonical FND2/A23/selection kararı. Gerekirse controlled design **ayrı yetki** gerektirir; JSON veya demo issuer yerine geçmez. |
| TS500 kararlılık / M6-B | Yatay modal E'nin mevcut tasarım kararlılık işlemine kaynak-yetkili taşınma yasası açık. | Proje/source-authorized modal stability-action kararının kapanışı; lokal satır adı/pozitif amplitüdden türetilmez. |
| Final shear / transverse readiness | Gerçek235 P7/Vc/end selector/effective depth/final cage bağımlılıkları açık. | Original B5/B6 ve selected geometry ile exact P7/Vc bound owner'ları + ayrı Ash/Asw/kanca kanıtı; referans sonucu kullanılamaz. |

**Next exact causal edge:** Bu referans producer yazılım dilimini ayrı değerlendirmek; gerçek235 için yukarıdaki current-source topology/material/analysis-design artifact ve M6-B proje kararını yetkili kaynakta edinmek. Offline reference başarısı tam gerçek235 hesabını kapatmaz. Yeni ETABS, getter, RunAnalysis/StartDesign, selection/database veya model değişimi yetkisi verilmedi.

WORKER_ETABS=NO; LIVE_GETPOINTS=NOT_EXECUTED/NOT_AUTHORIZED; NEW_NATIVE_GETTERS=0; 172_MATRIX_SCAN=NOT_STARTED; RESULT_CAPTURE=NO; FC09_PRODUCTION_GATE=UNCHANGED; GLOBAL_DELTA=NOT_PROVEN; M6_B=OPEN; R2_RERUN_READY=NO.
