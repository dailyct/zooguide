"""
步驟 2：依 data/species.json 從 iNaturalist (主要) 與 GBIF (備援) 下載訓練影像。

影像來源策略 (每類別上限 --per-class 張，預設 300)：
  1. iNaturalist「研究級」觀察紀錄 (野外，經社群鑑定一致)            ~ 70%
  2. iNaturalist「圈養/栽培 captive」觀察紀錄 (動物園、水族館場景)    補足剩餘
     → 動物園實際拍攝場景多為圈養個體，加入 captive 影像可縮小 domain gap
  3. 若仍不足，從 GBIF 抓 HUMAN_OBSERVATION 影像 (排除 iNat 資料集避免重複)

只下載 Creative Commons 授權照片，並把作者/授權記錄在 data/images_metadata.csv。
影像統一縮到長邊 384px 存 JPEG，節省磁碟與訓練 I/O。

用法：python scripts/02_download_images.py [--per-class 300] [--workers 16] [--only KEY ...]
"""
import argparse
import csv
import io
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SPECIES = ROOT / "data" / "species.json"
IMG_DIR = ROOT / "data" / "images"
META = ROOT / "data" / "images_metadata.csv"

UA = {"User-Agent": "zoo-guide-student-project/1.0 (educational)"}
INAT = "https://api.inaturalist.org/v1"
GBIF = "https://api.gbif.org/v1"
INAT_GBIF_DATASET = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"  # iNat research-grade on GBIF
CC = "cc0,cc-by,cc-by-nc,cc-by-sa,cc-by-nc-sa,cc-by-nd,cc-by-nc-nd"
MAX_SIDE = 384

session = requests.Session()
session.headers.update(UA)
_api_lock = threading.Lock()
_last_api = [0.0]


