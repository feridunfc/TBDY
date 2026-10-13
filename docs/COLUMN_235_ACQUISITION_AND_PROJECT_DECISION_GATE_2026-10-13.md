# Gerçek235 - mevcut kanıttan ayrı acquisition / proje gate'i

Baz: `43e8afabbb91087030ac30570197cd01761afd07` / `14a35d7e3af6c4f556800d867f89cc6e69dbd00d`.
Yeni supervisor devam incelemesi: **EDITABLE_REFERENCE_SOURCE_SLICE_ACCEPTED / CLOSED_REUSE**. Referans ekranı/raporu yeniden geliştirilmez. **REAL_235_FULL_PRODUCT_NOT_ACCEPTED**; PR208 draft/open/unmerged.

Supervisor24 odaklı testi ve aynı server/workspace üzerinde gerçek HTTP yeniden hesabını bağımsız doğruladı. İki browser/launcher profili testini seçmedi. Worker'ın2326 integrated/ZIP/JUnit ledger'ini ve bütün14sayfa görsel QA'sını bu review yeniden kabul etmedi. Bu kapsamlar birbirine yükseltilmez. Güncel61FA olguları son kabul edilmiş native capture zamanının sınırlı gözlemleridir; bugünkü Windows dosyası/PID worker tarafından yeniden gözlenmedi. İnceleme dosyasının özgün SHA'sı ve alınan PDF SHA'ları [derived cutset](COLUMN_235_CURRENT_SOURCE_AUTHORITY_CUTSET_2026-10-13.json) içinde ayrı tutulur; orijinaller değiştirilmedi.

## Gerçek235'te kanıtlanmış ve açık olanlar

| Veri | FC09 tarihsel kaynakta özgün kanıt | Güncel61FA aday kapsamı | Kullanıma kalan kesin gate |
|---|---|---|---|
| Frame kimliği |998 frame,235 mevcut |998frame adı; özgün GetNameList ad kümeleri eşit;235 mevcut | Bu eşitlik kolon sayımı, malzeme/topoloji veya analiz eşdeğerliği değildir. |
| Atama |235 / C1 / +0.00 / Column_80x80 |ABI4 yalnız Name235 -> Column_80x80 atamasını doğruladı | Story/C1/Shape/DesignType ve GUID güncel kaynakta henüz doğrulanmadı. |
| Kesit |Native rectangular table t2=t3=0.8m; Material=C35/45; section I2/I3 modifiers0.7 |ABI5 yalnız I22/I33=0.03413333333333332m4 kabul edilmiş unit scope | Tarihsel t2/t3/material/modifiers güncele taşınmaz. Kesit adı veya ataletlerden ölçü türetilmez; diğer10property'nin dimensional authority'si NOT_PROVEN. |
| Uç adları / konum |Native I=955, J=758;955:Base,Z=-5.15m;758:+0.00,Z=0m; her iki X=74m,Y=22.3m |Güncel235 GetPoints receipt yok | İlk ayrı teklif: mevcut ABI6 ile tek GetPoints; sonuç yalnız Point1/Point2 native slot adlarını kanıtlayabilir. |
| Uzunluk / istasyon |Native Column Object Connectivity Length=5.15m; Modal FrameForce ObjStation={0,2.225,4.45}m |Güncel uzunluk/offset/end-restraint/native station kanıtı yok | Bu ayrı büyüklüklerden ln, end offset veya clear-height çıkarılmaz. StrictColumnTopologyBundle/A18/A19 için kaynak bağlı geometri/restraint gerekir. |
| Malzeme / donatı |C35/45 native Fc raw35000kN/m2; rebar intent DefaultRebar_500; ToBeDesigned=True |Güncel235 material binding/fcd/fyd/fywd/aggregate yok | Eski materyal adı veya fck native değeri güncel design strength değildir. GetRebarColumn design intent, fiziksel veya ENGINE_SELECTED cage değildir. |
| Sonuç grain'i |Modal/Mode1..100; Frame235300local force satırı,955/758100'er local displacement satırı |Güncel B5/analysis result epoch yok | Bu FC09 mod kayıtları current61FA tasarım N/M/V veya concurrency/governing combo değildir. |
| Lineage |R3D factual epoch, is_analysis_result_epoch=False; current_b5_qualified=False |ABI2/4/5 model_fingerprint=None; kaynak SHA ve session gözlemi var | FileSHA/factual capture/session, özgün B4B/B5/B6 qualification yerine geçmez. |

