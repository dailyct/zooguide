"""動物影像辨識：Gemini 多模態；沒有 API Key 時退回「檔名提示」。"""
import io
import json
from typing import Dict, Optional

from backend import config
from backend.agent.tools import find_animal_in_text
from backend.services import llm


class InvalidImage(ValueError):
    """上傳的檔案不是可讀取的圖片。"""


def prepare_image(data: bytes) -> bytes:
    """驗證、轉成 RGB JPEG，並把最長邊縮到 MAX_IMAGE_SIDE 以內。"""
    from PIL import Image, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImage("無法讀取圖片，請確認檔案格式（JPG、PNG 等）") from exc

    image = image.convert("RGB")
    image.thumbnail((config.MAX_IMAGE_SIDE, config.MAX_IMAGE_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


def _build_prompt(animals: Dict[str, dict]) -> str:
    listing = "\n".join(f'- {aid}: {info["name"]}（{info.get("english_name", "")}）' for aid, info in animals.items())
    return (
        "你是動物園的影像辨識助手。請判斷這張照片中的主要動物是下列哪一種，只能從清單中選擇：\n"
        f"{listing}\n"
        "如果照片中沒有動物，或不是清單中的任何一種，animal 請填 \"unknown\"。\n"
        "請只回傳 JSON：{\"animal\": \"<id 或 unknown>\", \"confidence\": <0 到 1 的數字>}"
    )


def _parse_result(raw: str, animals: Dict[str, dict]) -> dict:
    """解析模型回傳的 JSON，並驗證 id 與信心度。"""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text.lower().startswith("json") else text
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"animal": None, "confidence": 0.0}

    animal = data.get("animal")
    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    if animal not in animals:
        return {"animal": None, "confidence": 0.0}
    return {"animal": animal, "confidence": round(confidence, 2)}


def recognize(image_bytes: bytes, filename: Optional[str], animals: Dict[str, dict]) -> dict:
    """回傳 {"animal": id|None, "name": str|None, "confidence": float, "mode": "gemini"|"offline"}。"""
    jpeg = prepare_image(image_bytes)  # 無論哪種模式都先驗證圖片

    if llm.is_available():
        from google.genai import types

        raw = llm.generate_with_parts(
            _build_prompt(animals),
            [types.Part.from_bytes(data=jpeg, mime_type="image/jpeg")],
            json_output=True,
        )
        result = _parse_result(raw, animals)
        mode = "gemini"
    else:
        hinted = find_animal_in_text(filename or "", animals)
        result = {"animal": hinted, "confidence": 0.5 if hinted else 0.0}
        mode = "offline"

    animal_id = result["animal"]
    result["name"] = animals[animal_id]["name"] if animal_id else None
    result["mode"] = mode
    return result
