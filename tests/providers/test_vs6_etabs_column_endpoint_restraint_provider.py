import pytest

from tbdy_engine.providers.etabs_column_endpoint_restraint_provider import (
    EtabsColumnEndpointRestraintError,
    capture_etabs_point_restraint,
)


class PointObj:
    def __init__(self, response):
        self.response = response

    def GetRestraint(self, name):
        return self.response


def test_decodes_generated_binding_get_restraint_shape_exactly():
    result = capture_etabs_point_restraint(
        PointObj(([True, True, False, False, False, False], 0)),
        "956",
    )
    assert result.point_unique_name == "956"
    assert result.dofs == (True, True, False, False, False, False)
    assert result.source_ref == "ETABS:PointObj.GetRestraint:956"


def test_nonzero_return_code_fails_closed():
    with pytest.raises(EtabsColumnEndpointRestraintError, match="returned code"):
        capture_etabs_point_restraint(
            PointObj(([True, True, False, False, False, False], 1)),
            "956",
        )


def test_non_boolean_dof_array_fails_closed():
    with pytest.raises(EtabsColumnEndpointRestraintError, match="requires one six-boolean DOF array"):
        capture_etabs_point_restraint(
            PointObj(([1, 1, 0, 0, 0, 0], 0)),
            "956",
        )
