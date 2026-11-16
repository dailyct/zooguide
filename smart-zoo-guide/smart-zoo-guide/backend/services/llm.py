"""Gemini 文字生成與向量化的薄封裝。

沒有設定 GEMINI_API_KEY 時 is_available() 為 False，呼叫端應該自行走離線流程。
"""
import threading
from typing import List, Optional

from backend import config


class LLMUnavailable(RuntimeError):
    """沒有 API Key、或 SDK 未安裝。"""


_client = None
_client_lock = threading.Lock()


def is_available() -> bool:
    return config.has_gemini()


def get_client():
    global _client
    if not is_available():
        raise LLMUnavailable("尚未設定 GEMINI_API_KEY")
    with _client_lock:
        if _client is None:
            try:
                from google import genai
            except ImportError as exc:  # pragma: no cover
                raise LLMUnavailable("未安裝 google-genai 套件") from exc
            _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def generate(system: str, messages: List[dict], temperature: float = 0.3) -> str:
    """messages 格式：[{"role": "user" | "assistant", "content": "..."}]，最後一則必須是 user。"""
    from google.genai import types

    client = get_client()
    contents = [
        types.Content(
            role="user" if m["role"] == "user" else "model",
            parts=[types.Part.from_text(text=m["content"])],
        )
        for m in messages
    ]
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=system, temperature=temperature),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("模型沒有回傳內容")
    return text


def generate_with_parts(prompt: str, parts: list, json_output: bool = False) -> str:
    """多模態呼叫（圖片、音訊）。parts 是 google.genai.types.Part 的清單。"""
    from google.genai import types

    client = get_client()
    cfg = types.GenerateContentConfig(
        temperature=0.0,
        response_mime_type="application/json" if json_output else None,
    )
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=list(parts) + [prompt],
        config=cfg,
    )
    return (response.text or "").strip()


def embed(texts: List[str], task_type: Optional[str] = None) -> List[List[float]]:
    from google.genai import types

    client = get_client()
    cfg = types.EmbedContentConfig(task_type=task_type) if task_type else None
    response = client.models.embed_content(
        model=config.GEMINI_EMBEDDING_MODEL,
        contents=texts,
        config=cfg,
    )
    return [list(e.values) for e in response.embeddings]
