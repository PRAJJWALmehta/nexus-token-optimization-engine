"""Health-check router.

Exposes ``GET /health`` — a fast, I/O-free liveness endpoint that load
balancers and readiness probes can poll.  As specified, it performs no
upstream connectivity checks so it always responds well within 100ms.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_class=JSONResponse)
async def health_check() -> dict:
    """Return gateway liveness status.

    Returns
    -------
    dict
        ``{"status": "healthy"}`` with HTTP 200.
    """
    return {"status": "healthy"}
