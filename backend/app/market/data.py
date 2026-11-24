"""Market data.

Two kinds:
- **Snapshot** (`data/market.json`): NIFTY 50 stocks and curated funds with fundamentals and risk
  metrics, used by the recommendation engine. Built by `python -m app.market.data` (about a minute)
  or the Refresh button in the app. Sources: Yahoo Finance via yfinance, and mfapi.in (AMFI NAVs).
- **Live** quotes for the chatbot: one stock or one fund, fetched on demand.
"""
import json
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import httpx
import pandas as pd
import yfinance as yf

from app.config import DATA_DIR, settings
from app.engine import metrics as m
from app.market.universe import FUND_QUERIES, NIFTY50, NIFTY_INDEX

log = logging.getLogger(__name__)
SNAPSHOT_FILE = DATA_DIR / "market.json"
MFAPI = "https://api.mfapi.in/mf"


# ---------- stocks (Yahoo Finance) ----------

def yahoo_symbol(symbol: str) -> str:
    return symbol if symbol.startswith("^") or "." in symbol else f"{symbol}.NS"


def fetch_closes(symbols: list[str], period: str = "5y") -> dict[str, pd.Series]:
    """Adjusted daily closes for many symbols in one request."""
    tickers = [yahoo_symbol(s) for s in symbols]
    df = yf.download(tickers, period=period, interval="1d", auto_adjust=True, progress=False,
                     group_by="ticker", threads=True)
    out: dict[str, pd.Series] = {}
    for sym, tk in zip(symbols, tickers):
        try:
            close = (df[tk]["Close"] if isinstance(df.columns, pd.MultiIndex) else df["Close"]).dropna()
        except KeyError:
            continue
        if len(close):
            close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
            out[sym] = close.astype(float)
    return out


def fetch_info(symbol: str) -> dict:
    try:
        return yf.Ticker(yahoo_symbol(symbol)).info or {}
    except Exception as e:  # yfinance raises many kinds of errors on bad symbols and rate limits
        log.warning("info failed for %s: %s", symbol, e)
        return {}


def _pct(info: dict, key: str) -> float | None:
    """yfinance returns some ratios as percentages (debtToEquity 45.2 means 0.452)."""
    v = info.get(key)
    return None if v is None else float(v) / 100


def build_stock_row(symbol: str, info: dict, closes: pd.Series, index_closes: pd.Series | None) -> dict:
    rf = settings.risk_free_rate
    last_year = m.window(closes, 365)
    return {
        "symbol": symbol,
        "name": info.get("longName") or info.get("shortName") or symbol,
        "sector": info.get("sector"),
        "price": m.clean(float(closes.iloc[-1]), 2),
        "market_cap": info.get("marketCap"),
        "pe": m.clean(info.get("trailingPE"), 2),
        "pb": m.clean(info.get("priceToBook"), 2),
        "roe": m.clean(info.get("returnOnEquity")),
        "debt_to_equity": m.clean(_pct(info, "debtToEquity")),
        "profit_margin": m.clean(info.get("profitMargins")),
        "dividend_yield": m.clean(_pct(info, "dividendYield")),
        "return_6m": m.clean(m.trailing_return(closes, 182)),
        "return_1y": m.clean(m.trailing_return(closes, 365)),
        "cagr_3y": m.clean(m.cagr(closes, 3)),
        "volatility_1y": m.clean(m.volatility(last_year)),
        "max_drawdown_1y": m.clean(m.max_drawdown(last_year)),
        "sharpe_1y": m.clean(m.sharpe(last_year, rf), 2),
        "beta_1y": m.clean(m.beta(last_year, m.window(index_closes, 365)), 2) if index_closes is not None else None,
    }


def refresh_stocks() -> tuple[list[dict], list[str]]:
    closes = fetch_closes(NIFTY50 + [NIFTY_INDEX])
    index = closes.get(NIFTY_INDEX)
    symbols = [s for s in NIFTY50 if s in closes]
    with ThreadPoolExecutor(8) as pool:
        infos = dict(zip(symbols, pool.map(fetch_info, symbols)))
    rows = [build_stock_row(s, infos[s], closes[s], index) for s in symbols]
    return rows, [s for s in NIFTY50 if s not in closes]


# ---------- mutual funds (mfapi.in) ----------

_EXCLUDE = re.compile(r"idcw|dividend|bonus|segregated|regular|payout|reinvest", re.I)
CATEGORY_RULES = [  # AMFI scheme_category -> app category, first match wins
    ("Index", ["index fund", "etf"]),
    ("ELSS", ["elss"]),
    ("Large Cap", ["large cap fund"]),
    ("Large & Mid Cap", ["large & mid cap"]),
    ("Flexi Cap", ["flexi cap"]),
    ("Multi Cap", ["multi cap"]),
    ("Mid Cap", ["mid cap fund"]),
    ("Small Cap", ["small cap fund"]),
    ("Hybrid", ["hybrid", "balanced advantage", "dynamic asset", "equity savings", "arbitrage"]),
    ("Liquid", ["liquid", "overnight", "money market"]),
    ("Debt", ["debt", "income", "gilt", "bond", "duration", "short term", "credit risk", "banking and psu"]),
]


def normalize_category(raw: str | None) -> str:
    r = (raw or "").lower()
    return next((cat for cat, keys in CATEGORY_RULES if any(k in r for k in keys)), "Other")


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", name.lower())).strip()


