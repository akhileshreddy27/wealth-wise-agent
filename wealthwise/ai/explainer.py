"""Plan explainer agent: turns the engine's plan (numbers + rationale) into a short, personal explanation.

The model only rephrases what the engine computed; without an API key the same facts are
stitched together by rules, so the feature always works.
"""
import json

from wealthwise.ai.gemini import AIUnavailable, generate
from wealthwise.expenses.analytics import inr

SYSTEM = """You explain an investment plan to an Indian retail investor in plain, warm English.
Use ONLY the numbers in the plan JSON; never compute or invent new figures.
Structure (markdown, under 220 words):
1. One sentence on their risk profile and what it means.
2. "Why this mix": 2-3 bullets on the allocation, using the rationale given.
3. "This month": what to do first (emergency fund if any, then the SIPs).
4. One honest caveat (markets go down; this is educational, not SEBI-registered advice)."""


def _compact(plan: dict) -> dict:
    """The facts the model may use. Rupee amounts are pre-formatted (₹1,10,000) so it quotes them as-is."""
    em, proj, fd = plan["emergency"], plan["projection"], plan["fd"]["best"]
    return {
        "risk": plan["risk"], "monthly_surplus": inr(plan["surplus"]),
        "emergency_fund": {"fully_funded": em["ok"], "target": inr(em["target"]), "still_needed": inr(em["shortfall"]),
                           "monthly_contribution": inr(em["monthly_contribution"]), "months_to_fill": em["months_to_fill"]},
        "allocation_percent": {k: round(v * 100) for k, v in plan["allocation"]["weights"].items()},
        "rationale": plan["allocation"]["rationale"],
        "monthly_sips": [{"what": s["label"], "monthly": inr(s["monthly"]),
                          "picks": [f["short_name"] for f in s["funds"]] + [st["symbol"] for st in s["stocks"]]}
                         for s in plan["sleeves"]],
        "best_fd": fd and {"bank": fd["bank"], "rate": f"{fd['rate']}%"},
        "projection": {"years": proj["years"], "monthly_sip": inr(proj["monthly_sip"]),
                       "assumed_return": f"{proj['expected_return']:.1%} a year", "total_invested": inr(proj["invested"]),
                       "could_grow_to": inr(proj["future_value"])},
        "notes": plan["notes"],
    }


def rule_based(plan: dict) -> str:
    risk, em, proj = plan["risk"], plan["emergency"], plan["projection"]
    lines = [f"Your risk score is **{risk['score']}/10 ({risk['category']})**.", "", "**Why this mix**"]
    lines += [f"- {r}" for r in plan["allocation"]["rationale"]]
    lines += ["", "**This month**"]
    if em["monthly_contribution"]:
        lines.append(f"- First, put {inr(em['monthly_contribution'])} into your emergency fund "
                     f"({inr(em['shortfall'])} still to go to reach 6 months of expenses).")
    for s in plan["sleeves"]:
        if s["sleeve"] != "emergency":
            lines.append(f"- {inr(s['monthly'])} into {s['label'].lower()}.")
    if proj["monthly_sip"]:
        lines += ["", f"At an assumed {proj['expected_return']:.1%} a year, {inr(proj['monthly_sip'])}/month for "
                      f"{proj['years']} years could grow to about {inr(proj['future_value'])} "
                      f"(you invest {inr(proj['invested'])}). Markets can fall; this is not guaranteed."]
    return "\n".join(lines)


def explain_plan(plan: dict) -> dict:
    try:
        response = generate(json.dumps(_compact(plan), default=str), SYSTEM, temperature=0.4)
        return {"text": response.text, "mode": "ai"}
    except AIUnavailable:
        return {"text": rule_based(plan), "mode": "rules"}
