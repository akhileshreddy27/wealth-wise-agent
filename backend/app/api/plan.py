from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import services
from app.ai.explainer import explain_plan
from app.db import get_db
from app.market.data import load_snapshot, refresh_snapshot

router = APIRouter(prefix="/api", tags=["plan"])


def _plan_or_404(db: Session) -> dict:
    plan = services.current_plan(db)
    if not plan:
        raise HTTPException(404, "Fill in your profile first.")
    return plan


@router.get("/plan")
def get_plan(db: Session = Depends(get_db)):
    return _plan_or_404(db)


@router.post("/plan/explain")
def explain(db: Session = Depends(get_db)):
    return explain_plan(_plan_or_404(db))


@router.get("/market/status")
def market_status():
    snap = load_snapshot()
    return {"updated_at": snap["updated_at"], "stocks": len(snap["stocks"]), "funds": len(snap["funds"]),
            "missing": snap.get("missing", {})}


@router.post("/market/refresh")
def market_refresh():
    """Re-download stock and fund data (about 15-60 seconds)."""
    try:
        snap = refresh_snapshot()
    except Exception as e:
        raise HTTPException(502, f"Refresh failed: {e}")
    return {"updated_at": snap["updated_at"], "stocks": len(snap["stocks"]), "funds": len(snap["funds"]),
            "missing": snap["missing"]}
