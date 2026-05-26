"""Global exception handling.

Intercepts exceptions raised during request processing and maps them to
standardized JSON responses. This ensures that upstream provider errors are
passed through transparently, while internal connection or logic errors are
presented consistently.
"""

import logging

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.models.chat import GatewayErrorDetail, GatewayErrorResponse

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI application."""

    @app.exception_handler(httpx.HTTPStatusError)
    async def http_status_error_handler(
        request: Request, exc: httpx.HTTPStatusError
    ) -> JSONResponse:
        """Pass through upstream 4xx/5xx HTTP errors."""
        # Because we are using client.stream(), we must read the response
        # body before we can access .text or .json()
        try:
            await exc.response.aread()
        except Exception:
            pass

        logger.warning(
            "Upstream HTTP %d error: %s",
            exc.response.status_code,
            exc.response.text,
        )
        try:
            # If the upstream returned JSON, forward it intact
            content = exc.response.json()
        except ValueError:
            # Otherwise, wrap the raw text in our standard gateway error format
            content = GatewayErrorResponse(
                error=GatewayErrorDetail(
                    message=exc.response.text,
                    code=str(exc.response.status_code),
                )
            ).model_dump()

        return JSONResponse(
            status_code=exc.response.status_code,
            content=content,
        )

    @app.exception_handler(httpx.ConnectError)
    async def connect_error_handler(
        request: Request, exc: httpx.ConnectError
    ) -> JSONResponse:
        """Handle inability to connect to the upstream API."""
        logger.error("Upstream connection error: %s", exc)
        return JSONResponse(
            status_code=502,
            content=GatewayErrorResponse(
                error=GatewayErrorDetail(
                    message="Failed to connect to upstream API.",
                )
            ).model_dump(),
        )

    @app.exception_handler(httpx.TimeoutException)
    async def timeout_error_handler(
        request: Request, exc: httpx.TimeoutException
    ) -> JSONResponse:
        """Handle upstream timeouts."""
        logger.error("Upstream timeout error: %s", exc)
        return JSONResponse(
            status_code=504,
            content=GatewayErrorResponse(
                error=GatewayErrorDetail(
                    message="Upstream API timed out.",
                    type="gateway_timeout",
                )
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Catch-all for any unhandled internal server error."""
        logger.exception("Unhandled internal error: %s", exc)
        return JSONResponse(
            status_code=502,
            content=GatewayErrorResponse(
                error=GatewayErrorDetail(
                    message="An unexpected error occurred in the proxy gateway.",
                )
            ).model_dump(),
        )
