"""
步驟 1：整理臺北市立動物園動物列表，並對照 iNaturalist / GBIF 分類資料庫校正學名。

輸入：data/raw/taipei_zoo_animals_raw.json  (來源：data.taipei「臺北市立動物園_動物資料」)
輸出：data/species.json      每個「辨識類別」一筆 (含 iNat taxon id、GBIF key、中文名、館區)
      data/species_list.csv  方便人工檢視

處理重點：
  * 原始資料有重複 (同一物種多筆)、罕用字變成 '?'、學名拼錯/舊名、缺學名。
  * 亞種一律歸到「種」層級當作一個辨識類別 (例如 臺灣黑熊 + 亞洲黑熊 → Ursus thibetanus)，
    因為影像上無法可靠區分亞種，且 iNaturalist 亞種層級照片很少。
"""
import csv
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "taipei_zoo_animals_raw.json"
OUT_JSON = ROOT / "data" / "species.json"
OUT_CSV = ROOT / "data" / "species_list.csv"

UA = {"User-Agent": "zoo-guide-student-project/1.0 (educational)"}
INAT = "https://api.inaturalist.org/v1"
GBIF = "https://api.gbif.org/v1"

# 原始資料中罕用字變成 '?' 的中文名修正
ZH_FIX = {
    "食蟹?": "食蟹獴",
    "美洲紅?": "美洲紅鹮",
    "紅?": "美洲紅鹮",
    "狐?": "狐獴",
    "褐負?": "褐負蝽",
    "埃及聖?": "埃及聖鹮",
    "鴯?": "鴯鶓",
}

# 原始資料中拼錯 / 過時 / 缺漏的學名修正 (以 iNaturalist 現行名稱或可搜尋到的名稱為準)
LATIN_FIX = {
    "Spheniscus demersu": "Spheniscus demersus",
    "Equus pony_mule": "Equus caballus",
    "Sus scrofa domestic": "Sus scrofa",
    "Chaicides ocellatus": "Chalcides ocellatus",
    "Chacophalps indica": "Chalcophaps indica",
    "Eurycanths Calcarata": "Eurycantha calcarata",
    "Phylium giganteum": "Phyllium giganteum",
    "Uroxissa caerulea": "Urocissa caerulea",
    "Steptopelia orientalis orii": "Streptopelia orientalis",
    "Pachlioptera aristolochiae interpositus": "Pachliopta aristolochiae",
    "Macroclemys temminckii": "Macrochelys temminckii",
    "Butorides striatus": "Butorides striata",
    "Alligator sinensus": "Alligator sinensis",
    "Testudo horsfieldi": "Testudo horsfieldii",
    "Equus burchelli antiquorum": "Equus quagga",
    "Cistoclemmys flavomarginata": "Cuora flavomarginata",
    "Rhacophorus prasinatus": "Zhangixalus prasinatus",
    "Potamotrygon sp": "Potamotrygon",
    "Entoria Sp.": "Entoria",
    "Pheidole Sp.": "Pheidole",
    "Idea Leuconoe": "Idea leuconoe",
    "Danaus Chrysippus": "Danaus chrysippus",
    "Danaus Genutia": "Danaus genutia",
    "Chitoria Chrysolora": "Chitoria chrysolora",
    "Camponotus Irritans": "Camponotus irritans",
    "Dorcus Schenkingi": "Dorcus schenklingi",
    "Phaenopharos Khaoyaiensis": "Phaenopharos khaoyaiensis",
    "Trachychorax Sexpunctatus": "Trachythorax sexpunctatus",
    "Papilio Paris Nakaharai": "Papilio paris",
    "Syrmaticus Mikado": "Syrmaticus mikado",
    "Megalaima nuchalis": "Psilopogon nuchalis",
    "Chelonoidis denticulata": "Chelonoidis denticulatus",
    "Choeropsis liberiensis": "Choeropsis liberiensis",
    "Geochelone sulcata": "Centrochelys sulcata",
    "Geochelone gigantea": "Aldabrachelys gigantea",
    "Python reticulatus": "Malayopython reticulatus",
    "Ophisaurus apodus": "Pseudopus apodus",
    "Bufo melanostictus": "Duttaphrynus melanostictus",
    "Rana taipehensis": "Hylarana taipehensis",
    "Rana swinhoana": "Odorrana swinhoana",
    "Rana adenopleura": "Nidirana adenopleura",
    "Japalura swinhonis": "Diploderma swinhonis",
    "Elaphe taeniura friesei": "Elaphe taeniura",
    "Pandinus imperator": "Pandinus imperator",
    "Brachypelma smithi": "Brachypelma smithi",
    "Leptotilos crumeniferus": "Leptoptilos crumenifer",
    "Ketupa flavipes": "Ketupa flavipes",
    "Ara chloroptera": "Ara chloropterus",
    "Ocyphaps lophotes": "Ocyphaps lophotes",
    "Anthropoides virgo": "Grus virgo",
    "Alopochen aegyptiacus": "Alopochen aegyptiaca",
    "Spilornis cheela": "Spilornis cheela",
    "Muntiacus reevesi micrurus": "Muntiacus reevesi",
    "Gerrhosaurus major": "Broadleysaurus major",
    "Papilio bianor takasago": "Papilio bianor",
    "Acraea issoria formosana": "Telchinia issoria",
}

