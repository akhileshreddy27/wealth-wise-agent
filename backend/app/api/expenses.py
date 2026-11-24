from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app import services
from app.ai.categorizer import categorize_with_ai
from app.api.deps import ai_rate_limit, client_id
from app.config import DATA_DIR
from app.db import Budget, Transaction, get_db
from app.expenses.analytics import month_key
from app.expenses.categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES, categorize
from app.expenses.importer import parse_statement

router = APIRouter(prefix="/api", tags=["expenses"])
DEMO_STATEMENT = DATA_DIR / "sample_statement.csv"
MAX_UPLOAD_BYTES = 1_000_000


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
def list_transactions(month: str | None = None, db: Session = Depends(get_db), cid: str = Depends(client_id)):
    txns = services.all_transactions(db, cid)
    return [_out(t) for t in txns if not month or month_key(t.date) == month]


@router.post("/transactions", status_code=201)
def create_transaction(body: TransactionIn, db: Session = Depends(get_db), cid: str = Depends(client_id)):
    t = Transaction(**body.model_dump(exclude={"category"}), client_id=cid,
                    category=_valid_category(body.kind, body.category, body.note))
    db.add(t)
    db.commit()
    return _out(t)


def _own(db: Session, cid: str, txn_id: int) -> Transaction:
    """The visitor's own transaction, or 404 (another visitor's id looks the same as a missing one)."""
    t = db.get(Transaction, txn_id)
    if not t or t.client_id != cid:
        raise HTTPException(404, "Transaction not found")
    return t


@router.put("/transactions/{txn_id}")
def update_transaction(txn_id: int, body: TransactionIn, db: Session = Depends(get_db), cid: str = Depends(client_id)):
    t = _own(db, cid, txn_id)
    for key, value in body.model_dump(exclude={"category"}).items():
        setattr(t, key, value)
    t.category = _valid_category(body.kind, body.category, body.note)
    db.commit()
    return _out(t)


@router.delete("/transactions/{txn_id}", status_code=204)
def delete_transaction(txn_id: int, db: Session = Depends(get_db), cid: str = Depends(client_id)):
    db.delete(_own(db, cid, txn_id))
    db.commit()


@router.delete("/transactions", status_code=204)
def delete_all_transactions(db: Session = Depends(get_db), cid: str = Depends(client_id)):
    db.execute(delete(Transaction).where(Transaction.client_id == cid))
    db.commit()


def _import_rows(db: Session, cid: str, rows: list[dict], use_ai: bool) -> dict:
    """Skip duplicates, optionally let the AI categoriser try rows the keyword rules left as 'other', then save."""
    existing = {(t.date, round(t.amount, 2), t.note) for t in services.all_transactions(db, cid)}
    new = [r for r in rows if (r["date"], r["amount"], r["note"]) not in existing]

    ai_categorised = 0
    if use_ai:
        unknown = [r for r in new if r["kind"] == "expense" and r["category"] == "other" and r["note"]]
        for row, guess in zip(unknown, categorize_with_ai([r["note"] for r in unknown]) or []):
            if guess != "other":
                row["category"] = guess
                ai_categorised += 1

    db.add_all(Transaction(**r, client_id=cid) for r in new)
    db.commit()
    return {"imported": len(new), "duplicates": len(rows) - len(new), "ai_categorised": ai_categorised}


@router.post("/transactions/import", dependencies=[Depends(ai_rate_limit)])
async def import_csv(file: UploadFile, db: Session = Depends(get_db), cid: str = Depends(client_id)):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The CSV is larger than 1 MB.")
    rows, errors = parse_statement(content)
    if not rows and errors:
        raise HTTPException(422, errors[0])
    return {**_import_rows(db, cid, rows, use_ai=True), "errors": errors[:10]}


@router.post("/transactions/demo")
def load_demo(db: Session = Depends(get_db), cid: str = Depends(client_id)):
    """Load a sample 6-month bank statement so the tracker has something to show (keyword rules only)."""
    rows, _ = parse_statement(DEMO_STATEMENT.read_bytes())
    return _import_rows(db, cid, rows, use_ai=False)


@router.get("/budgets")
def get_budgets(db: Session = Depends(get_db), cid: str = Depends(client_id)):
    return services.budgets(db, cid)


@router.put("/budgets")
def set_budgets(body: dict[str, float], db: Session = Depends(get_db), cid: str = Depends(client_id)):
    """{category: monthly limit}. A limit of 0 removes the budget."""
    for category, limit in body.items():
        if category not in EXPENSE_CATEGORIES:
            raise HTTPException(422, f"Unknown category '{category}'")
        if limit > 0:
            db.merge(Budget(client_id=cid, category=category, monthly_limit=limit))
        else:
            db.execute(delete(Budget).where(Budget.client_id == cid, Budget.category == category))
    db.commit()
    return services.budgets(db, cid)


@router.get("/expenses/summary")
def summary(month: str | None = None, db: Session = Depends(get_db), cid: str = Depends(client_id)):
    """Monthly totals, categories vs budget, 50/30/20, 6-month trend, and savings insights."""
    txns = services.all_transactions(db, cid)
    months = sorted({month_key(t.date) for t in txns}, reverse=True)
    data = services.spending(db, cid, month)
    return {"months": months, **(data or {"summary": None, "insights": None})}
