"""Original-source A35 domain examples; explicit facts, no native authority."""
from dataclasses import replace
from math import ceil
import pytest
from tbdy_engine.regulatory.column_detailing_checks import *
from tbdy_engine.design.columns.rebar_layout import ColumnRebarGeometryInputs, build_rectangular_column_rebar_geometry_candidate


def geometry(*, dense=False):
    return build_rectangular_column_rebar_geometry_candidate(ColumnRebarGeometryInputs(600 if dense else 800,600 if dense else 800,40,10),diameter_mm=32 if dense else 24,n_bars_dir2=5,n_bars_dir3=5)


def complete_facts(layout, area=640000.):
    ids=tuple(b.index for b in layout.bars);phi=layout.bar_diameter_mm
    xs=[b.x2_mm for b in layout.bars];ys=[b.x3_mm for b in layout.bars]
    corners=tuple(b.index for b in layout.bars if b.x2_mm in {min(xs),max(xs)} and b.x3_mm in {min(ys),max(ys)})
    bond=BondFacts(400.,2.,'II',40.,100.,True,False)
    return DetailingFacts(
        LapFacts(True,True,6000.,600.,area,(LapRow(ids,2000.,3000.,100.,0.,phi,float(max(12,ceil(phi/3))),11),),bond),
        AnchorageFacts(True,bond,(AnchorageRow(ids,'I',2000.,'STRAIGHT'),AnchorageRow(ids,'J',2000.,'STRAIGHT'))),
        TransitionFacts(True,False,60.,600.,'J',True,False,'TEST_BEND_REPORT',max(200.,6*phi)),
        SpliceFacts(True,(SpliceRow(1,800.,'MECHANICAL'),SpliceRow(3,1500.,'MECHANICAL')),500.,(700.,),(700.,),0,None,None,'TEST_COUPLER_REPORT'),
        ContinuityFacts(True,ids,corners,6000.,6000.,150.,float(max(12,ceil(phi/3))),max(200.,maximum_perimeter_bar_gap_mm(layout.bars))))


def evaluated(facts, layout=None, area=640000.):
    g=layout or geometry()
    return evaluate_detailing_facts(facts,bars=g.bars,gross_area_mm2=area)


def test_all_six_results_resolve_with_source_bound_facts():
    rows=evaluated(complete_facts(geometry()))
    assert tuple(x['item'] for x in rows)==ITEMS and all(x['status']=='PROVEN' for x in rows)
    assert rows[0]['values']['required_lb_mm']==pytest.approx(576.)
    assert rows[1]['values']['max_total_rho']==pytest.approx(2*16*3.141592653589793*24**2/4/640000)
    assert rows[3]['values']['slope']==.1 and rows[4]['values']['required_test_stress_mpa']==625.


@pytest.mark.parametrize('field,indices',[('lap',(0,1)),('anchorage',(2,)),('transition',(3,)),('splice',(4,)),('continuity',(5,))])
def test_missing_fact_population_is_unresolved_not_not_applicable(field,indices):
    facts=replace(complete_facts(geometry()),**{field:None});rows=evaluated(facts)
    assert all(rows[i]['status']=='UNRESOLVED' for i in indices)


def test_proven_absence_enables_only_applicable_na_outcomes():
    f=complete_facts(geometry());f=replace(f,lap=replace(f.lap,present=False,rows=()),transition=replace(f.transition,present=False,offset_mm=0.),splice=replace(f.splice,rows=()))
    rows=evaluated(f);assert [r['status'] for r in rows]==['NOT_APPLICABLE','NOT_APPLICABLE','PROVEN','NOT_APPLICABLE','NOT_APPLICABLE','PROVEN']


@pytest.mark.parametrize('item',range(6))
def test_each_rule_can_report_an_actual_failure(item):
    g=geometry(dense=item==1);f=complete_facts(g,area=360000. if item==1 else 640000.)
    if item==0:f=replace(f,lap=replace(f.lap,rows=(replace(f.lap.rows[0],start_mm=1000.,end_mm=2500.),)))
    elif item==2:f=replace(f,anchorage=replace(f.anchorage,rows=tuple(replace(row,available_length_mm=100.) for row in f.anchorage.rows)))
    elif item==3:f=replace(f,transition=replace(f.transition,bend_diameter_mm=50.))
    elif item==4:f=replace(f,splice=replace(f.splice,tension_tests_mpa=(624.,)))
    elif item==5:f=replace(f,continuity=replace(f.continuity,corner_bar_ids=f.continuity.corner_bar_ids[:-1]))
    row=evaluated(f,g,360000. if item==1 else 640000.)[item]
    assert row['status']=='FAIL' and row['reason']=='SOURCE_BOUND_RULE_NOT_SATISFIED'


