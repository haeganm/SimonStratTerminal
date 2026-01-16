"""FastAPI application entry point."""

import logging
import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api.routes import router
from app.core.config import settings
from app.core.logging_config import setup_logging

# Ensure logging is configured
setup_logging()
logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log request ID, endpoint, params, and timing."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID
        request_id = str(uuid.uuid4())[:8]
        
        # Start timing
        start_time = time.time()
        
        # Extract params
        params = dict(request.query_params)
        # Redact sensitive params (none currently, but structure for future)
        
        # Log request
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} params={params}"
        )
        
        # Process request
        response = await call_next(request)
        
        # Calculate timing
        timing_ms = int((time.time() - start_time) * 1000)
        
        # Log response
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} -> {response.status_code} timing_ms={timing_ms}"
        )
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response


# Create FastAPI app
app = FastAPI(
    title="Simons Trading System API",
    description="Systematic trading research platform",
    version="0.1.0",
)

# Add request logging middleware (before CORS)
app.add_middleware(RequestLoggingMiddleware)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
