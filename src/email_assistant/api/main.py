"""FastAPI app: JSON API under /api, plus the built UI (ui/dist) when present."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from email_assistant.api.routers import (
    config, feedback, gmail, guides, health, models, notifications, options, runs, setup, visualizations,
)
from email_assistant.gmail.watcher import watcher
from email_assistant.notifications.telegram_bot import listener
from email_assistant.settings import PROJECT_ROOT, get_settings

UI_DIST = PROJECT_ROOT / "ui" / "dist"


def create_app() -> FastAPI:
    logging.basicConfig(level=get_settings().log_level, format="%(levelname)s %(name)s: %(message)s")
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # receives 👍/👎 clicks and sends the daily ignored digest while the API runs
        if get_settings().telegram_listener_enabled:
            listener.start()
        # auto-trigger: idles until switched on in Settings -> Gmail, then handles new mail
        if get_settings().gmail_watcher_enabled:
            watcher.start()
        yield
        listener.stop()
        watcher.stop()

    app = FastAPI(title="Email assistant", lifespan=lifespan)
    for router in (health, config, options, notifications, gmail, models, setup, runs, guides, feedback, visualizations):
        app.include_router(router.router, prefix="/api")

    @app.exception_handler(ValidationError)
    async def _validation(_: Request, e: ValidationError):
        return JSONResponse(status_code=422, content={"detail": e.errors(include_url=False, include_context=False)})

    @app.exception_handler(ValueError)
    async def _value(_: Request, e: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(e)})

    if UI_DIST.exists():
        app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            file = UI_DIST / path
            return FileResponse(file if path and file.is_file() else UI_DIST / "index.html")

    return app


app = create_app()
