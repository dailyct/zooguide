from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class ChatRequest(BaseModel):
    user_id: str
    message: str

@router.post("/")
async def chat(req: ChatRequest):
    return {"reply": f"這是模組化架構的回應！你問了：{req.message}"}