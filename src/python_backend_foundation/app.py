"""Application factory and global API infrastructure registration."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.errors import UnhandledErrorMiddleware, register_exception_handlers
from .api.health import router as health_router
from .api.request_id import RequestIdMiddleware
from .api.router import router as api_router
from .config import Settings, load_settings
from .infra.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an independent application instance using validated configuration."""
    resolved = settings if settings is not None else load_settings()
    configure_logging(resolved.log_level)

    is_production = resolved.environment == "production"
    app = FastAPI(
        title=resolved.name,
        docs_url=None if is_production else "/docs",
        redoc_url=None if is_production else "/redoc",
        openapi_url=None if is_production else "/openapi.json",
    )
    app.state.settings = resolved

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(api_router)

    # Registration is inner → outer. An error boundary inside CORS ensures that
    # 500 responses are sanitized and still receive CORS headers when allowed.
    app.add_middleware(UnhandledErrorMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    # This middleware is outermost so even CORS preflight receives a request ID.
    app.add_middleware(RequestIdMiddleware)

    return app
