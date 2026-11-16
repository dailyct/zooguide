/*
 * 語音輸入與朗讀。
 * - 輸入：優先用瀏覽器內建的語音辨識（即時、不用上傳）；不支援時改為錄音後交給後端 /api/voice/stt。
 * - 朗讀：後端先把文字整理成適合朗讀的純文字，再由瀏覽器的 speechSynthesis 發聲。
 */
const Voice = (function () {
    "use strict";

    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const canRecord = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);

    function canListen() { return !!Recognition || canRecord; }

    /*
     * 開始聽。callbacks: { onText(text), onEnd(), onError(message) }
     * 回傳 { stop() }。
     */
    function listen(callbacks) {
        if (Recognition) return listenWithBrowser(callbacks);
        return listenWithRecorder(callbacks);
    }

    function listenWithBrowser(cb) {
        const rec = new Recognition();
        rec.lang = "zh-TW";
        rec.interimResults = false;
        rec.maxAlternatives = 1;
        rec.onresult = function (event) { cb.onText(event.results[0][0].transcript); };
        rec.onerror = function (event) {
            cb.onError(event.error === "not-allowed" ? "沒有麥克風權限，請在瀏覽器設定中允許" : "語音辨識失敗（" + event.error + "）");
        };
        rec.onend = function () { cb.onEnd(); };
        rec.start();
        return { stop: function () { rec.stop(); } };
    }

    function listenWithRecorder(cb) {
        let recorder = null;
        let stopped = false;
        navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
            const chunks = [];
            recorder = new MediaRecorder(stream);
            recorder.ondataavailable = function (e) { if (e.data.size) chunks.push(e.data); };
            recorder.onstop = function () {
                stream.getTracks().forEach(function (t) { t.stop(); });
                const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
                Api.stt(blob)
                    .then(function (res) { if (res.text) cb.onText(res.text); else cb.onError("沒有聽到聲音"); })
                    .catch(function (err) { cb.onError(err.message); })
                    .then(function () { cb.onEnd(); });
            };
            if (stopped) { recorder.stop(); return; }
            recorder.start();
            setTimeout(function () { if (recorder.state === "recording") recorder.stop(); }, 15000);
        }).catch(function () {
            cb.onError("沒有麥克風權限，請在瀏覽器設定中允許");
            cb.onEnd();
        });
        return {
            stop: function () {
                stopped = true;
                if (recorder && recorder.state === "recording") recorder.stop();
            },
        };
    }

    function canSpeak() { return "speechSynthesis" in window; }

    async function speak(text) {
        if (!canSpeak()) return;
        let spoken = text;
        try {
            spoken = (await Api.tts(text)).text || text;
        } catch (err) {
            /* 後端整理失敗就直接念原文 */
        }
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(spoken);
        utterance.lang = "zh-TW";
        window.speechSynthesis.speak(utterance);
    }

    function stopSpeaking() { if (canSpeak()) window.speechSynthesis.cancel(); }

    return { canListen: canListen, listen: listen, canSpeak: canSpeak, speak: speak, stopSpeaking: stopSpeaking };
})();
