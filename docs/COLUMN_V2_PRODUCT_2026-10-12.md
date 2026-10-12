# Column V2 - çalışan referans hesabı ve ayrı 235 kanıt bağlamı

V1'in pasif kanıt projeksiyonu korunmuştur. Yeni ürün, açık referans girdilerini
application sınırında mevcut `evaluate_column_design` motoruna bağlar. `Hesapla`
mevcut Python motorunu gerçekten çalıştırır; HTML/JavaScript hesap formülü içermez.
Bu bir REFERANS / DEMO hesabıdır; ETABS gözlemi veya B-BLOK üretim hesabı değildir.

## Yerel başlatma

Python 3.12 veya daha yeni sürüm. PDF için Windows Arial veya Linux DejaVu Sans
fontları gerekir. İlk kurulum: `python -m pip install -r requirements-column-v2.txt`.
Depoların tamamı gereklidir; üretim kodu test modülü import etmez.

Tek başlatma komutu (repo kökünden):

```powershell
python tools/serve_column_v2.py
```

Tarayıcıda `http://127.0.0.1:8765` açılır. İnternet, COM veya ETABS bağlantısı
gerekmez. `--port` isteğe bağlıdır. Kabul edilmiş pasif V1 arşivi, isteğe bağlı
`--evidence-dir <mevcut-artifact-klasörü>` ile teknik kanıt bağlantısına eklenir.
Bu arşiv sayısal referans hesabının ön koşulu değildir.

## Tam referans girdisi ve bağımsız beklenti

Girdiler `ReferenceColumnInput` ile typed doğrulanır. Başlangıç: 500 x 800 mm
**açık örnek** kesit; ln=3000 mm, k2=k3=1, ötelenmesi önlenmiş referans sistem,
işaretli moment oranları 0; fck=35 MPa, fcd=23.333333333333332 MPa,
fyd=434.7826086956522 MPa; Nd=1000 kN, M2=-10 kN.m, M3=20 kN.m;
örtü=40 mm, yerleşim etriyesi=10 mm, agrega=25 mm; çap kataloğu 14/20/25 mm.
Bu geometri kesit adından türetilmez. Malzeme tasarım değerleri açık girdilerdir;
yeni bir güvenlik katsayısı formülü uygulanmaz.

REFERENCE_ULS = 1.0 x REFERENCE_D; iki referans uçta aynı açık kuvvet/momentler.
Referans uçlar B-BLOK uçları değildir. ln/k/sway/moment oranları yalnız referans
kabulleridir; kuvvetlerden veya ham modal tablolardan üretilmez.

Mevcut `test_vs6_minimum_eccentricity.py` bağımsız beklentisi: 500/800 mm kesitte
emin(M3)=30 mm, emin(M2)=39 mm; işaretli düşük momentler -39/+30 kN.m olur.
Mevcut `test_vs6_slenderness.py` beklentisi: h=800, ln=3000, k=1 için i=240 mm,
lambda=12.5, sınır=34. Genişlik 500 -> 800 mm değişikliğiyle M3 lambda 20 -> 12.5,
M3 minimum moment 30 -> 39 kN.m. Bu sayılar UI/backend/PDF akışında çalıştırılır.
Kapasite/adayı oranı mevcut şekil değiştirme uyumu ve radyal kapasite sonucudur;
minimum moment veya narinlik limit oranı PMM kapasitesi olarak sunulmaz.

## Hesap kapsamı ve otorite

Çalışan birleşik yol: lineer referans talep üretimi, TS500 6.3.10 minimum
dışmerkezlik, TS500 7.6 narinlik ve legacy VS6 boyuna donatı adayı/kapasite denemesi.
36 yön ve 1000 N mevcut çözüm toleransı korunur. Motorun sonuç statüsü ve typed
çıktıları yeniden karar verilmeden projekte edilir. Aday geometrisinin gerçek
bar koordinatları çizilir; nihai/as-built donatı olduğu ileri sürülmez.

