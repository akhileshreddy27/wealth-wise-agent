"""Shared reads used by both the API routes and the AI agent's tools."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Budget, Profile, Transaction
from app.engine.plan import build_plan
from app.expenses.analytics import build_insights, build_summary, month_key
from app.market.data import load_snapshot


def get_profile(db: Session) -> Profile | None:
    return db.get(Profile, 1)


def profile_dict(p: Profile) -> dict:
    return {c.name: getattr(p, c.name) for c in Profile.__table__.columns}


def current_plan(db: Session) -> dict | None:
    p = get_profile(db)
    return build_plan(profile_dict(p), load_snapshot()) if p else None


def all_transactions(db: Session) -> list[Transaction]:
    return list(db.scalars(select(Transaction).order_by(Transaction.date.desc(), Transaction.id.desc())))


def budgets(db: Session) -> dict[str, float]:
    return {b.category: b.monthly_limit for b in db.scalars(select(Budget))}


def latest_month(txns: list[Transaction]) -> str | None:
    return month_key(max(t.date for t in txns)) if txns else None


def spending(db: Session, month: str | None = None) -> dict | None:
    """Monthly summary + insights for `month` (YYYY-MM), defaulting to the latest month with data."""
    txns = all_transactions(db)
    month = month or latest_month(txns)
    if not month:
        return None
    p = get_profile(db)
    fallback_income = p.monthly_income if p else 0
    b = budgets(db)
    return {"summary": build_summary(txns, month, b, fallback_income),
            "insights": build_insights(txns, month, b, fallback_income)}
