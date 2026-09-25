from __future__ import annotations

from types import SimpleNamespace

import pytest

import tbdy_engine.etabs.oapi.object_model as subject

from tbdy_engine.etabs.oapi.contracts import (
    EtabsOAPIError,
)


class _AreaObj:
    def __init__(self):
        self.label_raw = (
            "A10",
            "BASE",
            0,
        )

        self.points_raw = (
            4,
            (
                "P1",
                "P2",
                "P3",
                "P4",
            ),
            0,
        )

    def GetLabelFromName(self, name):
        assert name == "10"
        return self.label_raw

    def GetPoints(self, name):
        assert name == "10"
        return self.points_raw


class _PointObj:
    def __init__(self):
        self.coord_raw = (
            1.25,
            2.50,
            -5.15,
            0,
        )

    def GetCoordCartesian(
        self,
        name,
        x,
        y,
        z,
        csys="Global",
    ):
        assert name == "P1"
        assert x == 0.0
        assert y == 0.0
        assert z == 0.0
        assert csys == "Global"
        return self.coord_raw


def test_read_area_label_story_exact_abi():
    obj = _AreaObj()

    label, story, raw = (
        subject.read_area_label_story(
            obj,
            "10",
        )
    )

    assert label == "A10"
    assert story == "BASE"
    assert raw == obj.label_raw


def test_read_area_points_exact_abi():
    obj = _AreaObj()

    points, raw = (
        subject.read_area_points(
            obj,
            "10",
        )
    )

    assert points == (
        "P1",
        "P2",
        "P3",
        "P4",
    )

    assert raw == obj.points_raw


def test_read_point_coord_exact_abi():
    obj = _PointObj()

    x, y, z, raw = (
        subject.read_point_coord_cartesian(
            obj,
            "P1",
        )
    )

    assert (x, y, z) == (
        1.25,
        2.50,
        -5.15,
    )

    assert raw == obj.coord_raw


@pytest.mark.parametrize(
    "raw",
    (
        None,
        (),
        ("A10", "BASE"),
        ("A10", "BASE", 7),
        ("A10", "", 0),
    ),
)
def test_label_story_fail_closed(raw):
    obj = _AreaObj()
    obj.label_raw = raw

    with pytest.raises(
        EtabsOAPIError
    ):
        subject.read_area_label_story(
            obj,
            "10",
        )


@pytest.mark.parametrize(
    "raw",
    (
        None,
        (),
        (4, ("P1", "P2"), 0),
        (2, ("P1", "P2"), 0),
        (
            4,
            ("P1", "P2", "P3", "P4"),
            7,
        ),
        (
            4,
            ("P1", "P1", "P3", "P4"),
            0,
        ),
    ),
)
def test_points_fail_closed(raw):
    obj = _AreaObj()
    obj.points_raw = raw

    with pytest.raises(
        EtabsOAPIError
    ):
        subject.read_area_points(
            obj,
            "10",
        )


@pytest.mark.parametrize(
    "raw",
    (
        None,
        (),
        (1.0, 2.0, 3.0),
        (1.0, 2.0, 3.0, 7),
        (
            float("nan"),
            2.0,
            3.0,
            0,
        ),
    ),
)
def test_coord_fail_closed(raw):
    obj = _PointObj()
    obj.coord_raw = raw

    with pytest.raises(
        EtabsOAPIError
    ):
        subject.read_point_coord_cartesian(
            obj,
            "P1",
        )


def test_session_wrappers_use_verified_boundary(
    monkeypatch,
):
    sap = SimpleNamespace(
        AreaObj=_AreaObj(),
        PointObj=_PointObj(),
    )

    operations = []

    def execute(
        session,
        callback,
        *,
        operation,
        **_kwargs,
    ):
        operations.append(
            operation
        )

        return callback(
            object(),
            sap,
        )

    monkeypatch.setattr(
        subject,
        "_execute_verified_read",
        execute,
    )

    session = object()

    assert (
        subject
        .read_area_label_story_from_session(
            session,
            "10",
        )[:2]
        == (
            "A10",
            "BASE",
        )
    )

    assert (
        subject
        .read_area_points_from_session(
            session,
            "10",
        )[0]
        == (
            "P1",
            "P2",
            "P3",
            "P4",
        )
    )

    assert (
        subject
        .read_point_coord_cartesian_from_session(
            session,
            "P1",
        )[:3]
        == (
            1.25,
            2.50,
            -5.15,
        )
    )

    assert operations == [
        "oapi_area_obj_get_label_from_name",
        "oapi_area_obj_get_points",
        "oapi_point_obj_get_coord_cartesian",
    ]



class _FrameObjLocalAxes:
    def __init__(self):
        self.raw = (
            30.0,
            False,
            0,
        )
        self.calls = []

    def GetLocalAxes(
        self,
        name,
        angle,
        advanced,
    ):
        self.calls.append(
            (
                name,
                angle,
                advanced,
            )
        )

        return self.raw


