"""推薦分數的計算規則。

總分 = 興趣 × 0.40 + 距離 × 0.25 + 時間 × 0.20 + 新鮮度 × 0.15
其中「時間」是硬性條件：走過去加上參觀所需時間超過剩餘時間的動物，會被直接排除。
"""
from typing import Dict, List, Optional

from backend import config

WEIGHTS = {"interest": 0.40, "distance": 0.25, "time": 0.20, "novelty": 0.15}


def interest_score(animal_tags: List[str], interests: Dict[str, float]) -> float:
    """動物標籤與使用者興趣的匹配度（0~1）。沒有填興趣時給中性分數 0.5。"""
    if not interests:
        return 0.5
    score = sum(interests.get(tag, 0.0) for tag in animal_tags)
    return max(0.0, min(score, 1.0))


def distance_score(distance: Optional[float]) -> float:
    """越近越高；距離未知視為 0 分。"""
    if distance is None:
        return 0.0
    return max(0.0, 1.0 - distance / config.MAX_DISTANCE_FOR_SCORE)


def novelty_score(animal_tags: List[str], visited_tags: List[str]) -> float:
    """這隻動物的標籤裡，有多少是使用者還沒接觸過的（0~1）。"""
    if not animal_tags:
        return 0.0
    unseen = [t for t in animal_tags if t not in set(visited_tags)]
    return len(unseen) / len(animal_tags)


def walk_minutes(distance: Optional[float], walk_speed: float) -> int:
    """走過去需要的分鐘數（無條件進位）。距離未知時回傳一個很大的值。"""
    if distance is None:
        return 10 ** 6
    if distance <= 0:
        return 0
    return int(-(-distance // walk_speed))  # ceil


def total_score(interest: float, distance: float, time_ok: float, novelty: float) -> float:
    return (
        interest * WEIGHTS["interest"]
        + distance * WEIGHTS["distance"]
        + time_ok * WEIGHTS["time"]
        + novelty * WEIGHTS["novelty"]
    )
