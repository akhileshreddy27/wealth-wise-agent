"""Tests run offline on a throwaway SQLite database with AI switched off (tests that need the
model swap in `FakeGemini`)."""
import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp())
os.environ["DATABASE_URL"] = f"sqlite:///{(_tmp / 'test.db').as_posix()}"
os.environ["GEMINI_API_KEY"] = ""

import pytest  # noqa: E402

from wealthwise.db import Base, engine  # noqa: E402

PROFILE = {"name": "Test", "age": 26, "monthly_income": 80000, "monthly_expenses": 45000, "current_savings": 300000,
           "horizon_years": 10, "dependents": 0,
           "answers": {"market_drop": 3, "primary_goal": 3, "experience": 3, "return_vs_risk": 3, "income_stability": 3}}


def stock(symbol, sector, **kw):
    base = {"symbol": symbol, "name": symbol.title(), "sector": sector, "price": 100.0, "market_cap": 1e12,
            "pe": 20.0, "pb": 3.0, "roe": 0.15, "debt_to_equity": 0.5, "profit_margin": 0.12,
            "return_6m": 0.05, "return_1y": 0.10, "volatility_1y": 0.22, "beta_1y": 0.9}
    return base | kw


def fund(code, name, category, **kw):
    base = {"scheme_code": code, "name": f"{name} - Direct Plan - Growth", "fund_house": "AMC", "category": category,
            "return_1y": 0.1, "cagr_3y": 0.14, "cagr_5y": 0.15, "volatility_3y": 0.14, "sharpe_3y": 0.9,
            "sortino_3y": 1.2, "max_drawdown_3y": -0.15, "rolling_1y_positive_pct": 0.85}
    return base | kw


@pytest.fixture
def snapshot():
    return {
        "updated_at": "2026-11-24T00:00:00+00:00",
        "stocks": [stock("AAA", "Tech", roe=0.30, return_1y=0.25), stock("BBB", "Tech", roe=0.25),
                   stock("CCC", "Tech", roe=0.28), stock("DDD", "Banks", pe=12.0),
                   stock("EEE", "Energy", volatility_1y=0.45, beta_1y=1.6, return_1y=0.6),
                   stock("FFF", "FMCG", pe=-5.0)],
        "funds": [fund(1, "Alpha Nifty 50 Index Fund", "Index"), fund(2, "Beta Nifty 50 Index Fund", "Index", sharpe_3y=0.7),
                  fund(3, "Gamma Flexi Cap Fund", "Flexi Cap"), fund(4, "Delta Mid Cap Fund", "Mid Cap"),
                  fund(5, "Eps Small Cap Fund", "Small Cap"), fund(6, "Zeta Corporate Bond Fund", "Debt"),
                  fund(7, "Eta Liquid Fund", "Liquid"), fund(8, "Theta Balanced Advantage Fund", "Hybrid")],
    }


@pytest.fixture
def fresh_db(snapshot, monkeypatch):
    """Empty tables, and the small synthetic market snapshot instead of data/market.json."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    monkeypatch.setattr("wealthwise.services.load_snapshot", lambda: snapshot)
    yield
