# Wealth Wise: AI-powered personal finance assistant

A personal finance app for Indian investors that does three things:

1. **Personalised recommendations.** Custom scoring algorithms turn your profile into a monthly SIP plan with ranked mutual funds, scored NIFTY 50 stocks and the best fixed deposit for you. AI agents explain the plan and answer questions about it.
2. **RAG chatbot and learning modules.** An assistant that answers from 13 finance lessons (with citations) and pulls real-time stock prices and fund NAVs. Every lesson has video tutorials and a quiz.
3. **Expense tracker.** Import a bank statement or add spending by hand. You get budgets, the 50/30/20 rule, recurring-subscription and spending-spike detection, and savings tips.

> Educational project. Not SEBI-registered investment advice.

**Stack:** FastAPI · SQLite (SQLAlchemy) · Google Gemini (`google-genai`) · pandas / NumPy · yfinance + mfapi.in · React 19 + TypeScript + Vite + Tailwind CSS + Recharts

---

## How it works

```
                    ┌──────────────── React frontend ─────────────────┐
                    │ Dashboard · Plan · Expenses · Learn · Assistant │
                    └────────────────────────┬────────────────────────┘
                                             │ /api
┌────────────────────────────────── FastAPI backend ───────────────────────────────────┐
│                                                                                      │
│  engine/  (deterministic, no AI)        ai/  (Gemini agents)        rag/             │
│  risk ──► allocation ──► plan           assistant: tool-calling ──► knowledge base   │
│  stocks (factor scoring)   ▲            loop with 7 tools            BM25 + Gemini   │
│  funds  (peer ranking)     │            explainer: plan → words      embeddings, RRF │
│  fds    (best FD)          │            categoriser: unknown txns        ▲           │
│                            │                 │                           │           │
│  market/  snapshot (data/market.json) + live quotes      content/*.md (13 lessons)   │
│  expenses/  analytics · CSV import · categories          SQLite: profile, txns, budgets │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

**Rule: the AI never invents numbers.** Every figure comes from the deterministic engine or a tool call. Gemini explains, searches and orchestrates. Every AI feature also has a non-AI fallback, so the app works without an API key.

### 1. Recommendation engine (`backend/app/engine/`)

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

### 2. AI agents and RAG (`backend/app/ai/`, `backend/app/rag/`)

- **Assistant** (`assistant.py`): a Gemini tool-calling agent. The loop is written out by hand, not left to the SDK's automatic function calling, so the UI can show which tools ran and cite sources. Tools:
  `search_knowledge` (RAG over lessons) · `get_stock_quote` (live NSE price) · `get_fund_nav` (live AMFI NAV) · `get_stock_score` · `plan_goal` (SIP for a goal, inflation-adjusted) · `get_my_plan` · `get_my_spending`.
- **Knowledge base** (`knowledge.py`): lessons are split at their `##` headings into chunks. Search is hybrid: **BM25** keyword ranking plus **Gemini embeddings** (`gemini-embedding-001`, cached on disk and rebuilt when lessons change), merged with **reciprocal rank fusion**. Without a key it falls back to BM25 only.
- **Plan explainer** (`explainer.py`): turns the engine's plan JSON into a short personal explanation. Without a key, a rule-based version stitches together the same facts.
- **Categoriser** (`categorizer.py`): imported transactions the keyword rules can't place go to Gemini in one batch, with a JSON schema whose category is an `enum`, so it can only answer with real categories.

### 3. Expense tracker (`backend/app/expenses/`)

Monthly summary with budgets and the **50/30/20** split (SIPs count as saving, not spending). It also detects **recurring payments** (same merchant, ±15% amount, 2 of the last 3 months) and **spending spikes** (above mean + 2σ of the previous months), and shows the 10-year SIP value of cutting your biggest discretionary category. CSV import handles signed-amount and debit/credit statements, auto-categorises rows and skips duplicates.

---

## Run it locally (Windows)

Needs Python 3.12+ and Node 20+.

