"""FastAPI application factory.

Assembles the token-optimization gateway by wiring together the tenant extraction
middleware, chat and health routers, and the global exception handlers.
"""

from fastapi import FastAPI

from src.exceptions import register_exception_handlers
from src.middleware.tenant import TenantExtractionMiddleware
from src.routers import chat, health


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Nexus Token-Optimization Gateway",
        description="A transparent OpenAI-compatible reverse proxy for cost optimization.",
        version="0.1.0",
    )

    # 1. Register middleware
    app.add_middleware(TenantExtractionMiddleware)

    # 2. Register exception handlers
    register_exception_handlers(app)

    # 3. Include routers
    app.include_router(health.router)
    app.include_router(chat.router)

    return app


# The application instance used by Uvicorn
app = create_app()
