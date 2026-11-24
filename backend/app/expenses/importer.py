"""Bank-statement CSV import.

Needs a date column and either a signed amount (negative = money out) or debit/credit columns.
A description column (narration, details, ...) is used to auto-categorise each row.
"""
import csv
import io
from datetime import date, datetime

from app.expenses.categories import categorize

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y", "%d %b %Y", "%d-%b-%Y"]
COLUMNS = {
    "date": ["date", "txn date", "transaction date", "value date"],
    "note": ["narration", "description", "details", "particulars", "remarks", "note"],
    "amount": ["amount"],
    "debit": ["debit", "withdrawal", "withdrawal amt"],
    "credit": ["credit", "deposit", "deposit amt"],
}


def _date(s: str) -> date:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unrecognised date '{s}'")


def _num(s: str | None) -> float | None:
    s = (s or "").replace(",", "").replace("₹", "").strip()
    return float(s) if s else None


def parse_statement(content: bytes) -> tuple[list[dict], list[str]]:
    """Returns (transactions, errors). Each transaction: date, amount (> 0), kind, category, note."""
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="replace")))
    headers = {h.strip().lower(): h for h in reader.fieldnames or [] if h}
    col = {key: next((headers[a] for a in names if a in headers), None) for key, names in COLUMNS.items()}
    if not col["date"] or not (col["amount"] or col["debit"] or col["credit"]):
        return [], ["The CSV needs a 'Date' column and either 'Amount' or 'Debit'/'Credit' columns."]

    rows, errors = [], []
    for line, row in enumerate(reader, start=2):  # line 1 is the header
        try:
            note = (row.get(col["note"]) or "").strip()[:200] if col["note"] else ""
            if col["amount"] and _num(row.get(col["amount"])) is not None:
                signed = _num(row[col["amount"]])
            else:
                debit = _num(row.get(col["debit"])) if col["debit"] else None
                credit = _num(row.get(col["credit"])) if col["credit"] else None
                signed = -debit if debit else credit
            if not signed:
                raise ValueError("no amount")
            kind = "expense" if signed < 0 else "income"
            rows.append({"date": _date(row[col["date"]]), "amount": round(abs(signed), 2), "kind": kind,
                         "category": categorize(note, kind), "note": note})
        except (ValueError, TypeError, KeyError) as e:
            errors.append(f"Line {line}: {e}")
    return rows, errors
