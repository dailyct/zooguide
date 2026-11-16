"""語音轉文字：用 Gemini 轉錄上傳的音檔。"""
from backend.services import llm

SUPPORTED_PREFIX = "audio/"


class STTUnavailable(RuntimeError):
    """沒有設定 GEMINI_API_KEY。"""


def transcribe(audio_bytes: bytes, mime_type: str) -> str:
    if not llm.is_available():
        raise STTUnavailable("伺服器尚未設定 GEMINI_API_KEY，無法進行語音轉文字")

    from google.genai import types

    # 瀏覽器錄音常見 "audio/webm;codecs=opus"，只保留主要類型
    clean_type = (mime_type or "audio/webm").split(";")[0].strip()
    text = llm.generate_with_parts(
        "請逐字轉錄這段語音，使用繁體中文，只輸出轉錄的文字，不要加任何說明。如果沒有聽到語音，輸出空白。",
        [types.Part.from_bytes(data=audio_bytes, mime_type=clean_type)],
    )
    return text.strip()