def api_get(url, params, min_interval=1.0, tries=5):
    """序列化 + 限速的 API 呼叫 (iNat 建議 ~1 req/s)。"""
    for i in range(tries):
        with _api_lock:
            wait = _last_api[0] + min_interval - time.time()
            if wait > 0:
                time.sleep(wait)
            _last_api[0] = time.time()
        try:
            r = session.get(url, params=params, timeout=60)
            if r.status_code in (429, 503):
                time.sleep(10 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            print(f"   ! api {e}", file=sys.stderr)
            time.sleep(3 * (i + 1))
    return None


def inat_photos(taxon_id, want, captive, seen):
    """回傳 [(photo_id, url, license, attribution, obs_url)]"""
    out = []
    id_above = None
    params = {
        "taxon_id": taxon_id, "photos": "true", "photo_license": CC,
        # 排除「存在證據」標註為 糞便/足跡/骨骸/蛻皮/卵/毛髮/巢穴 的觀察 (只要動物本身的照片)
        "without_term_value_id": "25,26,27,28,30,31,35",
        "per_page": 200, "order_by": "id", "order": "desc",
    }
    if captive:
        params.update({"captive": "true", "identifications": "most_agree"})
    else:
        params.update({"quality_grade": "research", "captive": "false"})
    while len(out) < want:
        if id_above:
            params["id_below"] = id_above
        data = api_get(f"{INAT}/observations", params)
        if not data or not data.get("results"):
            break
        for obs in data["results"]:
            for p in obs.get("photos", [])[:1]:  # 每筆觀察只取第一張，避免同個體過多
                lic = p.get("license_code")
                if not lic or p["id"] in seen:
                    continue
                url = p["url"].replace("/square.", "/medium.")
                out.append((f"inat{p['id']}", url, lic, p.get("attribution", ""),
                            f"https://www.inaturalist.org/observations/{obs['id']}"))
                seen.add(p["id"])
        id_above = data["results"][-1]["id"]
        if len(data["results"]) < 200:
            break
    return out[:want]


def gbif_photos(gbif_key, want):
    out = []
    offset = 0
    while len(out) < want and offset < 2000:
        data = api_get(f"{GBIF}/occurrence/search", {
            "taxonKey": gbif_key, "mediaType": "StillImage", "basisOfRecord": "HUMAN_OBSERVATION",
            "limit": 300, "offset": offset}, min_interval=0.3)
        if not data or not data.get("results"):
            break
        for occ in data["results"]:
            if occ.get("datasetKey") == INAT_GBIF_DATASET:
                continue
            for m in occ.get("media", [])[:1]:
                lic = (m.get("license") or occ.get("license") or "")
                if m.get("type") != "StillImage" or not m.get("identifier"):
                    continue
                if "creativecommons" not in lic and "CC" not in lic.upper():
                    continue
                out.append((f"gbif{occ['key']}", m["identifier"], lic,
                            m.get("rightsHolder") or m.get("creator") or "",
                            f"https://www.gbif.org/occurrence/{occ['key']}"))
        if data.get("endOfRecords"):
            break
        offset += 300
    return out[:want]


def download_one(url, dest):
    if dest.exists():
        return True
    for i in range(3):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                return False
            r.raise_for_status()
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            if min(im.size) < 64:
                return False
            im.thumbnail((MAX_SIDE, MAX_SIDE), Image.BICUBIC)
            tmp = dest.with_suffix(".part")
            im.save(tmp, "JPEG", quality=90)
            tmp.replace(dest)
            return True
        except Exception:
            time.sleep(1 + i)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=300)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()

    classes = json.loads(SPECIES.read_text(encoding="utf-8"))["classes"]
    if args.only:
        classes = [c for c in classes if c["key"] in args.only]
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    new_meta = not META.exists()
    mf = META.open("a", newline="", encoding="utf-8")
    mw = csv.writer(mf)
    if new_meta:
        mw.writerow(["class_key", "file", "source", "license", "attribution", "source_url", "image_url"])

    pool = ThreadPoolExecutor(args.workers)
    summary = []
    for ci, c in enumerate(classes, 1):
        key = c["key"]
        cdir = IMG_DIR / key
        cdir.mkdir(exist_ok=True)
        have = len(list(cdir.glob("*.jpg")))
        if have >= args.per_class * 0.95:
            summary.append((key, have))
            print(f"[{ci}/{len(classes)}] {key}: 已有 {have} 張，略過")
            continue

        want = args.per_class
        seen = set()
        cand = inat_photos(c["inat_taxon_id"], int(want * 0.7), captive=False, seen=seen)
        cand += inat_photos(c["inat_taxon_id"], want - len(cand), captive=True, seen=seen)
        if len(cand) < want:  # captive 不足 → 再補研究級 (seen 會跳過已取過的)
            cand += inat_photos(c["inat_taxon_id"], want - len(cand), captive=False, seen=seen)
        if len(cand) < want and c.get("gbif_key"):
            cand += gbif_photos(c["gbif_key"], want - len(cand))

        futs = {}
        for pid, url, lic, attr, src in cand:
            dest = cdir / f"{pid}.jpg"
            futs[pool.submit(download_one, url, dest)] = (pid, url, lic, attr, src, dest)
        ok = 0
        for f in as_completed(futs):
            pid, url, lic, attr, src, dest = futs[f]
            if f.result():
                ok += 1
                mw.writerow([key, f"{key}/{dest.name}", "gbif" if pid.startswith("gbif") else "inaturalist",
                             lic, attr, src, url])
        mf.flush()
        total = len(list(cdir.glob("*.jpg")))
        summary.append((key, total))
        print(f"[{ci}/{len(classes)}] {key} ({c['display_name_zh']}): 候選 {len(cand)}，新下載 {ok}，共 {total} 張",
              flush=True)

    pool.shutdown()
    mf.close()
    low = [s for s in summary if s[1] < 50]
    print(f"\n完成 {len(summary)} 類；影像少於 50 張的類別 {len(low)} 個：")
    for k, n in low:
        print(f"   {k}: {n}")


if __name__ == "__main__":
    main()
