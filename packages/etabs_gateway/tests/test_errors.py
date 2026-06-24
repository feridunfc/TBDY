import pytest

from etabs_gateway.errors import ETABSAttachError, ETABSGatewayError


def test_typed_error_serializes_without_losing_context() -> None:
    error = ETABSAttachError(
        "Unable to attach to a running ETABS instance.",
        operation="attach",
        details={"attempt": 1},
    )

    assert isinstance(error, ETABSGatewayError)
    assert error.as_dict() == {
        "code": "ETABS_ATTACH_FAILED",
        "message": "Unable to attach to a running ETABS instance.",
        "operation": "attach",
        "details": {"attempt": 1},
    }


def test_error_rejects_empty_message() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        ETABSGatewayError("   ")
