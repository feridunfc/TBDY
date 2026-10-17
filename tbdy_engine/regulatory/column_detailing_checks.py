"""A35 detailing rules, supported rectangular deformed-bar scope.

Original PDFs: TBDY 2018 7.3.2.2, 7.3.3.1–3; TS500 7.4.1,
9.1.2(a), 9.2.2–4, 9.2.7(a), 9.3.1(b), 9.4. Source hashes are
reused verbatim from the existing FND-COL-1 source catalog. No new
regulatory approval record, project review, or native issuer is created.
"""
from dataclasses import dataclass, fields, is_dataclass
from math import atan2, ceil, hypot, isfinite
from types import UnionType
from typing import get_args, get_origin, get_type_hints
from tbdy_engine.regulatory.sources.fnd_col_1_longitudinal import SOURCE_DATA
from tbdy_engine.design.columns.rebar_layout import bar_area_mm2

SOURCE_HASHES=tuple(sorted((key,value[4]) for key,value in SOURCE_DATA.items()))
ITEMS=('LAP_SPLICE_LOCATION_REGION','LAP_SECTION_RHO','ANCHORAGE','SECTION_TRANSITION','MECHANICAL_WELDED_SPLICE_APPLICABILITY','CONTINUITY_CORNER_REQUIREMENTS')
CLAUSES=('TBDY2018 7.3.3.1; TS500 9.2.2, 9.2.7(a)', 'TBDY2018 7.3.2.2; TS500 7.4.1',
         'TS500 9.1.2(a); TBDY2018 7.3.3.2', 'TBDY2018 7.3.3.2; TS500 9.3.1(b), 9.4',
         'TBDY2018 7.3.3.3; TS500 9.2.3–4', 'TS500 7.4.1; TBDY2018 7.3.3.2')


@dataclass(frozen=True, slots=True)
class BondFacts:
    fyd_mpa: float
    fctd_mpa: float
    casting_position: str  # I or II; no inferred orientation
    cover_mm: float
    clear_spacing_mm: float
    deformed: bool
    bundled: bool


@dataclass(frozen=True, slots=True)
class LapRow:
    bar_ids: tuple[int,...]
    start_mm: float  # along explicitly reviewed physical clear height
    end_mm: float
    tie_spacing_mm: float
    gap_mm: float
    added_diameter_mm: float
    tie_diameter_mm: float | None = None
    tie_count: int | None = None


@dataclass(frozen=True, slots=True)
class LapFacts:
    present: bool
    population_complete: bool
    clear_height_mm: float
    min_dimension_mm: float
    gross_area_mm2: float
    rows: tuple[LapRow,...]
    bond: BondFacts | None


@dataclass(frozen=True, slots=True)
class AnchorageRow:
    bar_ids: tuple[int,...]
    end: str  # I/J are reviewed physical endpoints in this evidence only
    available_length_mm: float
    termination: str  # STRAIGHT or TOP_OR_LARGE_TRANSITION
    hook_tail_mm: float | None = None
    bend_diameter_mm: float | None = None


@dataclass(frozen=True, slots=True)
class AnchorageFacts:
    population_complete: bool
    bond: BondFacts
    rows: tuple[AnchorageRow,...]


@dataclass(frozen=True, slots=True)
class TransitionFacts:
    present: bool
    top_storey: bool
    offset_mm: float
    rise_mm: float
    anchorage_end: str
    opposite_beam: bool
    downward_hook: bool
    bend_test_ref: str | None
    bend_diameter_mm: float | None = None


@dataclass(frozen=True, slots=True)
class SpliceRow:
    bar_id: int
    position_mm: float
    kind: str  # MECHANICAL / WELDED


@dataclass(frozen=True, slots=True)
class SpliceFacts:
    population_complete: bool
    rows: tuple[SpliceRow,...]
    fyk_mpa: float
    tension_tests_mpa: tuple[float,...]
    compression_tests_mpa: tuple[float,...]
    production_weld_count: int
    metallurgy_ref: str | None
    ts708_conformity_ref: str | None
    test_report_ref: str | None


