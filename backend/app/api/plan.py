from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import services
from app.ai.explainer import explain_plan
from app.api.deps import ai_rate_limit, client_id
from app.config import settings
from app.db import get_db
from app.market.data import load_snapshot, refresh_snapshot

router = APIRouter(prefix="/api", tags=["plan"])


def _plan_or_404(db: Session, cid: str) -> dict:
    plan = services.current_plan(db, cid)
    if not plan:
        raise HTTPException(404, "Fill in your profile first.")
    return plan


@router.get("/plan")
def get_plan(db: Session = Depends(get_db), cid: str = Depends(client_id)):
    return _plan_or_404(db, cid)


@router.post("/plan/explain", dependencies=[Depends(ai_rate_limit)])
def explain(db: Session = Depends(get_db), cid: str = Depends(client_id)):
    return explain_plan(_plan_or_404(db, cid))


@router.get("/market/status")
def market_status():
    snap = load_snapshot()
    return {"updated_at": snap["updated_at"], "stocks": len(snap["stocks"]), "funds": len(snap["funds"]),
            "missing": snap.get("missing", {})}


@router.post("/market/refresh")
def market_refresh():
    """Re-download stock and fund data (about 15-60 seconds). Skipped if the data is fresh enough,
    so visitors of the public demo can't hammer Yahoo / mfapi."""
    updated = load_snapshot()["updated_at"]
    min_age = timedelta(minutes=settings.market_refresh_min_minutes)
    if updated and datetime.now(timezone.utc) - datetime.fromisoformat(updated) < min_age:
        return market_status() | {"skipped": f"Data is less than {settings.market_refresh_min_minutes} minutes old."}
    try:
        snap = refresh_snapshot()
    except Exception as e:
        raise HTTPException(502, f"Refresh failed: {e}")
    return {"updated_at": snap["updated_at"], "stocks": len(snap["stocks"]), "funds": len(snap["funds"]),
            "missing": snap["missing"]}
