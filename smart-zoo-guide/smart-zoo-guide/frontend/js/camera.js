// 即時影像物種辨識
// 開啟相機 → 定時擷取畫格 → POST /api/vision/ → 以指數移動平均 (EMA) 平滑多個畫格的結果
// 注意：瀏覽器只允許在 HTTPS 或 localhost 使用相機。

const ZooCamera = (() => {
    const FRAME_INTERVAL_MS = 500;   // 擷取間隔
    const FRAME_SIZE = 320;          // 上傳畫格長邊像素 (模型輸入 224，320 足夠且省頻寬)
    const EMA_ALPHA = 0.4;           // 新畫格權重；越小越穩定、越大反應越快
    const SHOW_THRESHOLD = 0.45;     // 平滑後信心度低於此值顯示「辨識中」

    let stream = null, timer = null, busy = false;
    let ema = {};                    // key -> 平滑後機率
    let info = {};                   // key -> 物種資訊 (中文名、館區...)
    const canvas = document.createElement("canvas");

    async function start(videoEl, onResult) {
        if (stream) return;
        stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 720 } },
            audio: false,
        });
        videoEl.srcObject = stream;
        await videoEl.play();
        ema = {};
        timer = setInterval(() => tick(videoEl, onResult), FRAME_INTERVAL_MS);
    }

    function stop(videoEl) {
        clearInterval(timer);
        timer = null;
        if (stream) stream.getTracks().forEach(t => t.stop());
        stream = null;
        if (videoEl) videoEl.srcObject = null;
    }

    async function tick(videoEl, onResult) {
        if (busy || !videoEl.videoWidth) return;   // 上一張還沒回來就跳過，避免請求堆積
        busy = true;
        try {
            const blob = await grabFrame(videoEl);
            const fd = new FormData();
            fd.append("image", blob, "frame.jpg");
            const res = await fetch("/api/vision/", { method: "POST", body: fd });
            if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
            onResult(smooth(await res.json()));
        } catch (e) {
            onResult({ error: e.message });
        } finally {
            busy = false;
        }
    }

    function grabFrame(videoEl) {
        const s = FRAME_SIZE / Math.max(videoEl.videoWidth, videoEl.videoHeight);
        canvas.width = Math.round(videoEl.videoWidth * s);
        canvas.height = Math.round(videoEl.videoHeight * s);
        canvas.getContext("2d").drawImage(videoEl, 0, 0, canvas.width, canvas.height);
        return new Promise(r => canvas.toBlob(r, "image/jpeg", 0.85));
    }

    function smooth(data) {
        const cur = {};
        data.top_k.forEach(t => { cur[t.key] = t.confidence; info[t.key] = t; });
        const keys = new Set([...Object.keys(ema), ...Object.keys(cur)]);
        keys.forEach(k => {
            ema[k] = (1 - EMA_ALPHA) * (ema[k] || 0) + EMA_ALPHA * (cur[k] || 0);
            if (ema[k] < 0.01) delete ema[k];
        });
        const ranked = Object.entries(ema).sort((a, b) => b[1] - a[1]).slice(0, 3)
            .map(([k, p]) => ({ ...info[k], confidence: p }));
        return {
            recognized: ranked.length > 0 && ranked[0].confidence >= SHOW_THRESHOLD,
            best: ranked[0],
            candidates: ranked,
            raw: data,
        };
    }

    return { start, stop, isRunning: () => !!stream };
})();
