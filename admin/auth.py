"""Simple Bearer-token authentication for admin panel."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from admin.config import admin_settings

_security = HTTPBearer()


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> str:
    """Validate Bearer token against ADMIN_SECRET env var."""
    if credentials.credentials != admin_settings.ADMIN_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
        )
    return credentials.credentials
