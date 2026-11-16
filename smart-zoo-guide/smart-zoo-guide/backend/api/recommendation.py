from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.agent.agent import get_agent
from backend.api.common import resolve_profile
from backend.database import database

router = APIRouter()


class RecommendRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    # 以下欄位都是可選的；沒帶的就使用資料庫裡儲存的使用者資料
    current_location: Optional[str] = None
    remaining_time: Optional[int] = Field(default=None, ge=0, le=1440)
    interests: Optional[Dict[str, float]] = None
    visited: Optional[List[str]] = None


@router.post("")
def get_recommendation(req: RecommendRequest):
    profile = resolve_profile(req.user_id, req.current_location, req.remaining_time, req.interests, req.visited)
    decision = get_agent().decide(profile)
    database.log_interaction(req.user_id, "recommend", decision["recommendation"])
    return decision
