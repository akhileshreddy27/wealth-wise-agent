"""My Plan: the recommendation engine's output, with an AI explanation."""
import pandas as pd
import streamlit as st

from app_pages.charts import allocation_donut
from app_pages.common import ago, allow_ai_call, db_session, inr, inr_compact, metric_row, pct, visitor_id
from wealthwise import services
from wealthwise.ai.explainer import explain_plan
from wealthwise.config import settings
from wealthwise.market.data import refresh_if_stale

vid = visitor_id()
with db_session() as db:
    plan = services.current_plan(db, vid)

if not plan:
    st.title("Your investment plan")
    st.info("Answer five questions and your plan appears here.")
    st.page_link("app_pages/profile.py", label="Set up your profile →", icon="📝")
    st.stop()

head, button = st.columns([4, 1], vertical_alignment="bottom")
head.title("Your investment plan")
head.caption(f"Built by Wealth Wise's scoring engine from NSE and AMFI data · updated {ago(plan['market_updated_at'])}")
if button.button("Refresh market data", icon=":material/refresh:"):
    with st.spinner("Downloading prices and NAVs (about 30 seconds)…"):
        try:
            _, refreshed = refresh_if_stale(settings.market_refresh_min_minutes)
            st.toast("Market data updated." if refreshed else
                     f"Already up to date (refreshes at most every {settings.market_refresh_min_minutes} min).")
            if refreshed:
                st.rerun()
        except Exception as e:
            st.error(f"Refresh failed: {e}")

em, proj = plan["emergency"], plan["projection"]
metric_row(
    {"label": "Risk score", "value": f"{plan['risk']['score']}/10", "delta": plan["risk"]["category"].title()},
    {"label": "Invest each month", "value": inr(plan["surplus"]), "delta": "your monthly surplus"},
    {"label": "Emergency fund", "value": "Fully funded" if em["ok"] else inr(em["shortfall"]),
     "delta": f"target {inr(em['target'])}" if em["ok"] else f"still needed · ~{em['months_to_fill']} months"},
    {"label": f"Projected in {proj['years']} yrs", "value": inr_compact(proj["future_value"]),
     "delta": f"{inr_compact(proj['invested'])} invested · ~{pct(proj['expected_return'])}/yr"},
)

left, right = st.columns([2, 3], gap="medium")
with left.container(border=True):
    st.markdown("**Asset allocation**: why your money is split this way")
    st.altair_chart(allocation_donut(plan["allocation"]["weights"]))
    for reason in plan["allocation"]["rationale"]:
        st.markdown(f"- {reason}")

with right.container(border=True):
    st.markdown("**✨ Explain my plan**")
    st.caption("The AI explainer agent puts the engine's numbers into plain words. It never makes up figures.")
    if st.button("Explain my plan", type="primary") and allow_ai_call():
        with st.spinner("Writing your explanation…"):
            st.session_state.explanation = explain_plan(plan)
    if "explanation" in st.session_state:
        result = st.session_state.explanation
        st.badge("Gemini" if result["mode"] == "ai" else "Rule-based", color="green" if result["mode"] == "ai" else "gray")
        st.markdown(result["text"])

st.subheader("Monthly plan")
st.caption("What to invest in each month, with the top-ranked funds for each part. Expand a row for the reasons.")
for sleeve in plan["sleeves"]:
    picks = [f["short_name"] for f in sleeve["funds"]] + [s["symbol"] for s in sleeve["stocks"]]
    if sleeve["sleeve"] == "fd" and plan["fd"]["best"]:
        picks = [f"{plan['fd']['best']['bank']} at {plan['fd']['best']['rate']}%"]
    with st.expander(f"**{inr(sleeve['monthly'])}/month** · {sleeve['label']} · {', '.join(picks)}"):
        if sleeve["funds"]:
            for col, f in zip(st.columns(len(sleeve["funds"])), sleeve["funds"]):
                with col.container(border=True):
                    st.markdown(f"**{f['short_name']}** · score {f['score']:.0f}/100")
                    st.caption(f"{f['category']} · #{f['rank_in_category']} of {f['peers']} in {f['peer_group']}")
                    m = f["metrics"]
                    st.markdown(f"3Y CAGR **{pct(m['cagr_3y'])}** · Sharpe **{m['sharpe_3y'] or '–'}** · "
                                f"max fall **{pct(m['max_drawdown_3y'])}**")
                    for r in f["reasons"]:
                        st.markdown(f":green[▲ {r}]")
                    for c in f["cautions"]:
                        st.markdown(f":orange[▼ {c}]")
        if sleeve["stocks"]:
            st.write(f"About {inr(sleeve['monthly'] / len(sleeve['stocks']))} a month for each of "
                     f"{', '.join(s['symbol'] for s in sleeve['stocks'])}. Buy whole shares as the money builds up; "
                     "scores are in the stocks table below.")
        if sleeve["sleeve"] == "fd":
            st.write("Save this up and open an FD each year; the FD card below has the rate and maturity value.")
for note in plan["notes"]:
    st.info(note, icon="ℹ️")

left, right = st.columns([3, 2], gap="medium")
with left.container(border=True):
    st.markdown("**Top NIFTY 50 stocks for your profile**")
    st.caption("Your direct-stock money goes into the top picks (one stock per ~₹1,500 a month)." if plan["stocks_in_plan"]
               else "For learning: your plan uses funds only, since direct stocks suit experienced investors.")
    rows = [{"Stock": s["symbol"], "Sector": s["sector"], "Score": s["score"], "Quality": s["factors"]["quality"],
             "Value": s["factors"]["value"], "Momentum": s["factors"]["momentum"], "Low vol": s["factors"]["low_vol"],
             "P/E": s["metrics"]["pe"], "Why": "; ".join(s["reasons"] + s["cautions"])} for s in plan["top_stocks"]]
    bar = lambda label: st.column_config.ProgressColumn(label, min_value=0, max_value=100, format="%d")  # noqa: E731
    st.dataframe(pd.DataFrame(rows), hide_index=True, column_config={
        "Score": st.column_config.NumberColumn(format="%.0f"), "Quality": bar("Quality"), "Value": bar("Value"),
        "Momentum": bar("Momentum"), "Low vol": bar("Low vol"), "P/E": st.column_config.NumberColumn(format="%.1f")})
    st.caption("Score = weighted percentile of value (P/E, P/B), quality (ROE, debt, margin), momentum (6M/1Y return) "
               "and low volatility, with weights set by your risk profile. Max two stocks per sector.")

fd = plan["fd"]
with right.container(border=True):
    st.markdown("**Best fixed deposit for you**")
    st.caption(f"{round(fd['tenure_days'] / 365)}-year tenure · on {inr(fd['amount'])} · rates as of {fd['as_of']} (indicative)")
    if fd["best"]:
        best = fd["best"]
        st.metric(best["bank"], f"{best['rate']}%", f"matures to {inr(best['maturity_value'])}", delta_arrow="off")
        if fd["safest"]:
            st.write(f"Bigger-bank option: **{fd['safest']['bank']}** at {fd['safest']['rate']}%.")
        st.dataframe(pd.DataFrame([{"Bank": q["bank"], "Rate %": q["rate"]} for q in fd["alternatives"]]), hide_index=True)
        for n in fd["notes"]:
            st.caption(n)
