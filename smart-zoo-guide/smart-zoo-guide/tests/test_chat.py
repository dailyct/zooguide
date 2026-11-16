from backend.api import chat as chat_module
from backend.database import database


def test_chat_offline_answers_from_the_knowledge_base(client):
    res = client.post("/api/chat", json={"user_id": "u1", "message": "老虎為什麼有條紋？"})
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "offline"
    assert body["animal"] == "tiger"
    assert "離線模式" in body["reply"]
    assert "條紋" in body["reply"]
    assert body["sources"] and all(s["animal_id"] == "tiger" for s in body["sources"])


def test_chat_uses_the_animal_being_viewed_when_the_question_names_none(client):
    res = client.post("/api/chat", json={"user_id": "u1", "message": "牠為什麼有條紋？", "current_animal": "tiger"})
    assert res.json()["animal"] == "tiger"


def test_chat_ignores_an_unknown_current_animal(client):
    res = client.post("/api/chat", json={"user_id": "u1", "message": "你好", "current_animal": "dragon"})
    assert res.status_code == 200
    assert res.json()["animal"] is None


def test_chat_validates_input(client):
    assert client.post("/api/chat", json={"user_id": "u1", "message": ""}).status_code == 422
    assert client.post("/api/chat", json={"user_id": "u1", "message": "x" * 501}).status_code == 422
    assert client.post("/api/chat", json={"message": "hi"}).status_code == 422


def test_chat_history_is_saved(client):
    client.post("/api/chat", json={"user_id": "u1", "message": "企鵝會飛嗎？"})
    history = database.get_chat_history("u1")
    assert [m.role for m in history] == ["user", "assistant"]
    assert history[0].content == "企鵝會飛嗎？"


def test_chat_uses_gemini_when_available(client, monkeypatch):
    captured = {}

    def fake_generate(system, messages, temperature=0.3):
        captured["messages"] = messages
        return "這是模型的回答"

    monkeypatch.setattr(chat_module.llm, "is_available", lambda: True)
    monkeypatch.setattr(chat_module.llm, "generate", fake_generate)
    monkeypatch.setattr(chat_module.retriever, "retrieve", lambda *a, **k: [
        {"id": "x", "text": "老虎的條紋是保護色。", "metadata": {"animal_id": "tiger"}, "score": 1.0}])

    # 先塞一段「以 assistant 開頭」的歷史，確認送給模型前會被修掉
    database.add_chat_message("u2", "assistant", "上一輪的回答")
    database.add_chat_message("u2", "user", "上一輪的問題")
    database.add_chat_message("u2", "assistant", "上一輪的回答 2")

    res = client.post("/api/chat", json={"user_id": "u2", "message": "老虎的條紋有什麼用？"})
    assert res.json()["reply"] == "這是模型的回答"
    assert res.json()["mode"] == "gemini"
    messages = captured["messages"]
    assert messages[0]["role"] == "user"
    assert messages[-1]["role"] == "user" and "老虎的條紋是保護色" in messages[-1]["content"]


def test_chat_falls_back_to_offline_when_the_model_fails(client, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(chat_module.llm, "is_available", lambda: True)
    monkeypatch.setattr(chat_module.llm, "generate", boom)
    monkeypatch.setattr(chat_module.retriever, "retrieve", lambda *a, **k: [])

    res = client.post("/api/chat", json={"user_id": "u3", "message": "你好"})
    assert res.status_code == 200
    assert res.json()["mode"] == "offline"
