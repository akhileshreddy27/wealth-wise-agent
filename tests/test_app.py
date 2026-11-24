"""The Streamlit pages (run headless with AppTest) and the per-visitor service layer."""
from datetime import date, datetime, timezone

from streamlit.testing.v1 import AppTest

from tests.conftest import PROFILE
from wealthwise import services
from wealthwise.config import DATA_DIR, ROOT_DIR
from wealthwise.db import Profile, SessionLocal, Transaction
from wealthwise.expenses.importer import parse_statement
from wealthwise.ratelimit import RateLimiter

VISITOR = "0123456789abcdef0123456789abcdef"


def save_profile(client_id: str, **extra) -> None:
    with SessionLocal() as db:
        db.add(Profile(client_id=client_id, **(PROFILE | extra), risk_score=6, risk_category="moderate"))
        db.commit()


def run_page(page: str, visitor: str = VISITOR, **query) -> AppTest:
    at = AppTest.from_file(str(ROOT_DIR / "streamlit_app.py"), default_timeout=30)
    at.query_params["u"] = visitor
    for k, v in query.items():
        at.query_params[k] = v
    at.run()
    if page != "dashboard":
        at.switch_page(f"app_pages/{page}.py").run()
    assert not at.exception, at.exception
    return at


# ---------- pages ----------

def test_dashboard_welcomes_new_visitor(fresh_db):
    at = run_page("dashboard")
    assert at.title[0].value == "Welcome to Wealth Wise"


def test_profile_form_saves_and_scores(fresh_db):
    at = run_page("profile")
    for radio in at.radio:
        radio.set_value(radio.options[2])
    at.button[0].click().run()   # the form's submit button
    with SessionLocal() as db:
        p = services.get_profile(db, VISITOR)
    assert p and 1 <= p.risk_score <= 10 and p.answers["market_drop"] == 3


def test_plan_page_shows_plan_and_rule_based_explanation(fresh_db):
    save_profile(VISITOR)
    at = run_page("plan")
    assert at.title[0].value == "Your investment plan"
    assert len(at.expander) >= 3                       # one per SIP sleeve
    next(b for b in at.button if b.label == "Explain my plan").click().run()
    assert any("6/10" in m.value for m in at.markdown)  # AI is off in tests -> rule-based text


def test_expenses_demo_import(fresh_db):
    at = run_page("expenses")
    next(b for b in at.button if b.label == "Load demo statement").click().run()
    assert not at.exception
    with SessionLocal() as db:
        assert len(services.all_transactions(db, VISITOR)) > 100
    assert any(m.label == "Savings rate" for m in at.metric)


def test_learn_list_and_lesson_quiz(fresh_db):
    at = run_page("learn")
    assert len([b for b in at.button if b.label == "Open lesson"]) == 13
    at = run_page("learn", lesson="sip")
    assert at.title[0].value.startswith("SIP")
    for radio in at.radio:
        radio.set_value(radio.options[0])
    next(b for b in at.button if b.label == "Check answers").click().run()
    with SessionLocal() as db:
        assert "sip" in services.quiz_scores(db, VISITOR)


def test_assistant_answers_from_lessons_without_ai(fresh_db):
    at = run_page("assistant")
    at.chat_input[0].set_value("What is an index fund?").run()
    assert not at.exception
    assert any("lessons say" in m.value for m in at.markdown)


# ---------- per-visitor data ----------

def test_visitors_only_see_their_own_data(fresh_db):
    alice, bob = "a" * 32, "b" * 32
    save_profile(alice, name="Alice")
    with SessionLocal() as db:
        db.add(Transaction(client_id=alice, date=date(2026, 6, 3), amount=450, kind="expense", category="dining", note="Zomato"))
        db.commit()
        services.set_budgets(db, alice, {"dining": 1000})

        assert services.get_profile(db, bob) is None and services.current_plan(db, bob) is None
        assert services.all_transactions(db, bob) == [] and services.budgets(db, bob) == {}
        assert services.spending(db, bob) is None
        assert services.get_profile(db, alice).name == "Alice"
        assert services.budgets(db, alice) == {"dining": 1000}


def test_import_skips_duplicates_and_budgets_can_be_removed(fresh_db):
    rows, _ = parse_statement((DATA_DIR / "sample_statement.csv").read_bytes())
    with SessionLocal() as db:
        first = services.import_rows(db, VISITOR, rows, use_ai=False)
        again = services.import_rows(db, VISITOR, rows, use_ai=False)
        assert first["imported"] > 100 and again == {"imported": 0, "duplicates": first["imported"], "ai_categorised": 0}
        services.set_budgets(db, VISITOR, {"dining": 3000, "shopping": 2000})
        services.set_budgets(db, VISITOR, {"dining": 0})
        assert services.budgets(db, VISITOR) == {"shopping": 2000}


def test_quiz_keeps_best_score(fresh_db):
    with SessionLocal() as db:
        services.save_quiz_score(db, VISITOR, "sip", 1.0)
        services.save_quiz_score(db, VISITOR, "sip", 0.5)
        assert services.quiz_scores(db, VISITOR) == {"sip": 1.0}


# ---------- demo protection ----------

def test_rate_limiter():
    limiter = RateLimiter(2, window_seconds=3600)
    assert [limiter.allow("x") for _ in range(3)] == [True, True, False]
    assert limiter.allow("y")                               # limits are per key
    assert all(RateLimiter(0, 60).allow("x") for _ in range(100))   # 0 = unlimited


def test_market_refresh_skipped_when_fresh(monkeypatch):
    from wealthwise.market import data
    fresh = {"updated_at": datetime.now(timezone.utc).isoformat(), "stocks": [], "funds": []}
    monkeypatch.setattr(data, "load_snapshot", lambda: fresh)
    monkeypatch.setattr(data, "refresh_snapshot", lambda: (_ for _ in ()).throw(AssertionError("should not refresh")))
    assert data.refresh_if_stale(60) == (fresh, False)
