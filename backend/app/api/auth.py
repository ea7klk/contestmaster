from typing import Annotated

from fastapi import Depends, HTTPException, status


class Principal:
    """Authenticated actor boundary; concrete session authentication is implemented later."""


def require_authenticated_user() -> Principal:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required.",
        headers={"WWW-Authenticate": "Session"},
    )


AuthenticatedUser = Annotated[Principal, Depends(require_authenticated_user)]