Tarihsel kayıtlar **karşılaştırma hedefi** olarak korunur. Current61FA EDB byteSHA ile historicalFC09 kimliği ayrı kalır. 1044/LC_DL displayed-precision eşleşmesi whole-model,235 veya analysis-result authority oluşturmaz. R3D-R3L, ABI2-5 ve kabul edilmiş referans dilimi yeniden açılmadı; özgün arşivden yalnız hedef235'in mevcut olguları yeniden indekslendi.

## Gate G1 - özgün ABI6 tek GetPoints için ayrı authorization incelemesi

**AUTHORIZATION=NO. LIVE_GETPOINTS=NOT_EXECUTED.** Yeni executable hazırlanmamıştır; orijinal paket baytları yeniden SHA ile doğrulandı. Repo dışındaki [cutset içinde pinlenen aynı orijinal ABI6 paketi](COLUMN_235_CURRENT_SOURCE_AUTHORITY_CUTSET_2026-10-13.json) yeniden kullanılır. Bu belge ve `SupervisorAuthorizedOneRead` anahtarı yetki vermez.

| Pin | Kesin değer |
|---|---|
| Operator checkout HEAD |98f15e0eb0709083785cdefbe923f22056e4d9b9 |
| Operator TREE |54af7aa7a314dfc0a80aa6766684a49150f452b6 |
| External Python SHA256 |847c1d44c0b519ca28417618efd4939a28e25ca7e604ceccf737db7edeaabf76 |
| Operator PowerShell SHA256 |eeb144121ab01f8edabc09894c5146e6ef73624427473810a707c107dec7d78d |
| Prepare PowerShell SHA256 |06df5c6f8f5201cce81a5cdc5c6e561f76fee53677f4173c0bde33232c2076c9 |
| Git target JSON SHA256 |bb660a45059af6d5d8d93581527092b83c6e159998225ec6ae75c32f5e220d79 |
| Exact target |FrameObj.GetPoints(Name="235") |
| Source |C:\tmp\B-BLOK_Revised.EDB |
| Candidate SHA256 |61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621 |
| Required existing PID |2072 |
| Required start UTC |2026-10-09T15:47:08.1780017Z |
| Runtime |ETABS23.2.0/API2.014; Python3.14.0/comtypes1.4.16; exact accepted _memberspec.py bytes |
| Native ABI |Name IN1; Point1/Point2 INOUT3; pRetVal OUT_RETVAL10; declaring IID{F87E3A66-8381-4202-897F-46683A8477D4} |
| Budget |max1 target attempt, max1 target callback,30seconds; no automatic retry/fallback |

**Önemli pin ayrımı:**43e8afa kabul edilen ürün kodu checkpoint'idir; native operatörün98f15e0 checkpoint'i değiştirilmez. Aynı TREE veya yeni ürün HEAD'i operatör HEAD kontrolünü kaldırma gerekçesi değildir. PowerShell `[ValidateSet(2072)]` ve exact start-time kontrolü içerir. PID2072 artık yoksa, başka süreçse veya startUTC değişmişse **STOP**. Başka PID/instance seçmek veya scripti repin etmek bu paketin kapsamında değildir; ayrı session/profile incelemesi gerekir. Worker mevcut Windows PID'nin bugün hâlâ bulunduğunu gözlemedi.

Authorization öncesi operatörün bağımsız sağlaması gerekenler:

