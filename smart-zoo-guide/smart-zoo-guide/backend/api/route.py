from typing import Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.agent.agent import get_agent
from backend.api.common import resolve_profile
from backend.database import database

router = APIRouter()


class RouteRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    time: Optional[int] = Field(default=None, ge=0, le=1440)  # 可用時間（分鐘），沒帶就用資料庫的剩餘時間
    current_location: Optional[str] = None
    interests: Optional[Dict[str, float]] = None
    visited: Optional[List[str]] = None


@router.post("")
def generate_route(req: RouteRequest):
    profile = resolve_profile(req.user_id, req.current_location, req.time, req.interests, req.visited)
    plan = get_agent().plan_route(profile)
    database.log_interaction(req.user_id, "route", None, ",".join(plan["route"]))
    return plan


@router.get("/map")
def get_map():
    """園區地圖資料：展區座標、動物清單與距離表。"""
    return get_agent().map_data()
