import json
import os

from backend import config
from backend.agent import decision
from backend.agent.agent import ZooAgent
from backend.agent.tools import find_animal_in_text, get_distance

CARNIVORE_FAN = {"interests": {"carnivore": 0.9}, "visited": [], "remaining_time": 120, "current_location": "entrance"}


# ---------- decision：計分規則 ----------
def test_walk_minutes_rounds_up():
    assert decision.walk_minutes(120, 60) == 2
    assert decision.walk_minutes(121, 60) == 3
    assert decision.walk_minutes(0, 60) == 0
    assert decision.walk_minutes(None, 60) > 1000


def test_interest_score_is_capped_and_neutral_without_interests():
    assert decision.interest_score(["cute"], {}) == 0.5
    assert decision.interest_score(["carnivore", "large"], {"carnivore": 0.9, "large": 0.9}) == 1.0
    assert decision.interest_score(["cute"], {"carnivore": 0.9}) == 0.0


def test_distance_score_bounds():
    assert decision.distance_score(0) == 1.0
    assert decision.distance_score(config.MAX_DISTANCE_FOR_SCORE * 2) == 0.0
    assert decision.distance_score(None) == 0.0


def test_novelty_score():
    assert decision.novelty_score(["cute", "herbivore"], []) == 1.0
    assert decision.novelty_score(["cute", "herbivore"], ["cute"]) == 0.5
    assert decision.novelty_score([], ["cute"]) == 0.0


# ---------- tools ----------
def test_get_distance_is_symmetric_and_handles_unknown(agent):
    assert get_distance(agent.routes, "tiger", "tiger") == 0
    assert get_distance(agent.routes, "tiger", "lion") == get_distance(agent.routes, "lion", "tiger")
    assert get_distance(agent.routes, "tiger", "nowhere") is None


def test_find_animal_in_text(agent):
    assert find_animal_in_text("老虎為什麼有條紋？", agent.animals) == "tiger"
    assert find_animal_in_text("Where are the pandas?", agent.animals) == "panda"
    assert find_animal_in_text("今天天氣真好", agent.animals) is None
    assert find_animal_in_text("印象很深刻", agent.animals) is None  # 不能因為「象」而誤判成大象


# ---------- ZooAgent.decide ----------
def test_decide_prefers_interest_and_closeness(agent):
    result = agent.decide(CARNIVORE_FAN)
    assert result["recommendation"] == "tiger"
    assert result["name"] == "孟加拉虎"
    assert 0 < result["score"] <= 1
    assert len(result["reason"]) >= 3
    assert len(result["alternatives"]) == 2


def test_decide_skips_visited_and_current_location(agent):
    profile = dict(CARNIVORE_FAN, visited=["tiger"], current_location="lion")
    result = agent.decide(profile)
    assert result["recommendation"] not in ("tiger", "lion")


def test_decide_excludes_animals_that_do_not_fit_the_time(agent):
    # 從入口出發只有 20 分鐘：只有獼猴（走 5 分鐘 + 參觀 10 分鐘）來得及
    result = agent.decide(dict(CARNIVORE_FAN, remaining_time=20))
    assert result["recommendation"] == "monkey"


def test_decide_when_time_is_up(agent):
    result = agent.decide(dict(CARNIVORE_FAN, remaining_time=3))
    assert result["recommendation"] is None
    assert "出口" in result["message"]


def test_decide_when_everything_is_visited(agent):
    result = agent.decide(dict(CARNIVORE_FAN, visited=list(agent.animals)))
    assert result["recommendation"] is None
    assert "逛完" in result["message"]


def test_decide_accepts_explicit_current_location(agent):
    result = agent.decide({"interests": {}, "visited": [], "remaining_time": 120}, current_location="lion")
    assert result["recommendation"] != "lion"


# ---------- ZooAgent.plan_route ----------
def test_plan_route_fits_budget_and_has_no_duplicates(agent):
    plan = agent.plan_route(dict(CARNIVORE_FAN, remaining_time=90))
    assert plan["route"], "90 分鐘至少排得出一站"
    assert len(plan["route"]) == len(set(plan["route"]))
    assert plan["estimated_time"] <= 90
    assert plan["estimated_time"] == sum(s["walk_minutes"] + s["visit_time"] for s in plan["stops"])
    assert plan["start"] == "entrance"


def test_plan_route_with_no_time_is_empty(agent):
    plan = agent.plan_route(dict(CARNIVORE_FAN, remaining_time=0))
    assert plan["route"] == []
    assert plan["estimated_time"] == 0


def test_plan_route_with_plenty_of_time_visits_everything(agent):
    plan = agent.plan_route(dict(CARNIVORE_FAN, remaining_time=600))
    assert sorted(plan["route"]) == sorted(agent.animals)


# ---------- 資料一致性 ----------
def test_data_files_are_consistent(agent):
    locations = set(agent.animals) | {"entrance"}
    assert locations <= set(agent.zones), "每隻動物與入口都要有地圖座標"
    for origin in locations:
        for target in locations - {origin}:
            assert get_distance(agent.routes, origin, target) is not None, f"缺少距離 {origin}→{target}"
    for animal_id, info in agent.animals.items():
        assert info["visit_time"] > 0
        assert info["tags"]
        assert os.path.exists(os.path.join(config.KNOWLEDGE_DIR, f"{animal_id}.txt")), f"缺少 {animal_id} 的知識庫"


def test_all_animal_tags_are_declared():
    with open(os.path.join(config.DATA_DIR, "animals.json"), encoding="utf-8") as f:
        data = json.load(f)
    declared = set(data["tags"])
    used = {t for info in data["animals"].values() for t in info["tags"]}
    assert used <= declared


def test_agent_can_be_created_from_custom_data_dir():
    assert ZooAgent(config.DATA_DIR).animals