@dataclass(frozen=True, slots=True)
class ContinuityFacts:
    population_complete: bool
    continuous_bar_ids: tuple[int,...]
    corner_bar_ids: tuple[int,...]
    covered_height_mm: float
    clear_height_mm: float
    max_tie_spacing_mm: float
    tie_diameter_mm: float
    max_restrained_bar_distance_mm: float


@dataclass(frozen=True, slots=True)
class DetailingFacts:
    """Six independently optional factual populations. None means missing, not N/A."""
    lap: LapFacts | None = None
    anchorage: AnchorageFacts | None = None
    transition: TransitionFacts | None = None
    splice: SpliceFacts | None = None
    continuity: ContinuityFacts | None = None


def _typed(value, annotation):
    origin=get_origin(annotation);args=get_args(annotation)
    if origin is UnionType:return any(_typed(value,a) for a in args)
    if origin is tuple:
        return type(value) is tuple and (all(_typed(x,args[0]) for x in value) if len(args)==2 and args[1] is Ellipsis else len(value)==len(args) and all(_typed(x,a) for x,a in zip(value,args)))
    if annotation is float:return type(value) in {int,float} and isfinite(value)
    return type(value) is annotation


def validate_detailing_fact_types(value):
    if is_dataclass(value):
        annotations=get_type_hints(type(value))
        for f in fields(value):
            child=getattr(value,f.name)
            if not _typed(child,annotations[f.name]):raise TypeError('Exact immutable detailing type required: '+f.name)
            validate_detailing_fact_types(child)
    elif type(value) is tuple:
        for child in value:validate_detailing_fact_types(child)
    elif type(value) is float and not isfinite(value):raise ValueError('Nonfinite detailing fact.')


def _positive(*values):
    if any(type(v) not in {float,int} or v<=0 or not isfinite(v) for v in values):raise ValueError('Positive finite detailing dimensions/strengths required.')


def tension_bond_length_mm(phi, facts):
    """TS500 9.1.2(a): unreduced straight deformed single-bar anchorage."""
    _positive(phi,facts.fyd_mpa,facts.fctd_mpa,facts.cover_mm,facts.clear_spacing_mm)
    if facts.deformed is not True or facts.bundled is not False or phi>40 or facts.casting_position not in {'I','II'}:
        return None  # unsupported geometry must not be made compliant
    lb=max(.12*phi*facts.fyd_mpa/facts.fctd_mpa,20*phi)
    if phi>32:lb*=100/(132-phi)
    if facts.casting_position=='I':lb*=1.4
    if facts.cover_mm<phi or facts.clear_spacing_mm<1.5*phi:lb*=1.2
    return lb


def maximum_perimeter_bar_gap_mm(bars):
    """A restraint gap cannot be shorter than the gap between adjacent bars."""
    ordered=sorted(bars,key=lambda b:atan2(b.x3_mm,b.x2_mm))
    return max(hypot(a.x2_mm-b.x2_mm,a.x3_mm-b.x3_mm) for a,b in zip(ordered,ordered[1:]+ordered[:1]))


