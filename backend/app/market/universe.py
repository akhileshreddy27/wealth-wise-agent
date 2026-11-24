"""What the app tracks. Edit these lists to widen the universe.

NIFTY 50 constituents change twice a year (NSE rebalances in March and September).
Symbols Yahoo can't resolve are skipped and reported by the refresh command.
"""

NIFTY_INDEX = "^NSEI"

NIFTY50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJFINANCE",
    "BAJAJFINSV", "BEL", "BHARTIARTL", "CIPLA", "COALINDIA", "DRREDDY", "EICHERMOT", "ETERNAL",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDIGO",
    "INFY", "ITC", "JIOFIN", "JSWSTEEL", "KOTAKBANK", "LT", "M&M", "MARUTI", "MAXHEALTH",
    "NESTLEIND", "NTPC", "ONGC", "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
    "SUNPHARMA", "TATACONSUM", "TMPV", "TATASTEEL", "TCS", "TECHM", "TITAN", "TRENT",
    "ULTRACEMCO", "WIPRO",
]

# Curated Direct-Growth funds, matched as whole phrases against mfapi.in's scheme list.
# Fund houses rename schemes, so update a name when the refresh says it no longer matches.
FUND_QUERIES = [
    # Index
    "UTI Nifty 50 Index Fund", "HDFC Nifty 50 Index Fund", "UTI Nifty Next 50 Index Fund",
    "Motilal Oswal Nifty Midcap 150 Index Fund",
    # Large cap
    "ICICI Prudential Large Cap Fund", "Nippon India Large Cap Fund", "Mirae Asset Large Cap Fund",
    # Flexi cap
    "Parag Parikh Flexi Cap Fund", "HDFC Flexi Cap Fund", "Kotak Flexi Cap Fund",
    # Mid cap
    "HDFC Mid Cap Fund", "Kotak Mid Cap Fund",
    # Small cap
    "Nippon India Small Cap Fund", "SBI Small Cap Fund", "Axis Small Cap Fund",
    # Hybrid
    "ICICI Prudential Balanced Advantage Fund", "HDFC Balanced Advantage Fund",
    # Debt
    "HDFC Corporate Bond Fund", "ICICI Prudential Corporate Bond Fund", "SBI Gilt Fund", "HDFC Short Term Fund",
    # Liquid
    "Parag Parikh Liquid Fund", "HDFC Liquid Fund", "SBI Liquid Fund",
]