İncelenen diğer yollar: canonical `column_longitudinal_rebar`,
`column_transverse_confinement`, dual-code eksenel kontrol, mevcut kesme ve
application composer yolları. Bunlar ek düzenleyici uygulanabilirlik, sonuç
kaynağı veya detaylandırma otoritesi gerektirir. Bu ilk tamamlanmış yol bunları
hesaplamaz. Nihai donatı, sargı/etriye uygunluğu, kesme, eksenel dual-code programı,
deprem yük kapsamı ve proje onayı açıkça kapsam dışıdır. Narinlik büyütme/ikinci
mertebe gerektirirse sonuç BLOCKED/ek hesap olarak gösterilir; hesaplanmış FAIL
yerine geçirilmez. Üretim evidence promotion koşulları değiştirilmemiştir.

## Durum ve rapor sözleşmesi

Girdi veya bağlam değişikliği hem DOM sonucunu hem server-side typed snapshot'ı
silerek revizyonu artırır. Eski revizyon/sonuç kimliğine rapor verilmez; hesap
sürerken girdi değişirse dönen eski sonuç reddedilir. Geçersiz/eksik girdi hiçbir
varsayılanla doldurulmaz. Kaynak/birim/bağlam anahtarları ve desteklenen fck tablosu
korunur. UI yalnız transport ve çizim gösterimi yapar. JSON ve PDF aynı
`ReferenceCalculation` typed snapshot'ından üretilir. Kullanıcı değişiklikleri
`changed_fields` ile referans kaynağından ayrı izlenir. PDF içeriğe göre bölünür.

B-BLOK/235: SHA-pinned kabul edilmiş ABI4/ABI5/ABI6 adoption dosyaları okunur.
`Column_80x80`, I22/I33=0.03413333333333332 m4, aday61FA ve tarihselFC09 ayrı
kaynaklardır. Girdi ve tasarım hesabı eksik; `calculations=[]`. Demo boyut,
malzeme, kuvvet, donatı veya sonuçları aktarılmaz. Ölçülü çizim yapılmaz. 235'in
kanıt PDF/JSON kimliği referans raporundan ayrıdır; V1 projeksiyonu pasif kalır.

## Ürün kabul kanıtı

Gerçek Chromium 153.0.8010.0, localhost HTTP adaptörü ve Python backend birlikte
çalıştırıldı: başlangıç hesabı, 500 -> 800 mm girdi değişikliği/stale/recalc,
235'e geçiş/sonucun silinmesi, PDF/JSON indirme ve ekran-JSON eşitliği.
Ayrı temiz venv, yalnız `requirements-column-v2.txt` bağımlılıklarıyla çalışır.
Backend ENGINE_ENTERED/ENGINE_RETURNED olayları tam kaynak kodu hash'leri,
girdi/sonuç kimlikleri ve revizyonları kaydeder. Native getter sayısı sıfır.
UI etkileşim JSON'u, backend JSONL'i, iki bağlamın gerçek PDF/JSON'u repo dışında
korunur. Tam private-evidence test ve mimari sonuçları ayrı offline receipt'e
kaydedilir; kanıt arşivi doğrulaması sayısal regresyondan ayrıdır.

FC09_PRODUCTION_GATE=UNCHANGED; WORKER_ETABS=NO; LIVE_GETPOINTS=NOT_AUTHORIZED;
NEW_NATIVE_GETTERS=0; MATRIX_SCAN=NOT_STARTED; RESULT_CAPTURE=NO;
GLOBAL_DELTA=NOT_PROVEN; M6_B=OPEN; R2_RERUN_READY=NO.

Sonraki adım: çalışan ürün ve gerçek hesap raporu için supervisor ürün incelemesi.
Canlı getter veya yeni mühendislik otoritesi bu teslimle yetkilendirilmez.
