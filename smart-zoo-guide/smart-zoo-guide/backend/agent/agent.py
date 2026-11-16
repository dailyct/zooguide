import json
import os
from functools import lru_cache
from typing import Dict, List, Optional

from backend import config
from backend.agent import decision
from backend.agent.state import UserState
from backend.agent.tools import animal_card, get_distance, list_animal_cards


class ZooAgent:
    """規則式導覽 Agent：負責「下一站去哪」與「整條路線怎麼排」。"""

    def __init__(self, data_dir: str = config.DATA_DIR):
        animals_data = self._load(data_dir, "animals.json")
        self.animals: Dict[str, dict] = animals_data["animals"]
        self.tag_labels: Dict[str, str] = animals_data.get("tags", {})  # 興趣標籤的中文名稱
        routes_data = self._load(data_dir, "routes.json")
        self.routes: Dict[str, Dict[str, float]] = routes_data["routes"]
        self.walk_speed: float = routes_data.get("walk_speed_m_per_min", config.DEFAULT_WALK_SPEED)
        zones_data = self._load(data_dir, "zones.json")
        self.zones: Dict[str, dict] = zones_data["zones"]          # 地圖上的點：入口與各動物館
        self.areas: Dict[str, dict] = zones_data.get("areas", {})  # 地圖上的底色區塊
        self.map_size: dict = zones_data.get("map", {"width": 600, "height": 400})

    @staticmethod
    def _load(data_dir: str, filename: str) -> dict:
        with open(os.path.join(data_dir, filename), "r", encoding="utf-8") as f:
            return json.load(f)

    # ---------- 單站推薦 ----------
    def _score_candidates(self, state: UserState) -> List[dict]:
        """替每一隻「還沒看過、也不在腳邊、時間來得及」的動物打分，由高到低排序。"""
        visited_tags = [t for aid in state.visited if aid in self.animals for t in self.animals[aid]["tags"]]
        candidates = []
        for animal_id, info in self.animals.items():
            if animal_id in state.visited or animal_id == state.current_location:
                continue

            distance = get_distance(self.routes, state.current_location, animal_id)
            walk = decision.walk_minutes(distance, self.walk_speed)
            needed = walk + info["visit_time"]
            if needed > state.remaining_time:
                continue  # 時間不夠，直接排除

            interest = decision.interest_score(info["tags"], state.interests)
            dist_s = decision.distance_score(distance)
            novelty = decision.novelty_score(info["tags"], visited_tags)
            score = decision.total_score(interest, dist_s, 1.0, novelty)

            candidates.append({
                "id": animal_id,
                "name": info["name"],
                "score": score,
                "distance": distance,
                "walk_minutes": walk,
                "visit_time": info["visit_time"],
                "interest": interest,
                "novelty": novelty,
                "remaining_after": state.remaining_time - needed,
            })
        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates

    def decide(self, user_profile: dict, current_location: Optional[str] = None) -> dict:
        state = UserState.from_dict(user_profile, current_location)
        unvisited = [a for a in self.animals if a not in state.visited and a != state.current_location]
        candidates = self._score_candidates(state)

        if not candidates:
            if not unvisited:
                message = "你已經逛完所有展區了，辛苦了！"
            else:
                message = f"剩餘 {state.remaining_time} 分鐘不夠再走訪任何一個展區，建議直接前往出口。"
            return {
                "recommendation": None,
                "name": "無",
                "score": 0.0,
                "reason": [message],
                "alternatives": [],
                "message": message,
            }

        best = candidates[0]
        reasons = [
            f"符合你的興趣（{round(best['interest'] * 100)}% 匹配）",
            f"距離目前位置 {round(best['distance'])} 公尺，步行約 {best['walk_minutes']} 分鐘",
            f"參觀約需 {best['visit_time']} 分鐘，看完還剩 {best['remaining_after']} 分鐘",
        ]
        if best["novelty"] >= 0.99 and state.visited:
            reasons.append("跟你前面看過的動物類型不同，能增加新鮮感")

        return {
            "recommendation": best["id"],
            "name": best["name"],
            "score": round(best["score"], 2),
            "reason": reasons,
            "alternatives": [
                {"id": c["id"], "name": c["name"], "score": round(c["score"], 2)} for c in candidates[1:3]
            ],
            "message": None,
        }

    # ---------- 整條路線 ----------
    def plan_route(self, user_profile: dict, current_location: Optional[str] = None) -> dict:
        """每一步都重新呼叫 decide 的邏輯，直到時間用完或所有展區看完。"""
        state = UserState.from_dict(user_profile, current_location)
        start_time = state.remaining_time
        stops = []
        total_distance = 0.0

        while True:
            candidates = self._score_candidates(state)
            if not candidates:
                break
            best = candidates[0]
            spent = best["walk_minutes"] + best["visit_time"]
            stops.append({
                "id": best["id"],
                "name": best["name"],
                "distance": round(best["distance"]),
                "walk_minutes": best["walk_minutes"],
                "visit_time": best["visit_time"],
            })
            total_distance += best["distance"]
            state = state.after_visit(best["id"], spent)

        return {
            "route": [s["id"] for s in stops],
            "stops": stops,
            "estimated_time": start_time - state.remaining_time,
            "total_distance": round(total_distance),
            "start": UserState.from_dict(user_profile, current_location).current_location,
        }

    # ---------- 給前端畫地圖、列清單用 ----------
    def map_data(self) -> dict:
        return {
            "map": self.map_size,
            "areas": self.areas,
            "zones": self.zones,
            "animals": list_animal_cards(self.animals),
            "routes": self.routes,
            "tags": self.tag_labels,
        }

    def get_animal(self, animal_id: str) -> Optional[dict]:
        info = self.animals.get(animal_id)
        return animal_card(animal_id, info) if info else None


@lru_cache(maxsize=1)
def get_agent() -> ZooAgent:
    """全域共用的 Agent（第一次使用時才讀檔）。"""
    return ZooAgent()
