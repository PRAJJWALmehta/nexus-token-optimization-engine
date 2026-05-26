"""Tenant extraction middleware.

Inspects every incoming request's ``Authorization: Bearer <key>`` header and
extracts a tenant identifier from the key prefix (the segment before the first
``_`` delimiter).

Examples
--------
- ``Authorization: Bearer tenantABC_sk-rest-of-key``  →  tenant_id = ``"tenantABC"``
- ``Authorization: Bearer sk-no-prefix-key``           →  tenant_id = ``"default"``
- *(no Authorization header)*                          →  tenant_id = ``"default"``

The resolved tenant ID is attached to ``request.state.tenant_id`` so any
downstream route handler can read it without re-parsing the header.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_DEFAULT_TENANT = "default"


class TenantExtractionMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that derives a tenant ID from the API key prefix."""

    async def dispatch(self, request: Request, call_next) -> Response:
        tenant_id = _extract_tenant_id(request)
        request.state.tenant_id = tenant_id
        response = await call_next(request)
        return response


def _extract_tenant_id(request: Request) -> str:
    """Parse the ``Authorization`` header and extract the tenant prefix.

    Parameters
    ----------
    request:
        The incoming Starlette/FastAPI request.

    Returns
    -------
    str
        The tenant identifier, or ``"default"`` when no prefix is found.
    """
    auth_header: str = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return _DEFAULT_TENANT

    api_key = auth_header[len("bearer "):].strip()

    if "_" in api_key:
        # Tenant prefix is everything before the first underscore
        return api_key.split("_", 1)[0]

    return _DEFAULT_TENANT
