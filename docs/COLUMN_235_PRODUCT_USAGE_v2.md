# Kolon 235 — çalıştırma ve hesap kapsamı

Paket dizininde Python 3.12 veya üstüyle:

```sh
python tools/start_column_product.py
```

Komutun gösterdiği `http://127.0.0.1:8765` adresini açın. İlk kurulumda internet erişimi gerekir. Mevcut başlatıcı reportlab 4.4.9, PyYAML 6.0.2 (saf Python) ve jsonschema 4.25.1 pinlerini doğrular. YAML veya `.env` dosyası doldurmanız gerekmez. Kullanılan port doluysa mevcut süreç korunur; başka port için `--port 8766` kullanılabilir. Windows çalıştırması bu teslimde doğrulanmış sayılmaz.

## Önce örneği çözün

1. Sayfa açılınca **Örneği yükle ve çöz** düğmesine basın. JSON hazırlamaya veya grupları tek tek review etmeye gerek yok.
2. Sağ tarafta **Eksenel basınç** ve **İki eksenli eğilme / PMM** sonucu görünür. Örnekte Nd=1200 kN, eksenel sınır 13440 kN ve PMM kullanım oranı yaklaşık %10,77'dir.
3. Yük, kesit veya donatıyı değiştirip **Hesapla** deyin. Örneğin J/M2'yi 3000 kN·m yaparsanız PMM uygunsuz olur. Sonuçtan PDF/JSON/HTML indirebilirsiniz.

Örnek, açıkça **sentetik** olarak işaretlenir. Kayıttaki açıklama uygulamanın örneği olduğunu belirtir; gerçek kişi incelemesi, proje belgesi veya native analiz yetkisi üretilmez.

Elinizdeki sentetik JSON için: **JSON yükle → Bu JSON’u örnek olarak çöz**. İçe alma tek başına otomatik inceleme veya hesap yapmaz. Bu ikinci düğme, dosyayı sentetik kapsamda kullanmayı açıkça seçmenizdir. Kaynak/kolon/birim ve eski sonuç korumaları korunur.

Kendi girdileriniz için **235 taslağımı aç** düğmesine basın. Örneğin yükleri ve donatısı bu taslağa taşınmaz. Gerekli sayıları girin; **Girdilerin beyanı** alanında adınızı ve girdi kaynağını yazıp kutuyu işaretleyin. **Hesapla**, tamamlanan grupları mevcut inceleme yolundan tek işlemde kaydeder. Eksik isteğe bağlı gruplar diğer hesabı durdurmaz. İsterseniz grupları ayrı kaydetme yolu da ayrıntıda durur.

Ana ekranda iki kesit kontrolü gösterilir. Narinlik, sargı, diğer proje kontrolleri ve teknik kaynak kayıtları açılır ayrıntılardadır. **Diğer hesaplar ve kanıtlar** menüsündeki kabul edilmiş kanıt ekranı bir hesap ekranı değildir.

## Gerçek kullanıcı taslağı

`B-BLOK / 235 çalışma` bağlamını seçin. Ekrandaki kaynak bağlı taslak ve `Column_235_User_Draft_v2_2026-10-17.json`, aynı bilinen beyanları içerir:

- 80 × 80 cm kesit; 445 cm net boy. Kattan kata 515 cm ve kiriş 70 cm bilgisi notta korunur; net boydan kiriş tekrar düşülmez.
- Yerel 2, Global X'e paralel. Pozitif işaret ve yerel 3'ün global yönü bilinmiyor.
- Radye alt mesnet; üstte dört yönde kiriş ve döşeme. Bodrumda X/Y perdeleri ve sınırlı ötelenme beyanı.
- Beton C35/45 ve boyuna çelik S500. Tasarım dayanımları veya enine çelik sınıfı adlardan doldurulmaz.

Taslakta kişi, belge, tarih veya review kaydı üretilmez. k, ötelenme sınıfı, kuvvetler, cover ve donatı düzeni boştur. Başlangıç taslağının hesaplanması bir tasarım sonucu üretmez.

## Beyan esaslı kesit kontrolleri

Girdiyi tamamlayın; ilgili grup için doğru kişi, referans ve kökenle inceleme kaydı oluşturun. Bu kayıt kullanıcı beyanıdır; doğrulanmış mühendis imzası veya native gözlem değildir.