1. Exact mevcut PID2072 ve process-start; exact loaded path, candidate file SHA; accepted program/API/unit/lock context. Kaynak/session/units drift'te STOP; eski FC09 baytlarının bulunması current investigation ön koşulu değildir.
2. Exact clean `C:\Users\FCY\PycharmProjects\tbdy_engine_r3m_probe` operator checkout98f15e0/TREE; eski ABI4/5 ve ABI6 scoped LF/hash kuralları. Dirty/newer/diverged çalışma korunur. Orijinal prepare.ps1 yalnız checkout/file kontrolü yapar; operatör/getter çağırmaz.
3. Özgün ABI2, ABI3 metadata, ABI3 wrapper, ABI4 assignment ve ABI5 property JSON+sidecar çiftleri C:\tmp altında değişmemiş olmalı. Missing pair STOP; orijinal veya sidecar yeniden üretilmez.
4. Python/PowerShell/target/dependency SHA pinleri aynı olmalı. Exact current owner declaration/type/flags/wrapper/code/closure/binding kontrolleri sole target çağrısı öncesinde korunur; QueryInterface, cast, overload veya başka COM attachment yok. Backend vtable/method IID=NOT_OBSERVED_NOT_PROBED kalır.
5. Supervisor yalnız bu bir target read'i açıkça yetkilendirmeli. İnceleme PASS'i veya checkbox/switch native yetki yerine geçmez.

**Yalnız ayrı yetki verildikten sonra değerlendirilecek özgün komut; ŞİMDİ ÇALIŞTIRILMAYACAK:**

```powershell
& 'C:\tmp\column_r1_r3m_abi6_operator.ps1' `
  -VerifiedEtabsPid 2072 `
  -CandidateSha256 '61FA288FE6AA098B16062B0BAAE3FB882937AB68280C93971475AA39B2246621' `
  -SupervisorAuthorizedOneRead