# 缺學名的條目 (以中文名對應)
MISSING_LATIN = {
    "黃頸亞馬遜鸚鵡": "Amazona auropalliata",
    # 高山巨針蟻：原始資料無學名、查無可靠對應 → 不納入 (列在 unresolved)
}

SPECIES_OR_BELOW = {"species", "hybrid", "subspecies", "variety", "form", "infrahybrid"}
BELOW_SPECIES = {"subspecies", "variety", "form", "infrahybrid"}


CACHE_FILE = ROOT / "data" / "raw" / "api_cache.json"
_cache = json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}


def get(url, params=None, tries=4):
    ck = url + "?" + json.dumps(params, sort_keys=True)
    if ck in _cache:
        return _cache[ck]
    data = _get(url, params, tries)
    if data is not None:
        _cache[ck] = data
        CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False), encoding="utf-8")
    return data


def _get(url, params=None, tries=4):
    for i in range(tries):
        try:
            time.sleep(1.0)  # iNat 建議 ≤ 60 req/min
            r = requests.get(url, params=params, headers=UA, timeout=30)
            if r.status_code == 429:
                time.sleep(5 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            print(f"   ! {e}; retry", file=sys.stderr)
            time.sleep(2 * (i + 1))
    return None


def inat_search(name):
    """在 iNaturalist 搜尋學名，回傳最佳 taxon (dict) 或 None。"""
    low = name.lower().strip()
    words = low.split()
    binomial = len(words) >= 2
    data = get(f"{INAT}/taxa", {"q": name, "is_active": "true", "per_page": 10, "locale": "zh-TW"})
    res = (data or {}).get("results") or []
    if binomial and not any(t["name"].lower() == low or t.get("matched_term", "").lower() == low
                            for t in res):
        # 常見字 (如 Lynx) 會被其他類群 (Lynx spiders) 擠出前 10 名 → 用 autocomplete 再查一次
        data2 = get(f"{INAT}/taxa/autocomplete", {"q": name, "is_active": "true", "per_page": 10,
                                                  "locale": "zh-TW"})
        res = ((data2 or {}).get("results") or []) + res
    if binomial:  # 二名法查詢不接受屬以上層級的結果
        res = [t for t in res if t["rank"] in SPECIES_OR_BELOW or t["rank"] == "complex"]
    if not res:
        return None
    for t in res:  # 完全符合現行學名
        if t["name"].lower() == low:
            return t
    for t in res:  # 符合同物異名 (matched_term)
        if t.get("matched_term", "").lower() == low:
            return t
    if not binomial:  # 單字 (屬/科) 查詢：接受同名的分類群
        for t in res:
            if t["name"].lower() == words[0]:
                return t
        return None
    # 二名法：種小名 (或亞種名) 必須出現在結果的學名或同物異名中 (可處理屬名變更)，
    # 只有屬名相同是不夠的 (例：Lynx lynx ≠ Lynx rufus)
    for t in res:
        cand = (t["name"].lower().split()[1:] + t.get("matched_term", "").lower().split()[1:])
        if any(w in cand for w in words[1:]):
            return t
    return None


def inat_taxon(tid):
    data = get(f"{INAT}/taxa/{tid}", {"locale": "zh-TW"})
    return data["results"][0] if data and data.get("results") else None


def gbif_match(name):
    data = get(f"{GBIF}/species/match", {"name": name, "verbose": "false"})
    if data and data.get("matchType") != "NONE":
        return data
    return None


def main():
    raw = json.loads(RAW.read_text(encoding="utf-8"))["result"]["results"]
    print(f"原始資料 {len(raw)} 筆")

    classes = {}  # inat taxon id -> class record
    unresolved = []
    cache = {}

    for a in raw:
        zh = ZH_FIX.get(a["a_name_ch"].strip(), a["a_name_ch"].strip())
        latin = (a.get("a_name_latin") or "").strip() or MISSING_LATIN.get(zh, "")
        if not latin:
            unresolved.append((zh, "(無學名)"))
            continue
        query = LATIN_FIX.get(latin, latin)

        if query not in cache:
            t = inat_search(query)
            if t is None:
                # 退而求其次：GBIF 模糊比對拿到正確學名後再查 iNat
                g = gbif_match(query)
                if g and g.get("canonicalName") and g["canonicalName"].lower() != query.lower():
                    t = inat_search(g["canonicalName"])
            if t is not None and t["rank"] in BELOW_SPECIES:
                # 亞種 → 上溯到種
                full = inat_taxon(t["id"])
                parent = full and next((x for x in reversed(full.get("ancestors", []))
                                        if x["rank"] == "species"), None)
                if parent:
                    t = parent
            cache[query] = t
        t = cache[query]
        if t is None:
            unresolved.append((zh, latin))
            print(f"  ✗ 無法對應: {zh} / {latin}")
            continue

        tid = t["id"]
        rec = classes.get(tid)
        if rec is None:
            rec = classes[tid] = {
                "inat_taxon_id": tid,
                "scientific_name": t["name"],
                "rank": t["rank"],
                "inat_common_name": t.get("preferred_common_name", ""),
                "iconic_taxon": t.get("iconic_taxon_name", ""),
                "inat_obs_count": t.get("observations_count", 0),
                "zoo_names_zh": [],
                "zoo_names_en": [],
                "zoo_latin_original": [],
                "locations": [],
                "zoo_record_ids": [],
                "lat": a.get("a_latitude", ""),
                "lng": a.get("a_longitude", ""),
                "class_zh": a.get("a_class", ""),
                "conservation": a.get("a_conservation", ""),
            }
        for key, val in (("zoo_names_zh", zh), ("zoo_names_en", a.get("a_name_en", "").strip()),
                         ("zoo_latin_original", latin)):
            if val and val not in rec[key]:
                rec[key].append(val)
        for loc in (a.get("a_location") or "").split(";"):
            loc = loc.strip()
            if loc and loc not in rec["locations"]:
                rec["locations"].append(loc)
        rec["zoo_record_ids"].append(a["_id"])
        print(f"  ✓ {zh:<12} {latin:<40} → {t['name']} ({t['rank']}, id={tid})")

    # GBIF taxon key (下載備援影像用)
    for rec in classes.values():
        g = gbif_match(rec["scientific_name"])
        rec["gbif_key"] = g.get("usageKey") if g else None
        # 類別 key：學名轉為資料夾安全字串
        rec["key"] = rec["scientific_name"].replace(" ", "_").replace("×", "x")
        rec["display_name_zh"] = "／".join(rec["zoo_names_zh"])

    out = sorted(classes.values(), key=lambda r: r["key"])
    OUT_JSON.write_text(json.dumps({"classes": out, "unresolved": unresolved},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
    with OUT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["key", "display_name_zh", "scientific_name", "rank", "inat_taxon_id",
                    "gbif_key", "inat_obs_count", "locations", "zoo_latin_original"])
        for r in out:
            w.writerow([r["key"], r["display_name_zh"], r["scientific_name"], r["rank"],
                        r["inat_taxon_id"], r["gbif_key"], r["inat_obs_count"],
                        ";".join(r["locations"]), ";".join(r["zoo_latin_original"])])
    print(f"\n完成：{len(out)} 個辨識類別，{len(unresolved)} 筆無法對應 → {OUT_JSON}")
    for u in unresolved:
        print("   未對應:", u)


if __name__ == "__main__":
    main()
