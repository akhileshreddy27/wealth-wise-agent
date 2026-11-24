from tests.conftest import PROFILE


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ai_enabled"] is False and body["has_profile"] is False


def test_profile_then_plan(client):
    assert client.get("/api/plan").status_code == 404
    assert client.put("/api/profile", json=PROFILE | {"answers": {"market_drop": 3}}).status_code == 422

    saved = client.put("/api/profile", json=PROFILE).json()
    assert 1 <= saved["risk_score"] <= 10
    plan = client.get("/api/plan").json()
    assert plan["risk"]["score"] == saved["risk_score"] and plan["sleeves"]
    assert client.post("/api/plan/explain").json()["mode"] == "rules"


def test_transactions_crud_and_budgets(client):
    created = client.post("/api/transactions", json={"date": "2026-06-03", "amount": 450, "note": "Zomato"}).json()
    assert created["category"] == "dining"                         # auto-categorised
    assert client.post("/api/transactions", json={"date": "2026-06-03", "amount": 1, "category": "nope"}).status_code == 422

    updated = client.put(f"/api/transactions/{created['id']}",
                         json={"date": "2026-06-03", "amount": 500, "category": "groceries", "note": "Zomato"}).json()
    assert updated["category"] == "groceries" and updated["amount"] == 500

    assert client.put("/api/budgets", json={"groceries": 400}).json() == {"groceries": 400}
    summary = client.get("/api/expenses/summary").json()
    assert summary["months"] == ["2026-06"]
    assert summary["summary"]["categories"][0]["budget_used"] == 1.25

    assert client.delete(f"/api/transactions/{created['id']}").status_code == 204
    assert client.get("/api/transactions").json() == []


def test_demo_import_skips_duplicates(client):
    first = client.post("/api/transactions/demo").json()
    assert first["imported"] > 100
    assert client.post("/api/transactions/demo").json()["duplicates"] == first["imported"]
    upload = client.post("/api/transactions/import",
                         files={"file": ("s.csv", b"Date,Narration,Amount\n01/01/2026,Uber,-200\n", "text/csv")}).json()
    assert upload["imported"] == 1


def test_learn_and_chat(client):
    modules = client.get("/api/learn/modules").json()
    assert len(modules) == 13
    lesson = client.get(f"/api/learn/modules/{modules[0]['id']}").json()
    assert lesson["markdown"].startswith("# ") and lesson["quiz"]
    reply = client.post("/api/chat", json={"messages": [{"role": "user", "content": "What is an index fund?"}]}).json()
    assert reply["mode"] == "search" and reply["sources"]
    assert client.post("/api/chat", json={"messages": [{"role": "assistant", "content": "hi"}]}).status_code == 422
