"""Request dependencies. `get_current_user` is the single identity seam.

PR #1 only has the dev identity, which Settings refuses to enable outside local/test.
The auth PR replaces this function's body and keeps its signature.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request, status

DEV_USER_ID = "dev-user"


@dataclass(frozen=True)
class CurrentUser:
    id: str


def get_current_user(request: Request) -> CurrentUser:
    if request.app.state.settings.dev_identity_enabled:
        return CurrentUser(DEV_USER_ID)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
