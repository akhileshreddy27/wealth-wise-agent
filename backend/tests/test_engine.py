import pytest

from app.engine.allocation import asset_allocation, emergency_plan, monthly_split, sip_future_value
from app.engine.fds import load_fd_rates, pick_fd
from app.engine.funds import picks_for_sleeve, rank_funds, short_name
from app.engine.plan import build_plan
from app.engine.ranking import percentiles
from app.engine.risk import compute_risk
from app.engine.stocks import pick_stocks, score_stocks
from tests.conftest import PROFILE

BOLD = {"market_drop": 4, "primary_goal": 4, "experience": 4, "return_vs_risk": 4, "income_stability": 4}


def test_capacity_caps_bold_answers():
    young, _ = compute_risk(BOLD, age=25, horizon_years=15, dependents=0, monthly_expenses=40000, current_savings=300000)
    near_retirement, category = compute_risk(BOLD, age=58, horizon_years=2, dependents=3,
                                             monthly_expenses=40000, current_savings=50000)
    assert young == 10
    assert near_retirement < young and category != "aggressive"


def test_missing_answers_rejected():
    with pytest.raises(ValueError):
        compute_risk({"market_drop": 3}, 30, 10, 0, 40000, 100000)


def test_short_horizon_means_no_equity():
    alloc = asset_allocation(risk_score=9, risk_category="aggressive", age=30, horizon_years=2)
    assert alloc["weights"]["equity"] == 0
    assert sum(alloc["weights"].values()) == pytest.approx(1)
    assert any("horizon" in r for r in alloc["rationale"])


def test_age_cap():
    assert asset_allocation(10, "aggressive", age=60, horizon_years=10)["weights"]["equity"] == 0.5


def test_emergency_fund_first():
    em = emergency_plan(monthly_expenses=40000, current_savings=60000, investable=30000)
    assert em["shortfall"] == 180000 and em["monthly_contribution"] == 15000  # big gap: half the surplus
    assert emergency_plan(40000, 240000, 30000)["ok"]


def test_small_sleeves_merged():
    split, notes = monthly_split(5000, {"core": 0.8, "small": 0.05, "fd": 0.15})
    assert "small" not in split and sum(split.values()) == 5000
    assert notes


def test_sip_future_value():
    # ₹10,000/month for 10 years at 12% ≈ ₹23.2 lakh (the figure quoted in the SIP lesson)
    assert sip_future_value(10000, 10, 0.12) == pytest.approx(2_323_391, rel=1e-3)


def test_percentiles_ties_and_direction():
    assert percentiles([1, 2, 2, 3]) == [0.0, 0.5, 0.5, 1.0]
    assert percentiles([10, None, 30], higher_is_better=False) == [1.0, None, 0.0]


def test_stock_risk_filter_and_sector_cap(snapshot):
    conservative = score_stocks(snapshot["stocks"], "conservative")
    assert not next(s for s in conservative if s["symbol"] == "EEE")["eligible"]   # too volatile
    picks = pick_stocks(score_stocks(snapshot["stocks"], "aggressive"), n=5, max_per_sector=2)
    assert sum(p["sector"] == "Tech" for p in picks) == 2
    loss_maker = next(s for s in conservative if s["symbol"] == "FFF")
    assert "loss-making" in " ".join(loss_maker["cautions"])


def test_funds_ranked_within_sleeve(snapshot):
    ranked = rank_funds(snapshot["funds"])
    core = picks_for_sleeve(ranked, "core")
    assert [f["scheme_code"] for f in core] == [1, 2]       # higher Sharpe first
    assert all(f["category"] != "Mid Cap" for f in core)
    assert short_name("SBI LIQUID FUND - DIRECT PLAN - GROWTH") == "SBI Liquid Fund"


def test_fd_pick_matches_horizon_and_flags_small_finance_banks():
    rows, as_of = load_fd_rates()
    fd = pick_fd(rows, as_of, horizon_years=3, age=30)
    assert fd["tenure_days"] == 3 * 365
    assert all(q["rate"] <= fd["best"]["rate"] for q in fd["alternatives"])
    senior = pick_fd(rows, as_of, horizon_years=3, age=65)
    assert senior["best"]["rate"] >= fd["best"]["rate"]


def test_build_plan(snapshot):
    profile = PROFILE | {"risk_score": 6, "risk_category": "moderate"}
    plan = build_plan(profile, snapshot)
    assert plan["surplus"] == 35000
    assert plan["emergency"]["ok"]                               # 3 lakh covers 6 x 45k
    assert sum(s["monthly"] for s in plan["sleeves"]) == pytest.approx(35000, abs=100)
    assert plan["stocks_in_plan"]                                # experience 3 -> some direct stocks
    assert all(s["funds"] for s in plan["sleeves"] if s["sleeve"] not in ("stocks", "fd"))
    assert plan["projection"]["future_value"] > plan["projection"]["invested"]
