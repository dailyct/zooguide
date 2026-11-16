"""
步驟 7：從網路 (Wikimedia Commons) 抓「訓練集以外」的圖片，測試模型的泛化能力。

訓練資料來自 iNaturalist / GBIF；這裡改用 Wikimedia Commons，並排除標題含 iNaturalist 的檔案
(部分 iNat 照片會被轉存到 Commons)，盡量避免測試圖與訓練圖重疊。
也排除地圖、頭骨、標本、手繪圖等非活體照片。

輸出：data/web_test/<類別>/*.jpg、data/web_test/sources.csv、models/web_test_report.json
用法：python scripts/07_web_test.py [--per-class 3] [--skip-download]
"""
import argparse
import csv
import io
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))  # 讓 backend 可被 import
from backend.services.vision import CONFIDENCE_THRESHOLD, ZooVisionClassifier  # noqa: E402

OUT = ROOT / "data" / "web_test"
LABELS = ROOT / "models" / "labels.json"
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "zoo-guide-student-project/1.0 (educational; image classifier evaluation)"}
BAD = re.compile(r"inaturalist|map|range|distribution|skull|skelet|bone|drawing|illustrat|plate|"
                 r"stamp|coin|logo|specimen|museum|taxiderm|mount|diagram|\begg|track|scat|dung|"
                 r"fossil|painting|sketch|statue|sculpture|toy|cartoon|art\b|svg|\bx-ray|"
                 r"figure|\bfig\.|zookeys|10\.\d{4,}", re.I)  # 期刊論文圖版 (多為標本照)


def search(name, n):
    """回傳 [(title, thumb_url, page_url, license)]"""
    r = requests.get(API, headers=UA, timeout=30, params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
        "gsrsearch": f'"{name}" filetype:bitmap', "gsrlimit": 30,
        "prop": "imageinfo", "iiprop": "url|extmetadata|mime", "iiurlwidth": 640})
    r.raise_for_status()
    pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        title = p["title"]
        if ii.get("mime") != "image/jpeg" or BAD.search(title):
            continue
        meta = ii.get("extmetadata", {})
        desc = " ".join(str(meta.get(k, {}).get("value", "")) for k in ("ImageDescription", "Credit"))
        if re.search(r"inaturalist", desc, re.I):
            continue
        lic = meta.get("LicenseShortName", {}).get("value", "")
        out.append((title, ii.get("thumburl") or ii["url"], ii.get("descriptionurl", ""), lic))
        if len(out) >= n:
            break
    return out


def download(labels, per_class):
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, lab in enumerate(labels, 1):
        d = OUT / lab["key"]
        if d.exists() and len(list(d.glob("*.jpg"))) >= per_class:
            continue
        d.mkdir(exist_ok=True)
        try:
            hits = search(lab["scientific_name"], per_class)
        except requests.RequestException as e:
            print(f"  ! {lab['key']}: {e}")
            continue
        for j, (title, url, page, lic) in enumerate(hits):
            try:
                r = requests.get(url, headers=UA, timeout=30)
                r.raise_for_status()
                Image.open(io.BytesIO(r.content)).convert("RGB").save(d / f"commons_{j}.jpg", quality=92)
                rows.append([lab["key"], f"{lab['key']}/commons_{j}.jpg", title, page, lic])
            except Exception as e:
                print(f"  ! {title}: {e}")
            time.sleep(0.2)
        print(f"[{i}/{len(labels)}] {lab['name_zh']}: {len(hits)} 張", flush=True)
        time.sleep(0.5)
    with (OUT / "sources.csv").open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)


def evaluate(labels):
    clf = ZooVisionClassifier()
    by_key = {l["key"]: l for l in labels}
    n = c1 = c5 = recog = recog_ok = 0
    per = defaultdict(lambda: [0, 0])
    wrong = []
    for d in sorted(p for p in OUT.iterdir() if p.is_dir()):
        for f in sorted(d.glob("*.jpg")):
            r = clf.predict(f.read_bytes())
            keys = [t["key"] for t in r["top_k"]]
            ok = keys[0] == d.name
            n += 1
            c1 += ok
            c5 += d.name in keys
            per[d.name][0] += ok
            per[d.name][1] += 1
            if r["recognized"]:
                recog += 1
                recog_ok += ok
            if not ok:
                wrong.append({"file": f"{d.name}/{f.name}", "true": by_key[d.name]["name_zh"],
                              "pred": r["name"], "conf": r["confidence"]})
    rep = {"n": n, "top1": c1 / n, "top5": c5 / n, "classes": len(per),
           "coverage_at_threshold": recog / n, "accuracy_when_recognized": recog_ok / max(1, recog),
           "threshold": CONFIDENCE_THRESHOLD,
           "wrong": sorted(wrong, key=lambda w: -w["conf"])}
    (ROOT / "models" / "web_test_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                                                          encoding="utf-8")
    print(f"\n網路圖片測試：{n} 張 / {len(per)} 類")
    print(f"  top-1 {rep['top1']:.1%}   top-5 {rep['top5']:.1%}")
    print(f"  信心度 ≥ {rep['threshold']}：給答案 {rep['coverage_at_threshold']:.1%}，"
          f"其中正確 {rep['accuracy_when_recognized']:.1%}")
    print("\n高信心度的錯誤 (前 15)：")
    for w in rep["wrong"][:15]:
        print(f"  {w['conf']:.2f}  {w['true']} → {w['pred']}   ({w['file']})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=3)
    ap.add_argument("--skip-download", action="store_true")
    args = ap.parse_args()
    labels = json.loads(LABELS.read_text(encoding="utf-8"))
    if not args.skip_download:
        download(labels, args.per_class)
    evaluate(labels)


if __name__ == "__main__":
    main()
