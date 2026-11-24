"""Wealth Wise API. Run: uvicorn app.main:app --reload  (docs at http://localhost:8000/docs)

In production the built React app (frontend/dist) is served from here too, so the whole
site is one service."""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app import services
from app.api import expenses, learn, plan, profile
from app.api.deps import client_id
from app.config import BACKEND_DIR, settings
from app.db import get_db, init_db
from app.market.data import load_snapshot
from app.rag.knowledge import get_knowledge_base

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Build the lesson index (embeddings) in the background so the first visitor doesn't wait.
    threading.Thread(target=get_knowledge_base, daemon=True).start()
    yield


app = FastAPI(title="Wealth Wise", version="2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_methods=["*"], allow_headers=["*"])
for module in (profile, plan, expenses, learn):
    app.include_router(module.router)


@app.get("/api/health")
def health(db: Session = Depends(get_db), cid: str = Depends(client_id)):
    return {
        "ai_enabled": settings.ai_enabled,
        "model": settings.gemini_model if settings.ai_enabled else None,
        "knowledge_search": get_knowledge_base().mode,
        "market_updated_at": load_snapshot()["updated_at"],
        "has_profile": services.get_profile(db, cid) is not None,
    }


# ---------- the React app (production build) ----------

FRONTEND_DIST = BACKEND_DIR.parent / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        """Files from the build (favicon...), otherwise index.html so routes like /plan work on refresh."""
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        file = (FRONTEND_DIST / path).resolve()
        if path and file.is_file() and FRONTEND_DIST.resolve() in file.parents:
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")
