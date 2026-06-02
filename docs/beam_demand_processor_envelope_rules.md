# BeamDemandProcessor — Envelope Rules

## Birim Standardı

| Büyüklük | Birim |
|----------|-------|
| Uzunluk | mm |
| Kuvvet | kN |
| Moment | kNm |
| Gerilme | MPa |
| Donatı alanı (hesap) | mm² |
| Donatı alanı (rapor) | cm² |
| Sehim | mm |

## Zone Tanımları

İstasyonlar önce normalize edilir: `relative_station = station - min(station)`.
Bu sayede ETABS station'ları 0'dan başlamasa bile doğru bölgeleme yapılır.

| Zone | Relative Station Aralığı |
|------|--------------------------|
| left | relative ≤ 0.25L |
| mid | 0.25L < relative < 0.75L |
| right | relative ≥ 0.75L |

L = kiriş boyu (mm). `length_mm` parametresi verilmezse `max(station) - min(station)` kullanılır.

## Demand Seçim Kuralları

| Demand | Kural |
|--------|-------|
| Md_left_neg_kNm | Left zone negatif M3 → abs en büyük → pozitif magnitude |
| Md_mid_pos_kNm | Mid zone pozitif M3 → en büyük pozitif. Hiç pozitif yoksa None. |
| Md_right_neg_kNm | Right zone negatif M3 → abs en büyük → pozitif magnitude |
| Vd_left_kN | Left zone abs(V2) en büyük → pozitif magnitude |
| Vd_right_kN | Right zone abs(V2) en büyük → pozitif magnitude |
| N_kN | Tüm zone'larda abs(p_kN) en büyük, orijinal işaret korunur (basınç +) |
| torsion_Td_kNm | Tüm zone'larda abs(t_kNm) en büyük. 0 ise None. |

## Evidence

Her demand için `BeamDemandEvidence`:
- `demand_name`: Hangi demand
- `combo`: Governing kombinasyon
- `station`: Orijinal ETABS station (normalize edilmemiş)
- `raw_value`: Orijinal işaretli değer
- `rule`: Seçim kuralı

## Determinizm

Aynı input → aynı output. 100 tekrarda `asdict(result)` birebir aynı.

## Yasaklar

Bu modül:
- Design calculation yapmaz
- ETABS/SapModel/comtypes import etmez
- Provided reinforcement karşılaştırmaz
- Rapor/UI üretmez
