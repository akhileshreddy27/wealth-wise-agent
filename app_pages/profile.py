"""Profile: finances + the 5-question risk questionnaire -> risk score (drives every recommendation)."""
from datetime import datetime, timezone

import streamlit as st

from app_pages.common import db_session, visitor_id
from wealthwise import services
from wealthwise.db import Profile
from wealthwise.engine.risk import QUESTIONNAIRE, compute_risk

vid = visitor_id()
with db_session() as db:
    saved = services.get_profile(db, vid)
    current = services.profile_dict(saved) if saved else None

st.title("Your profile" if current else "Set up your profile")
st.caption("Your answers set your risk score (1–10), which drives every recommendation.")

p = current or {"name": "", "age": 25, "monthly_income": 60000, "monthly_expenses": 35000, "current_savings": 100000,
                "horizon_years": 10, "dependents": 0, "answers": {}}

with st.form("profile"):
    left, right = st.columns([2, 3], gap="large")
    with left:
        st.subheader("Your finances")
        name = st.text_input("Name (optional)", p["name"], max_chars=80)
        age = st.number_input("Age", 18, 90, p["age"])
        income = st.number_input("Monthly take-home income (₹)", 0, 10_000_000, int(p["monthly_income"]), step=1000)
        expenses = st.number_input("Monthly expenses (₹)", 0, 10_000_000, int(p["monthly_expenses"]), step=1000,
                                   help="Everything you spend in a month, excluding SIPs and investments.")
        savings = st.number_input("Savings you can access (₹)", 0, 1_000_000_000, int(p["current_savings"]), step=1000,
                                  help="Bank balance, FDs, liquid funds.")
        horizon = st.number_input("Investment horizon (years)", 1, 40, p["horizon_years"],
                                  help="When will you need most of this money?")
        dependents = st.number_input("People who depend on your income", 0, 10, p["dependents"])
    with right:
        st.subheader("Risk questionnaire")
        answers = {}
        for i, q in enumerate(QUESTIONNAIRE, 1):
            previous = p["answers"].get(q["id"])
            choice = st.radio(f"{i}. {q['question']}", q["options"], key=f"q_{q['id']}",
                              index=previous - 1 if previous else None)
            answers[q["id"]] = q["options"].index(choice) + 1 if choice else None
    submitted = st.form_submit_button("Save and see my plan", type="primary")

if submitted:
    if None in answers.values():
        st.error("Please answer all five questions.")
    else:
        score, category = compute_risk(answers, age, horizon, dependents, expenses, savings)
        with db_session() as db:
            row = services.get_profile(db, vid) or Profile(client_id=vid)
            row.name, row.age, row.monthly_income, row.monthly_expenses = name, age, income, expenses
            row.current_savings, row.horizon_years, row.dependents, row.answers = savings, horizon, dependents, answers
            row.risk_score, row.risk_category, row.updated_at = score, category, datetime.now(timezone.utc)
            db.add(row)
            db.commit()
        st.switch_page("app_pages/plan.py")
