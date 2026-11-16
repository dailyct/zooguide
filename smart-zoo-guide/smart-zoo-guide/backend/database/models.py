"""資料庫與 API 共用的資料模型。"""
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from backend import config


class UserProfile(BaseModel):
    user_id: str
    current_location: str = config.DEFAULT_LOCATION
    remaining_time: int = Field(default=config.DEFAULT_REMAINING_TIME, ge=0, le=1440)
    interests: Dict[str, float] = Field(default_factory=dict)
    visited: List[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: str  # "user" 或 "assistant"
    content: str


class Interaction(BaseModel):
    user_id: str
    action: str
    animal_id: Optional[str] = None
    detail: Optional[str] = None
