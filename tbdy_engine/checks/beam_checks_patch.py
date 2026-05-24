# tbdy_engine/checks/beam_checks_patch.py
from tbdy_engine.design.beams.beam_module import BeamDesignModule

def register_beam_checks(registry, context):
    module = BeamDesignModule(context)

    registry.add_check(
        check_id="beam_geometry",
        fn=lambda ctx: module.run_geometry_checks(),
        category="geometry",
        description="Beam geometry (width, depth, span) check",
    )

    registry.add_check(
        check_id="beam_flexure",
        fn=lambda ctx: module.run_flexure_checks(),
        category="flexure",
        description="Beam flexure capacity check",
        depends_on="beam_geometry",
    )

    registry.add_check(
        check_id="beam_shear",
        fn=lambda ctx: module.run_shear_checks(),
        category="shear",
        description="Beam shear capacity check",
        depends_on="beam_geometry",
    )

    registry.add_check(
        check_id="beam_ductility",
        fn=lambda ctx: module.run_ductility_checks(),
        category="ductility",
        description="Beam ductility/detailing check",
        depends_on=["beam_flexure","beam_shear"],
    )

    registry.add_check(
        check_id="beam_capacity_hierarchy",
        fn=lambda ctx: module.run_capacity_hierarchy_checks(),
        category="capacity_hierarchy",
        description="Beam vs connected columns capacity hierarchy",
        depends_on=["beam_geometry","column_capacity_hierarchy"],
    )

    registry.add_check(
        check_id="beam_design_full",
        fn=lambda ctx: module.run_full_design(),
        category="design_full",
        description="Full beam design summary",
        depends_on=[
            "beam_geometry",
            "beam_flexure",
            "beam_shear",
            "beam_ductility",
            "beam_capacity_hierarchy",
        ],
    )