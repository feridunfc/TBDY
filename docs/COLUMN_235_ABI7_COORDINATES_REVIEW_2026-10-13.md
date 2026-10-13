# 235 — ABI6 adoption ve yalnız iki koordinat için offline inceleme

ABI6 özgün receipt **ACCEPTED / CLOSED_REUSE**: mevcut61FA aday kaynaktaki Frame235,
Point1=955 ve Point2=758. Application pRetVal exactint0; tek target attempt ve tek
callback. Başka GetPoints yapılmayacak. Özgün JSON ve sidecar repo dışında,
değişmemiştir; yalnız [türetilmiş adoption indeksi](COLUMN_235_ABI6_ADOPTION_AND_ABI7_OFFLINE_RECEIPT_2026-10-13.json)
ve [kaynak bağlı hedef](COLUMN_235_ABI7_COORDINATES_TARGET_2026-10-13.json) Git'tedir.
Supervisor52 receipt kontrolü repository test kimliği değildir.

| Gerçek235 kapsamı | Mevcut kanıt | Kalan sınır |
|---|---|---|
| Kesit ataması |235 → Column_80x80, acceptedABI4 |Kesit adından ölçü üretilmez. |
| I22 / I33 |0.03413333333333332m⁴, namedsection acceptedABI5 |Diğer10property NOT_COMPARABLE/NOT_PROVEN; wholemodel eşdeğerliği yok. |
| Uç adları |Native Point1=955 / Point2=758, acceptedABI6 |Alt/üst veya analiz-joint rolü yok. |
| Güncel koordinat |NOT_OBSERVED |Bu offline paket canlı koordinat yetkisi değildir. |
| Geometri / ln / k / offsets / restraints |NOT_PROVEN |İki nokta koordinatı bile bunların tamamını kanıtlamaz. |
| Material / physical cage / B5 / B6 |NOT_PROVEN |FC09 olguları veya referans hesap sonucu güncele taşınmaz. |

## Önerilen kesin çağrı sözleşmesi

Yalnız aşağıdaki iki çağrı; sıra acceptedABI6 native slot sırasıdır, alt/üst sırası değildir:

```python
existing_verified_model.PointObj.GetCoordCartesian(Name="955", CSys="Global")
existing_verified_model.PointObj.GetCoordCartesian(Name="758", CSys="Global")
```

Bu satırlar paket incelemesi içindir; doğrudan çalıştırma komutu değildir. `(Name,"Global")`
CSys'i X slotuna bağlayabilir ve kullanılmaz. Existing repository object_model wrapper'ı
beş native girdiyi açık yerlerine koyar; yeni paket o wrapper'ı değiştirmez.
Kabul edilmiş orijinal generated comtypes wrapper'ı Name/CSys keyword'lerini,
atlanmış X/Y/Z INOUT değerlerini destekler. Replacement wrapper veya positional
fallback yok.

| Sözleşme | Kabul edilmiş orijinal ABI3 gözlemi |
|---|---|
| Owner / table |POINTER(cPointObj), __com_interface__, tek _methods_ declaration |
| Declaring IID |{6674645D-E89A-459F-A446-8DB204577C60} |
| Parametre / flag |Name1, X3, Y3, Z3, CSys17(defaultGlobal), pRetVal10 |
| Tipler |BSTR, POINTER(Float64)×3, BSTR, POINTER(Int32); restypeHRESULT |
| Efektif Python girdisi |positional[], named{Name,CSys}; omittedINOUT[X,Y,Z] |
| Python dönüş sırası |X,Y,Z,pRetVal; list/tuple4outputs |
| Raw metadata SHA |81ca90983b67c9de85c7256c12c6a768ab7e676ae084d8b8de90e386a084730a |
| Raw wrapper SHA |eca6cba1bbb040d61d9f286ac280ffac62dd294cb82cde299b3124ea3af85c9b |
| Backend vtable / methodIID |NOT_OBSERVED_NOT_PROBED |

Her proposed call'dan önce aynı declaration, pointer/pointee/flags/order/IID ve
aynı static descriptor, code/closure/globals/backend prototype/dependency ve bound
owner yeniden eşleşmelidir. Missing/ambiguous/malformed/different metadata STOP;
QueryInterface, casting, alternateattach veya overload yok. Eski snapshot'taki
target_invokedfalse/native_returnNOT_OBSERVED alanları değiştirilmez.

## Birim ve yanıt authority'si

