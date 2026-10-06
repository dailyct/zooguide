from fastapi import APIRouter

router = APIRouter()

@router.post("/")
async def vision_mock():
    return {"animal": "tiger", "confidence": 0.94}