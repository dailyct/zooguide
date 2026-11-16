"""輕量向量庫：純 Python 實作，資料以 JSON 存檔（動物園的知識量很小，不需要外部資料庫）。

向量在寫入前都已 L2 正規化，因此內積就是 cosine 相似度。
"""
import json
import os
import threading
from typing import Dict, List, Optional


class VectorStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self.embedder: str = ""
        self.items: List[dict] = []  # {"id", "text", "vector", "metadata"}
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.embedder = data.get("embedder", "")
            self.items = data.get("items", [])
        except (json.JSONDecodeError, OSError):
            # 檔案壞掉就當作空庫，之後會自動重建
            self.embedder, self.items = "", []

    def _save(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"embedder": self.embedder, "items": self.items}, f, ensure_ascii=False)
        os.replace(tmp, self.path)

    def __len__(self) -> int:
        return len(self.items)

    def replace_all(self, items: List[dict], embedder: str) -> None:
        with self._lock:
            self.items = items
            self.embedder = embedder
            self._save()

    def search(self, query_vector: List[float], k: int = 3, filter_meta: Optional[Dict[str, str]] = None) -> List[dict]:
        with self._lock:
            pool = self.items
        if filter_meta:
            pool = [it for it in pool if all(it["metadata"].get(key) == val for key, val in filter_meta.items())]
        scored = []
        for it in pool:
            vec = it["vector"]
            if len(vec) != len(query_vector):
                continue
            score = sum(a * b for a, b in zip(vec, query_vector))
            scored.append({"id": it["id"], "text": it["text"], "metadata": it["metadata"], "score": score})
        scored.sort(key=lambda s: s["score"], reverse=True)
        return scored[:k]