def test_read_frame_local_axes_exact_comtypes_abi():
    obj = _FrameObjLocalAxes()

    angle, advanced, raw = (
        subject.read_frame_local_axes(
            obj,
            "211",
        )
    )

    assert obj.calls == [
        (
            "211",
            0.0,
            False,
        )
    ]

    assert angle == 30.0
    assert advanced is False
    assert raw == obj.raw


@pytest.mark.parametrize(
    "raw",
    (
        None,
        (),
        (0.0, False),
        (0.0, False, 7),
        (float("nan"), False, 0),
        (0.0, 0, 0),
    ),
)
def test_read_frame_local_axes_fail_closed(raw):
    obj = _FrameObjLocalAxes()
    obj.raw = raw

    with pytest.raises(
        EtabsOAPIError
    ):
        subject.read_frame_local_axes(
            obj,
            "211",
        )


def test_read_frame_local_axes_session_wrapper(
    monkeypatch,
):
    obj = _FrameObjLocalAxes()

    sap = SimpleNamespace(
        FrameObj=obj,
    )

    operations = []

    def execute(
        session,
        callback,
        *,
        operation,
        **_kwargs,
    ):
        operations.append(
            operation
        )

        return callback(
            object(),
            sap,
        )

    monkeypatch.setattr(
        subject,
        "_execute_verified_read",
        execute,
    )

    angle, advanced, _raw = (
        subject
        .read_frame_local_axes_from_session(
            object(),
            "211",
        )
    )

    assert angle == 30.0
    assert advanced is False

    assert operations == [
        "oapi_frame_obj_get_local_axes"
    ]



# ============================================================
# PointObj.GetConnectivity exact factual ABI
# ============================================================


class _PointObjConnectivity:
    def __init__(self):
        self.raw = (
            3,
            (2, 5, 7),
            ("211", "10", "L1"),
            (1, 2, 1),
            0,
        )
        self.calls = []

    def GetConnectivity(
        self,
        name,
        number_items,
        object_type,
        object_name,
        point_number,
    ):
        self.calls.append(
            (
                name,
                number_items,
                object_type,
                object_name,
                point_number,
            )
        )

        return self.raw


def test_read_point_connectivity_exact_comtypes_abi():
    obj = _PointObjConnectivity()

    fact = subject.read_point_connectivity(
        obj,
        "919",
    )

    assert obj.calls == [
        (
            "919",
            0,
            (),
            (),
            (),
        )
    ]

    assert fact.point_name == "919"
    assert fact.number_items == 3

    assert tuple(
        (
            item.object_type,
            item.object_name,
            item.point_number,
        )
        for item in fact.items
    ) == (
        (2, "211", 1),
        (5, "10", 2),
        (7, "L1", 1),
    )

    assert fact.raw_response == obj.raw


def test_read_point_connectivity_zero_items_is_factual_empty():
    obj = _PointObjConnectivity()

    obj.raw = (
        0,
        (),
        (),
        (),
        0,
    )

    fact = subject.read_point_connectivity(
        obj,
        "919",
    )

    assert fact.number_items == 0
    assert fact.items == ()


@pytest.mark.parametrize(
    "raw",
    (
        None,
        (),
        (
            1,
            (2,),
            ("211",),
            (1,),
        ),
        (
            1,
            (2,),
            ("211",),
            (1,),
            7,
        ),
        (
            2,
            (2,),
            ("211",),
            (1,),
            0,
        ),
        (
            1,
            (1,),
            ("211",),
            (1,),
            0,
        ),
        (
            1,
            (2,),
            ("",),
            (1,),
            0,
        ),
        (
            1,
            (2,),
            ("211",),
            (0,),
            0,
        ),
        (
            2,
            (2, 2),
            ("211", "211"),
            (1, 1),
            0,
        ),
    ),
)
def test_read_point_connectivity_fail_closed(raw):
    obj = _PointObjConnectivity()

    obj.raw = raw

    with pytest.raises(
        EtabsOAPIError
    ):
        subject.read_point_connectivity(
            obj,
            "919",
        )


def test_read_point_connectivity_session_wrapper(
    monkeypatch,
):
    obj = _PointObjConnectivity()

    sap = SimpleNamespace(
        PointObj=obj,
    )

    operations = []

    def execute(
        session,
        callback,
        *,
        operation,
        **_kwargs,
    ):
        operations.append(
            operation
        )

        return callback(
            object(),
            sap,
        )

    monkeypatch.setattr(
        subject,
        "_execute_verified_read",
        execute,
    )

    fact = (
        subject
        .read_point_connectivity_from_session(
            object(),
            "919",
        )
    )

    assert fact.number_items == 3

    assert operations == [
        "oapi_point_obj_get_connectivity"
    ]