def evaluate_detailing_facts(facts, *, bars, gross_area_mm2):
    if type(facts) is not DetailingFacts:raise TypeError('DetailingFacts required.')
    validate_detailing_fact_types(facts)
    if not bars:raise ValueError('Selected bar population required.')
    ids={b.index for b in bars};phi=max(b.diameter_mm for b in bars)
    if len(ids)!=len(bars) or any(abs(b.diameter_mm-phi)>1e-9 for b in bars):raise ValueError('Supported uniform selected bar population required.')
    ordered=sorted(bars,key=lambda b:atan2(b.x3_mm,b.x2_mm))
    adjacent={frozenset((a.index,b.index)) for a,b in zip(ordered,ordered[1:]+ordered[:1])}
    _positive(gross_area_mm2)
    results=[]
    def emit(i,status,reason,values=None):
        results.append({'item':ITEMS[i],'status':status,'reason':reason,'values':values or {},'clause':CLAUSES[i]})
    def checked(i,ok,values):emit(i,'PROVEN' if ok else 'FAIL','SOURCE_BOUND_RULE_SATISFIED' if ok else 'SOURCE_BOUND_RULE_NOT_SATISFIED',values)
    def population(rowids):
        if type(rowids) is not tuple or any(type(x) is not int for x in rowids):raise TypeError('Exact immutable integer bar IDs required.')
        if len(rowids)!=len(set(rowids)) or not set(rowids).issubset(ids):raise ValueError('Unknown/duplicate selected bar identity.')
    lap=facts.lap;lap_intervals=[]
    if lap is not None and facts.continuity is not None and abs(lap.clear_height_mm-facts.continuity.clear_height_mm)>1e-6:raise ValueError('Detailing clear-height scopes differ.')
    if lap is None or lap.population_complete is not True:
        emit(0,'UNRESOLVED','COMPLETE_LAP_LOCATION_POPULATION_REQUIRED');emit(1,'UNRESOLVED','COMPLETE_LAP_SECTION_POPULATION_REQUIRED')
    elif lap.present is False:
        if lap.rows:raise ValueError('No-lap applicability contradicts lap rows.')
        emit(0,'NOT_APPLICABLE','REVIEWED_COMPLETE_POPULATION_HAS_NO_LAPS');emit(1,'NOT_APPLICABLE','REVIEWED_COMPLETE_POPULATION_HAS_NO_LAPS')
    elif lap.present is True:
        _positive(lap.clear_height_mm,lap.min_dimension_mm,lap.gross_area_mm2)
        if abs(lap.gross_area_mm2-gross_area_mm2)>1e-6* gross_area_mm2:raise ValueError('Lap Ac differs from selected section.')
        if not lap.rows:
            emit(0,'UNRESOLVED','LAP_ROWS_REQUIRED');emit(1,'UNRESOLVED','LAP_ROWS_REQUIRED')
        else:
            lengths=[];valid=True;ties_complete=True
            for row in lap.rows:
                population(row.bar_ids)
                if not row.bar_ids:raise ValueError('Empty lap row.')
                _positive(row.end_mm-row.start_mm,row.tie_spacing_mm,row.added_diameter_mm)
                if row.tie_diameter_mm is None or row.tie_count is None:ties_complete=False
                else:
                    _positive(row.tie_diameter_mm,row.tie_count)
                    if type(row.tie_count) is not int:raise TypeError("Integer lap tie count required.")
                    valid &= row.tie_diameter_mm>=max(phi/3,8) and row.tie_count>=max(6,ceil((row.end_mm-row.start_mm)/row.tie_spacing_mm)+1)
                if row.gap_mm<0:raise ValueError('Negative lap gap.')
                if abs(row.added_diameter_mm-phi)>1e-9:raise ValueError('Unequal-diameter lap is outside supported scope.')
                if any(bid==oldid and max(row.start_mm,a)<=min(row.end_mm,b) for oldid,a,b in lap_intervals for bid in row.bar_ids):raise ValueError('Overlapping duplicate lap population.')
                lap_intervals.extend((bid,row.start_mm,row.end_mm) for bid in row.bar_ids)
                length=row.end_mm-row.start_mm;lengths.append(length)
                valid &= row.start_mm>=lap.clear_height_mm/3 and row.end_mm<=2*lap.clear_height_mm/3 and row.tie_spacing_mm<=min(lap.min_dimension_mm/3,150) and row.gap_mm<=min(length/6,100)
            lb=None if lap.bond is None else tension_bond_length_mm(phi,lap.bond)
            if lb is None or not ties_complete:emit(0,'UNRESOLVED','SUPPORTED_BOND_AND_LAP_TIE_FACTS_REQUIRED',{'location_and_spacing_satisfied':valid})
            else:checked(0,valid and min(lengths)>=lb,{'required_lb_mm':lb,'min_lap_length_mm':min(lengths),'allowed_region_mm':(lap.clear_height_mm/3,2*lap.clear_height_mm/3)})
            points=sorted({z for _,a,b in lap_intervals for z in (a,b)})
            total=sum(b.area_mm2 for b in bars)
            populations=[(z,tuple(bid for bid,a,b in lap_intervals if a<=z<=b)) for z in points]
            ratios=[(total+len(pop)*bar_area_mm2(phi))/gross_area_mm2 for z,pop in populations]
            checked(1,max(ratios)<=.06,{'max_total_rho':max(ratios),'limit':.06,'section_populations':populations,'base_area_mm2':total})
    else:raise ValueError('Explicit lap applicability required.')
    anchor=facts.anchorage;anchor_good={}
    if anchor is None or anchor.population_complete is not True:
        emit(2,'UNRESOLVED','COMPLETE_ANCHORAGE_END_POPULATION_REQUIRED')
    else:
        lb=tension_bond_length_mm(phi,anchor.bond);seen=set();checks=[]
        for row in anchor.rows:
            population(row.bar_ids)
            if not row.bar_ids or row.end not in {'I','J'} or row.termination not in {'STRAIGHT','TOP_OR_LARGE_TRANSITION'}:raise ValueError('Exact anchorage end/type required.')
            _positive(row.available_length_mm)
            for bid in row.bar_ids:
                if (bid,row.end) in seen:raise ValueError('Duplicate anchorage bar/end.')
                seen.add((bid,row.end))
            required=None if lb is None else max(1.5*lb,40*phi) if row.termination=='TOP_OR_LARGE_TRANSITION' else lb
            ok=required is not None and row.available_length_mm>=required
            if row.termination=='TOP_OR_LARGE_TRANSITION':ok &= row.hook_tail_mm is not None and row.bend_diameter_mm is not None and row.hook_tail_mm>=12*phi and row.bend_diameter_mm>=6*phi
            checks.append({'bar_ids':row.bar_ids,'end':row.end,'provided_mm':row.available_length_mm,'required_mm':required,'satisfied':ok})
            for bid in row.bar_ids:anchor_good[(bid,row.end)]=ok and row.termination=='TOP_OR_LARGE_TRANSITION'
        if seen!={(bid,end) for bid in ids for end in ('I','J')} or lb is None:emit(2,'UNRESOLVED','EVERY_SELECTED_BAR_END_AND_SUPPORTED_BOND_REQUIRED',{'rows':checks})
        else:checked(2,all(x['satisfied'] for x in checks),{'rows':checks,'lb_mm':lb})
    tr=facts.transition
    if tr is None:emit(3,'UNRESOLVED','SECTION_CHANGE_AND_TOP_STOREY_APPLICABILITY_REQUIRED')
    elif type(tr.present) is not bool or type(tr.top_storey) is not bool:raise ValueError('Explicit transition applicability required.')
    elif not tr.present and not tr.top_storey:
        if tr.offset_mm!=0:raise ValueError('No transition contradicts nonzero offset.')
        emit(3,'NOT_APPLICABLE','REVIEWED_NO_SECTION_CHANGE_AND_NOT_TOP_STOREY')
    else:
        _positive(tr.rise_mm)
        if tr.offset_mm<0 or tr.anchorage_end not in {'I','J'}:raise ValueError('Exact transition geometry/end required.')
        slope=tr.offset_mm/tr.rise_mm
        if not tr.top_storey and slope<=1/6:
            if tr.present and (not tr.bend_test_ref or tr.bend_diameter_mm is None):emit(3,'UNRESOLVED','TS500_9_4_BEND_TEST_AND_DIAMETER_REQUIRED',{'slope':slope})
            else:checked(3,tr.bend_diameter_mm is not None and tr.bend_diameter_mm>=6*phi,{'slope':slope,'max_slope':1/6,'bend_diameter_mm':tr.bend_diameter_mm,'min_bend_diameter_mm':6*phi})
        elif not anchor_good or not tr.bend_test_ref:emit(3,'UNRESOLVED','TERMINAL_ANCHORAGE_AND_BEND_TEST_REQUIRED',{'slope':slope})
        else:checked(3,all(anchor_good.get((bid,tr.anchorage_end),False) for bid in ids) and (tr.opposite_beam or tr.downward_hook),{'slope':slope,'anchorage_end':tr.anchorage_end})
    sp=facts.splice
    if sp is None or sp.population_complete is not True:emit(4,'UNRESOLVED','COMPLETE_MECHANICAL_WELDED_SPLICE_POPULATION_REQUIRED')
    elif not sp.rows:emit(4,'NOT_APPLICABLE','REVIEWED_COMPLETE_POPULATION_HAS_NO_MECHANICAL_WELDED_SPLICES')
    else:
        _positive(sp.fyk_mpa)
        if any(x.bar_id not in ids or x.kind not in {'MECHANICAL','WELDED'} for x in sp.rows):raise ValueError('Exact splice bar/type required.')
        if any(type(x.bar_id) is not int or type(x.position_mm) not in {int,float} or x.position_mm<0 for x in sp.rows):raise ValueError('Nonnegative exact splice station required.')
        if type(sp.production_weld_count) is not int or sp.production_weld_count<0:raise ValueError('Integer weld production population required.')
        if len({(x.bar_id,x.position_mm) for x in sp.rows})!=len(sp.rows):raise ValueError('Duplicate splice.')
        mech=any(x.kind=='MECHANICAL' for x in sp.rows);weld=any(x.kind=='WELDED' for x in sp.rows)
        # Adjacent bars are determined from the actual perimeter coordinates.
        distances=[abs(a.position_mm-b.position_mm) for i,a in enumerate(sp.rows) for b in sp.rows[i+1:] if frozenset((a.bar_id,b.bar_id)) in adjacent]
        spacing=min(distances) if distances else None
        missing=not sp.test_report_ref or not sp.tension_tests_mpa or (mech and not sp.compression_tests_mpa) or (weld and (not sp.metallurgy_ref or not sp.ts708_conformity_ref or sp.production_weld_count<len([x for x in sp.rows if x.kind=='WELDED'])))
        if missing:emit(4,'UNRESOLVED','SOURCE_BOUND_TEST_OR_WELD_QUALIFICATION_REQUIRED')
        else:
            _positive(*sp.tension_tests_mpa,*sp.compression_tests_mpa)
            needed=max(5,ceil(sp.production_weld_count/50)) if weld else 1
            ok=(spacing is None or spacing>=600) and min(sp.tension_tests_mpa)>=1.25*sp.fyk_mpa and (not mech or min(sp.compression_tests_mpa)>=1.25*sp.fyk_mpa) and len(sp.tension_tests_mpa)>=needed
            checked(4,ok,{'adjacent_bar_pairs':tuple(sorted(tuple(sorted(pair)) for pair in adjacent)),'min_stagger_mm':spacing,'required_stagger_mm':600,'required_test_stress_mpa':1.25*sp.fyk_mpa,'required_tension_test_count':needed})
    co=facts.continuity
    if co is None or co.population_complete is not True:emit(5,'UNRESOLVED','COMPLETE_CONTINUITY_CORNER_AND_TIE_POPULATION_REQUIRED')
    else:
        population(co.continuous_bar_ids);population(co.corner_bar_ids)
        _positive(co.covered_height_mm,co.clear_height_mm,co.max_tie_spacing_mm,co.tie_diameter_mm,co.max_restrained_bar_distance_mm)
        xs=[b.x2_mm for b in bars];ys=[b.x3_mm for b in bars]
        corners={(x,y) for x in (min(xs),max(xs)) for y in (min(ys),max(ys))}
        provided={(b.x2_mm,b.x3_mm) for b in bars if b.index in co.corner_bar_ids}
        geometry_gap=maximum_perimeter_bar_gap_mm(bars)
        consistent=co.max_restrained_bar_distance_mm+1e-9>=geometry_gap
        ok=consistent and geometry_gap<=300 and set(co.continuous_bar_ids)==ids and corners.issubset(provided) and co.covered_height_mm>=co.clear_height_mm and co.max_tie_spacing_mm<=min(12*min(b.diameter_mm for b in bars),200) and co.tie_diameter_mm>=phi/3 and co.max_restrained_bar_distance_mm<=300
        checked(5,ok,{'geometry_minimum_possible_restraint_gap_mm':geometry_gap,'declared_max_restrained_gap_mm':co.max_restrained_bar_distance_mm,'restraint_gap_consistent_with_bar_geometry':consistent,'restraint_gap_limit_mm':300,'corner_coordinates':tuple(sorted(corners)),'provided_corner_ids':co.corner_bar_ids,'continuous_bar_ids':co.continuous_bar_ids,'max_tie_spacing_limit_mm':min(12*phi,200),'height_covered_mm':co.covered_height_mm})
    return tuple(results)
