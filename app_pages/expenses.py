"""Expense tracker: budgets, the 50/30/20 rule, recurring payments, spending spikes, savings tips."""
from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import delete

from app_pages.charts import category_bars, trend_bars
from app_pages.common import allow_ai_call, db_session, inr, metric_row, month_label, pct, visitor_id
from wealthwise import services
from wealthwise.config import DATA_DIR, settings
from wealthwise.db import Transaction
from wealthwise.expenses.analytics import month_key
from wealthwise.expenses.categories import EXPENSE_CATEGORIES, INCOME_CATEGORIES, categorize
from wealthwise.expenses.importer import parse_statement

vid = visitor_id()


def import_statement(content: bytes, use_ai: bool) -> None:
    rows, errors = parse_statement(content)
    if not rows:
        st.error(errors[0] if errors else "No transactions found in that file.")
        return
    with db_session() as db:
        r = services.import_rows(db, vid, rows, use_ai)
    msg = f"Imported {r['imported']} transactions"
    msg += f", skipped {r['duplicates']} duplicates" if r["duplicates"] else ""
    msg += f", {r['ai_categorised']} categorised by AI" if r["ai_categorised"] else ""
    st.toast(msg + (f". {len(errors)} rows had errors." if errors else "."), icon="✅")
    st.session_state.pop("month", None)


st.title("Expense tracker")
st.caption("Track spending, set budgets and find savings. Investments (SIPs) count as saving, not spending.")

# ----- adding data -----
a, b, c = st.columns(3)
if a.button("Load demo statement", icon=":material/dataset:", help="Six months of sample bank transactions"):
    import_statement((DATA_DIR / "sample_statement.csv").read_bytes(), use_ai=False)
with b.popover("Import bank CSV", icon=":material/upload:"):
    st.caption("Needs a Date column and either Amount (negative = money out) or Debit/Credit columns. "
               "Unknown merchants are categorised by AI.")
    upload = st.file_uploader("Statement CSV", type="csv", label_visibility="collapsed")
    if upload and st.session_state.get("imported_file") != upload.file_id:
        st.session_state.imported_file = upload.file_id
        import_statement(upload.getvalue(), use_ai=settings.ai_enabled and allow_ai_call())
with c.popover("Add transaction", icon=":material/add:"):
    with st.form("add", clear_on_submit=True):
        kind = st.segmented_control("Type", ["expense", "income"], default="expense", format_func=str.title)
        when = st.date_input("Date", date.today(), format="DD/MM/YYYY")
        amount = st.number_input("Amount (₹)", min_value=1.0, step=100.0)
        note = st.text_input("Description", placeholder="e.g. Swiggy order")
        options = {**EXPENSE_CATEGORIES, **INCOME_CATEGORIES}
        category = st.selectbox("Category", ["auto"] + list(options),
                                format_func=lambda k: "Auto-detect" if k == "auto" else options[k]["label"])
        if st.form_submit_button("Add", type="primary"):
            kind = kind or "expense"
            valid = EXPENSE_CATEGORIES if kind == "expense" else INCOME_CATEGORIES
            cat = category if category in valid else categorize(note, kind)
            with db_session() as db:
                db.add(Transaction(client_id=vid, date=when, amount=amount, kind=kind, category=cat, note=note))
                db.commit()
            st.session_state.pop("month", None)
            st.rerun()

with db_session() as db:
    txns = services.all_transactions(db, vid)
months = sorted({month_key(t.date) for t in txns}, reverse=True)
if not months:
    st.info("No transactions yet. Load the demo statement, import a bank CSV, or add one by hand.")
    st.stop()

month = st.selectbox("Month", months, key="month", format_func=month_label)
with db_session() as db:
    data = services.spending(db, vid, month)
s, ins = data["summary"], data["insights"]

rate_ok = (s["savings_rate"] or 0) >= 0.2
metric_row(
    {"label": "Income", "value": inr(s["income_base"]), "delta": "from your profile" if s["income_is_estimate"] else None},
    {"label": "Spent", "value": inr(s["expense"] - s["invested"])},
    {"label": "Invested", "value": inr(s["invested"]), "delta": "SIPs and investments"},
    {"label": "Savings rate", "value": pct(s["savings_rate"], 0), "delta": "target 20%+",
     "delta_color": "green" if rate_ok else "red"},
)

