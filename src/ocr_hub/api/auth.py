"""Authentication dependencies for Tenant API Keys and Admin Master Key."""

import secrets
from typing import Any

from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ocr_hub import config
from ocr_hub.repositories import tenants_repo

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_tenant(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict[str, Any]:
    """Authenticate a tenant by Bearer token or X-API-Key header."""
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials.strip()
    elif x_api_key:
        token = x_api_key.strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide 'Authorization: Bearer <api_key>' or 'X-API-Key'.",
        )

    tenant = tenants_repo.get_tenant_by_api_key(token)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key.",
        )
    return tenant


def verify_admin_key(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> str:
    """Verify the master ADMIN_API_KEY via X-Admin-Key or Bearer token."""
    provided = None
    if x_admin_key:
        provided = x_admin_key.strip()
    elif credentials and credentials.credentials:
        provided = credentials.credentials.strip()

    if not provided or not secrets.compare_digest(provided, config.ADMIN_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing Admin API key.",
        )
    return provided
