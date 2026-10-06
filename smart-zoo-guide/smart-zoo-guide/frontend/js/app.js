const USER_ID = "U001";

// 模擬的 User Profile (實戰中從資料庫拉取)
const userProfile = {
    user_id: USER_ID,
    current_location: "tiger",
    remaining_time: 45,
    interests: { "carnivore": 0.9, "cute": 0.3 },
    visited: ["tiger"]
};

// 1. Vision API 模擬
async function takePicture() {
    document.getElementById("vision-result").innerText = "辨識中...";
    const res = await fetch("/api/vision", { method: "POST" });
    const data = await res.json();
    document.getElementById("vision-result").innerText = `辨識成功：${data.animal} (信心度 ${data.confidence})`;
}

// 2. Chat API (RAG + LLM)
async function sendChat() {
    const msg = document.getElementById("user-msg").value;
    if (!msg) return;
    
    document.getElementById("chat-box").innerText = "思考中...";
    const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: USER_ID, message: msg })
    });
    const data = await res.json();
    document.getElementById("chat-box").innerText = data.reply;
}

// 3. Agent Recommendation API
async function getRecommendation() {
    document.getElementById("recommendation-box").innerText = "Agent 決策中...";
    const res = await fetch("/api/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(userProfile)
    });
    const data = await res.json();
    
    let html = `<strong>🎯 推薦前往：${data.name}</strong><br>`;
    html += `匹配分數：${data.score}<br><ul>`;
    data.reason.forEach(r => html += `<li>${r}</li>`);
    html += `</ul>`;
    
    document.getElementById("recommendation-box").innerHTML = html;
}