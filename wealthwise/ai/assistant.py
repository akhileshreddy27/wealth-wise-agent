"""The Wealth Wise assistant: a tool-using Gemini agent with RAG over the learning modules.

The loop is written out (rather than using the SDK's automatic function calling) so the app can
show which tools were used and cite the lesson sections an answer is based on.

Rule: the model never makes up figures. Prices, NAVs, plan amounts and spending all come from
tools; concepts come from the lessons via `search_knowledge`.
"""
import logging
from datetime import date

from google.genai import types
from sqlalchemy.orm import Session

from wealthwise import services
from wealthwise.ai.gemini import AIUnavailable, generate
from wealthwise.engine.allocation import sip_future_value
from wealthwise.engine.stocks import score_stocks
from wealthwise.market.data import live_fund_nav, live_stock_quote, load_snapshot
from wealthwise.rag.knowledge import get_knowledge_base

log = logging.getLogger(__name__)
MAX_STEPS = 6
INFLATION = 0.06

SYSTEM = """You are Wealth Wise, a friendly personal-finance assistant for Indian users. Today is {today}.

How to answer:
- For concepts (SIPs, FDs, tax, risk ...), call search_knowledge first and base your answer on it.
  Cite the sections you used inline as [1], [2] using the numbers in the tool result.
- For live prices or NAVs, call get_stock_quote or get_fund_nav. For the user's own plan or spending,
  call get_my_plan or get_my_spending. To judge a NIFTY 50 stock, call get_stock_score.
  For "how much should I invest to reach X in N years", call plan_goal.
- Never invent numbers. Every figure you state must come from a tool result.
- Amounts are in rupees; write them the Indian way (₹1,50,000; ₹2.5 lakh).
- Be concise: short paragraphs or bullets, under 200 words unless asked for more.
- You are an educational tool, not a SEBI-registered adviser. For big decisions, say so briefly.
"""


