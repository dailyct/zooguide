import json

class ZooAgent:
    # 接收外部傳入的 data_path
    def __init__(self, data_path):
        with open(data_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.animals = data["animals"]
            self.routes = data["routes"]

    def calculate_interest_score(self, animal_tags, user_interests):
        score = 0.0
        for tag in animal_tags:
            if tag in user_interests:
                score += user_interests[tag]
        return min(score, 1.0)

    def decide(self, user_profile, current_location="tiger"):
        best_animal = None
        highest_score = -1
        reasons = []

        interests = user_profile.get("interests", {})
        visited = user_profile.get("visited", [])
        remaining_time = user_profile.get("remaining_time", 60)

        for animal_id, info in self.animals.items():
            if animal_id in visited or animal_id == current_location:
                continue
            
            interest_score = self.calculate_interest_score(info["tags"], interests)
            distance = self.routes.get(current_location, {}).get(animal_id, 999)
            distance_score = max(0, 1.0 - (distance / 500)) 
            time_score = 1.0 if remaining_time >= info["visit_time"] else 0.0
            novelty_score = 1.0 

            total_score = (interest_score * 0.4) + (distance_score * 0.25) + (time_score * 0.2) + (novelty_score * 0.15)

            if total_score > highest_score:
                highest_score = total_score
                best_animal = animal_id
                reasons = [
                    f"符合你的興趣 ({round(interest_score*100)}% 匹配)",
                    f"距離目前位置 {distance} 公尺",
                    f"參觀時間需 {info['visit_time']} 分鐘，時間充裕"
                ]

        return {
            "recommendation": best_animal,
            "name": self.animals[best_animal]["name"] if best_animal else "無",
            "score": round(highest_score, 2),
            "reason": reasons
        }