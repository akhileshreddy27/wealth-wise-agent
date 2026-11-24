"""Altair charts shared by the pages."""
import altair as alt
import pandas as pd

from app_pages.common import ASSET_COLORS, ASSET_LABELS


def allocation_donut(weights: dict[str, float]) -> alt.Chart:
    """Donut with the legend (and percentages) underneath, so it fits narrow columns."""
    df = pd.DataFrame([{"asset": ASSET_LABELS[k], "percent": round(v * 100)} for k, v in weights.items() if v > 0])
    df["label"] = df["asset"] + " " + df["percent"].astype(str) + "%"
    color = alt.Color("label:N", title=None, sort=list(df["label"]),
                      scale=alt.Scale(domain=list(df["label"]), range=[ASSET_COLORS[a] for a in df["asset"]]),
                      legend=alt.Legend(orient="bottom", columns=2, labelFontSize=13, symbolType="square"))
    return (alt.Chart(df).mark_arc(innerRadius=50, outerRadius=85, padAngle=0.02)
            .encode(theta="percent:Q", color=color, order=alt.Order("percent:Q", sort="descending"),
                    tooltip=["asset", alt.Tooltip("percent", title="%")])
            .properties(height=260).configure_view(stroke=None))


def trend_bars(trend: list[dict]) -> alt.Chart:
    rows = [{"month": t["month"], "what": what, "amount": t[key]}
            for t in trend for what, key in (("Income", "income"), ("Outflow", "expense"))]
    return (alt.Chart(pd.DataFrame(rows)).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(x=alt.X("yearmonth(month):O", title=None, axis=alt.Axis(format="%b", labelAngle=0)),
                    xOffset="what:N",
                    y=alt.Y("amount:Q", title=None, axis=alt.Axis(format="~s")),
                    color=alt.Color("what:N", title=None, scale=alt.Scale(range=["#059669", "#94a3b8"]),
                                    legend=alt.Legend(orient="top")),
                    tooltip=[alt.Tooltip("yearmonth(month):O", title="Month", format="%b %Y"), "what",
                             alt.Tooltip("amount:Q", format=",.0f")])
            .properties(height=260))


def category_bars(categories: list[dict]) -> alt.Chart:
    df = pd.DataFrame([{"category": c["label"], "spent": c["amount"], "budget": c["budget"],
                        "over": bool(c["budget_used"] and c["budget_used"] > 1)} for c in categories if c["amount"] > 0])
    base = alt.Chart(df).encode(y=alt.Y("category:N", sort="-x", title=None))
    bars = base.mark_bar(cornerRadiusEnd=3).encode(
        x=alt.X("spent:Q", title=None, axis=alt.Axis(format="~s")),
        color=alt.condition("datum.over", alt.value("#e11d48"), alt.value("#64748b")),
        tooltip=["category", alt.Tooltip("spent:Q", format=",.0f"), alt.Tooltip("budget:Q", format=",.0f")])
    budget_ticks = base.mark_tick(color="#0f172a", thickness=2, size=18).encode(x="budget:Q")
    return (bars + budget_ticks).properties(height=max(160, 28 * len(df)))