```

Gateway mevcut verified PID/STA sahibini kullanır. Bağımsız EDB SHA before/after; source/session/units/lock ve PID-start guards; callback içinde nested gateway identity okumaları yok. Exact üç-item Python list/tuple: iki farklı nonempty exactstr + exactint0; ilk mismatch/error/timeout STOP. Eksik/raw başarısızlık ve gateway/chained error bilgisi immutable yeni repo-dışı JSON+sidecar'da korunur. HRESULT application pRetVal yerine sayılmaz. Point1/Point2 sırası korunur; sorting, trimming, nearest-coordinate fallback, duplicate-row seçim veya bottom/top rolü türetilmez.

**Selection NOT_READ**; yeni selection identity iddiası yok. Results.Setup veya DatabaseTables selection erişimi/değişimi yok. GetPoints başarılı olsa bile coordinates/Story/local axes/offsets/end restraints/analysis-joint/panel-zone/matrix/force/material/engineering readiness yetkisi veya kanıtı oluşturmaz. Tarihi955/758 ile eşleşme yalnız ad eşleşmesidir. Sonraki hiçbir getter otomatik yetkili değildir.

## G2/G3 - current topology/material gate'leri, henüz executable değil

G1 receipt kabul edilirse current native object names ile aynı source/session/unit bağlı geometri, local-axis/offset ve incident beam/end-restraint/material-usage facts için **ayrı bounded acquisition tasarımı** hazırlanır. İlgili native declaration/ABI/wrapper ve field-unit semantiği gözlenmeden çalıştırılabilir getter komutu uydurulmaz. Bütün model census'u,172-point scan veya P2/modal recapture bu adımın otomatik devamı değildir.

`StrictColumnTopologyBundle` ve `UsedRcMaterialPopulation` için current facts; `ReviewedColumnDesignBasis` için ayrı fcd/fyd/fywd/aggregate/ductility review gerekir. Sadece property name, historical0.8m, historicalC35/45 veya kullanıcı review'u native/current authority değildir.

## G4/G5 - sonuç ve üretim lineage gate'i

Önce current source için **özgün, hâlâ geçerli in-process owner artifact** aranır: source_model_ref/model_fingerprint, owned-scratch/source/input/result/units continuity, defined/run case scope ve qualified B4B/B5; ardından same-source B6 selected-combo/required-rebar/catalog/material continuity. Başka oturumun artifact'i veya JSON/receipt'ten yeni sealed issuer üretmek yasaktır.

Eldeki korunan arşivde235 current qualified B5/B6 yok. Bu bir runtime/platform yetersizliği değil, somut issuer/sonuç bağımlılığıdır. Existing `execute_controlled_analysis`/controlled design sahipleri analysis/design ile owned scratch üzerinde özgün lineage üretiyorsa, **ayrı, gözden geçirilmiş operator transaction ve ayrı RunAnalysis/StartDesign authorization** gerekir. Bu belgede o işlem tasarımı/komutu veya yetkisi verilmedi. Protected source EDB değişmez; action scope/scratch ownership/restoration kanıtı kurulmadan invocation yok. Modeldeki mevcut result görmek tek başına bu sahibi atlatmaz.

## M6-B - acquisition'dan bağımsız, kesin proje/source kararı

GetPoints'in cevaplayamayacağı karar formu; doldurulmuş/onanmış sayılmaz:

| Gerekli karar | Durum | Kabul için gereken özgün referans / owner bağı |
|---|---|---|
| TS5007.13 için modal yatayE action semantics ve birleştirme yasası |NOT_PROVIDED |Dated original normative/source text, authority reference ve project-reviewed applicability; mevcut accepted M6-A/R3D amplitude basis ile bağ. Per-member RS maxima toplama veya sıfır-vertical-resultant varsayımı yok. |
| Stability case/combo scope ve G/Q/E membership |NOT_PROVIDED_CURRENT_SOURCE |Exact current approved combo definitions/leaf case identity; closed factual E3 no-GQE bulgusuna karşı yeni authority açıkça belgelenmeli; yeni combo/model mutasyonu bu belgeyle yetkili değil. |
| Current whole-story fiziksel/result population ve global displacement route |NOT_PROVEN |Source/session/epoch, mode grain, normalization/units, exact object-result endpoint/analysis-joint/panel-zone applicability ve mevcut global-coordinate qualification gate'leri; sadece235 ya da field adlarıyla kapanmaz. |
| Joint delta R/v tercihi / kullanım kararı |PROJECT_DECISION_REQUIRED |Explicit dated engineer/project decision and applicable source contract; örnek rapordan veya identity matrix'ten türetilmez. |
| N/M/V state'lerini VS5/P7/Vc/canonical selection/final cage'e bağlama |NOT_PROVIDED |Exact case/end/station/selectors ve source-bound B5/B6; distinct Ash/Asw ve physical tie/cage evidence. |

Bu kararlar yazılım tarafından varsayılanlarla doldurulmaz. Güncel mevcut imzalı belge/qualified artifact verilirse offline reconciliation yapılabilir; karar/mode/matrix/result edinimi için yetkisiz canlı çağrı yapılmaz.

**NEXT EXACT CAUSAL EDGE:** supervisor G1 özgün ABI6 paketini ayrı yetki için değerlendirsin; önce PID/start ve source/package pins sağlanmalı. Paralelde mühendis current source M6-B/combination kararının özgün referansını sağlamalı. Tek GetPoints'in başarısı tam235 kapanışı değildir.

WORKER_ETABS=NO; NEW_NATIVE_GETTERS=0; LIVE_GETPOINTS=NOT_EXECUTED/NOT_AUTHORIZED;172_MATRIX_SCAN=NOT_STARTED;RESULT_CAPTURE=NO;FC09_PRODUCTION_GATE=UNCHANGED;GLOBAL_DELTA=NOT_PROVEN;M6_B=OPEN;R2_RERUN_READY=NO.
