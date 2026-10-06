from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class RouteRequest(BaseModel):
    user_id: str
    time: int

@router.post("/")
async def generate_route(req: RouteRequest):
    return {"route": ["Tiger", "Lion", "Panda"], "estimated_time": 45}