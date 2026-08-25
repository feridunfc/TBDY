from tools.probe_vs6_topology_sources import TOPOLOGY_TABLES


def test_vs6_topology_probe_requests_exact_object_and_joint_sources():
    assert "Point Object Connectivity" in TOPOLOGY_TABLES
    assert "Objects and Elements - Joints" in TOPOLOGY_TABLES
    assert "Column Object Connectivity" in TOPOLOGY_TABLES
    assert "Beam Object Connectivity" in TOPOLOGY_TABLES
    assert "Frame Assignments - Section Properties" in TOPOLOGY_TABLES
    assert "Frame Assignments - End Length Offsets" in TOPOLOGY_TABLES
    assert "Frame Assignments - Local Axes" in TOPOLOGY_TABLES
    assert "Frame Section Property Definitions - Concrete Rectangular" in TOPOLOGY_TABLES


def test_vs6_topology_probe_does_not_request_result_or_design_tables():
    assert all("Element Forces" not in name for name in TOPOLOGY_TABLES)
    assert all("Design" not in name for name in TOPOLOGY_TABLES)


def test_vs6_topology_probe_has_no_section_name_or_angle_authority():
    # These exclusions are architectural: topology must be exact ETABS evidence,
    # never inferred from section names or frame inclination.
    source_names = " ".join(TOPOLOGY_TABLES)
    assert "section-name parser" not in source_names.lower()
    assert "angle classifier" not in source_names.lower()
