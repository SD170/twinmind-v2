from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.settings import router as settings_router
from app.api.suggestions import router as suggestions_router
from app.api.expansion import router as expansion_router
from app.api.export import router as export_router
from app.api.transcription import router as transcription_router
from app.config import get_settings
from app.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="TwinMind Backend Skeleton", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(settings_router, prefix="/api/v1")
    app.include_router(suggestions_router, prefix="/api/v1")
    app.include_router(expansion_router, prefix="/api/v1")
    app.include_router(export_router, prefix="/api/v1")
    app.include_router(transcription_router, prefix="/api/v1")
    return app


app = create_app()
