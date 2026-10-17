# Kolon 235 — kabul edilmiş ABI-7 koordinatlarının ürüne benimsenmesi

Kapsam: özgün receipt'in offline doğrulanması, kaynak bağlı türetilmiş kanıt ve mevcut ürün ekranı/raporu. Yeni native getter veya metadata çalıştırılmadı. İki-okuma yetkisi tüketildi. Gerçek 235 tasarım kabulü verilmedi.

## Gözlem ve kaynak ayrımı

| Native slot | PointObj | CSys | X (m) | Y (m) | Z (m) |
| --- | --- | --- | ---: | ---: | ---: |
| Point1 | 955 | Global | 74.0 | 22.3 | -5.15 |
| Point2 | 758 | Global | 74.0 | 22.3 | 0.0 |

Bu sıra özgün ABI-6 GetPoints235 slotlarıdır; fiziksel alt/üst değildir. Her iki özgün ABI-7 dönüşü list(float, float, float, int0), uygulama durum kodu0'dır. COM HRESULT taşıması ayrı kalır; backend vtable/method IID NOT_OBSERVED_NOT_PROBED. Koordinat farkı ln/k, ofset, restraint veya analysis-joint/panel-zone eşlemesine çevrilmedi.

Güncel aday SHA256 `61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621`; tarihsel FC09 SHA256 `FC09E5EEB1E195C7141EB992EC501E0004EA733078997C58E1F84D979F70758F`. Bunlar ayrı authority'lerdir. Kesit ataması Column_80x80 ve I22/I33=0.03413333333333332 m⁴ önceki kabul edilmiş ABI-4/5 kanıtlarından reuse edilir; ölçü veya malzeme adı çıkarılmaz.

Özgün JSON `column-r1-r3m-abi7-coordinates_20261014_083705_600_893204f2c8c947248955ba9265ddcfbc.json`, SHA256 `2e16f45f8aa7347fb49a53cd6fd0d9dfd66c93619705ba9f411e8d6bdf3e6bf1`; özgün sidecar bayt SHA256 `8fef35063195940461627ede28d1535d6be33ab926f10b5bf53a3cde6576ba9f`. Orijinaller Git dışında, değişmeden korunur. Ham response/metadata/wrapper kopyası Git'e eklenmedi. Türetilmiş indeks: `COLUMN_235_ABI7_LIVE_COORDINATES_ADOPTION_2026-10-14.json`.

Capture HEAD `9f426f5b6376b9c6da984270171556d2e3b2c496`, TREE `c557a517d07fa973a8ea5c2aabb3fbb8d65d34fb`; yazılım tabanı main `1440df1b9300f75b1e604204438f5cada9ebd247`, TREE `8c962be58474de12d1aab26b65d177f333e319a0`. Main üzerinde native çağrı yapıldığı ileri sürülmez. Önce/sonra kaynak SHA, session/birim/lock kayıtları eşittir; bu sürekli gözlem veya mevcut Windows sürecine worker erişimi değildir. Fingerprint null/UNAVAILABLE kalır.

## Çalışan ürünün davranışı

Depo kökünden mevcut komut: `python tools/start_column_product.py`. Bu offline localhost çalışma ekranıdır. 235 kanıt bağlamı ve 235 çalışma bağlamı, aynı benimsenmiş Global/m koordinatları gösterir. Kullanıcı tasarım alanları boş kalır; accepted_native_coordinates salt okunur ve istemci değişikliği reddedilir. Referans sonuçları bu pakete aktarılmaz. PDF/JSON, ekranda tüketilen aynı kanıtı ve özgün receipt kimliğini taşır. V1'in pasif tarihsel modal arşivi değişmedi. Yeni pinli adoption JSON için tek dosyalık LF checkout kuralı eklendi; eski dört kural ve diğer dosyaların core.autocrlf davranışı korundu. Bu yalnız byte-pin checkout doğrulamasıdır; bütün Windows ürün çalışma ortamının qualification'ı değildir.

Gerçek235 hesabı için geometri boyutları, düzenleyici ln/k ve applicability, malzeme/tasarım dayanımları, mevcut donatı, kuvvet ve sonuç dönemi ayrıca nitelendirilmelidir. BLOCKED hesaplanmış FAIL değildir. Bu adım boyut çizimini veya tasarım hazır durumunu açmaz.

## Kesit ölçüsü / malzeme için en küçük sonraki kapsam

Makine okunur plan: `COLUMN_235_SECTION_MATERIAL_OFFLINE_PLAN_2026-10-14.json`. Kaynak dosya hash'leri ve kabul edilmiş sekiz metadata method'u korunur. Bu liste GetRectangle, material getter veya GetRebarColumn deklarasyonu içermez.

İlk öneri yalnız mevcut verified PID/STA sahibindeki `model.PropFrame` üzerinde **GetRectangle metadata/wrapper incelemesi**dir. Katalogdaki GetRectangle geometri yolu bir aday kaynak köprüsüdür; mevcut 23.2 aday modelin ABI veya dikdörtgen uygulanabilirlik kanıtı değildir. Python owner, _type_, __com_interface__, MRO/IID, _methods_/_disp_methods_, tek exact declaration ve mevcut wrapper code/closure/type gözlenmelidir. Method native/Python call shape ve çıktı sırası henüz nitelendirilmedi; öneride uydurulmuş argüman veya return tuple yoktur. GetSectProps'ın kabul edilmiş PropFrame IID'si yeni method deklarasyonunun yerine geçmez.

Metadata-only paket ayrıca incelenip yetkilendirilmeden hazırlanmış canlı komut yoktur. Sonra, tam method/wrapper ve dikdörtgen applicability/alan semantiği kanıtlanırsa ayrı tek named section getter önerilebilir. GetRectangle başarıyla materyal kimliği sağlarsa o gerçek ad sonraki material metadata önerisinin hedefini kurar; C35/45 veya kesit-adı formülü kullanılmaz. İlk getter başarısızsa başka şekil/getter fallback'i yapılmaz.

Mevcut typed material owners `get_material_type_from_session` ve `get_isotropic_material_properties_from_session` yeniden yazılmaz. E/G, fcd/fyd/fywk/fywd değildir. Concrete definition için mevcut used_rc_material_population yolu actual generated ABI ve kaynak bağını ayrıca gerektirir. RebarColumn intent, kabul edilmiş mevcut donatı kafesi değildir. `bind_reviewed_column_design_basis` için reviewed concrete/steel/aggregate/action-family ve dönem/fingerprint şartları korunur; missing fingerprint yeni coord receipt ile doldurulmaz.

## Durdurma sınırı

WORKER_ETABS=NO; ADDITIONAL_NATIVE_AUTHORIZATION=NONE; yeni metadata/getter=0; matris taraması başlamadı; result/P2 capture yok. Model, analysis, units, seçim veya database transaction mutasyonu yok. FC09_PRODUCTION_GATE=UNCHANGED; GLOBAL_DELTA=NOT_PROVEN; M6_B=OPEN; R2_RERUN_READY=NO. Yeni merge uygulanmayacak.