left, right = st.columns([3, 2], gap="medium")
with left.container(border=True):
    st.markdown("**Savings insights**")
    if ins["potential_monthly_saving"]:
        st.caption(f"Up to {inr(ins['potential_monthly_saving'])}/month you could save")
    box = {"danger": st.error, "warning": st.warning, "info": st.info, "success": st.success}
    for i in ins["insights"]:
        box[i["severity"]](f"**{i['title']}**  \n{i['detail']}")
    if not ins["insights"]:
        st.write("Nothing to flag this month.")

with right.container(border=True):
    st.markdown("**50/30/20 rule**")
    st.caption("Share of income: needs ≤ 50%, wants ≤ 30%, savings ≥ 20%")
    for key, label, target in (("needs", "Needs", 0.5), ("wants", "Wants", 0.3), ("savings", "Savings", 0.2)):
        share = s["bucket_share"][key] or 0
        ok = share >= target if key == "savings" else share <= target
        st.progress(min(share, 1.0), text=f"{'✅' if ok else '⚠️'} {label}: **{pct(share, 0)}** of income "
                                          f"(target {pct(target, 0)}) · {inr(s['buckets'][key])}")

left, right = st.columns([3, 2], gap="medium")
with left.container(border=True):
    st.markdown("**Spending by category** (black tick = budget)")
    st.altair_chart(category_bars(s["categories"]))
    with st.expander("Edit monthly budgets"):
        current = {c["category"]: c["budget"] or 0 for c in s["categories"]}
        table = pd.DataFrame([{"category": k, "Category": v["label"], "Monthly budget (₹)": current.get(k, 0)}
                              for k, v in EXPENSE_CATEGORIES.items()])
        edited = st.data_editor(table, hide_index=True, column_order=["Category", "Monthly budget (₹)"],
                                disabled=["Category"], key="budgets",
                                column_config={"Monthly budget (₹)": st.column_config.NumberColumn(min_value=0, step=500)})
        if st.button("Save budgets"):
            with db_session() as db:
                services.set_budgets(db, vid, dict(zip(edited["category"], edited["Monthly budget (₹)"].fillna(0))))
            st.rerun()
with right.container(border=True):
    st.markdown("**Last 6 months**")
    st.altair_chart(trend_bars(s["trend"]))

# ----- transactions -----
with st.container(border=True):
    st.markdown(f"**Transactions · {month_label(month)}**")
    st.caption("Change a category in the table, or tick rows to delete, then save.")
    labels = {k: v["label"] for k, v in {**EXPENSE_CATEGORIES, **INCOME_CATEGORIES}.items()}
    shown = [t for t in txns if month_key(t.date) == month]
    df = pd.DataFrame([{"id": t.id, "Date": t.date, "Description": t.note, "Category": labels.get(t.category, t.category),
                        "Amount": t.amount if t.kind == "income" else -t.amount, "Delete": False} for t in shown])
    edited = st.data_editor(df, hide_index=True, column_order=["Date", "Description", "Category", "Amount", "Delete"],
                            disabled=["Date", "Description", "Amount"], key=f"txns_{month}",
                            column_config={"Category": st.column_config.SelectboxColumn(options=list(labels.values())),
                                           "Amount": st.column_config.NumberColumn(format="₹%,.0f"),
                                           "Date": st.column_config.DateColumn(format="DD MMM")})
    save, clear = st.columns([1, 4])
    if save.button("Save changes", type="primary"):
        by_label = {v: k for k, v in labels.items()}
        with db_session() as db:
            for _, row in edited.iterrows():
                t = db.get(Transaction, int(row["id"]))
                if not t or t.client_id != vid:
                    continue
                if row["Delete"]:
                    db.delete(t)
                else:
                    new = by_label.get(row["Category"], t.category)
                    valid = EXPENSE_CATEGORIES if t.kind == "expense" else INCOME_CATEGORIES
                    t.category = new if new in valid else t.category  # an expense can't become "Salary"
            db.commit()
        st.rerun()
    with clear.popover("Delete all transactions", icon=":material/delete:"):
        st.write("This removes every transaction you've added. It can't be undone.")
        if st.button("Yes, delete all", type="primary"):
            with db_session() as db:
                db.execute(delete(Transaction).where(Transaction.client_id == vid))
                db.commit()
            st.session_state.pop("month", None)
            st.rerun()
