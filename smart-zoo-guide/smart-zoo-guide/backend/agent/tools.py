"""Agent 與 API 共用的小工具函式（純函式，方便測試）。"""
from typing import Dict, List, Optional


def get_distance(routes: Dict[str, Dict[str, float]], origin: str, target: str) -> Optional[float]:
    """兩點之間的距離（公尺）；同一點為 0，查無資料回傳 None。"""
    if origin == target:
        return 0
    if target in routes.get(origin, {}):
        return routes[origin][target]
    # 路線表是對稱的，反向查一次
    return routes.get(target, {}).get(origin)


def find_animal_in_text(text: str, animals: Dict[str, dict]) -> Optional[str]:
    """從一句話裡找出提到的動物 id（比對名稱與別名，取最長的別名優先）。"""
    lowered = (text or "").lower()
    best_id, best_len = None, 0
    for animal_id, info in animals.items():
        names = [animal_id, info.get("name", "")] + list(info.get("aliases", []))
        for name in names:
            name = (name or "").lower()
            if name and name in lowered and len(name) > best_len:
                best_id, best_len = animal_id, len(name)
    return best_id


def animal_card(animal_id: str, info: dict) -> dict:
    """對外回傳用的動物簡介。"""
    return {
        "id": animal_id,
        "name": info["name"],
        "english_name": info.get("english_name", ""),
        "tags": info.get("tags", []),
        "visit_time": info["visit_time"],
        "zone": info.get("zone"),
        "description": info.get("description", ""),
    }


def list_animal_cards(animals: Dict[str, dict]) -> List[dict]:
    return [animal_card(aid, info) for aid, info in animals.items()]
