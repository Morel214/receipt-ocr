"""Authentication dependencies for Tenant API Keys and optional Admin Key."""

import secrets
from typing import Any

from fastapi import Header, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ocr_hub import config
from ocr_hub.repositories import tenants_repo

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_tenant(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    api_key: str | None = Query(default=None, description="Optional API key via query string"),
) -> dict[str, Any]:
    """Authenticate a user/bot by Bearer token, X-API-Key header, or ?api_key= query param."""
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials.strip()
    elif x_api_key:
        token = x_api_key.strip()
    elif api_key:
        token = api_key.strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Pass 'Authorization: Bearer <api_key>', 'X-API-Key', or '?api_key='.",
        )

    tenant = tenants_repo.get_tenant_by_api_key(token)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key.",
        )
    return tenant


def check_optional_admin_key(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> bool:
    """Return True only when ADMIN_API_KEY is configured in .env and the caller supplied a matching key."""
    if not config.ADMIN_API_KEY:
        return False

    provided = None
    if x_admin_key:
        provided = x_admin_key.strip()
    elif credentials and credentials.credentials:
        provided = credentials.credentials.strip()

    if not provided:
        return False
    return secrets.compare_digest(provided, config.ADMIN_API_KEY)


def require_strict_admin_key(
    is_admin: bool = Security(check_optional_admin_key),
) -> str:
    """Require a configured and valid ADMIN_API_KEY (used for editing/stopping/deleting shared taxonomy & catalog)."""
    if not config.ADMIN_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ADMIN_API_KEY is not configured on the server. Set ADMIN_API_KEY in .env to enable admin edits.",
        )
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin API key required for this action.",
        )
    return config.ADMIN_API_KEY


def verify_admin_key(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> str:
    """Verify ADMIN_API_KEY if one is configured in .env; allow open access if ADMIN_API_KEY is empty."""
    if not config.ADMIN_API_KEY:
        return ""

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