class Agent:
    """One conversation turn. Tools are methods so they can reach the database and collect sources."""

    def __init__(self, db: Session, client_id: str):
        self.db, self.client_id = db, client_id
        self.sources: list[dict] = []
        self.tools_used: list[dict] = []

    # ----- tools (signature + docstring = the schema Gemini sees) -----

    def search_knowledge(self, query: str) -> dict:
        """Search Wealth Wise's lessons on personal finance in India (budgeting, emergency fund, SIPs,
        mutual funds, index funds, FDs, asset allocation, tax saving, capital gains, stock and risk metrics,
        goal planning). Returns numbered passages to cite as [n]."""
        passages = []
        for hit in get_knowledge_base().search(query, k=4):
            known = next((s for s in self.sources if s["id"] == hit["id"]), None)
            if not known:
                known = {"n": len(self.sources) + 1, **{k: hit[k] for k in ("id", "module_id", "module_title", "section")}}
                self.sources.append(known)
            passages.append({"n": known["n"], "lesson": hit["module_title"], "section": hit["section"], "text": hit["text"]})
        return {"passages": passages}

    def get_stock_quote(self, symbol: str) -> dict:
        """Live price and today's change for an NSE stock. `symbol` is the NSE ticker, e.g. TCS, INFY, HDFCBANK."""
        return live_stock_quote(symbol)

    def get_fund_nav(self, fund_name: str) -> dict:
        """Latest NAV and 1/3/5-year returns of an Indian mutual fund (Direct-Growth plan),
        e.g. "Parag Parikh Flexi Cap Fund"."""
        return live_fund_nav(fund_name)

    def get_stock_score(self, symbol: str) -> dict:
        """Wealth Wise's factor score (value, quality, momentum, low volatility; 0-100) for a NIFTY 50 stock,
        judged for this user's risk profile, with its key metrics."""
        snap = load_snapshot()
        profile = services.get_profile(self.db, self.client_id)
        scored = score_stocks(snap["stocks"], profile.risk_category if profile else "moderate")
        symbol = symbol.strip().upper().removesuffix(".NS")
        for rank, s in enumerate(scored, 1):
            if s["symbol"] == symbol:
                return {**s, "rank_in_nifty50": rank, "data_as_of": snap["updated_at"]}
        return {"error": f"{symbol} is not in the NIFTY 50 universe Wealth Wise scores."}

    def plan_goal(self, target_amount_today: float, years: int) -> dict:
        """Monthly SIP needed to reach a goal. `target_amount_today` is the goal's cost in today's rupees
        (it is inflated at 6% a year); the return assumed depends on how far away the goal is."""
        years = max(1, int(years))
        future_target = target_amount_today * (1 + INFLATION) ** years
        annual_return = 0.07 if years < 3 else 0.09 if years < 7 else 0.12  # debt-like / balanced / equity-like
        per_rupee = sip_future_value(1, years, annual_return)
        monthly = future_target / per_rupee
        profile = services.get_profile(self.db, self.client_id)
        surplus = max(0.0, profile.monthly_income - profile.monthly_expenses) if profile else None
        return {"target_today": round(target_amount_today), "target_in_future_rupees": round(future_target),
                "inflation_assumed": INFLATION, "years": years, "return_assumed": annual_return,
                "monthly_sip_needed": round(monthly, -2), "total_invested": round(monthly * 12 * years, -3),
                "user_monthly_surplus": surplus}

    def get_my_plan(self) -> dict:
        """The user's personalised monthly investment plan: risk profile, emergency fund, asset allocation,
        SIP amounts per sleeve with recommended funds, best FD, and a projection."""
        plan = services.current_plan(self.db, self.client_id)
        if not plan:
            return {"error": "The user hasn't filled in their profile yet. Ask them to complete it on the Profile page."}
        return {
            "risk": plan["risk"], "monthly_surplus": plan["surplus"], "emergency_fund": plan["emergency"],
            "allocation": plan["allocation"]["weights"], "why_this_allocation": plan["allocation"]["rationale"],
            "monthly_sips": [{"sleeve": s["label"], "monthly": s["monthly"],
                              "funds": [f["short_name"] for f in s["funds"]],
                              "stocks": [st["symbol"] for st in s["stocks"]]} for s in plan["sleeves"]],
            "best_fd": plan["fd"]["best"], "projection": plan["projection"],
        }

    def get_my_spending(self, month: str) -> dict:
        """The user's spending summary and savings insights for a month. `month` is YYYY-MM,
        or "latest" for the most recent month with transactions."""
        data = services.spending(self.db, self.client_id, None if month in ("", "latest") else month)
        if not data:
            return {"error": "No transactions yet. The user can add some on the Expenses page."}
        s = data["summary"]
        return {
            "month": s["month"], "income": s["income_base"], "spent": s["expense"], "invested": s["invested"],
            "savings_rate": s["savings_rate"], "rule_50_30_20_share": s["bucket_share"],
            "top_categories": [{"category": c["label"], "amount": c["amount"], "budget": c["budget"]}
                               for c in s["categories"][:6]],
            "insights": [f"{i['title']}: {i['detail']}" for i in data["insights"]["insights"]],
        }

    @property
    def tools(self):
        return [self.search_knowledge, self.get_stock_quote, self.get_fund_nav, self.get_stock_score,
                self.plan_goal, self.get_my_plan, self.get_my_spending]

    def call_tool(self, name: str, args: dict) -> dict:
        fn = {t.__name__: t for t in self.tools}.get(name)
        self.tools_used.append({"name": name, "args": args})
        if not fn:
            return {"error": f"Unknown tool {name}"}
        try:
            return fn(**args)
        except Exception as e:  # network errors, bad symbols: let the model say so
            log.warning("tool %s failed: %s", name, e)
            return {"error": f"{name} failed: {e}"}

    # ----- the loop -----

    def run(self, messages: list[dict]) -> str:
        contents = [types.Content(role="user" if m["role"] == "user" else "model", parts=[types.Part(text=m["content"])])
                    for m in messages]
        system = SYSTEM.format(today=date.today().isoformat())
        for _ in range(MAX_STEPS):
            response = generate(contents, system, tools=self.tools)
            calls = response.function_calls
            if not calls:
                return response.text or "Sorry, I couldn't come up with an answer. Try rephrasing?"
            contents.append(response.candidates[0].content)  # keeps the model's thought signatures
            contents.append(types.Content(role="user", parts=[
                types.Part(function_response=types.FunctionResponse(
                    id=call.id, name=call.name, response={"result": self.call_tool(call.name, dict(call.args or {}))}))
                for call in calls]))
        return "I needed too many steps for that one. Could you ask a narrower question?"


def chat(db: Session, client_id: str, messages: list[dict]) -> dict:
    """Answer the last user message. Without an API key, falls back to plain lesson search."""
    agent = Agent(db, client_id)
    try:
        reply = agent.run(messages)
        mode = "ai"
        cited = [s for s in agent.sources if f"[{s['n']}]" in reply]
        agent.sources = cited  # show only the lesson sections the answer actually cites
    except AIUnavailable:
        hits = agent.search_knowledge(messages[-1]["content"])["passages"][:2]
        reply = ("AI answers are off (no `GEMINI_API_KEY` set), so here is what the lessons say:\n\n"
                 + "\n\n".join(f"**{h['lesson']}: {h['section']}** [{h['n']}]\n\n{h['text']}" for h in hits))
        agent.sources = agent.sources[:2]
        mode = "search"
    return {"reply": reply, "sources": agent.sources, "tools_used": agent.tools_used, "mode": mode}
