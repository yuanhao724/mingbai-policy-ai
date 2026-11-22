from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .api import chat, documents, policy, stats
from .config import settings
from .seed import seed_if_empty


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db(settings.db_path)
    seed_if_empty()
    yield


app = FastAPI(
    title="Mori API",
    description="把散落的文档，变成可对话的知识。",
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(policy.router)
app.include_router(stats.router)

if settings.frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(settings.frontend_dir)), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(settings.frontend_dir / "index.html")
