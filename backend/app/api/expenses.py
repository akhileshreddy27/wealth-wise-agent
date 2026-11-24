from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import services
from app.ai.categorizer import categorize_with_ai
from app.config import DATA_DIR
from app.db import Budget, Transaction, get_db
from app.expenses.analytics import month_key
from app.expenses.categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES, categorize
from app.expenses.importer import parse_statement

router = APIRouter(prefix="/api", tags=["expenses"])
DEMO_STATEMENT = DATA_DIR / "sample_statement.csv"


class TransactionIn(BaseModel):
    date: date
    amount: float = Field(gt=0)
    kind: Literal["expense", "income"] = "expense"
    category: str | None = None   # auto-detected from the note when left empty
    note: str = Field("", max_length=200)


def _out(t: Transaction) -> dict:
    return {"id": t.id, "date": t.date.isoformat(), "amount": t.amount, "kind": t.kind, "category": t.category, "note": t.note}


def _valid_category(kind: str, category: str | None, note: str) -> str:
    valid = EXPENSE_CATEGORIES if kind == "expense" else INCOME_CATEGORIES
    if category and category not in valid:
        raise HTTPException(422, f"Unknown {kind} category '{category}'")
    return category or categorize(note, kind)


@router.get("/expenses/categories")
def categories():
    return {"expense": EXPENSE_CATEGORIES, "income": INCOME_CATEGORIES}


@router.get("/transactions")
def list_transactions(month: str | None = None, db: Session = Depends(get_db)):
    txns = services.all_transactions(db)
    return [_out(t) for t in txns if not month or month_key(t.date) == month]


@router.post("/transactions", status_code=201)
def create_transaction(body: TransactionIn, db: Session = Depends(get_db)):
    t = Transaction(**body.model_dump(exclude={"category"}), category=_valid_category(body.kind, body.category, body.note))
    db.add(t)
    db.commit()
    return _out(t)


@router.put("/transactions/{txn_id}")
def update_transaction(txn_id: int, body: TransactionIn, db: Session = Depends(get_db)):
    t = db.get(Transaction, txn_id) or _not_found()
    for key, value in body.model_dump(exclude={"category"}).items():
        setattr(t, key, value)
    t.category = _valid_category(body.kind, body.category, body.note)
    db.commit()
    return _out(t)


@router.delete("/transactions/{txn_id}", status_code=204)
def delete_transaction(txn_id: int, db: Session = Depends(get_db)):
    db.delete(db.get(Transaction, txn_id) or _not_found())
    db.commit()


@router.delete("/transactions", status_code=204)
def delete_all_transactions(db: Session = Depends(get_db)):
    db.execute(delete(Transaction))
    db.commit()


def _not_found():
    raise HTTPException(404, "Transaction not found")


def _import_rows(db: Session, rows: list[dict]) -> dict:
    """Skip duplicates, let the AI categoriser try rows the keyword rules left as 'other', then save."""
    existing = {(t.date, round(t.amount, 2), t.note) for t in db.scalars(select(Transaction))}
    new = [r for r in rows if (r["date"], r["amount"], r["note"]) not in existing]

    unknown = [r for r in new if r["kind"] == "expense" and r["category"] == "other" and r["note"]]
    ai_categorised = 0
    guesses = categorize_with_ai([r["note"] for r in unknown])
    for row, guess in zip(unknown, guesses or []):
        if guess != "other":
            row["category"] = guess
            ai_categorised += 1

    db.add_all(Transaction(**r) for r in new)
    db.commit()
    return {"imported": len(new), "duplicates": len(rows) - len(new), "ai_categorised": ai_categorised}


@router.post("/transactions/import")
async def import_csv(file: UploadFile, db: Session = Depends(get_db)):
    rows, errors = parse_statement(await file.read())
    if not rows and errors:
        raise HTTPException(422, errors[0])
    return {**_import_rows(db, rows), "errors": errors[:10]}


@router.post("/transactions/demo")
def load_demo(db: Session = Depends(get_db)):
    """Load a sample 6-month bank statement so the tracker has something to show."""
    rows, _ = parse_statement(DEMO_STATEMENT.read_bytes())
    return _import_rows(db, rows)


@router.get("/budgets")
def get_budgets(db: Session = Depends(get_db)):
    return services.budgets(db)


@router.put("/budgets")
def set_budgets(body: dict[str, float], db: Session = Depends(get_db)):
    """{category: monthly limit}. A limit of 0 removes the budget."""
    for category, limit in body.items():
        if category not in EXPENSE_CATEGORIES:
            raise HTTPException(422, f"Unknown category '{category}'")
        if limit > 0:
            db.merge(Budget(category=category, monthly_limit=limit))
        else:
            db.execute(delete(Budget).where(Budget.category == category))
    db.commit()
    return services.budgets(db)


@router.get("/expenses/summary")
def summary(month: str | None = None, db: Session = Depends(get_db)):
    """Monthly totals, categories vs budget, 50/30/20, 6-month trend, and savings insights."""
    txns = services.all_transactions(db)
    months = sorted({month_key(t.date) for t in txns}, reverse=True)
    data = services.spending(db, month)
    return {"months": months, **(data or {"summary": None, "insights": None})}