def test_anchorage_original_formula_position_diameter_and_confinement_factors():
    b=BondFacts(400.,2.,'II',50.,100.,True,False)
    assert tension_bond_length_mm(20.,b)==480.
    assert tension_bond_length_mm(20.,replace(b,casting_position='I'))==pytest.approx(672.)
    assert tension_bond_length_mm(36.,b)==pytest.approx(900.)
    assert tension_bond_length_mm(20.,replace(b,cover_mm=10.))==pytest.approx(576.)
    assert tension_bond_length_mm(20.,replace(b,bundled=True)) is None


def test_lap_population_counts_overlap_at_exact_stations_and_rejects_duplicate_bar_rows():
    f=complete_facts(geometry());rows=evaluated(f)
    assert all(len(pop)==16 for station,pop in rows[1]['values']['section_populations'])
    with pytest.raises(ValueError):evaluated(replace(f,lap=replace(f.lap,rows=f.lap.rows*2)))
    with pytest.raises(ValueError):evaluated(replace(f,lap=replace(f.lap,present=False)))
    with pytest.raises(ValueError):evaluated(replace(f,lap=replace(f.lap,gross_area_mm2=1.)))


def test_small_transition_requires_bend_geometry_and_large_transition_requires_terminal_anchorage():
    f=complete_facts(geometry())
    assert evaluated(replace(f,transition=replace(f.transition,bend_diameter_mm=None)))[3]['status']=='UNRESOLVED'
    changed=replace(f,transition=replace(f.transition,offset_mm=200.))
    assert evaluated(changed)[3]['status']=='FAIL'
    anchor=replace(f.anchorage,rows=tuple(replace(row,termination='TOP_OR_LARGE_TRANSITION',hook_tail_mm=288.,bend_diameter_mm=144.) for row in f.anchorage.rows))
    assert evaluated(replace(changed,anchorage=anchor))[3]['status']=='PROVEN'


def test_weld_tests_require_metallurgy_conformity_sampling_and_125_percent_strength():
    f=complete_facts(geometry());weld=replace(f.splice,rows=tuple(replace(row,kind='WELDED') for row in f.splice.rows),production_weld_count=251,tension_tests_mpa=(700.,)*6,compression_tests_mpa=(),metallurgy_ref='TEST_METALLURGY',ts708_conformity_ref='TEST_TS708')
    assert evaluated(replace(f,splice=weld))[4]['status']=='PROVEN'
    assert evaluated(replace(f,splice=replace(weld,tension_tests_mpa=(700.,)*5)))[4]['status']=='FAIL'
    assert evaluated(replace(f,splice=replace(weld,metallurgy_ref=None)))[4]['status']=='UNRESOLVED'


def test_stagger_uses_adjacent_actual_bar_coordinates_and_600mm_boundary():
    f=complete_facts(geometry());sp=f.splice
    assert evaluated(replace(f,splice=replace(sp,rows=(sp.rows[0],replace(sp.rows[1],position_mm=1400.)))))[4]['status']=='PROVEN'
    assert evaluated(replace(f,splice=replace(sp,rows=(sp.rows[0],replace(sp.rows[1],position_mm=1399.)))))[4]['status']=='FAIL'
    # Bar 10 is diagonal from bar 1; not an adjacent pair.
    assert evaluated(replace(f,splice=replace(sp,rows=(sp.rows[0],SpliceRow(10,800.,'MECHANICAL')))))[4]['status']=='PROVEN'


@pytest.mark.parametrize('mutation',[lambda f:replace(f,lap=replace(f.lap,present=1)),lambda f:replace(f,continuity=replace(f.continuity,continuous_bar_ids=(True,))),lambda f:replace(f,transition=replace(f.transition,offset_mm=float('nan')))])
def test_malformed_facts_never_resolve(mutation):
    with pytest.raises((ValueError,TypeError)):evaluated(mutation(complete_facts(geometry())))


def test_continuity_cannot_hide_a_real_bar_gap_with_a_smaller_reviewed_scalar():
    g=build_rectangular_column_rebar_geometry_candidate(ColumnRebarGeometryInputs(800,800,40,10),diameter_mm=24,n_bars_dir2=2,n_bars_dir3=2)
    facts=complete_facts(g);facts=replace(facts,continuity=replace(facts.continuity,max_restrained_bar_distance_mm=200.))
    result=evaluated(facts,g)[5]
    assert result['status']=='FAIL'
    assert result['values']['geometry_minimum_possible_restraint_gap_mm']==676.
    assert not result['values']['restraint_gap_consistent_with_bar_geometry']
