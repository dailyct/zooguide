from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backend.api.common import read_upload
from backend.services import stt, tts

router = APIRouter()


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/stt")
def speech_to_text(file: UploadFile = File(...)):
    content_type = file.content_type or ""
    if not content_type.startswith(stt.SUPPORTED_PREFIX):
        raise HTTPException(status_code=400, detail="請上傳音訊檔（audio/*）")
    data = read_upload(file)
    try:
        text = stt.transcribe(data, content_type)
    except stt.STTUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"語音辨識服務暫時無法使用：{exc}")
    return {"text": text}


@router.post("/tts")
def text_to_speech(req: TTSRequest):
    """回傳整理好的朗讀文字；實際發聲由瀏覽器的 speechSynthesis 負責。"""
    return {"status": "success", "text": tts.prepare_speech_text(req.text), "engine": "browser", "lang": "zh-TW"}
