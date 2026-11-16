/* 畫面與流程：把 Api、ZooMap、Camera、Voice 串起來。使用者資料都存在後端，前端只記得 user id。 */
(function () {
    "use strict";

    const $ = function (id) { return document.getElementById(id); };
    const el = Dom.el;

    function getUserId() {
        try {
            let id = localStorage.getItem("zoo_user_id");
            if (!id) {
                id = "u-" + Math.random().toString(36).slice(2, 10);
                localStorage.setItem("zoo_user_id", id);
            }
            return id;
        } catch (err) {
            return "u-" + Math.random().toString(36).slice(2, 10); // 瀏覽器禁用儲存空間時，這次造訪用臨時 id
        }
    }

    const state = {
        userId: getUserId(),
        map: null,         // /api/route/map
        profile: null,     // /api/profile/{id}
        recommendation: null,
        plan: null,
        selected: null,    // 地圖上選取的動物
        currentAnimal: null, // 聊天時帶入的動物（相機辨識或問答偵測到的）
    };

    // ---------- 小工具 ----------
    let statusTimer = null;
    function setStatus(message, isError) {
        const box = $("status");
        box.textContent = message || "";
        box.className = "status" + (isError ? " error" : "");
        clearTimeout(statusTimer);
        if (message) statusTimer = setTimeout(function () { box.textContent = ""; }, isError ? 6000 : 3000);
    }

    /* 執行非同步動作期間停用按鈕，錯誤統一顯示在底部提示。 */
    async function guarded(button, fn) {
        if (button) button.disabled = true;
        try {
            await fn();
        } catch (err) {
            setStatus(err.message, true);
        } finally {
            if (button) button.disabled = false;
        }
    }

    /* 會改動使用者資料的操作排成一列，避免快速連點時後送出的請求被先到的蓋掉。 */
    let queue = Promise.resolve();
    function enqueue(fn) {
        queue = queue.then(fn).catch(function (err) { setStatus(err.message, true); });
        return queue;
    }

    function animalName(id) {
        const found = state.map.animals.find(function (a) { return a.id === id; });
        return found ? found.name : id;
    }

    function invalidateSuggestions() {
        state.recommendation = null;
        state.plan = null;
    }

    // ---------- 行程 ----------
    function renderTrip() {
        const profile = state.profile;
        $("time-input").value = profile.remaining_time;
        const here = state.map.zones[profile.current_location];
        $("location-label").textContent = here ? here.name : profile.current_location;
        $("visited-count").textContent = profile.visited.length;
        $("animal-total").textContent = state.map.animals.length;

        const box = Dom.clear($("interest-chips"));
        Object.keys(state.map.tags).forEach(function (tag) {
            const on = (profile.interests[tag] || 0) > 0;
            box.appendChild(el("button", {
                type: "button",
                class: "chip",
                "aria-pressed": on ? "true" : "false",
                text: state.map.tags[tag],
                onclick: function () { toggleInterest(tag); },
            }));
        });
    }

    function saveProfile(patch) {
        return enqueue(async function () {
            const merged = Object.assign({}, state.profile, patch);
            state.profile = await Api.saveProfile(state.userId, {
                current_location: merged.current_location,
                remaining_time: merged.remaining_time,
                interests: merged.interests,
                visited: merged.visited,
            });
            invalidateSuggestions();
            renderAll();
        });
    }

    function toggleInterest(tag) {
        const interests = Object.assign({}, state.profile.interests);
        if ((interests[tag] || 0) > 0) delete interests[tag];
        else interests[tag] = 0.9;
        saveProfile({ interests: interests });
    }

    $("time-input").addEventListener("change", function (event) {
        if (!state.profile) return;
        const minutes = Math.max(0, Math.min(1440, parseInt(event.target.value, 10) || 0));
        saveProfile({ remaining_time: minutes });
    });

    $("reset-btn").addEventListener("click", function () {
        if (!state.profile) return;
        state.currentAnimal = null;
        state.selected = null;
        saveProfile({ visited: [], current_location: "entrance" }).then(function () {
            setStatus("已清除參觀紀錄，剩餘時間請依需要自行調整");
        });
    });

    async function visit(animalId) {
        await enqueue(async function () {
            state.profile = await Api.visit(state.userId, animalId);
            state.currentAnimal = animalId;
            state.selected = animalId;
            invalidateSuggestions();
            renderAll();
            setStatus("已標記「" + animalName(animalId) + "」為已參觀，剩餘 " + state.profile.remaining_time + " 分鐘");
        });
    }

    // ---------- 推薦與路線 ----------
    function visitButton(animalId) {
        return el("button", {
            type: "button",
            text: "我到了，標記為已參觀",
            onclick: function (event) { guarded(event.currentTarget, function () { return visit(animalId); }); },
        });
    }

    function renderReco() {
        const box = Dom.clear($("reco-result"));

        if (state.plan) {
            const plan = state.plan;
            if (!plan.route.length) {
                box.textContent = "目前沒有可以安排的展區（可能已經逛完，或剩餘時間不足）。";
                return;
            }
            box.append(
                el("h3", { text: "🗺️ 建議路線" }),
                el("ol", {}, plan.stops.map(function (s) {
                    return el("li", { text: s.name + "：步行約 " + s.walk_minutes + " 分鐘（" + s.distance + " 公尺），參觀 " + s.visit_time + " 分鐘" });
                })),
                el("div", { class: "meta", text: "預估共 " + plan.estimated_time + " 分鐘，約 " + plan.total_distance + " 公尺" })
            );
            return;
        }

        const rec = state.recommendation;
        if (!rec) {
            box.textContent = "按下按鈕，讓導覽員幫你決定下一站。";
            return;
        }
        if (!rec.recommendation) {
            box.textContent = rec.message || "目前沒有可以推薦的展區。";
            return;
        }
        box.append(
            el("h3", { text: "🎯 推薦前往：" + rec.name }),
            el("div", { text: "匹配分數：" + rec.score }),
            el("ul", {}, rec.reason.map(function (r) { return el("li", { text: r }); }))
        );
        if (rec.alternatives.length) {
            box.append(el("div", {
                class: "meta",
                text: "其他選擇：" + rec.alternatives.map(function (a) { return a.name + "（" + a.score + "）"; }).join("、"),
            }));
        }
        box.append(el("div", { class: "actions" }, [visitButton(rec.recommendation)]));
    }

    $("recommend-btn").addEventListener("click", function (event) {
        if (!state.map) return;
        guarded(event.currentTarget, async function () {
            const rec = await Api.recommend(state.userId);
            state.recommendation = rec;
            state.plan = null;
            if (rec.recommendation) state.selected = rec.recommendation;
            renderReco();
            renderMap();
            renderDetail();
        });
    });

    $("route-btn").addEventListener("click", function (event) {
        if (!state.map) return;
        guarded(event.currentTarget, async function () {
            state.plan = await Api.planRoute(state.userId);
            state.recommendation = null;
            renderReco();
            renderMap();
        });
    });

    // ---------- 地圖與動物簡介 ----------
    function renderMap() {
        ZooMap.render($("map-wrap"), state.map, {
            location: state.profile.current_location,
            visited: state.profile.visited,
            recommended: state.recommendation ? state.recommendation.recommendation : null,
            selected: state.selected,
            routeIds: state.plan ? state.plan.route : [],
        }, selectAnimal);
    }

    function selectAnimal(animalId) {
        state.selected = animalId;
        renderDetail();
        renderMap();
    }

    function renderDetail() {
        const box = Dom.clear($("animal-detail"));
        const animal = state.map.animals.find(function (a) { return a.id === state.selected; });
        if (!animal) {
            box.textContent = "點選地圖上的動物，可以看簡介。";
            return;
        }
        const visited = state.profile.visited.indexOf(animal.id) !== -1;
        const buttons = [el("button", {
            type: "button",
            class: "secondary",
            text: "問問牠",
            onclick: function () { askAbout(animal.id); },
        })];
        if (!visited) buttons.push(visitButton(animal.id));

        box.append(
            el("h3", { text: animal.name + (animal.english_name ? "（" + animal.english_name + "）" : "") + (visited ? " ✓" : "") }),
            el("div", { text: animal.description }),
            el("div", {}, animal.tags.map(function (t) { return el("span", { class: "tag", text: state.map.tags[t] || t }); })),
            el("div", { class: "meta", text: "建議參觀時間：" + animal.visit_time + " 分鐘" }),
            el("div", { class: "actions" }, buttons)
        );
    }

    // ---------- 相機 ----------
    let previewUrl = null;
    $("photo-input").addEventListener("change", async function (event) {
        const file = event.target.files[0];
        event.target.value = ""; // 讓同一張照片可以再選一次
        if (!file || !state.map) return;

        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = URL.createObjectURL(file);
        const preview = $("photo-preview");
        preview.src = previewUrl;
        preview.hidden = false;

        const box = $("vision-result");
        box.textContent = "辨識中…";
        try {
            const blob = await Camera.downscale(file);
            renderVision(await Api.vision(state.userId, blob, file.name));
        } catch (err) {
            box.textContent = "辨識失敗：" + err.message;
        }
    });

    function renderVision(result) {
        const box = Dom.clear($("vision-result"));
        if (!result.animal) {
            box.textContent = result.mode === "offline"
                ? "目前是離線模式，只能依檔名判斷動物（例如 tiger.jpg）。設定 GEMINI_API_KEY 後即可用 AI 辨識照片。"
                : "認不出這是哪一種動物，換個角度或靠近一點再拍一次吧。";
            return;
        }
        state.currentAnimal = result.animal;
        state.selected = result.animal;
        box.append(
            el("h3", { text: "辨識結果：" + result.name }),
            el("div", { text: "信心度 " + Math.round(result.confidence * 100) + "%" + (result.mode === "offline" ? "（離線模式，依檔名判斷）" : "") })
        );
        const actions = [el("button", { type: "button", class: "secondary", text: "問問牠", onclick: function () { askAbout(result.animal); } })];
        if (state.profile.visited.indexOf(result.animal) === -1) actions.push(visitButton(result.animal));
        box.append(el("div", { class: "actions" }, actions));
        renderChatContext();
        renderDetail();
        renderMap();
    }

    // ---------- 問答 ----------
    function addBubble(kind, text) {
        const log = $("chat-log");
        const bubble = el("div", { class: "bubble " + kind, text: text });
        log.appendChild(bubble);
        log.scrollTop = log.scrollHeight;
        return bubble;
    }

    function renderChatContext() {
        const line = $("chat-context");
        Dom.clear(line);
        if (!state.currentAnimal) {
            line.hidden = true;
            return;
        }
        line.hidden = false;
        line.append(
            "目前聊的動物：" + animalName(state.currentAnimal) + "　",
            el("button", {
                type: "button",
                class: "secondary",
                text: "清除",
                onclick: function () { state.currentAnimal = null; renderChatContext(); },
            })
        );
    }

    function askAbout(animalId) {
        state.currentAnimal = animalId;
        renderChatContext();
        $("chat-input").focus();
        $("chat-input").placeholder = "問問" + animalName(animalId) + "的故事…";
    }

    $("chat-form").addEventListener("submit", async function (event) {
        event.preventDefault();
        const input = $("chat-input");
        const text = input.value.trim();
        if (!text) return;
        input.value = "";
        addBubble("me", text);
        const pending = addBubble("bot pending", "思考中…");
        $("send-btn").disabled = true;
        try {
            const res = await Api.chat(state.userId, text, state.currentAnimal);
            pending.className = "bubble bot";
            pending.textContent = res.reply;
            if (res.animal) {
                state.currentAnimal = res.animal;
                renderChatContext();
            }
            if ($("speak-toggle").checked) Voice.speak(res.reply);
        } catch (err) {
            pending.className = "bubble bot";
            pending.textContent = "抱歉，出了點問題：" + err.message;
        } finally {
            $("send-btn").disabled = false;
            input.focus();
        }
    });

    // ---------- 語音 ----------
    let listening = null;
    const mic = $("mic-btn");
    if (!Voice.canListen()) mic.hidden = true;
    if (!Voice.canSpeak()) $("speak-toggle").parentElement.hidden = true;

    function setRecording(on) {
        mic.classList.toggle("recording", on);
        mic.setAttribute("aria-pressed", on ? "true" : "false");
    }

    mic.addEventListener("click", function () {
        if (listening) {
            listening.stop();
            return;
        }
        setRecording(true);
        setStatus("聆聽中…說完後再按一次麥克風");
        try {
            listening = Voice.listen({
                onText: function (text) {
                    $("chat-input").value = text;
                    $("send-btn").click();
                },
                onEnd: function () {
                    listening = null;
                    setRecording(false);
                },
                onError: function (message) { setStatus(message, true); },
            });
        } catch (err) {
            listening = null;
            setRecording(false);
            setStatus("無法啟動語音輸入", true);
        }
    });

    $("speak-toggle").addEventListener("change", function (event) {
        if (!event.target.checked) Voice.stopSpeaking();
    });

    // ---------- 啟動 ----------
    function renderAll() {
        renderTrip();
        renderReco();
        renderMap();
        renderDetail();
        renderChatContext();
    }

    async function init() {
        const badge = $("mode-badge");
        try {
            const results = await Promise.all([Api.getMap(), Api.getProfile(state.userId), Api.health()]);
            state.map = results[0];
            state.profile = results[1];
            const gemini = results[2].llm === "gemini";
            badge.textContent = gemini ? "AI 模式：Gemini" : "離線模式";
            badge.className = "badge " + (gemini ? "ok" : "warn");
            badge.title = gemini ? "問答與相機辨識使用 Gemini" : "未設定 GEMINI_API_KEY：問答改用知識庫原文，相機辨識改看檔名";
            renderAll();
        } catch (err) {
            badge.textContent = "伺服器未連線";
            badge.className = "badge warn";
            setStatus(err.message, true);
        }
    }

    init();
})();
