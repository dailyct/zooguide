"""文字向量化。

- 有 GEMINI_API_KEY：使用 Gemini embedding（語意檢索，效果較好）。
- 沒有：使用本機的雜湊 n-gram 向量（不需網路，適合開發與測試；中文用單字加雙字詞）。
"""
import hashlib
import math
import re
from typing import List

from backend import config
from backend.services import llm

LOCAL_DIM = 512
_TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]")


def _tokens(text: str) -> List[str]:
    """英數字以單字為單位；中文以單字加相鄰雙字詞為單位。"""
    raw = _TOKEN_RE.findall(text.lower())
    tokens = list(raw)
    for a, b in zip(raw, raw[1:]):
        if "一" <= a <= "鿿" and "一" <= b <= "鿿":
            tokens.append(a + b)
    return tokens


def _hash_embed(text: str) -> List[float]:
    vec = [0.0] * LOCAL_DIM
    for tok in _tokens(text):
        digest = hashlib.md5(tok.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % LOCAL_DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def embedder_name() -> str:
    """向量來源的識別字串；來源改變時，向量庫必須重建。"""
    if llm.is_available():
        return f"gemini:{config.GEMINI_EMBEDDING_MODEL}"
    return f"local-hash-{LOCAL_DIM}"


def _normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def embed_documents(texts: List[str]) -> List[List[float]]:
    if llm.is_available():
        return [_normalize(v) for v in llm.embed(texts, task_type="RETRIEVAL_DOCUMENT")]
    return [_hash_embed(t) for t in texts]


def embed_query(text: str) -> List[float]:
    if llm.is_available():
        return _normalize(llm.embed([text], task_type="RETRIEVAL_QUERY")[0])
    return _hash_embed(text)