| Hesap | Gereken bağımsız review grupları | Sonuç kapsamı |
| --- | --- | --- |
| Minimum dışmerkezlik | Kesit / yerel eksenler | Mevcut TS500 `emin` owner'ı |
| Koşullu narinlik | Kesit + ln/k/ötelenme sınıfı; gerekiyorsa işaretli oran | Mevcut narinlik kararı; whole-system kabulü değildir |
| TS500 eksenel basınç sınırı | Kesit + beton fck/fcd + beyan edilen durumlar | TS500 Nd; TBDY Ndm yerine kullanılmaz |
| Kullanıcı donatılı PMM | Önceki girdiler + boyuna fyd + açık çevre yerleşimi | Mevcut şekil değiştirme uyumu, 72 yönlü zarf ve radyal owner |
| Saf enine alt kontroller | Kesit + beton + enine çelik + cage/aralıklar + fiziksel enine boyutlar + uygulanabilirlik + durumlar | Mevcut enine owner'ın bağımsız alt kontrolleri; canonical seçim isteyen alt kontroller engelli kalabilir |

PMM yerleşimi, her iki yüzde köşeler dahil adet, çap, net örtü ve etriye çapıyla mevcut dikdörtgen çevre yerleşimi owner'ından üretilir. Toplam adet, üretilen bar koordinatlarıyla eşleşmelidir. Yalnız adet ve çap yeterli değildir. Desteklenen yüz adetleri 2–100'dür. Farklı bar düzenleri bu girdinin kapsamına girmez.

N-M2-M3 için açık eşzamanlılık ve işaret beyanı gerekir. İki I/J satırı aynı belirtilen case/step içindeki ayrı durumlardır. Her satırın istasyonu ve kaynak referansı korunur. Bağımsız envelope maksimumları eşzamanlı kuvvetler değildir. Yöneten sonuç yalnız girilen durum kümesine aittir. I/J etiketinden fiziksel alt/üst türetilmez.

PMM, girilen momentlerin kesit kapasitesini karşılaştırır. Girilen momentlere minimum dışmerkezlik veya ikinci mertebe düzeltmesi uygulanmış olduğu varsayılmaz. Kaynak bağlı canonical talep yolu bu işlemleri kendi mevcut owner'larıyla ayrıca yapar.

Beton, boyuna çelik, enine çelik ve agrega ayrı incelenir. Bir grubun eksikliği diğerinin kaydını engellemez. Tam `ReviewedColumnDesignBasis` dört temel tamamlanınca kurulur. Sayısal değişiklik kendi incelemesini ve bağımlı sonuçları geçersizleştirir. Kesit/cage değişikliği bunlara bağlı donatı incelemelerini de geçersizleştirir.

235 ekranında cm, kN, MPa ve kN·m kullanılır. JSON girdi sözleşmesindeki mm/m ve kuvvet birimleri korunur. İncelenmiş bir değerin ekranda yeniden okunması, ondalık dönüşüm gürültüsü nedeniyle değerini veya inceleme hash'ini değiştirmez. Özgün Global/m koordinatları dönüşmez.

## Sentetik public akış

`Column_235_Synthetic_Public_Inputs_v2.json` yalnız açık test verisidir; gerçek 235 kuvvetlerini içermez. Ekrandaki paket içe alma yolunu kullanın ve ilgili grupları `SYNTHETIC_TEST` kökeniyle inceleyin. Dosyada hazır review bulunmaz. Geçerli ve uygunsuz kuvvet/aralık değişiklikleri gerçek owner sonuçlarını değiştirir.

235 → referans → 235 geçişi mevcut oturumdaki taslağı korur. Önceki hesap sonucu geri getirilmez; tekrar Hesapla gerekir. Oturum/sunucu kapanmadan önce girdi paketini dışa aktarın. Yeni bir kalıcı veri tabanı eklenmemiştir.

v1 paketler açık v2 geçişinden geçer. Kaynak/kolon/dönem/birimler doğrulanır; eski review kayıtları taşınmaz. Yeni gruplar ve anlamlar yeniden incelenir. Yanlış kaynak veya dönem içe aktarımı sonucu ve çizimi geçersizleştirir.

## Nitelikli canonical sonuçların uygulama girişi

Normal başlatıcının nitelikli sonuç kataloğu boştur. HTTP/JSON üzerinden issuer, native lineage veya tasarım yetkisi yüklenemez.

Mevcut uygulama host'u, gerçek public `execute_project(...)` çıktısı olan özgün `ProjectExecutionArtifact` nesnesini bağımsız beklenen `QualifiedColumnScope` ile `QualifiedColumnChannel.publish(...)` üzerinden yayımlar. `make_server(..., qualified_channel=channel)` aynı kanalın ürün girişidir. İstemci yalnız katalogdaki handle ve exact scope seçer. Kaynak, birim, dönem, B5/B6, FND2 nesne sürekliliği ve artifact fingerprint'i yeniden doğrulanır.

Ürün, 14 kart için mevcut typed owner çıktısını tüketir. Topoloji, kararlılık ve yerel ötelenme gibi önceden yalnız ara adımda kalan owner nesneleri, FND2'nin dondurulmuş girdi değerinin dışında rapor amaçlı tutulur. Eksik veya engelli bir kardeş kolon, diğer kolonun seçimini veya readiness kararını devralmaz. Nitelikli veri yoksa kartın eksik typed girdisi/yetkisi görünür kalır.

