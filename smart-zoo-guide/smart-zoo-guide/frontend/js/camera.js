/* 相機相關：上傳前先把照片縮小，手機拍的原圖常有好幾 MB，縮圖能讓辨識更快。 */
const Camera = (function () {
    "use strict";

    const MAX_SIDE = 1024;

    function loadImage(file) {
        return new Promise(function (resolve, reject) {
            const url = URL.createObjectURL(file);
            const img = new Image();
            img.onload = function () { URL.revokeObjectURL(url); resolve(img); };
            img.onerror = function () { URL.revokeObjectURL(url); reject(new Error("無法讀取這張圖片")); };
            img.src = url;
        });
    }

    /* 回傳縮小後的 JPEG Blob；任何一步失敗就回傳原檔，讓後端自己驗證。 */
    async function downscale(file) {
        try {
            const img = await loadImage(file);
            const ratio = Math.min(1, MAX_SIDE / Math.max(img.width, img.height));
            const canvas = document.createElement("canvas");
            canvas.width = Math.round(img.width * ratio);
            canvas.height = Math.round(img.height * ratio);
            canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
            const blob = await new Promise(function (resolve) { canvas.toBlob(resolve, "image/jpeg", 0.85); });
            return blob || file;
        } catch (err) {
            return file;
        }
    }

    return { downscale: downscale };
})();
