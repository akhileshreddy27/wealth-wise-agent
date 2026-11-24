# Wealth Wise: AI-powered personal finance assistant

**Live demo:** https://wealth-wise-agent-vzjfenxbpqtwmkyajtdm7y.streamlit.app/

A personal finance app for Indian investors that does three things:

1. **Personalised recommendations.** Custom scoring algorithms turn your profile into a monthly SIP plan with ranked mutual funds, scored NIFTY 50 stocks and the best fixed deposit for you. AI agents explain the plan and answer questions about it.
2. **RAG chatbot and learning modules.** An assistant that answers from 13 finance lessons (with citations) and pulls real-time stock prices and fund NAVs. Every lesson has video tutorials and a quiz.
3. **Expense tracker.** Import a bank statement or add spending by hand. You get budgets, the 50/30/20 rule, recurring-subscription and spending-spike detection, and savings tips.

> Educational project. Not SEBI-registered investment advice.

**Stack (all Python):** Streamlit · Google Gemini (`google-genai`) · pandas / NumPy · SQLite (SQLAlchemy) · Altair · yfinance + mfapi.in

---

## How it works

```
┌──────────────────────────── Streamlit app (app_pages/) ─────────────────────────────┐
│        Dashboard · My Plan · Profile · Expenses · Assistant · Lessons               │
└───────────────────────────────────────┬─────────────────────────────────────────────┘
                                        │ plain Python calls
┌──────────────────────────────── wealthwise/ package ────────────────────────────────┐
│  engine/  (deterministic, no AI)      ai/  (Gemini agents)          rag/            │
│  risk ──► allocation ──► plan         assistant: tool-calling ──►  knowledge base   │
│  stocks (factor scoring)  ▲           loop with 7 tools             BM25 + Gemini   │
│  funds  (peer ranking)    │           explainer: plan → words       embeddings, RRF │
│  fds    (best FD)         │           categoriser: unknown txns         ▲           │
│  market/  snapshot (data/market.json) + live quotes     content/*.md (13 lessons)   │
│  expenses/  analytics · CSV import     services.py ── SQLite: profile, txns, budgets│
└─────────────────────────────────────────────────────────────────────────────────────┘
```

**Rule: the AI never invents numbers.** Every figure comes from the deterministic engine or a tool call. Gemini explains, searches and orchestrates. Every AI feature also has a non-AI fallback, so the app works without an API key.

### 1. Recommendation engine (`wealthwise/engine/`)

| Step | File | What it does |
|---|---|---|
| Risk score 1–10 | `risk.py` | Risk *tolerance* from a 5-question quiz (60%) plus risk *capacity* from age, horizon, dependents and emergency cushion (40%). Capacity caps tolerance: a 58-year-old with a 2-year horizon can't come out "aggressive". |
| Asset allocation | `allocation.py` | Equity starts at 10% + 8% per risk point, then explainable caps apply: **110 − age**, and a **horizon cap** (0% equity under 3 years, 30% under 5, 55% under 7). The rest is split between FDs and debt funds, with a 5–10% liquid buffer. Each cap that applies is recorded as a reason. |
| Emergency fund first | `allocation.py` | 6 months of expenses in a liquid fund. If the gap can be closed within 3 months, the whole surplus goes to it; otherwise half does, so investing still starts. |
| SIP split | `allocation.py` | Equity is spread over sleeves (index / flexi / mid / small / hybrid, plus direct stocks for experienced investors). Sleeves under the ₹500 SIP minimum are merged. |
| Stock scoring | `stocks.py` | NIFTY 50 percentile scores on four factors: **value** (P/E, P/B), **quality** (ROE, debt/equity, margin), **momentum** (6M, 1Y return) and **low volatility** (volatility, beta). Factor weights depend on your risk profile, a risk filter removes stocks too volatile for you, and there's a cap of 2 picks per sector. |
| Fund ranking | `funds.py` | Each fund is compared only with its peer group (same category; index funds by the index they track). Weighted percentiles of Sharpe, Sortino, 3Y/5Y CAGR, rolling 1Y consistency and max drawdown. Scores in small peer groups are pulled toward 50. |
| FD pick | `fds.py` | Best rate for a tenure matched to your horizon (1–5 years), senior rates at 60+. If the top rate is from a small finance bank, the best large-bank option is shown too, with the DICGC ₹5 lakh insurance limit. |
| Metrics | `metrics.py` | CAGR, annualised volatility, Sharpe, Sortino, max drawdown, beta vs NIFTY 50 and rolling-return consistency, computed from 5 years of daily prices / NAVs. |

### 2. AI agents and RAG (`wealthwise/ai/`, `wealthwise/rag/`)

- **Assistant** (`assistant.py`): a Gemini tool-calling agent. The loop is written out by hand, not left to the SDK's automatic function calling, so the app can show which tools ran and cite sources. Tools:
  `search_knowledge` (RAG over lessons) · `get_stock_quote` (live NSE price) · `get_fund_nav` (live AMFI NAV) · `get_stock_score` · `plan_goal` (SIP for a goal, inflation-adjusted) · `get_my_plan` · `get_my_spending`.
