/* 與後端溝通的封裝，以及建立 DOM 的小工具。所有函式都掛在全域的 Api / Dom 上。 */
const Api = (function () {
    "use strict";

    async function request(path, options) {
        let res;
        try {
            res = await fetch(path, options);
        } catch (err) {
            throw new Error("無法連線到伺服器，請確認網路狀態");
        }
        let data = null;
        try {
            data = await res.json();
        } catch (err) {
            /* 回應不是 JSON（例如 502 頁面），下面會用狀態碼組錯誤訊息 */
        }
        if (!res.ok) {
            const detail = data && data.detail;
            if (typeof detail === "string") throw new Error(detail);
            if (res.status === 422) throw new Error("輸入的內容格式不正確");
            throw new Error("伺服器發生問題（" + res.status + "），請稍後再試");
        }
        return data;
    }

    function json(method, path, body) {
        return request(path, {
            method: method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
    }

    function upload(path, fields, fileField, blob, filename) {
        const form = new FormData();
        Object.keys(fields).forEach(function (key) { form.append(key, fields[key]); });
        form.append(fileField, blob, filename);
        return request(path, { method: "POST", body: form });
    }

    const user = function (id) { return "/api/profile/" + encodeURIComponent(id); };

    return {
        health: function () { return request("/api/health"); },
        getMap: function () { return request("/api/route/map"); },
        getProfile: function (id) { return request(user(id)); },
        saveProfile: function (id, profile) { return json("PUT", user(id), profile); },
        visit: function (id, animalId) { return json("POST", user(id) + "/visit", { animal_id: animalId }); },
        recommend: function (id) { return json("POST", "/api/recommend", { user_id: id }); },
        planRoute: function (id) { return json("POST", "/api/route", { user_id: id }); },
        chat: function (id, message, currentAnimal) {
            return json("POST", "/api/chat", { user_id: id, message: message, current_animal: currentAnimal || null });
        },
        vision: function (id, blob, filename) {
            return upload("/api/vision", { user_id: id }, "file", blob, filename);
        },
        stt: function (blob) { return upload("/api/voice/stt", {}, "file", blob, "speech.webm"); },
        tts: function (text) { return json("POST", "/api/voice/tts", { text: text }); },
    };
})();

const Dom = (function () {
    "use strict";

    /* el("div", {class: "x", text: "hi", onclick: fn}, [child, "text"])；一律用 textContent，不會解析 HTML。 */
    function el(tag, attrs, children) {
        const node = document.createElement(tag);
        Object.keys(attrs || {}).forEach(function (key) {
            const value = attrs[key];
            if (key === "text") node.textContent = value;
            else if (key.indexOf("on") === 0) node.addEventListener(key.slice(2), value);
            else if (value !== null && value !== undefined && value !== false) node.setAttribute(key, value === true ? "" : value);
        });
        (children || []).forEach(function (child) { node.append(child); });
        return node;
    }

    function clear(node) {
        while (node.firstChild) node.removeChild(node.firstChild);
        return node;
    }

    return { el: el, clear: clear };
})();