def find_direct_growth(schemes: list[dict], query: str) -> dict | None:
    """The Direct-Growth scheme whose name contains `query` as a whole phrase (shortest name wins).
    Phrase matching keeps "Large Cap Fund" from matching "Large & Mid Cap Fund"."""
    phrase = re.compile(r"\b" + re.escape(_norm(query)) + r"\b")
    good = [s for s in schemes
            if phrase.search(_norm(s["schemeName"])) and "direct" in s["schemeName"].lower()
            and "growth" in s["schemeName"].lower() and not _EXCLUDE.search(s["schemeName"])]
    return min(good, key=lambda s: len(s["schemeName"])) if good else None


def parse_navs(payload: dict) -> pd.Series:
    points = [(datetime.strptime(p["date"], "%d-%m-%Y").date(), float(p["nav"])) for p in payload["data"] if p.get("nav")]
    return m.to_series(points)


def build_fund_row(payload: dict) -> dict:
    meta, navs, rf = payload["meta"], parse_navs(payload), settings.risk_free_rate
    three_y = m.window(navs, 3 * 365)
    has_3y = (navs.index[-1] - navs.index[0]).days >= 3 * 365 - 7
    return {
        "scheme_code": int(meta["scheme_code"]),
        "name": meta["scheme_name"],
        "fund_house": meta.get("fund_house"),
        "category": normalize_category(meta.get("scheme_category")),
        "nav": m.clean(float(navs.iloc[-1])),
        "nav_date": navs.index[-1].date().isoformat(),
        "return_1y": m.clean(m.trailing_return(navs, 365)),
        "cagr_3y": m.clean(m.cagr(navs, 3)),
        "cagr_5y": m.clean(m.cagr(navs, 5)),
        "volatility_3y": m.clean(m.volatility(three_y)) if has_3y else None,
        "sharpe_3y": m.clean(m.sharpe(three_y, rf), 2) if has_3y else None,
        "sortino_3y": m.clean(m.sortino(three_y, rf), 2) if has_3y else None,
        "max_drawdown_3y": m.clean(m.max_drawdown(three_y)) if has_3y else None,
        "rolling_1y_positive_pct": m.clean(m.rolling_positive_share(navs)),
    }


def refresh_funds() -> tuple[list[dict], list[str]]:
    with httpx.Client(timeout=60) as client:
        schemes = client.get(MFAPI).raise_for_status().json()
        matches = {q: find_direct_growth(schemes, q) for q in FUND_QUERIES}

        def load(scheme: dict) -> dict | None:
            try:
                return build_fund_row(client.get(f"{MFAPI}/{scheme['schemeCode']}").raise_for_status().json())
            except Exception as e:
                log.warning("fund %s failed: %s", scheme["schemeName"], e)
                return None

        with ThreadPoolExecutor(6) as pool:
            rows = list(pool.map(load, [s for s in matches.values() if s]))
    return [r for r in rows if r], [q for q, s in matches.items() if not s]


# ---------- snapshot ----------

def refresh_snapshot() -> dict:
    stocks, missing_stocks = refresh_stocks()
    funds, missing_funds = refresh_funds()
    snapshot = {"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "stocks": stocks, "funds": funds,
                "missing": {"stocks": missing_stocks, "funds": missing_funds}}
    SNAPSHOT_FILE.write_text(json.dumps(snapshot, indent=1), encoding="utf-8")
    return snapshot


def load_snapshot() -> dict:
    if not SNAPSHOT_FILE.exists():
        return {"updated_at": None, "stocks": [], "funds": [], "missing": {}}
    return json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))


# ---------- live quotes for the chatbot ----------

def live_stock_quote(symbol: str) -> dict:
    """Latest price and day change for an NSE symbol (e.g. "TCS") or Yahoo ticker."""
    symbol = symbol.strip().upper().removesuffix(".NS")
    hist = yf.Ticker(yahoo_symbol(symbol)).history(period="5d", interval="1d", auto_adjust=True)
    if hist.empty:
        return {"error": f"No price data found for '{symbol}'. Use the NSE symbol, e.g. INFY or HDFCBANK."}
    close = hist["Close"].dropna()
    last, prev = float(close.iloc[-1]), float(close.iloc[-2]) if len(close) > 1 else None
    return {"symbol": symbol, "price": round(last, 2), "as_of": close.index[-1].date().isoformat(),
            "change_pct_1d": round((last / prev - 1) * 100, 2) if prev else None}


def live_fund_nav(name: str) -> dict:
    """Latest NAV of a mutual fund (Direct-Growth plan) by name, from AMFI via mfapi.in."""
    with httpx.Client(timeout=20) as client:
        results = client.get(f"{MFAPI}/search", params={"q": name}).raise_for_status().json()
        scheme = find_direct_growth(results, name) or next(
            (r for r in results if "direct" in r["schemeName"].lower() and "growth" in r["schemeName"].lower()), None)
        if not scheme:
            return {"error": f"No Direct-Growth fund found matching '{name}'."}
        payload = client.get(f"{MFAPI}/{scheme['schemeCode']}").raise_for_status().json()
    row = build_fund_row(payload)
    return {k: row[k] for k in ("name", "category", "nav", "nav_date", "return_1y", "cagr_3y", "cagr_5y")}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    snap = refresh_snapshot()
    print(f"Saved {len(snap['stocks'])} stocks and {len(snap['funds'])} funds to {SNAPSHOT_FILE}")
    if any(snap["missing"].values()):
        print("Not found:", snap["missing"], file=sys.stderr)