- **Knowledge base** (`knowledge.py`): lessons are split at their `##` headings into chunks. Search is hybrid: **BM25** keyword ranking plus **Gemini embeddings** (`gemini-embedding-001`, cached on disk and rebuilt when lessons change), merged with **reciprocal rank fusion**. Without a key it falls back to BM25 only.
- **Plan explainer** (`explainer.py`): turns the engine's plan JSON into a short personal explanation. Without a key, a rule-based version stitches together the same facts.
- **Categoriser** (`categorizer.py`): imported transactions the keyword rules can't place go to Gemini in one batch, with a JSON schema whose category is an `enum`, so it can only answer with real categories.

### 3. Expense tracker (`wealthwise/expenses/`)

Monthly summary with budgets and the **50/30/20** split (SIPs count as saving, not spending). It also detects **recurring payments** (same merchant, ±15% amount, 2 of the last 3 months) and **spending spikes** (above mean + 2σ of the previous months), and shows the 10-year SIP value of cutting your biggest discretionary category. CSV import handles signed-amount and debit/credit statements, auto-categorises rows and skips duplicates.

---

## Run it locally (Windows)

Needs Python 3.12+.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # then paste your Gemini key into .env (optional)
.\.venv\Scripts\streamlit run streamlit_app.py
```

The app opens at http://localhost:8501. Fill in your profile → see your plan → on Expenses click **Load demo statement** → try the Assistant.

### Gemini API key (free)

Get one at https://aistudio.google.com/apikey and put it in `.env`:

```
GEMINI_API_KEY=your-key-here
```

Restart the app. The sidebar shows "Gemini AI on" and lesson search becomes "hybrid". Change the model with `GEMINI_MODEL` (default `gemini-3.6-flash`). If Google reports the model as busy or slow, the app retries on `GEMINI_FALLBACK_MODELS` (default `gemini-3.5-flash-lite`).

### Market data

`data/market.json` holds a snapshot of 50 stocks and 24 funds. Refresh it with the **Refresh market data** button on the My Plan page, or:

```powershell
.\.venv\Scripts\python -m wealthwise.market.data
```

FD rates live in `wealthwise/market/fd_rates.json` and must be updated by hand from bank websites (the app labels them as indicative).

### Deploy (free, on Streamlit Community Cloud)

1. Sign in at https://share.streamlit.io with GitHub.
2. **Create app → Deploy a public app from GitHub**: pick this repository, branch `main`, main file `streamlit_app.py`.
3. Under **Advanced settings**, choose Python 3.12 and paste into **Secrets**: `GEMINI_API_KEY = "your-key-here"`
4. Click **Deploy**. The first build takes a few minutes.

The free app sleeps after a while without visitors (the first visit then wakes it), and its disk is temporary, so visitors' data resets when it restarts. That's fine for a demo.

**Public-demo safety:** there is no login. Each visitor gets a random id kept in the page URL (`?u=...`), and only ever sees their own profile, transactions, budgets and quiz scores. AI calls are rate-limited per visitor (`AI_REQUESTS_PER_HOUR`, default 20) and for the whole app (`AI_REQUESTS_PER_HOUR_TOTAL`, default 300) to protect the Gemini quota, and market data can be re-downloaded at most once an hour.

### Tests

```powershell
.\.venv\Scripts\pytest -q
```

40 tests run offline: the engine, expense analytics, CSV import, RAG search, the agent loop with a scripted fake Gemini, visitor isolation and rate limits, and every Streamlit page run headless with Streamlit's `AppTest`.

---

## Project layout

```
streamlit_app.py       entry point: page setup and navigation
app_pages/             dashboard · profile · plan · expenses · learn · assistant
                       common.py (visitor id, rate limits, formatting) · charts.py (Altair)
wealthwise/
  config.py, db.py     settings (.env / Streamlit secrets) and SQLite models, all per visitor
  services.py          reads and writes shared by the pages and the agent's tools
  ratelimit.py         in-memory rate limiter for AI calls
  engine/              risk · allocation · stocks · funds · fds · ranking · metrics · plan
  market/              universe.py (what's tracked) · data.py (snapshot + live quotes) · fd_rates.json
  expenses/            categories · analytics · importer
  ai/                  gemini.py (SDK wrapper) · assistant · explainer · categorizer
  rag/                 knowledge.py · content/ (13 lessons + modules.json: quizzes, verified videos)
data/                  market.json · sample_statement.csv (the SQLite DB and embeddings cache are created here)
tests/
```

## Limitations

- No accounts: your data is tied to the `?u=...` id in your link, so anyone you share the full link with sees your data, and a new link starts fresh.
- Stock fundamentals come from Yahoo Finance and can be missing or delayed. FD rates are a hand-maintained table.
- Expected returns (equity 12%, debt 7%) are long-run assumptions, not forecasts.