**1. Backend** (http://localhost:8000, API docs at http://localhost:8000/docs)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env        # then paste your Gemini key into .env (optional)
.\.venv\Scripts\uvicorn app.main:app --reload
```

**2. Frontend** (http://localhost:5173), in a second terminal

```powershell
cd frontend
npm install
npm run dev
```

**3. Use it.** Fill in your profile → see your plan → on Expenses click **Load demo statement** → try the Assistant.

### Gemini API key (free)

Get one at https://aistudio.google.com/apikey and put it in `backend/.env`:

```
GEMINI_API_KEY=your-key-here
```

Restart the backend. The sidebar shows "Gemini AI on" and lesson search becomes "hybrid". Change the model with `GEMINI_MODEL` (default `gemini-3.6-flash`). If Google reports the model as busy or slow, the app retries on `GEMINI_FALLBACK_MODELS` (default `gemini-3.5-flash-lite`).

### Market data

`backend/data/market.json` holds a snapshot of 50 stocks and 24 funds. Refresh it with the **Refresh market data** button on the Plan page, or:

```powershell
cd backend
.\.venv\Scripts\python -m app.market.data
```

FD rates live in `backend/app/market/fd_rates.json` and must be updated by hand from bank websites (the app labels them as indicative).

### Deploy (free, on Render)

The repo deploys as **one web service**: the `Dockerfile` builds the React app and the FastAPI backend serves it.

1. Sign in at https://render.com with GitHub.
2. **New → Blueprint**, then pick this repository (Render reads `render.yaml`).
3. Paste your Gemini key when Render asks for `GEMINI_API_KEY`, then click **Apply**.
4. The first build takes about 5 minutes. Your site is at `https://wealth-wise-<something>.onrender.com`.

Notes on the free plan: the service sleeps after 15 minutes without visitors, so the first visit afterwards takes about a minute; and its disk is temporary, so visitors' data resets when the service restarts. That's fine for a demo.

**Public-demo safety:** there is no login, so each browser gets a random visitor id (`X-Client-Id` header) and only ever sees its own profile, transactions and budgets. AI endpoints are rate-limited per IP (`AI_REQUESTS_PER_HOUR`, default 30) to protect the Gemini quota, and market data can be re-downloaded at most once an hour.

### Tests

```powershell
cd backend
.\.venv\Scripts\pytest -q
```

38 tests run offline: the engine, expense analytics, CSV import, RAG search, the API (including visitor isolation and rate limits), and the agent loop with a scripted fake Gemini.

---

## Project layout

```
backend/
  app/
    main.py            FastAPI app, /api/health, serves the built frontend in production
    config.py, db.py   settings (.env) and SQLite models: Profile, Transaction, Budget (all per visitor)
    ratelimit.py       in-memory rate limiter for the AI endpoints
    services.py        shared reads used by routes and agent tools
    api/               deps.py (visitor id, rate limit) · profile.py · plan.py (plan, explain, market) · expenses.py · learn.py (lessons, chat)
    engine/            risk · allocation · stocks · funds · fds · ranking · metrics · plan
    market/            universe.py (what's tracked) · data.py (snapshot + live quotes) · fd_rates.json
    expenses/          categories · analytics · importer
    ai/                gemini.py (SDK wrapper) · assistant · explainer · categorizer
    rag/               knowledge.py · content/ (13 lessons + modules.json: quizzes, verified videos)
  data/                market.json · sample_statement.csv (SQLite DB and embeddings cache are created here)
  tests/
frontend/src/
  pages/               Dashboard · Profile · Plan · Expenses · Learn · LearnModule · Assistant
  components/          Layout · ui (cards, buttons, badges…)
  lib/                 api.ts (client, types, ₹ formatting) · useApi · progress (quiz scores)
```

## API

| Method | Path | |
|---|---|---|
| GET | `/api/health` | AI on/off, search mode, data freshness |
| GET / PUT | `/api/profile` | profile (PUT computes the risk score) |
| GET | `/api/profile/questionnaire` | risk questions |
| GET | `/api/plan` | full personalised plan |
| POST | `/api/plan/explain` | AI (or rule-based) explanation |
| GET / POST | `/api/market/status`, `/api/market/refresh` | snapshot info / re-download |
| GET / POST | `/api/transactions` | list (`?month=YYYY-MM`) / add (category auto-detected) |
| PUT / DELETE | `/api/transactions/{id}` | edit / delete |
| POST | `/api/transactions/import`, `/api/transactions/demo` | CSV upload / sample statement |
| GET / PUT | `/api/budgets` | monthly limit per category |
| GET | `/api/expenses/summary?month=` | summary, 50/30/20, trend, insights |
| GET | `/api/learn/modules`, `/api/learn/modules/{id}` | lessons, videos, quizzes |
| POST | `/api/chat` | assistant (`{messages: [{role, content}]}`) |

## Limitations

- No accounts: data is tied to a random id in your browser, so clearing site data (or another browser) starts fresh.
- Stock fundamentals come from Yahoo Finance and can be missing or delayed. FD rates are a hand-maintained table.
- Expected returns (equity 12%, debt 7%) are long-run assumptions, not forecasts.
