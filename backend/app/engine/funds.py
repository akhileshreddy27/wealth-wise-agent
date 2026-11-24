"""Mutual fund ranking within peer group, and the sleeve -> fund-category mapping.

A fund is only compared with funds of the same AMFI category (a small-cap fund's returns
say nothing about a liquid fund's). Score = weighted percentile of:
  Sharpe 3Y 25%, Sortino 3Y 15%, 3Y CAGR 15%, 5Y CAGR 15%, rolling 1Y consistency 15%, max drawdown 15%.
Missing metrics (e.g. a fund younger than 5 years) count as neutral and are flagged. Index funds are compared
only with index funds of the same segment, and scores in small peer groups are shrunk toward 50.
"""
import re

from app.engine.ranking import NEUTRAL, bottom_label, percentile_table, top_label

FACTORS: list[tuple[str, float, str]] = [   # (metric, weight, label); all higher-is-better
    ("sharpe_3y", 0.25, "Sharpe (3Y)"),
    ("sortino_3y", 0.15, "Sortino (3Y)"),
    ("cagr_3y", 0.15, "3Y CAGR"),
    ("cagr_5y", 0.15, "5Y CAGR"),
    ("rolling_1y_positive_pct", 0.15, "Positive 1Y periods"),
    ("max_drawdown_3y", 0.15, "Max drawdown (3Y)"),   # -0.10 beats -0.30, so higher is better too
]
_PCT = {"cagr_3y", "cagr_5y", "rolling_1y_positive_pct", "max_drawdown_3y"}

# Which fund categories may fill each sleeve. Index funds are split by what they track.
SLEEVE_CATEGORIES = {
    "core":   ["Index", "Large Cap"],
    "hybrid": ["Hybrid"],
    "flexi":  ["Flexi Cap", "Multi Cap", "Large & Mid Cap"],
    "mid":    ["Mid Cap", "Index"],
    "small":  ["Small Cap", "Index"],
    "debt":   ["Debt"],
    "liquid": ["Liquid"],
}
_MID = re.compile(r"mid ?cap", re.I)
_SMALL = re.compile(r"small ?cap", re.I)


def index_segment(name: str) -> str:
    """Which sleeve an index fund belongs to, from the index it tracks."""
    return "small" if _SMALL.search(name) else "mid" if _MID.search(name) else "core"


def in_sleeve(fund: dict, sleeve: str) -> bool:
    if fund["category"] not in SLEEVE_CATEGORIES.get(sleeve, []):
        return False
    if fund["category"] == "Index":
        return index_segment(fund["name"]) == sleeve
    return True


def _fmt(metric: str, v: float) -> str:
    return f"{v * 100:.1f}%" if metric in _PCT else f"{v:.2f}"


def short_name(name: str) -> str:
    """"SBI LIQUID FUND - DIRECT PLAN - GROWTH" -> "SBI Liquid Fund"."""
    name = re.sub(r"\s*\(erstwhile.*?\)", "", re.sub(r"\s*-\s*Direct Plan.*$", "", name, flags=re.I), flags=re.I).strip()
    if name.isupper():
        name = " ".join(w if len(w) <= 3 else w.capitalize() for w in name.split())
    return name


INDEX_PEER_GROUP = {"core": "Nifty / large-cap index", "mid": "Mid-cap index", "small": "Small-cap index"}


def peer_group(fund: dict) -> str:
    """Funds are compared within their category; index funds only with funds tracking the same segment."""
    return INDEX_PEER_GROUP[index_segment(fund["name"])] if fund["category"] == "Index" else fund["category"]


def shrink(score: float, n: int) -> float:
    """Pull scores toward 0.5 in small peer groups: being 2nd of 2 is weak evidence of a bad fund.
    n=2 keeps 1/3 of the distance from 0.5, n=3 half, n=9 80%; ranks don't change."""
    return NEUTRAL + (score - NEUTRAL) * (n - 1) / (n + 1)


def rank_funds(funds: list[dict]) -> list[dict]:
    """Score every fund against its peer group. Returns all funds, best first within each group."""
    groups: dict[str, list[dict]] = {}
    for f in funds:
        groups.setdefault(peer_group(f), []).append(f)

    out = []
    for group_name, group in groups.items():
        table = percentile_table(group, {m: ((lambda f, m=m: f.get(m)), True) for m, _, _ in FACTORS})
        peers = f"{len(group)} {group_name} funds" if len(group) > 1 else None
        scored = []
        for f, pcts in zip(group, table):
            raw = sum(w * (pcts[m] if pcts[m] is not None else NEUTRAL) for m, w, _ in FACTORS)
            score = shrink(raw, len(group))
            missing = [label for m, _, label in FACTORS if f.get(m) is None]
            reasons, cautions = [], []
            if peers:
                ranked = sorted(((pcts[m], m, label) for m, _, label in FACTORS if pcts[m] is not None), reverse=True)
                reasons = [f"{label} {_fmt(m, f[m])} ({top_label(p, peers)})" for p, m, label in ranked[:2] if p >= 0.6]
                cautions = [f"{label} {_fmt(m, f[m])} ({bottom_label(p, peers)})" for p, m, label in ranked[-1:] if p <= 0.25]
            if missing:
                cautions.append(f"Limited history: no {', '.join(missing[:2])}{' …' if len(missing) > 2 else ''}")
            scored.append({
                "scheme_code": f["scheme_code"], "name": f["name"], "short_name": short_name(f["name"]),
                "fund_house": f.get("fund_house"), "category": f["category"], "peer_group": group_name,
                "metrics": {m: f.get(m) for m, _, _ in FACTORS} | {"return_1y": f.get("return_1y"),
                                                                   "volatility_3y": f.get("volatility_3y")},
                "score": round(score * 100, 1), "peers": len(group),
                "reasons": reasons, "cautions": cautions,
            })
        scored.sort(key=lambda r: (-r["score"], -(r["metrics"]["sharpe_3y"] or -99)))
        for i, r in enumerate(scored, 1):
            r["rank_in_category"] = i
        out.extend(scored)
    return out


def picks_for_sleeve(ranked: list[dict], sleeve: str, n: int = 2) -> list[dict]:
    """Best `n` funds for a sleeve, across its allowed categories."""
    pool = [f for f in ranked if in_sleeve({"category": f["category"], "name": f["name"]}, sleeve)]
    pool.sort(key=lambda r: (-r["score"], -(r["metrics"]["sharpe_3y"] or -99)))
    return pool[:n]
