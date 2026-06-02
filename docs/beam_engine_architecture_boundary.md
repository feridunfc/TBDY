# Beam Design Engine — Architecture Boundary

## Birim Standardı

| Büyüklük | Birim |
|----------|-------|
| Uzunluk | mm |
| Kuvvet | kN |
| Moment | kNm |
| Gerilme | MPa |
| Donatı alanı (hesap) | mm² |
| Donatı alanı (rapor) | cm² |

## Boundary Guard
BeamDesignEngine TÜKETİR:

BeamModelContext (geometry + material + metadata)

BeamDemandSet (Md, Vd, N, T + governing evidence)

BeamDesignEngine ÜRETİR:

BeamDesignResult (As_required, Mpr, Ve_capacity, checks, evidence)

BeamDesignEngine TÜKETMEZ:

Raw ETABS rows (FrameForce, SapModel, comtypes)

ETABS design output

BeamProvidedReinforcement

CheckAdapter, ReportingFacade

Streamlit state, report artifacts


## Katman Sınırları

| Katman | Input | Output | Yasak |
|--------|-------|--------|-------|
| Provider | ETABS/JSON/Manual | BeamModelContext | As_required, Ve_capacity |
| Demand Processor | RawFrameForceRows | BeamDemandSet | As_required, Mpr |
| Design Engine | Context + DemandSet | BeamDesignResult | ETABS, provided rebar |
| Verification | DesignResult + ProvidedReinf | VerificationResult | DesignResult mutasyonu |
| Crosscheck | DesignResult + ETABS output | ETABSComparisonResult | DesignResult.status değiştirme |
| Reports | Tüm result'lar | JSON/Excel/UI | Hesap yapmak |

## Boundary Scan Kuralları

`demand.py` içinde `RawFrameForceRow` serbesttir.
Aşağıdaki dosyalarda `FrameForce` kelimesi YASAKTIR:
- `design/beams/design_result.py`
- `design/beams/calculators/*.py`
- `design/beams/beam_design_engine.py` (gelecek)
- `verification/**/*.py`

Tüm design engine ve calculators dosyalarında şunlar YASAKTIR:
- `comtypes`, `SapModel`
- `ETABS design output`
- `provided_area`, `selected_area`
- `ReportingFacade`, `CheckAdapter`
- `streamlit`

## Torsion Notu

`BeamDemandSet.torsion_Td_kNm` talebi taşır.
Torsion design henüz implemente edilmemiştir.
İleride eklenecek, şimdilik sadece talep olarak korunur.

## ETABSComparisonResult R14 Genişleme Notu

R9C'de `ETABSComparisonResult` tek karşılaştırma alanı taşır.
R14'te şu yapıya büyütülecektir:
ETABSComparisonItem:
comparison_field
engine_value
etabs_value
difference_percent
agreement_status

ETABSComparisonResult:
items: list[ETABSComparisonItem]
overall_agreement_status


## Kabul Kriterleri

- [x] BEAM_MODEL_CONTEXT_CONTRACT = PROVEN
- [x] BEAM_DEMAND_SET_CONTRACT = PROVEN
- [x] BEAM_PROVIDED_REINFORCEMENT_CONTRACT = PROVEN
- [x] DESIGN_ENGINE_BOUNDARY = DOCUMENTED_AND_GUARDED
- [x] label metadata'da, geometry'de değil
- [x] status default NOT_EVALUATED
- [x] torsion notu eklendi
- [x] R14 genişleme notu eklendi
- [x] Boundary scan kuralları belgelendi
R9C — Kapanış
#	Dosya	İçerik
1	design/beams/context.py	BeamModelContext, label metadata'da
2	design/beams/demand.py	BeamDemandSet, torsion notu eklendi
3	design/beams/design_result.py	Tüm status'ler NOT_EVALUATED
4	verification/beams/provided_reinforcement.py	BeamProvidedReinforcement
5	verification/beams/verification_result.py	R14 genişleme notu eklendi
6	docs/beam_engine_architecture_boundary.md	Boundary scan kuralları belgelendi


R9C tamamlandı. R10A'ya hazırız.


Evet, bu versiyon uygun. Önceki audit notlarının ana risklerini kapatmış:

label geometry'den metadata'ya taşınmış
BeamModelContext reinforcement içermiyor
BeamProvidedReinforcement ayrı verification input'u
BeamDesignResult ve alt result status default = NOT_EVALUATED
torsion demand olarak taşınıyor ama design claim'i yok
ETABSComparisonResult R14'te genişleyecek diye notlanmış
demand.py içinde RawFrameForceRow istisnası belgelendi

Bu, R9C için doğru mimari kilit.

Tek küçük düzeltme: dokümandaki iki yerde yanlışlıkla text satırı kalmış görünüyor. Bunları kaldır:


Bunlar kritik değil ama doküman temizliği için silinsin.

R9C kabul şartı için ayrıca test dosyaları şart. Dosya içerikleri doğru olsa bile “R9C tamamlandı” demek için şu testlerin geçmesi gerekir:
