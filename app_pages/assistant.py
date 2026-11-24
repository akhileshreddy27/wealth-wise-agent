"""The AI assistant: a Gemini tool-calling agent with RAG over the lessons and live market data."""
import streamlit as st

from app_pages.common import allow_ai_call, db_session, visitor_id
from wealthwise.ai.assistant import chat
from wealthwise.config import settings

SUGGESTIONS = [
    "Explain my plan in simple words",
    "What is the NAV of Parag Parikh Flexi Cap Fund today?",
    "How much SIP do I need for ₹20 lakh in 8 years?",
    "Where am I overspending?",
    "Is HDFCBANK a good pick for me?",
    "FD or debt fund for money I need in 2 years?",
]
TOOL_LABEL = {
    "search_knowledge": "📚 searched lessons", "get_stock_quote": "📈 live stock price", "get_fund_nav": "📊 live fund NAV",
    "get_stock_score": "🧮 stock score", "plan_goal": "🎯 goal calculator", "get_my_plan": "🗂️ your plan",
    "get_my_spending": "💳 your spending",
}

vid = visitor_id()
history: list[dict] = st.session_state.setdefault("chat", [])

head, reset = st.columns([5, 1], vertical_alignment="bottom")
head.title("Assistant")
head.caption("Gemini agent with tools: your plan and spending, live NSE prices and AMFI NAVs, and the lessons (cited)."
             if settings.ai_enabled else
             "AI is off (no GEMINI_API_KEY), so answers come straight from the lessons.")
if history and reset.button("New chat", icon=":material/refresh:"):
    history.clear()
    st.rerun()


def show_answer(turn: dict) -> None:
    st.markdown(turn["content"])
    meta = turn.get("meta")
    if not meta:
        return
    tools = list(dict.fromkeys(t["name"] for t in meta["tools_used"]))
    if tools:
        st.caption("Used: " + " · ".join(TOOL_LABEL.get(t, t) for t in tools))
    if meta["sources"]:
        links = [f"[[{s['n']}] {s['module_title']}: {s['section']}](learn?lesson={s['module_id']}&u={vid})"
                 for s in meta["sources"]]
        st.caption("Sources: " + " · ".join(links))


for turn in history:
    with st.chat_message(turn["role"]):
        show_answer(turn) if turn["role"] == "assistant" else st.markdown(turn["content"])

question = st.chat_input("Ask about SIPs, your plan, a stock, your spending…")
if not history and not question:
    question = st.pills("Try one of these:", SUGGESTIONS, key="suggestion")

if question:
    with st.chat_message("user"):
        st.markdown(question)
    history.append({"role": "user", "content": question})
    with st.chat_message("assistant"):
        if settings.ai_enabled and not allow_ai_call():
            history.pop()
            st.stop()
        with st.spinner("Thinking… (looking things up can take 10–30 seconds)"):
            try:
                with db_session() as db:
                    reply = chat(db, vid, [{"role": t["role"], "content": t["content"]} for t in history[-20:]])
            except Exception as e:  # quota / network errors from Gemini
                history.pop()
                st.error(f"The AI service failed: {e}")
                st.stop()
        turn = {"role": "assistant", "content": reply["reply"], "meta": reply}
        show_answer(turn)
    history.append(turn)
