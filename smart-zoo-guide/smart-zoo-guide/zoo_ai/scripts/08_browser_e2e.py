"""
步驟 8：在真實瀏覽器中端到端測試網站的「即時辨識」功能。

做法：把數張網路測試圖片 (data/web_test，訓練沒看過) 串成 MJPEG 影片，
透過 Chromium 的假攝影機參數 (--use-file-for-fake-video-capture) 當成相機畫面，
用 Playwright 驅動系統內建的 Microsoft Edge 開啟網站 → 按「開啟即時辨識」→
記錄網頁上 #vision-result 的顯示內容與截圖，確認每段影片都顯示正確動物。

前置：後端需已啟動，例如
    python -m uvicorn backend.main:app --port 8765
用法：python scripts/08_browser_e2e.py [--url http://127.0.0.1:8765] [--seconds-per-animal 6]
"""
import argparse
import json
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageOps
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WEB_TEST = ROOT / "data" / "web_test"
OUT = ROOT / "logs" / "browser_e2e"
FPS = 30  # Chromium 讀取 MJPEG 假攝影機檔案時以 30fps 播放

# 測試用的動物 (類別 key)：每種挑一張網路測試圖，依序播放
ANIMALS = ["Panthera_leo", "Ailuropoda_melanoleuca", "Phascolarctos_cinereus",
           "Urocissa_caerulea", "Giraffa_reticulata", "Elephas_maximus"]


def pick_image(key, report):
    """挑一張模型在網路測試中有答對的圖 (測網站流程，而非再測一次模型)；沒有就取第一張。"""
    d = WEB_TEST / key
    files = sorted(d.glob("*.jpg"))
    wrong = {w["file"] for w in report.get("wrong", [])}
    for f in files:
        if f"{key}/{f.name}" not in wrong:
            return f
    return files[0] if files else None


def build_mjpeg(images, seconds, path):
    with open(path, "wb") as out:
        for img_path in images:
            # 裁切成 4:3 (模擬真實相機畫面；補黑邊會造成真實相機不會有的失真)
            im = ImageOps.fit(Image.open(img_path).convert("RGB"), (640, 480))
            tmp = Path(path).with_suffix(".frame.jpg")
            im.save(tmp, "JPEG", quality=85)
            frame = tmp.read_bytes()
            for _ in range(int(seconds * FPS)):
                out.write(frame)
            tmp.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    ap.add_argument("--seconds-per-animal", type=float, default=6.0)
    args = ap.parse_args()

    labels = {l["key"]: l for l in json.loads((ROOT / "models" / "labels.json").read_text(encoding="utf-8"))}
    report_path = ROOT / "models" / "web_test_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
    chosen = [(k, pick_image(k, report)) for k in ANIMALS]
    chosen = [(k, p) for k, p in chosen if p]
    OUT.mkdir(parents=True, exist_ok=True)
    seg = args.seconds_per_animal

    # Chromium 參數不支援中文路徑 → 影片放在系統暫存資料夾
    with tempfile.TemporaryDirectory() as tmp:
        video = Path(tmp) / "fake_camera.mjpeg"
        build_mjpeg([p for _, p in chosen], seg, video)
        print("假攝影機影片：", " → ".join(labels[k]["name_zh"] for k, _ in chosen))

        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge", headless=True, args=[
                "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
                f"--use-file-for-fake-video-capture={video}"])
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            ctx.grant_permissions(["camera"], origin=args.url)
            page = ctx.new_page()
            console_errors = []
            page.on("console", lambda m: m.type == "error" and console_errors.append(m.text))
            page.on("pageerror", lambda e: console_errors.append(str(e)))

            page.goto(args.url, wait_until="networkidle")
            page.screenshot(path=str(OUT / "00_home.png"), full_page=True)
            page.click("#camera-btn")
            t0 = time.time()
            timeline = []
            total = seg * len(chosen)
            shot = 0
            while time.time() - t0 < total:
                t = time.time() - t0
                timeline.append((round(t, 1), page.inner_text("#vision-result").replace("\n", " | ")))
                # 每段影片的尾端截圖
                if t >= (shot + 1) * seg - 0.8 and shot < len(chosen):
                    page.locator(".card").first.screenshot(path=str(OUT / f"{shot + 1:02d}_{chosen[shot][0]}.png"))
                    shot += 1
                time.sleep(0.5)
            btn_text = page.inner_text("#camera-btn")
            page.click("#camera-btn")  # 停止
            browser.close()

    # 判定：每段影片後半段 (畫面穩定後) 顯示的辨識結果中，是否以正確動物為主
    results = []
    for i, (k, p) in enumerate(chosen):
        lo, hi = i * seg + seg * 0.5, (i + 1) * seg
        shown = [txt for t, txt in timeline if lo <= t < hi]
        expect = labels[k]["name_zh"]
        hits = sum(f"✅ {expect}" in s for s in shown)
        results.append({"animal": expect, "image": str(p.relative_to(ROOT)), "samples": len(shown),
                        "correct_samples": hits, "pass": hits >= max(1, len(shown) // 2),
                        "last_shown": shown[-1] if shown else ""})
    summary = {"url": args.url, "camera_button_while_running": btn_text, "console_errors": console_errors,
               "results": results, "timeline": timeline}
    (OUT / "result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n相機啟動後按鈕文字：{btn_text}")
    for r in results:
        print(f"  {'PASS' if r['pass'] else 'FAIL'}  {r['animal']}: 後半段 {r['correct_samples']}/{r['samples']} 次顯示正確"
              f"   最後畫面：{r['last_shown'][:70]}")
    print(f"  瀏覽器 console 錯誤：{console_errors or '無'}")
    print(f"截圖與紀錄：{OUT}")


if __name__ == "__main__":
    main()