[CSI GetCoordCartesian resmi yöntemi](https://docs.csiamerica.com/help-files/etabs-api-2016/html/694d9bce-0611-9568-a5e0-54263db349e6.htm)
koordinatları Present Units ve belirtilen CSys kapsamında tanımlar; application
zero başarıdır. [GetPresentUnits_2](https://docs.csiamerica.com/help-files/etabs-api-2016/html/9ebec594-b55b-44f4-2958-2109cdcfb9ee.htm)
ile [eLength enum](https://docs.csiamerica.com/help-files/etabs-api-2016/html/78035b1d-0cc5-ff44-33a8-6342d825da8c.htm)
m=6 ilişkisini destekler. Sayfalar2026-10-13'te yeniden okunmuştur; ETABS2016
dokümantasyonu, kabul edilmiş23.2 generated declaration/wrapper ile uyumludur.
Bu proposal'ın kaynak köprüsü ve sürüm sınırı supervisor incelemesine açıktır;
23.2 method belgesi veya canlı koordinat yanıtı gözlendi denmez. Bu nesne geometri
sözleşmesi, global displacement result-layer qualification değildir.

Başarı için üç exact Pythonfloat/finite binary64 ve son exact Pythonint0 gerekir.
String/int/bool koordinat, NaN/Inf, eksik/fazla output, nonzeroapplicationstatus
ve yanlış sıra reddedilir. Container/scalar types, original values ve hem raw hem
typed hash korunur. HRESULT COM transport ayrı kalır, skaler HRESULT gözlenmez.
Native X/Y/Z sırası ve işaretleri korunur; conversion, rounding, axis swap veya
tarihsel reference-value correction yapılmaz. Coordinateunit yalnız değişmeyen
presentlength6/metre context altında geçerlidir.

## Bounded operator transaction — yetki verilmedi

- Existing verified PID2072 ve exact processstartUTC2026-10-09T15:47:08.1780017Z.
  Başka PID/start/instance veya sourceSHA drift STOP; orijinal FC09 gate değişmez.
- Exact pathC:\tmp\B-BLOK_Revised.EDB; current candidateSHA61FA…246621 tam değeri
  target/index/package pins içinde; protected historicalFC09 kimliği ayrı tutulur.
- Runtime Python3.14.0/comtypes1.4.16 ve kabul edilmiş _memberspecSHA değişmez.
  Altı original JSON/sidecar dependency çifti before/after tekrar hash'lenir.
- Python ve PowerShell repo dışındadır. Orijinal ABI6Python helper'ı aynı SHA ile
  salt guard definitions olarak import edilir; __main__/GetPoints çalıştırılmaz.
- Final package pins exact new HEAD/TREE, Python/operator/prepare/helper SHA ve
  scoped LF target bytes içerir. Git autocrlftrue checkout testi offline yapılır;
  gerçek Windows target SHA/CLEAN kontrolleri operatör preflight'ında zorunludur.
  Hash mismatch'te normalization/repair yok; eski üç LF kuralı korunmuştur.
- Tek verified STA callback; toplam max2targetattempt; exact order955sonra758;
  callback timeout30s ve her target öncesi/sonrası monotonic deadline guard.
  İlk error/mismatch/timeout STOP; ikinci target veya automaticretry yok. Native
  call'ın iptal edildiği varsayılmaz; timeout sonrası tekrar denenmez.
- Loadedpath/session/units/lock before/after independently reread by existing
  session owner; callback içinde nestedgatewayidentityread yok. Callback içi
  guard yalnız sourcefileSHA'dır. Before/after kayıtlar sınır gözlemleridir.
- New exclusive receipt ve sidecar repo dışında tutulur; hata/partialnative
  yanıt, phase markers ve gateway code/operation/details/chainedcause korunur.
  Bir çağrı başarılı diğeriyse başarısızsa paket bütünü qualified değildir.
- SelectionNOT_READ; Results.Setup/DatabaseTables erişimi veya mutation yok.
  RunAnalysis/StartDesign/Save/SetPresentUnits, results/matrices/census yasaktır.

Önerilen operator komutu final dış pakette pinlidir. **ŞİMDİ ÇALIŞTIRILMAZ**;
ayrı supervisor authorization olmadan switch/başarılı offline test yetki vermez:

```powershell
& 'C:\tmp\column_r1_r3m_abi7_operator.ps1' `
  -VerifiedEtabsPid 2072 `
  -CandidateSha256 '61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621' `
  -SupervisorAuthorizedTwoCoordinates
```

**NEXT EXACT CAUSAL EDGE:** ABI6 adoption + ABI7 source/ABI/Python/unit/budget
paketi supervisor incelemesi; yalnız kabulden sonra ayrı canlı authorization
değerlendirilebilir. M6-B project/source kararları ve current B5/B6 lineage ayrı
açıktır. Referans ürün CLOSED_REUSE; yeni UI/demo/PDF turu yapılmadı. PR208
draft/open, merge yetkisi yok.

## Offline doğrulama kapsamı

Son dosya78odaklı PASS; ABI6+ABI7 birlikte141PASS. Önceki523test dosyası değişmedi,
2326önceki test kimliğinin tamamı fresh private koşusunda PASS oldu. O koşunun
başlangıçta yüklenen yeni test düzeneğinde üç hata vardı: Linux'ta sahte Windows
ctypes.HRESULT transport tipinin fixture'da eksik olması. Yalnız yeni offline
test fixture'ı düzeltildi; dış probe veya production code değişmedi. Üç kimlik
son141PASS koşusunda yeniden geçti. Özgün ilk2401PASS/3FAIL log/XML korunur;
tek temiz2404fullrun iddiası yok. Son doğrulama coverage'ı açık partition provenance
ile2404kimliktir; supervisor bağımsız ledger kabulü iddia edilmez.

Fresh exactbase architecture37case:31PASS ve aynı6gerçekFAIL; completeguardsets
eşit, new/expanded0. Protected45hashdrift0. Compile/import/diffPASS; PowerShell
nativeparser burada yoktur, template/command/pin statikauditPASS. ActualWindows
checkout ve canlı coordinate qualification operatör/supervisor gate'inde kalır.

WORKER_ETABS=NO; LIVE_GETPOINTS=EXECUTED_BY_AUTHORIZED_OPERATOR_ONCE;
ONE_CALL_AUTHORIZATION=CONSUMED; LIVE_GETCOORDCARTESIAN=NOT_EXECUTED/NOT_AUTHORIZED;
172_MATRIX_SCAN=NOT_STARTED; RESULT_CAPTURE=NO; FC09_PRODUCTION_GATE=UNCHANGED;
GLOBAL_DELTA=NOT_PROVEN; M6_B=OPEN; R2_RERUN_READY=NO.
