const USER_ID = "U001";

// 模擬的 User Profile (實戰中從資料庫拉取)
const userProfile = {
    user_id: USER_ID,
    current_location: "tiger",
    remaining_time: 45,
    interests: { "carnivore": 0.9, "cute": 0.3 },
    visited: ["tiger"]
};

// 1. Vision：即時影像物種辨識 (camera.js)
async function toggleCamera() {
    const video = document.getElementById("camera-video");
    const btn = document.getElementById("camera-btn");
    const out = document.getElementById("vision-result");
    if (ZooCamera.isRunning()) {
        ZooCamera.stop(video);
        btn.innerText = "📷 開啟即時辨識";
        return;
    }
    try {
        out.innerText = "啟動相機中...";
        await ZooCamera.start(video, renderVision);
        btn.innerText = "⏹ 停止辨識";
    } catch (e) {
        out.innerText = `無法開啟相機：${e.message}（需 HTTPS 或 localhost）`;
    }
}

function renderVision(r) {
    const out = document.getElementById("vision-result");
    if (r.error) { out.innerText = `辨識錯誤：${r.error}`; return; }
    if (!r.recognized) {
        out.innerHTML = "🔍 辨識中…請將鏡頭對準動物" +
            (r.best ? `<br><small>可能是：${r.candidates.map(c => `${c.name_zh} ${(c.confidence * 100).toFixed(0)}%`).join("、")}</small>` : "");
        return;
    }
    const b = r.best;
    out.innerHTML = `<strong>✅ ${b.name_zh}</strong>（${(b.confidence * 100).toFixed(1)}%）<br>` +
        `<em>${b.scientific_name}</em>${b.name_en ? ` · ${b.name_en}` : ""}<br>` +
        `📍 ${b.locations.join("、")}${b.conservation ? `<br>保育等級：${b.conservation}` : ""}`;
    // 讓推薦 Agent 知道使用者目前所在位置附近的動物
    userProfile.last_seen_animal = b.key;
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