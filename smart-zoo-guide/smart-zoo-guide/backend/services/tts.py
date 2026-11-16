"""文字轉語音的前處理。

實際發聲交給瀏覽器內建的 Web Speech API（speechSynthesis），不需要額外的付費服務；
後端負責把 LLM 的回答整理成適合朗讀的純文字（去掉 Markdown 符號、限制長度）。
"""
import re

MAX_SPEAK_CHARS = 400

_MARKDOWN_PATTERNS = [
    (re.compile(r"```.*?```", re.S), ""),
    (re.compile(r"`([^`]*)`"), r"\1"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),
    (re.compile(r"\*([^*]+)\*"), r"\1"),
    (re.compile(r"^#{1,6}\s*", re.M), ""),
    (re.compile(r"^\s*[-*]\s+", re.M), ""),
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),
]


def prepare_speech_text(text: str) -> str:
    cleaned = text or ""
    for pattern, repl in _MARKDOWN_PATTERNS:
        cleaned = pattern.sub(repl, cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > MAX_SPEAK_CHARS:
        cleaned = cleaned[:MAX_SPEAK_CHARS].rstrip("，、；： ") + "……"
    return cleaned
