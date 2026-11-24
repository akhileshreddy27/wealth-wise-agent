from datetime import date

from app.config import DATA_DIR
from app.db import Transaction
from app.expenses.analytics import build_insights, build_summary, detect_recurring, inr
from app.expenses.categories import categorize
from app.expenses.importer import parse_statement


def txn(d, amount, category, kind="expense", note=""):
    return Transaction(date=date.fromisoformat(d), amount=amount, kind=kind, category=category, note=note)


def test_inr_formatting():
    assert inr(1234567) == "₹12,34,567"
    assert inr(999) == "₹999"


def test_keyword_categoriser():
    assert categorize("SWIGGY ORDER 123") == "dining"
    assert categorize("SALARY CR ACME", "income") == "salary"
    assert categorize("random merchant") == "other"


def test_parse_signed_and_debit_credit_csv():
    rows, errors = parse_statement(b"Date,Narration,Amount\n01/06/2026,Swiggy,-450\n02/06/2026,SALARY CR,80000\n")
    assert not errors
    assert [(r["kind"], r["amount"], r["category"]) for r in rows] == [("expense", 450, "dining"), ("income", 80000, "salary")]
    rows, _ = parse_statement(b"Txn Date,Details,Debit,Credit\n2026-06-03,Uber,250,\n")
    assert rows[0]["kind"] == "expense" and rows[0]["category"] == "transport"
    _, errors = parse_statement(b"foo,bar\n1,2\n")
    assert errors


def test_sample_statement_parses_cleanly():
    rows, errors = parse_statement((DATA_DIR / "sample_statement.csv").read_bytes())
    assert len(rows) > 100 and not errors


def test_summary_counts_sip_as_saving():
    txns = [txn("2026-06-01", 50000, "salary", "income"), txn("2026-06-02", 20000, "rent"),
            txn("2026-06-05", 10000, "investments"), txn("2026-06-06", 5000, "dining")]
    s = build_summary(txns, "2026-06", budgets={"dining": 4000})
    assert s["expense"] == 35000 and s["invested"] == 10000
    assert s["net"] == 25000                         # income - (spending excluding the SIP)
    dining = next(c for c in s["categories"] if c["category"] == "dining")
    assert dining["budget_used"] == 1.25


def test_insights_flag_over_budget_and_subscriptions():
    txns = [txn(f"2026-{m:02d}-05", 649, "subscriptions", note="NETFLIX.COM") for m in (4, 5, 6)]
    txns += [txn("2026-06-01", 50000, "salary", "income"), txn("2026-06-10", 6000, "shopping")]
    out = build_insights(txns, "2026-06", budgets={"shopping": 3000})
    kinds = {i["type"] for i in out["insights"]}
    assert {"over_budget", "subscriptions"} <= kinds
    assert detect_recurring(txns, "2026-06")[0]["monthly_amount"] == 649
