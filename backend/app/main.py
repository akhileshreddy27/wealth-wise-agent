"""Wealth Wise API. Run: uvicorn app.main:app --reload  (docs at http://localhost:8000/docs)"""
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import services
from app.api import expenses, learn, plan, profile
from app.config import settings
from app.db import get_db, init_db
from app.market.data import load_snapshot
from app.rag.knowledge import get_knowledge_base

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Wealth Wise", version="2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_methods=["*"], allow_headers=["*"])
for module in (profile, plan, expenses, learn):
    app.include_router(module.router)


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    return {
        "ai_enabled": settings.ai_enabled,
        "model": settings.gemini_model if settings.ai_enabled else None,
        "knowledge_search": get_knowledge_base().mode,
        "market_updated_at": load_snapshot()["updated_at"],
        "has_profile": services.get_profile(db) is not None,
    }
