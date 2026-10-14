"""Offline 235 input/review and independent existing leaf composition.

No live issuer, design-lineage construction, production readiness promotion or
native call belongs here. Project declarations remain project declarations.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime
from hashlib import sha256
import base64, json, math
from copy import deepcopy

from tbdy_engine.application.column_design_basis import (
    ReviewedConcreteDesignStrength, ReviewedLongitudinalSteelDesignStrength,
    ReviewedTransverseSteelDesignStrength, ReviewedAggregateBasis, ReviewedColumnDesignBasis,
)
from tbdy_engine.design.columns.slenderness import (
    ColumnSlendernessAxisBasis, ColumnSlendernessBasis, evaluate_ts500_column_slenderness,
)
from tbdy_engine.design.columns.minimum_eccentricity import ts500_minimum_eccentricity_mm

SCHEMA = 'column.product.235.input.v1'
# Empty values are intentional. Neither section names nor old modal rows fill them.
FIELDS = (
 ('width_mm','Yerel 2 genişliği','mm','geometry','positive'),
 ('depth_mm','Yerel 3 derinliği','mm','geometry','positive'),
 ('axis_basis','Kesit / eksen tanımı','-','geometry','axis'),
 ('free_length_mm','TS500 serbest boy ln','mm','slenderness','positive'),
 ('k_m2','Etkin boy k / M2','-','slenderness','positive'),
 ('k_m3','Etkin boy k / M3','-','slenderness','positive'),
 ('sway_classification','Ötelenme sınıfı','-','slenderness','sway'),
 ('moment_ratio_m2','İşaretli M1/M2 / M2','-','slenderness','ratio'),
 ('moment_ratio_m3','İşaretli M1/M2 / M3','-','slenderness','ratio'),
 ('concrete_name','Beton adı','-','materials','text'),
 ('steel_name','Boyuna çelik adı','-','materials','text'),
 ('transverse_steel_name','Enine çelik adı','-','materials','text'),
 ('fck_mpa','Beton fck','MPa','materials','positive'),
 ('fcd_mpa','Beton fcd','MPa','materials','positive'),
 ('fyd_mpa','Boyuna fyd','MPa','materials','positive'),
 ('fywk_mpa','Enine fywk','MPa','materials','positive'),
 ('fywd_mpa','Enine fywd','MPa','materials','positive'),
 ('aggregate_max_mm','En büyük agrega','mm','materials','positive'),
 ('output_case','Tasarım case/combo adı','-','actions','text'),
 ('station_i_m','Native I slotu istasyonu','m','actions','nonnegative'),
 ('station_j_m','Native J slotu istasyonu','m','actions','nonnegative'),
 ('nd_i_kn','I slotu Nd (basınç +)','kN','actions','number'),
 ('m2_i_knm','I slotu M2','kN.m','actions','number'),
 ('m3_i_knm','I slotu M3','kN.m','actions','number'),
 ('nd_j_kn','J slotu Nd (basınç +)','kN','actions','number'),
 ('m2_j_knm','J slotu M2','kN.m','actions','number'),
 ('m3_j_knm','J slotu M3','kN.m','actions','number'),
 ('v2_kn','V2 talep adayı','kN','actions','number'),
 ('v3_kn','V3 talep adayı','kN','actions','number'),
 ('clear_cover_mm','Net beton örtüsü','mm','cage','positive'),
 ('longitudinal_diameter_mm','Kullanıcı boyuna çap','mm','cage','positive'),
 ('longitudinal_bar_count','Kullanıcı boyuna adet','-','cage','integer'),
 ('tie_diameter_mm','Kullanıcı etriye çapı','mm','cage','positive'),
 ('confinement_spacing_mm','Sargı aralığı','mm','cage','positive'),
 ('middle_spacing_mm','Orta bölge aralığı','mm','cage','positive'),
 ('shear_spacing_mm','Kesme aralığı','mm','cage','positive'),
 ('number_2_dir_tie_bars','Yerel 2 etriye kolu','-','cage','integer'),
 ('number_3_dir_tie_bars','Yerel 3 etriye kolu','-','cage','integer'),
)
GROUPS = ('geometry','slenderness','materials','actions','cage')
GROUP_LABELS = dict(zip(GROUPS, ('Kesit / eksen review','Narinlik basis review','Malzeme basis review','Kuvvet adayı / ayrı result gate','USER_PROVIDED_REBAR')))


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()


def digest(value): return sha256(canonical(value)).hexdigest()


def require(test, message):
    if not test: raise ValueError(message)


@dataclass(frozen=True, slots=True)
class ColumnProductAuthority:
    source_sha256: str
    historical_sha256: str
    evidence_epoch: str
    evidence: dict
    original_pins: dict
    adoption_pins: dict

    def packet(self):
        return {'schema':SCHEMA,'project_id':'B-BLOK','component_id':'235',
            'source_sha256':self.source_sha256,'historical_sha256':self.historical_sha256,
            'evidence_epoch':self.evidence_epoch,'result_epoch':None,
            'adoption_pins':deepcopy(self.adoption_pins),'original_receipt_pins':deepcopy(self.original_pins),
            'accepted_native_coordinates':deepcopy(self.evidence['current_point_coordinates']),
            'units':{f[0]:f[2] for f in FIELDS},'values':{f[0]:None for f in FIELDS},'reviews':{},'original_pairs':{}}


def group_payload(packet, group):
    return {k:packet['values'][k] for k,_,_,g,_ in FIELDS if g==group}


def validate_packet(packet, authority: ColumnProductAuthority):
    require(type(packet) is dict,'Kolon girdi paketi JSON nesnesi olmalı.')
    require(set(packet)==set(authority.packet()),'Bilinmeyen/eksik paket alanı; native veya lineage authority eklenemez.')
    template=authority.packet()
    for key in ('schema','project_id','component_id','source_sha256','historical_sha256','evidence_epoch','result_epoch','adoption_pins','original_receipt_pins','accepted_native_coordinates','units'):
        require(packet[key]==template[key], 'Kaynak/birim/kolon/dönem/pin uyuşmazlığı: '+key)
    require(type(packet['values']) is dict and set(packet['values'])==set(template['values']),'Eksiksiz alan şeması gerekli.')
    for key,_,_,_,kind in FIELDS:
        value=packet['values'][key]
        if value is None: continue
        if kind in {'text','axis','sway'}:
            require(isinstance(value,str) and value.strip()==value and bool(value) and len(value)<=180,key+': açık metin gerekli.')
            if kind=='axis':require(value=='RECTANGULAR_LOCAL2_LOCAL3', 'Yerel 2/3 dikdörtgen basis açıkça review edilmeli.')
            if kind=='sway':require(value in {'SWAY_PREVENTED','SWAY_PERMITTED'},'Ötelenme sınıfı tanınmadı.')
        else:
            require(type(value) in {int,float} and math.isfinite(value),key+': sonlu sayı gerekli.')
            if kind=='positive':require(value>0,key+': pozitif olmalı.')
            if kind=='nonnegative':require(value>=0,key+': negatif olamaz.')
            if kind=='integer':require(type(value) is int and value>0,key+': pozitif tamsayı gerekli.')
            if kind=='ratio':require(-1<=value<=1,key+': [-1,1] aralığı gerekli.')
    require(type(packet['reviews']) is dict and set(packet['reviews']).issubset(GROUPS),'Review grubu tanınmadı.')
    for group,review in packet['reviews'].items():
        require(type(review) is dict and set(review)=={'reviewer','reference','reviewed_at','origin','input_sha256','source_sha256','evidence_epoch'},'Review şeması farklı.')
        for key in ('reviewer','reference'):
            require(isinstance(review[key],str) and review[key].strip()==review[key] and 0<len(review[key])<=200,'Review kişi/belge referansı gerekli.')
        require(review['origin'] in {'PROJECT_DOCUMENT','USER_DECLARATION','SYNTHETIC_TEST'},'Review native authority değildir.')
        try: date=datetime.fromisoformat(review['reviewed_at'])
        except (ValueError,TypeError):raise ValueError('ISO review zamanı gerekli.') from None
        require(date.tzinfo is not None,'Review zamanı saat dilimi içermeli.')
        require(review['source_sha256']==authority.source_sha256 and review['evidence_epoch']==authority.evidence_epoch,'Review kaynak/dönem farklı.')
        require(review['input_sha256']==digest(group_payload(packet,group)),'Eski review: girdi değişti.')
        required=[k for k,_,_,g,kind in FIELDS if g==group and kind!='ratio']
        require(all(packet['values'][k] is not None for k in required),'Review için grup girdileri tamamlanmalı.')
    require(type(packet['original_pairs']) is dict and set(packet['original_pairs']).issubset(authority.original_pins),'Orijinal receipt sahibi farklı.')
    for role,pair in packet['original_pairs'].items():
        require(type(pair) is dict and set(pair)=={'json_base64','sidecar_base64'},'Orijinal receipt + sidecar birlikte gerekli.')
        try:
            raw=base64.b64decode(pair['json_base64'],validate=True);side=base64.b64decode(pair['sidecar_base64'],validate=True)
        except (ValueError,TypeError):raise ValueError('Orijinal baytlar base64 olmalı.') from None
        pin=authority.original_pins[role]
        require(sha256(raw).hexdigest()==pin['json_sha256'] and sha256(side).hexdigest()==pin['sidecar_sha256'],'Orijinal receipt/sidecar SHA256 farklı.')
        require(pin['json_sha256'] in side.decode('ascii'),'Sidecar özgün JSON kimliğini taşımıyor.')
    if 'materials' in packet['reviews']: reviewed_material_basis(packet)
    return deepcopy(packet)


def apply_review(packet, group, declaration, authority):
    validate_packet(packet,authority);require(group in GROUPS,'Review grubu farklı.')
    require(type(declaration) is dict and set(declaration)=={'reviewer','reference','reviewed_at','origin'},'Review kişi/belge/zaman/köken gerekli.')
    new=deepcopy(packet);new['reviews'][group]={**declaration,'input_sha256':digest(group_payload(packet,group)),
        'source_sha256':authority.source_sha256,'evidence_epoch':authority.evidence_epoch}
    return validate_packet(new,authority)


def reviewed_material_basis(packet):
    v=packet['values'];r=packet['reviews']['materials'];refs=(r['reference'],)
    return ReviewedColumnDesignBasis(
        concrete_strengths=(ReviewedConcreteDesignStrength(v['concrete_name'],v['fcd_mpa'],refs),),
        longitudinal_steel_strengths=(ReviewedLongitudinalSteelDesignStrength(v['steel_name'],v['fyd_mpa'],refs),),
        transverse_steel_strengths=(ReviewedTransverseSteelDesignStrength(v['transverse_steel_name'],v['fywk_mpa'],v['fywd_mpa'],refs),),
        aggregate=ReviewedAggregateBasis(v['aggregate_max_mm'],refs),basis_refs=refs)


@dataclass(frozen=True, slots=True)
class ColumnProductControl:
    id: str
    title: str
    owner: str
    status: str
    value: float | None = None
    limit: float | None = None
    unit: str = '-'
    trace: str = ''
    dependencies: tuple[str,...] = ()
    closure_owner: str = 'Proje mühendisi / ayrı nitelikli acquisition'
    governing: str | None = None
    source: str = ''
    formula: str = ''


@dataclass(frozen=True, slots=True)
class ColumnProductEvaluation:
    input_packet: dict
    input_sha256: str
    controls: tuple[ColumnProductControl,...]
    slenderness: object | None
    material_basis: ReviewedColumnDesignBasis | None
    invoked_owners: tuple[str,...]

    @property
    def result_id(self):
        return digest({'input_sha256':self.input_sha256,'controls':[asdict(c) for c in self.controls]})


def evaluate_column_product(packet, authority):
    p=validate_packet(packet,authority);v=p['values'];reviews=p['reviews'];controls=[];invoked=[];slenderness=None
    geo='geometry' in reviews
    for axis,key in [('M2','depth_mm'),('M3','width_mm')]:
        if geo:
            value=ts500_minimum_eccentricity_mm(v[key]);invoked.append('ts500_minimum_eccentricity_mm')
            controls.append(ColumnProductControl('emin_'+axis,'Minimum dışmerkezlik / '+axis,
                'tbdy_engine.design.columns.minimum_eccentricity.ts500_minimum_eccentricity_mm','CALCULATED_PROJECT_REVIEW',value=value,unit='mm',
                trace=f"h={v[key]:g} mm → emin={value:g} mm; moment floor için kaynak nitelikli Nd yok.",
                source='TS500 6.3.10 / '+reviews['geometry']['reference'],formula='emin = 15 mm + 0.03 h'))
        else:controls.append(ColumnProductControl('emin_'+axis,'Minimum dışmerkezlik / '+axis,'tbdy_engine.design.columns.minimum_eccentricity.ts500_minimum_eccentricity_mm','BLOCKED',unit='mm',dependencies=('Açık yerel 2/3 kesit ölçüleri ve geometry review',)))
    if geo and 'slenderness' in reviews:
        refs=(reviews['geometry']['reference'],reviews['slenderness']['reference'])
        refs=tuple(dict.fromkeys(refs))
        axes=[ColumnSlendernessAxisBasis(axis=axis,section_dimension_mm=v[key],free_length_ln_mm=v['free_length_mm'],effective_length_factor_k=v['k_'+axis.lower()],sway_classification=v['sway_classification'],moment_ratio_m1_over_m2=v['moment_ratio_'+axis.lower()],source_refs=refs) for axis,key in [('M2','depth_mm'),('M3','width_mm')]]
        slenderness=evaluate_ts500_column_slenderness(component_id='235',basis=ColumnSlendernessBasis('235',*axes,refs));invoked.append('evaluate_ts500_column_slenderness')
        for a in [slenderness.m2,slenderness.m3]:
            controls.append(ColumnProductControl('slenderness_'+a.axis,'Narinlik / '+a.axis,'tbdy_engine.design.columns.slenderness.evaluate_ts500_column_slenderness',a.status,a.slenderness_ratio_lk_over_i,a.neglect_limit,'-',
                f"ln={a.free_length_ln_mm:g} mm; k={a.effective_length_factor_k:g}; i={a.radius_of_gyration_i_mm:g} mm; lk={a.effective_length_lk_mm:g} mm → λ={a.slenderness_ratio_lk_over_i:g}. Proje review koşullu; A17/M6-B kapanışı değildir.",
                source='TS500 7.6 / '+reviews['slenderness']['reference'],formula='i=0.30h; lk=k ln; λ=lk/i; limit mevcut motor dalından'))
    else:
        for axis in ['M2','M3']:controls.append(ColumnProductControl('slenderness_'+axis,'Narinlik / '+axis,'tbdy_engine.design.columns.slenderness.evaluate_ts500_column_slenderness','BLOCKED',dependencies=('geometry review','TS500 ln/k/ötelenme sınıfı review'),closure_owner='Proje mühendisi; A17/A19 üretim bağlamı ayrıca'))
    material=reviewed_material_basis(p) if 'materials' in reviews else None
    if material:invoked.append('ReviewedColumnDesignBasis')
    controls.append(ColumnProductControl('material','Malzeme tasarım basis','tbdy_engine.application.column_design_basis.ReviewedColumnDesignBasis','REVIEWED_PROJECT_DECLARATION' if material else 'BLOCKED',trace='Reviewed strength/aggregate tipleri doğrulandı; native section-material eşlemesi ve bind_reviewed_column_design_basis henüz yok.' if material else '',dependencies=('Native section-material bağlama',) if material else ('Malzeme adları/dayanımları/agrega ve materials review',)))
    specs=(
      ('topology','Geometri / fiziksel uçlar','tbdy_engine.features.column_shear_topology.StrictColumnTopologyBundle',('ABI6 adları ve ABI7 koordinatları kabul edildi; fiziksel uç/yerel eksen/offset/restraint bağı eksik','Analysis-joint ve panel-zone source bağı')),
      ('design_actions','Tasarım kombinasyonları / N-M-V','tbdy_engine.application.column_a23_design_demands',('Current 61FA analysis-result/B5 epoch ve continuity','Case/combo/end/station ve source-qualified force semantics','Reviewed load-family kapsamı')),
      ('stability','Kat/whole-system kararlılık','tbdy_engine.application.column_stability_runtime.compose_story_stability_candidate_runtime',('M6-B source-authorized modal stability-action semantics','Global displacement contract ve physical binding','Elverişsiz GQE/GQW ve tam kat/whole-system kapsamı')),
      ('local_sway','Yerel ötelenme / etkin boy','tbdy_engine.application.column_local_sway_runtime.compose_column_local_axis_sway_runtime',('A16 global kararlılık','Strict topology / yerel eksen A17','A18 restraint/A19 yetkisi; tek kolon yerine kat toplamı kullanılamaz')),
      ('second_order','İkinci mertebe / moment büyütme','tbdy_engine.application.column_a22_moment_magnification',('A17–A23 source-qualified girdiler','Current analysis-result epoch; gerekiyorsa genel ikinci mertebe')),
      ('longitudinal','Boyuna donatı / PMM seçimi','tbdy_engine.application.column_longitudinal_runtime.compose_column_longitudinal_runtime',('FND2 readiness binding','Qualified current B6 DesignLineage/DesignResultIdentity','Native section/material/rebar catalog ve A23 demands')),
      ('detailing','Boyuna detaylandırma','tbdy_engine.application.column_longitudinal_detailing.materialize_selected_column_longitudinal_detailing',('Canonical ENGINE_SELECTED_REBAR','Lap/splice/anchorage/transition/continuity kaynakları')),
      ('cage','Nihai cage / USER_PROVIDED_REBAR','tbdy_engine.application.column_final_cage.ReviewedColumnFinalCageContext',('Kullanıcı cage review ve factual project RebarCatalog','A37 local-axis mapping; nihai boyuna seçimin yerine geçmez')),
      ('confinement','Enine donatı / sargı','tbdy_engine.regulatory.column_transverse_confinement.evaluate_column_transverse_confinement_bound',('Canonical selected rebar + qualified B6 lineage','A36 applicability / fywk/fywd / Ac/Ack / directions / physical cage')),
      ('axial','Eksenel kontrol','tbdy_engine.regulatory.vs5_column_axial_program',('Current B5/B6 / factual section & material','Reviewed VS5 applicability ve tasarım Nd')),
      ('shear','Kesme talebi / P7','tbdy_engine.application.column_p7_runtime.compose_column_p7_runtime',('Retained current A23 demand states','Canonical longitudinal selection','Reviewed P7/short-column applicability ve free length')),
      ('limited_shear','Sınırlı süneklik / kısa kolon','tbdy_engine.application.column_limited_shear_runtime',('Reviewed limited/short-column applicability','A37 final physical cage ve qualified current demand')),
      ('vc','Beton kesme kapasitesi / Vc','tbdy_engine.application.column_vc_runtime',('A37 reviewed Vc applicability','Native section/material + current demand/cage')),
      ('readiness','Kolon tasarım readiness','tbdy_engine.application.project_execution / column_execution / coverage',('FND2+B6+A35+A36+A37+A38–A40 canonical kapanış','Current source continuity; tüm uygulanabilir kontroller')),
    )
    for id,title,owner,deps in specs:
        trace='USER_PROVIDED_REBAR review kaydedildi; ENGINE_SELECTED_REBAR/final/as-built yapılmadı.' if id=='cage' and 'cage' in reviews else ('I/J kuvvet adayları ayrı tutuldu; current-result authority verilmedi.' if id=='design_actions' and 'actions' in reviews else '')
        controls.append(ColumnProductControl(id,title,owner,'BLOCKED',trace=trace,dependencies=deps))
    return ColumnProductEvaluation(p,digest(p),tuple(controls),slenderness,material,tuple(invoked))
