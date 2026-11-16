from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agent.agent import get_agent
from backend.agent.decision import walk_minutes
from backend.agent.tools import get_distance
from backend.database import database
from backend.database.models import UserProfile

router = APIRouter()


class ProfileUpdate(BaseModel):
    current_location: str
    remaining_time: int = Field(ge=0, le=1440)
    interests: dict
    visited: list


class VisitRequest(BaseModel):
    animal_id: str


def _validate(animal_ids: list, location: str) -> None:
    agent = get_agent()
    unknown = [a for a in animal_ids if a not in agent.animals]
    if unknown:
        raise HTTPException(status_code=422, detail=f"未知的動物：{', '.join(unknown)}")
    if location not in agent.animals and location not in agent.zones:
        raise HTTPException(status_code=422, detail=f"未知的位置：{location}")


@router.get("/{user_id}")
def read_profile(user_id: str):
    return database.get_profile(user_id)


@router.put("/{user_id}")
def update_profile(user_id: str, body: ProfileUpdate):
    _validate(body.visited, body.current_location)
    profile = UserProfile(
        user_id=user_id,
        current_location=body.current_location,
        remaining_time=body.remaining_time,
        interests={str(k): float(v) for k, v in body.interests.items()},
        visited=[str(a) for a in body.visited],
    )
    return database.save_profile(profile)


@router.post("/{user_id}/visit")
def visit_animal(user_id: str, body: VisitRequest):
    """遊客抵達並參觀完一隻動物：標記已參觀、更新位置、扣掉走路加參觀的時間。"""
    agent = get_agent()
    info = agent.animals.get(body.animal_id)
    if info is None:
        raise HTTPException(status_code=404, detail="找不到這隻動物")

    profile = database.get_profile(user_id)
    distance = get_distance(agent.routes, profile.current_location, body.animal_id)
    spent = info["visit_time"] + (walk_minutes(distance, agent.walk_speed) if distance is not None else 0)

    profile.remaining_time = max(0, profile.remaining_time - spent)
    profile.current_location = body.animal_id
    if body.animal_id not in profile.visited:
        profile.visited.append(body.animal_id)
    saved = database.save_profile(profile)
    database.log_interaction(user_id, "visit", body.animal_id)
    return saved
