"""The recommendation engine: profile + market snapshot -> a personalised monthly plan.

Steps (all deterministic; the AI only explains the result, it never invents numbers):
1. Monthly surplus = income - expenses.
2. Emergency fund first (6 months of expenses in a liquid fund).
3. Asset allocation from risk score, age and horizon (`allocation.py`).
4. Split the rest of the surplus into SIP sleeves, rounded to ₹100.
5. Fill each sleeve with the best-ranked funds for it (`funds.py`), direct stocks with the
   best-scored NIFTY 50 stocks (`stocks.py`), and the FD sleeve with the best FD (`fds.py`).
"""
from wealthwise.engine.allocation import (
    SLEEVE_ASSET, SLEEVE_LABEL, asset_allocation, emergency_plan, expected_return, monthly_split,
    sip_future_value, sleeve_weights,
)
from wealthwise.engine.fds import load_fd_rates, pick_fd
from wealthwise.engine.funds import SLEEVE_CATEGORIES, picks_for_sleeve, rank_funds
from wealthwise.engine.stocks import pick_stocks, score_stocks


def build_plan(profile: dict, snapshot: dict) -> dict:
    """`profile` has the Profile columns; `snapshot` is the market data (`market/data.py`)."""
    category, score = profile["risk_category"], profile["risk_score"]
    experience = profile["answers"].get("experience", 1)

    surplus = max(0.0, profile["monthly_income"] - profile["monthly_expenses"])
    emergency = emergency_plan(profile["monthly_expenses"], profile["current_savings"], surplus)
    investable = round(surplus - emergency["monthly_contribution"], 2)

    allocation = asset_allocation(score, category, profile["age"], profile["horizon_years"])
    split, notes = monthly_split(investable, sleeve_weights(allocation, category, experience))

    ranked_funds = rank_funds(snapshot["funds"])
    scored_stocks = score_stocks(snapshot["stocks"], category) if snapshot["stocks"] else []
    fd_rows, fd_as_of = load_fd_rates()
    fd = pick_fd(fd_rows, fd_as_of, profile["horizon_years"], profile["age"],
                 amount=max(split.get("fd", 0) * 12, 10000))

    sleeves = []
    for sleeve, amount in sorted(split.items(), key=lambda kv: -kv[1]):
        row = {"sleeve": sleeve, "label": SLEEVE_LABEL[sleeve], "asset": SLEEVE_ASSET[sleeve],
               "monthly": amount, "funds": [], "stocks": []}
        if sleeve in SLEEVE_CATEGORIES:
            row["funds"] = picks_for_sleeve(ranked_funds, sleeve, n=2)
        elif sleeve == "stocks":  # about ₹1,500 a month per stock, so each can buy whole shares
            row["stocks"] = pick_stocks(scored_stocks, n=max(1, min(5, int(amount // 1500))))
        sleeves.append(row)

    if emergency["monthly_contribution"]:
        notes.append(f"Once your emergency fund is full (in about {emergency['months_to_fill']} months), move the "
                     "money going into it to your SIPs, in the same proportions.")
        sleeves.insert(0, {"sleeve": "emergency", "label": "Emergency fund (liquid fund)", "asset": "liquid",
                           "monthly": emergency["monthly_contribution"],
                           "funds": picks_for_sleeve(ranked_funds, "liquid", n=1), "stocks": []})

    best_fd_rate = fd["best"]["rate"] / 100 if fd["best"] else None
    exp_return = expected_return(allocation["weights"], best_fd_rate)
    years = profile["horizon_years"]
    sip_total = sum(split.values())
    projection = {
        "years": years, "monthly_sip": sip_total, "expected_return": exp_return,
        "invested": round(sip_total * 12 * years),
        "future_value": round(sip_future_value(sip_total, years, exp_return)),
    }

    return {
        "risk": {"score": score, "category": category},
        "surplus": surplus,
        "emergency": emergency,
        "allocation": allocation,
        "sleeves": sleeves,
        "notes": notes,
        # Shown to everyone for learning; only part of the plan (the "stocks" sleeve) for experienced investors.
        "top_stocks": pick_stocks(scored_stocks, n=5),
        "stocks_in_plan": "stocks" in split,
        "fd": fd,
        "projection": projection,
        "market_updated_at": snapshot.get("updated_at"),
    }