Bu giriş yeni native acquisition açmaz. Teslimdeki offline test taşıması kullanıcı çalışma yolu veya gerçek 235 kanıtı olarak sunulmaz.

## A35 detaylandırma sözleşmesi

`materialize_selected_column_longitudinal_detailing(selected_rebar, reviewed_evidence=...)`, özgün canonical seçim üzerinde altı bağımsız hükmü değerlendirir. Eksik kanıt `UNRESOLVED`; yeterli uygunsuz kanıt `FAIL`; kaynak ve tam popülasyonla kanıtlanan yokluk `NOT_APPLICABLE` üretir. Başarısız hüküm `DETAILING_PROVEN` olamaz.

`ReviewedColumnDetailingEvidence`, kolon/seçim/model/dönem/material context/B6 result ve lineage kimliklerini, özgün mevzuat SHA'larını, desteklenen uygulanabilirliği, inceleyen kişi/tarihi/referansı ve facts hash'ini bağlar. Kullanılan boyuna fyd, özgün seçimin typed material context'iyle eşleşir. Hiçbir inceleme kaydı otomatik üretilmez.

| Sonuç | Factual girdi ve uygulama | Özgün kaynak |
| --- | --- | --- |
| Bindirme bölgesi | Tam lap popülasyonu; bar kimlikleri, başlangıç/bitiş, serbest boy, aralık/çap/adet/gap, bond facts | TBDY 7.3.3.1; TS500 9.2.2, 9.2.7(a) |
| Bindirme kesitindeki rho | Aynı istasyondaki bütün ek barları; mevcut gerçek bar alanı ve Ac; yüzde 6 sınırı | TBDY 7.3.2.2; TS500 7.4.1 |
| Kenetlenme | Her seçilmiş barın iki ucu; sağlanan boy; fyd/fctd, döküm konumu, örtü/aralık, bitiş/kanca | TS500 9.1.2(a); TBDY 7.3.3.2 |
| Kesit geçişi | Değişim ve üst kat uygulanabilirliği; offset/rise; bend deneyi/çapı; gerekiyorsa son kenetlenme ve karşı kiriş/kıvrım | TBDY 7.3.3.2; TS500 9.3.1(b), 9.4 |
| Mekanik/kaynaklı ek | Tam ek popülasyonu; gerçek komşu bar koordinatları; boyuna şaşırtma; akma dayanımı, deney sonuçları ve rapor/metalurji/TS708 uygunluğu | TBDY 7.3.3.3; TS500 9.2.3–4 |
| Süreklilik/köşeler | Tam bar/köşe/bağlı tutma popülasyonu, seçilmiş gerçek bar koordinatlarından aralık alt sınırı, kapsanan yükseklik ve enine donatı geometrisi | TS500 7.4.1; TBDY 7.3.3.2 |

Desteklenen A35 kapsamı, yüksek süneklik hükümleri uygulanmış dikdörtgen, eş çaplı, demetsiz nervürlü barlardır. Bond hesabı 40 mm'ye kadar TS500 düz ve azaltılmamış kenetlenmedir; farklı/demet barlar veya başka uygulanabilirlik otomatik uygun sayılamaz. Mekanik ve kaynaklı ek deneyleri açık kaynak raporlarını gerektirir.

A35, canonical seçimin ardından ayrı public materializer ile offline değerlendirilebilir. Mevcut public `execute_project` / `execute_column_domain` / longitudinal composer girişlerinde isteğe bağlı `reviewed_detailing_by_component` / `reviewed_detailing_evidence` taşınır; bu map mevcut seçimin exact kimliklerine bağlı olmalıdır. Salt seçim yapılmış olması detaylandırma veya bütün kolon kabulü değildir.

## Rapor kimliği

Hesaplanan deterministik içerik ve koşu zarfı ayrıdır. UI teknik paneli, JSON, HTML ve PDF aynı `run_envelope` değerini taşır: workspace, hesap revizyonu, result/input kimliği, scope, çalışan kod manifestinin hash'i ve runtime profile. `evidence_epoch` workspace revizyonu değildir. Git HEAD yerine ölçülmüş kod manifesti kullanılır; HEAD uydurulmaz. Kod dosyası süreç çalışırken değişirse hesap/export için yeniden başlatma gerekir. Eski revizyon veya yanlış result_id ile export reddedilir.

Gerçek 235'in güncel kuvvetleri, yerleşimi, enine çeliği ve gerekli proje kararları hâlâ dış girdidir. Global Δ NOT_PROVEN, M6-B OPEN ve R2 hazır değil durumu bu ürün teslimiyle kapanmaz.
