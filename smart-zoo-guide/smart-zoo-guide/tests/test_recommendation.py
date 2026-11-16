import pytest

PROFILE = {"user_id": "u1", "current_location": "entrance", "remaining_time": 120,
           "interests": {"carnivore": 0.9}, "visited": []}


def test_recommend_with_explicit_profile(client):
    res = client.post("/api/recommend", json=PROFILE)
    assert res.status_code == 200
    body = res.json()
    assert body["recommendation"] == "tiger"
    assert body["reason"]


def test_recommend_falls_back_to_the_stored_profile(client):
    res = client.post("/api/recommend", json={"user_id": "brand-new"})
    assert res.status_code == 200
    assert res.json()["recommendation"] is not None  # 預設 60 分鐘、位置在入口


def test_recommend_when_time_is_up_returns_null(client):
    res = client.post("/api/recommend", json=dict(PROFILE, remaining_time=3))
    assert res.status_code == 200
    assert res.json()["recommendation"] is None
    assert res.json()["message"]


@pytest.mark.parametrize("bad", [{"remaining_time": -1}, {"remaining_time": 99999}, {"interests": {"cute": "lots"}}])
def test_recommend_rejects_invalid_input(client, bad):
    assert client.post("/api/recommend", json=dict(PROFILE, **bad)).status_code == 422


def test_route_plan_fits_the_time_budget(client):
    res = client.post("/api/route", json={"user_id": "u1", "time": 90, "interests": {"cute": 0.9}})
    assert res.status_code == 200
    body = res.json()
    assert body["route"] and len(body["route"]) == len(set(body["route"]))
    assert body["estimated_time"] <= 90


def test_map_data_has_zones_and_animals(client):
    body = client.get("/api/route/map").json()
    assert "entrance" in body["zones"]
    assert {a["id"] for a in body["animals"]} <= set(body["zones"])
    assert body["areas"] and body["map"]["width"] > 0
    assert body["tags"]["carnivore"] == "肉食"
    assert all(a["zone"] in body["areas"] for a in body["animals"])


def test_profile_defaults_update_and_validation(client):
    profile = client.get("/api/profile/p1").json()
    assert profile["current_location"] == "entrance"
    assert profile["visited"] == []

    ok = client.put("/api/profile/p1", json={"current_location": "lion", "remaining_time": 30,
                                             "interests": {"cute": 1.5}, "visited": ["tiger"]})
    assert ok.status_code == 200
    assert ok.json()["interests"] == {"cute": 1.0}  # 權重會被限制在 0~1
    assert client.get("/api/profile/p1").json()["visited"] == ["tiger"]

    bad_animal = client.put("/api/profile/p1", json={"current_location": "entrance", "remaining_time": 30,
                                                     "interests": {}, "visited": ["dragon"]})
    assert bad_animal.status_code == 422
    bad_place = client.put("/api/profile/p1", json={"current_location": "moon", "remaining_time": 30,
                                                    "interests": {}, "visited": []})
    assert bad_place.status_code == 422


def test_visit_updates_time_location_and_is_idempotent(client):
    first = client.post("/api/profile/v1/visit", json={"animal_id": "tiger"}).json()
    # 預設 60 分鐘；入口→老虎 410 公尺（走 7 分鐘）+ 參觀 15 分鐘
    assert first["remaining_time"] == 60 - 7 - 15
    assert first["current_location"] == "tiger"
    assert first["visited"] == ["tiger"]

    second = client.post("/api/profile/v1/visit", json={"animal_id": "tiger"}).json()
    assert second["visited"] == ["tiger"]

    follow_up = client.post("/api/recommend", json={"user_id": "v1"}).json()
    assert follow_up["recommendation"] != "tiger"


def test_visit_unknown_animal_is_404(client):
    assert client.post("/api/profile/v1/visit", json={"animal_id": "dragon"}).status_code == 404


def test_health_reports_offline_mode(client):
    assert client.get("/api/health").json() == {"status": "ok", "llm": "offline"}
