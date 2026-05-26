"""Application entrypoint.

Runs the FastAPI application using the Uvicorn ASGI server, configuring the
host and port from environment settings.
"""

import uvicorn

from src.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "src.app:app",
        host=settings.host,
        port=settings.port,
        reload=False,  # Set to True for development/local execution if needed
    )
