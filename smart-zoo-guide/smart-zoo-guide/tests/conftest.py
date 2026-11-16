"""測試共用設定：每個測試都用獨立的暫存資料庫與向量庫，並強制走離線模式（不呼叫 Gemini）。"""
import pytest

from backend import config
from backend.rag import retriever


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(config, "VECTOR_DB_PATH", str(tmp_path / "vector_db" / "store.json"))
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    retriever.reset()
    yield
    retriever.reset()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def agent():
    from backend.agent.agent import ZooAgent

    return ZooAgent()
