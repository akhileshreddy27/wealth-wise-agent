"""AI layer tests with a scripted stand-in for Gemini (no network)."""
import json
from types import SimpleNamespace

from google.genai import types

from wealthwise.ai import assistant, categorizer, explainer
from wealthwise.db import Base, SessionLocal, engine
from wealthwise.engine.plan import build_plan
from wealthwise.rag.knowledge import BM25, KnowledgeBase, chunk_lessons, load_modules, rrf
from tests.conftest import PROFILE


class FakeGemini:
    """Returns the scripted responses in order and records what it was sent."""

    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, contents, system, **kw):
        self.calls.append({"contents": list(contents) if isinstance(contents, list) else contents, **kw})
        return self.responses.pop(0)


def tool_call(name, **args):
    call = types.FunctionCall(id=f"call-{name}", name=name, args=args)
    return SimpleNamespace(function_calls=[call], text=None,
                           candidates=[SimpleNamespace(content=types.Content(role="model", parts=[types.Part(function_call=call)]))])


def answer(text):
    return SimpleNamespace(function_calls=None, text=text, candidates=[])


# ---------- RAG ----------

def test_lessons_chunk_by_section():
    chunks = chunk_lessons(load_modules())
    assert len(chunks) > 40
    assert "sip#rupee-cost-averaging" in {c.id for c in chunks}


def test_keyword_search_finds_the_right_lesson():
    kb = KnowledgeBase(chunk_lessons(load_modules()))
    assert kb.mode == "keyword"
    assert kb.search("rupee cost averaging")[0]["module_id"] == "sip"
    assert kb.search("DICGC insurance on bank deposits")[0]["module_id"] == "fixed-deposits"


def test_bm25_and_rrf():
    scores = BM25(["cats purr", "dogs bark loudly", "cats and dogs"]).scores("dogs")
    assert scores[0] == 0 and scores[1] > 0 and scores[2] > 0
    fused = rrf([[0, 1], [1, 2]])
    assert max(fused, key=fused.get) == 1     # ranked well by both lists


def test_hybrid_search_uses_embeddings(tmp_path, monkeypatch):
    monkeypatch.setattr("wealthwise.rag.knowledge.EMBEDDINGS_FILE", tmp_path / "emb.json")
    chunks = chunk_lessons(load_modules())
    target = next(i for i, c in enumerate(chunks) if c.id == "emergency-fund#where-to-keep-it")

    def fake_embed(texts, task):  # every chunk points one way except the target, which matches the query
        if task == "RETRIEVAL_QUERY":
            return [[0.0, 1.0]]
        return [[0.0, 1.0] if i == target else [1.0, 0.0] for i in range(len(texts))]

    kb = KnowledgeBase(chunks, fake_embed)
    assert kb.mode == "hybrid"
    assert any(h["id"] == chunks[target].id for h in kb.search("zzz unrelated words", k=2))
    assert (tmp_path / "emb.json").exists()


# ---------- agents ----------

def _db_with_profile():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from wealthwise.db import Profile
    db = SessionLocal()
    db.add(Profile(client_id="local", **PROFILE, risk_score=6, risk_category="moderate"))
    db.commit()
    return db


def test_agent_runs_tools_and_collects_citations(monkeypatch, snapshot):
    monkeypatch.setattr("wealthwise.services.load_snapshot", lambda: snapshot)
    fake = FakeGemini(tool_call("search_knowledge", query="what is a SIP"), tool_call("get_my_plan"),
                      answer("A SIP invests monthly [1]. Your plan has a few."))
    monkeypatch.setattr(assistant, "generate", fake)
    with _db_with_profile() as db:
        out = assistant.chat(db, "local", [{"role": "user", "content": "Explain SIPs and my plan"}])
    assert out["mode"] == "ai" and out["reply"].startswith("A SIP")
    assert [t["name"] for t in out["tools_used"]] == ["search_knowledge", "get_my_plan"]
    assert out["sources"][0]["n"] == 1 and out["sources"][0]["module_id"]
    # the tool result went back to the model as a function response with the call's id
    last_sent = fake.calls[-1]["contents"][-1]
    assert last_sent.parts[0].function_response.id == "call-get_my_plan"
    assert last_sent.parts[0].function_response.response["result"]["risk"]["category"] == "moderate"


def test_agent_reports_tool_errors_to_the_model(monkeypatch):
    def boom(symbol):
        raise ConnectionError("offline")
    monkeypatch.setattr(assistant, "live_stock_quote", boom)
    fake = FakeGemini(tool_call("get_stock_quote", symbol="TCS"), answer("Couldn't fetch the price right now."))
    monkeypatch.setattr(assistant, "generate", fake)
    with _db_with_profile() as db:
        out = assistant.chat(db, "local", [{"role": "user", "content": "TCS price?"}])
    sent = fake.calls[-1]["contents"][-1].parts[0].function_response.response["result"]
    assert "offline" in sent["error"] and out["reply"].startswith("Couldn't")


def test_chat_without_key_falls_back_to_search():
    with _db_with_profile() as db:
        out = assistant.chat(db, "local", [{"role": "user", "content": "how big should my emergency fund be"}])
    assert out["mode"] == "search" and out["sources"]
    assert "GEMINI_API_KEY" in out["reply"]


def test_explainer_rule_fallback(snapshot):
    plan = build_plan(PROFILE | {"risk_score": 6, "risk_category": "moderate"}, snapshot)
    out = explainer.explain_plan(plan)
    assert out["mode"] == "rules" and "6/10" in out["text"]


def test_categoriser_only_accepts_known_categories(monkeypatch):
    reply = json.dumps([{"index": 0, "category": "dining"}, {"index": 1, "category": "made-up"}])
    monkeypatch.setattr(categorizer, "generate", FakeGemini(answer(reply)))
    assert categorizer.categorize_with_ai(["CHAAYOS", "XYZ"]) == ["dining", "other"]


def test_plan_goal_tool():
    with _db_with_profile() as db:
        out = assistant.Agent(db, "local").plan_goal(target_amount_today=2_000_000, years=8)
    assert out["target_in_future_rupees"] > 2_000_000 and out["return_assumed"] == 0.12
    assert 10_000 < out["monthly_sip_needed"] < 30_000 and out["user_monthly_surplus"] == 35000


def test_generate_falls_back_when_model_is_busy(monkeypatch):
    from google.genai import errors

    from wealthwise.ai import gemini
    tried = []

    class FakeModels:
        def generate_content(self, model, contents, config):
            tried.append(model)
            if len(tried) == 1:
                raise errors.ServerError(503, {"error": {"message": "high demand", "status": "UNAVAILABLE"}})
            return answer("ok")

    monkeypatch.setattr(gemini, "client", lambda: SimpleNamespace(models=FakeModels()))
    monkeypatch.setattr(gemini, "models", lambda: ["main", "backup"])
    assert gemini.generate("hi", "sys").text == "ok"
    assert tried == ["main", "backup"]
