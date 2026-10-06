import os
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict
from backend.agent.agent import ZooAgent

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PATH = os.path.join(BASE_DIR, "backend", "data", "animals.json")

agent = ZooAgent(data_path=DATA_PATH)

class RecommendRequest(BaseModel):
    user_id: str
    current_location: str
    remaining_time: int
    interests: Dict[str, float]
    visited: List[str]

@router.post("/")
async def get_recommendation(req: RecommendRequest):
    user_profile = {
        "interests": req.interests,
        "visited": req.visited,
        "remaining_time": req.remaining_time
    }
    decision = agent.decide(user_profile, req.current_location)
    return decision