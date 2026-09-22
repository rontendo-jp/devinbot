import secrets
from typing import Optional

from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_admin(authorization: Optional[str] = Header(default=None)) -> None:
    """Guard for configuration endpoints: `Authorization: Bearer <ADMIN_API_TOKEN>`.

    Fails closed when ADMIN_API_TOKEN is not configured.
    """
    if not settings.admin_api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_TOKEN is not configured; admin endpoints are disabled",
        )
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(token.strip(), settings.admin_api_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or missing admin token")
