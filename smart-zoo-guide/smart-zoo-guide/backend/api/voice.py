from fastapi import APIRouter

router = APIRouter()

@router.post("/stt")
async def speech_to_text():
    return {"text": "這是一段語音轉文字的測試"}

@router.post("/tts")
async def text_to_speech():
    return {"status": "success", "audio_url": "/mock_audio.mp3"}