"""檢索入口：第一次使用時自動建庫；向量來源（離線／Gemini）改變時自動重建。"""
import threading
from typing import List, Optional

from backend import config
from backend.rag import embeddings, ingest
from backend.rag.vector_store import VectorStore

_store: Optional[VectorStore] = None
_lock = threading.Lock()


def get_store() -> VectorStore:
    global _store
    with _lock:
        if _store is None:
            _store = VectorStore(config.VECTOR_DB_PATH)
        if len(_store) == 0 or _store.embedder != embeddings.embedder_name():
            ingest.ingest(_store)
    return _store


def reset() -> None:
    """測試用：丟掉快取，下次檢索會重新載入。"""
    global _store
    with _lock:
        _store = None


def retrieve(query: str, k: int = config.RAG_TOP_K, animal_id: Optional[str] = None) -> List[dict]:
    """回傳最相關的 k 個片段。指定 animal_id 時只在該動物的知識裡找。"""
    store = get_store()
    vector = embeddings.embed_query(query)
    filter_meta = {"animal_id": animal_id} if animal_id else None
    return store.search(vector, k=k, filter_meta=filter_meta)
