"""Fixed deposits: load the bank rate table and pick the best FD for the user's horizon."""
import json
from pathlib import Path

RATES_FILE = Path(__file__).resolve().parent.parent / "market" / "fd_rates.json"
DICGC_LIMIT = 500000  # deposit insurance per depositor per bank


def load_fd_rates(path: Path = RATES_FILE) -> tuple[list[dict], str]:
    """Flatten fd_rates.json into one row per (bank, tenure slab). Returns (rows, as_of)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for bank in data["banks"]:
        slabs = bank.get("slabs", data["slabs"])
        if len(slabs) != len(bank["rates"]):
            raise ValueError(f"{bank['bank']}: {len(bank['rates'])} rates for {len(slabs)} slabs")
        for (lo, hi), rate in zip(slabs, bank["rates"]):
            rows.append({"bank": bank["bank"], "bank_type": bank["type"], "min_days": lo, "max_days": hi,
                         "rate": rate, "senior_rate": round(rate + bank["senior_bonus"], 2),
                         "source_url": bank.get("url")})
    return rows, data["as_of"]


def maturity_value(principal: float, rate_pct: float, days: int, compounding_per_year: int = 4) -> float:
    """Quarterly compounding, the Indian bank standard for cumulative FDs."""
    return principal * (1 + rate_pct / 100 / compounding_per_year) ** (compounding_per_year * days / 365)


def pick_fd(rows: list[dict], as_of: str, horizon_years: int, age: int, amount: float = 100000) -> dict:
    """Best rate for a tenure matched to the horizon (1-5 years), with senior rates at 60+.
    If the best rate is from a small finance bank, also show the best from a bigger bank."""
    days = min(max(horizon_years, 1), 5) * 365
    senior = age >= 60

    def quote(r: dict) -> dict:
        rate = r["senior_rate"] if senior else r["rate"]
        value = maturity_value(amount, rate, days)
        return {"bank": r["bank"], "bank_type": r["bank_type"], "rate": rate, "tenure_days": days,
                "maturity_value": round(value, 2), "interest": round(value - amount, 2), "source_url": r["source_url"]}

    quotes = sorted((quote(r) for r in rows if r["min_days"] <= days <= r["max_days"]), key=lambda q: -q["rate"])
    notes = [f"Tenure matched to your {horizon_years}-year horizon" + (" (capped at 5 years)." if horizon_years > 5 else ".")]
    if senior:
        notes.append("Senior-citizen rates applied (age 60+).")

    best = quotes[0] if quotes else None
    safest = None
    if best and best["bank_type"] == "small_finance":
        safest = next((q for q in quotes if q["bank_type"] != "small_finance"), None)
        notes.append(f"Small finance banks pay more but carry more risk. DICGC insures only ₹{DICGC_LIMIT // 100000} "
                     "lakh per bank, so keep larger deposits in a bigger bank.")

    return {"amount": amount, "tenure_days": days, "best": best, "safest": safest,
            "alternatives": quotes[1:4], "as_of": as_of, "notes": notes}
