"""Shared reads used by both the API routes and the AI agent's tools. Everything is per visitor."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from wealthwise.ai.categorizer import categorize_with_ai
from wealthwise.db import Budget, Profile, QuizScore, Transaction
from wealthwise.engine.plan import build_plan
from wealthwise.expenses.analytics import build_insights, build_summary, month_key
from wealthwise.market.data import load_snapshot


def get_profile(db: Session, client_id: str) -> Profile | None:
    return db.get(Profile, client_id)


def profile_dict(p: Profile) -> dict:
    return {c.name: getattr(p, c.name) for c in Profile.__table__.columns if c.name != "client_id"}


def current_plan(db: Session, client_id: str) -> dict | None:
    p = get_profile(db, client_id)
    return build_plan(profile_dict(p), load_snapshot()) if p else None


def all_transactions(db: Session, client_id: str) -> list[Transaction]:
    return list(db.scalars(select(Transaction).where(Transaction.client_id == client_id)
                           .order_by(Transaction.date.desc(), Transaction.id.desc())))


def budgets(db: Session, client_id: str) -> dict[str, float]:
    return {b.category: b.monthly_limit for b in db.scalars(select(Budget).where(Budget.client_id == client_id))}


def latest_month(txns: list[Transaction]) -> str | None:
    return month_key(max(t.date for t in txns)) if txns else None


def spending(db: Session, client_id: str, month: str | None = None) -> dict | None:
    """Monthly summary + insights for `month` (YYYY-MM), defaulting to the latest month with data."""
    txns = all_transactions(db, client_id)
    month = month or latest_month(txns)
    if not month:
        return None
    p = get_profile(db, client_id)
    fallback_income = p.monthly_income if p else 0
    b = budgets(db, client_id)
    return {"summary": build_summary(txns, month, b, fallback_income),
            "insights": build_insights(txns, month, b, fallback_income)}


def quiz_scores(db: Session, client_id: str) -> dict[str, float]:
    return {q.module_id: q.best for q in db.scalars(select(QuizScore).where(QuizScore.client_id == client_id))}


def save_quiz_score(db: Session, client_id: str, module_id: str, score: float) -> None:
    """Keep the visitor's best score for a lesson."""
    row = db.get(QuizScore, (client_id, module_id))
    if row:
        row.best = max(row.best, score)
    else:
        db.add(QuizScore(client_id=client_id, module_id=module_id, best=score))
    db.commit()


def import_rows(db: Session, client_id: str, rows: list[dict], use_ai: bool) -> dict:
    """Save parsed statement rows: skip duplicates, and optionally let the AI categoriser place the
    expenses the keyword rules left as 'other'."""
    existing = {(t.date, round(t.amount, 2), t.note) for t in all_transactions(db, client_id)}
    new = [r for r in rows if (r["date"], r["amount"], r["note"]) not in existing]

    ai_categorised = 0
    if use_ai:
        unknown = [r for r in new if r["kind"] == "expense" and r["category"] == "other" and r["note"]]
        for row, guess in zip(unknown, categorize_with_ai([r["note"] for r in unknown]) or []):
            if guess != "other":
                row["category"] = guess
                ai_categorised += 1

    db.add_all(Transaction(**r, client_id=client_id) for r in new)
    db.commit()
    return {"imported": len(new), "duplicates": len(rows) - len(new), "ai_categorised": ai_categorised}


def set_budgets(db: Session, client_id: str, limits: dict[str, float]) -> None:
    """{category: monthly limit}; a limit of 0 or less removes that budget."""
    for category, limit in limits.items():
        row = db.get(Budget, (client_id, category))
        if limit and limit > 0:
            if row:
                row.monthly_limit = limit
            else:
                db.add(Budget(client_id=client_id, category=category, monthly_limit=limit))
        elif row:
            db.delete(row)
    db.commit()
