"""Agent 決策時使用的使用者狀態。"""
from dataclasses import dataclass, field
from typing import Dict, List

from backend import config


@dataclass
class UserState:
    interests: Dict[str, float] = field(default_factory=dict)
    visited: List[str] = field(default_factory=list)
    remaining_time: int = config.DEFAULT_REMAINING_TIME
    current_location: str = config.DEFAULT_LOCATION

    @classmethod
    def from_dict(cls, data: dict, current_location: str = None) -> "UserState":
        return cls(
            interests=dict(data.get("interests") or {}),
            visited=list(data.get("visited") or []),
            remaining_time=int(data.get("remaining_time", config.DEFAULT_REMAINING_TIME)),
            current_location=current_location or data.get("current_location") or config.DEFAULT_LOCATION,
        )

    def after_visit(self, animal_id: str, minutes_spent: int) -> "UserState":
        """回傳參觀完某隻動物後的新狀態（不修改原物件）。"""
        return UserState(
            interests=self.interests,
            visited=self.visited + [animal_id],
            remaining_time=max(0, self.remaining_time - minutes_spent),
            current_location=animal_id,
        )
