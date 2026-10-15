import pytest
from fastapi import HTTPException

from backend.app.api.auth import require_authenticated_user


def test_privileged_auth_dependency_rejects_anonymous_requests():
    with pytest.raises(HTTPException) as error:
        require_authenticated_user()

    assert error.value.status_code == 401
    assert error.value.headers == {"WWW-Authenticate": "Session"}
