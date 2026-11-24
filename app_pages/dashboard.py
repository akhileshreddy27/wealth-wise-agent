"""Dashboard: where your money stands, at a glance."""
import streamlit as st

from app_pages.charts import allocation_donut
from app_pages.common import db_session, inr, inr_compact, metric_row, month_label, pct, visitor_id
from wealthwise import services

vid = visitor_id()
with db_session() as db:
    profile = services.get_profile(db, vid)
    plan = services.current_plan(db, vid) if profile else None
    spending = services.spending(db, vid)

if not profile:
    st.title("Welcome to Wealth Wise")
    st.caption("Your AI-powered personal finance assistant for Indian investors.")
    cols = st.columns(3)
    for col, (title, text) in zip(cols, [
        ("📊 Personal plan", "A risk score from a 5-question quiz, then a monthly SIP plan with ranked mutual funds, "
                            "scored NIFTY 50 stocks and the best FD for you."),
        ("🧾 Expense tracker", "Import a bank statement or add spending. See budgets, the 50/30/20 split, "
                              "subscriptions and spending spikes."),
        ("💬 Learn and ask", "13 short lessons with videos and quizzes, and an AI assistant that answers from them "
                            "with live market data."),
    ]):
        with col.container(border=True):
            st.markdown(f"**{title}**")
            st.write(text)
    st.page_link("app_pages/profile.py", label="Get started: 2-minute profile →", icon="🚀")
    st.stop()

st.title(f"Hi{', ' + profile.name if profile.name else ''} 👋")
st.caption("Here's where your money stands.")

metric_row(
    {"label": "Risk profile", "value": f"{plan['risk']['score']}/10", "delta": plan["risk"]["category"].title()},
    {"label": "Monthly surplus", "value": inr(plan["surplus"]), "delta": "income − expenses"},
    {"label": "Monthly SIPs", "value": inr(plan["projection"]["monthly_sip"]),
     "delta": f"+ {inr(plan['emergency']['monthly_contribution'])} to emergency fund"
     if plan["emergency"]["monthly_contribution"] else "emergency fund is full"},
    {"label": f"In {plan['projection']['years']} years", "value": inr_compact(plan["projection"]["future_value"]),
     "delta": f"~{pct(plan['projection']['expected_return'])}/yr, not guaranteed"},
)

left, right = st.columns(2, gap="medium")
with left.container(border=True):
    st.markdown("**Your asset allocation**")
    st.altair_chart(allocation_donut(plan["allocation"]["weights"]))
    st.page_link("app_pages/plan.py", label="Full plan →")

with right.container(border=True):
    if not spending:
        st.markdown("**Spending**")
        st.info("No transactions yet. Load the demo statement or import your own on the Expenses page.")
    else:
        s = spending["summary"]
        st.markdown(f"**Spending: {month_label(s['month'])}**")
        a, b, c = st.columns(3)
        a.metric("Income", inr(s["income_base"]))
        b.metric("Spent", inr(s["expense"] - s["invested"]))
        c.metric("Savings rate", pct(s["savings_rate"], 0))
        icons = {"danger": "🔴", "warning": "🟠", "info": "🔵", "success": "🟢"}
        for i in spending["insights"]["insights"][:4]:
            st.markdown(f"{icons[i['severity']]} {i['title']}")
    st.page_link("app_pages/expenses.py", label="Expenses →")

a, b = st.columns(2)
with a.container(border=True):
    st.page_link("app_pages/assistant.py", label="**Ask the assistant →**")
    st.caption('"Is my emergency fund enough?" · "What\'s Parag Parikh Flexi Cap\'s NAV today?" · '
               '"How much SIP for ₹20 lakh in 8 years?"')
with b.container(border=True):
    st.page_link("app_pages/learn.py", label="**Learn the basics →**")
    st.caption("13 short lessons with videos and quizzes: SIPs, index funds, FDs, tax, risk metrics and more.")
