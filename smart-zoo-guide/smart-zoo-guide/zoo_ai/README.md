# zoo_ai — 臺北市立動物園物種辨識模型

從開放資料取得動物園動物列表 → 由 iNaturalist / GBIF 下載影像 → 訓練影像分類模型 → 匯出 ONNX 給後端 `/api/vision/` 使用。

## 流程

| 步驟 | 腳本 | 輸出 |
|---|---|---|
| 0 | 下載動物列表（data.taipei「臺北市立動物園_動物資料」API） | `data/raw/taipei_zoo_animals_raw.json` |
| 1 | `scripts/01_build_species_list.py`：去重、修正中文罕用字與學名、對應 iNaturalist taxon / GBIF key、亞種歸到種 | `data/species.json`、`data/species_list.csv` |
| 2 | `scripts/02_download_images.py`：每類最多 300 張 CC 授權照片（iNat 研究級 + iNat 圈養紀錄 + GBIF 補足），長邊縮到 384px | `data/images/<學名>/*.jpg`、`data/images_metadata.csv`（作者/授權） |
| 3 | `scripts/03_train.py`：ConvNeXt-Tiny 遷移學習 | `models/zoo_convnext_tiny.pt`、`models/labels.json`、`models/train_history.json` |
| 4 | `scripts/04_export_onnx.py`：匯出 ONNX 並驗證，複製到 `backend/models/` | `models/zoo_classifier.onnx`（FP32）等 |
| 5 | `scripts/05_evaluate.py`：test split 詳細評估（門檻、各類準確率、混淆） | `models/eval_report.json` |
| 6 | `scripts/06_quantize_onnx.py`：INT8 動態量化（只量化 MatMul/Gemm），與 FP32 比較 | `backend/models/zoo_classifier.onnx`（INT8，34 MB）、`models/quantization_report.json` |
| 7 | `scripts/07_web_test.py`：從 Wikimedia Commons 抓訓練集以外的圖片測試 | `data/web_test/`（不進 git）、`models/web_test_report.json` |
| 8 | `scripts/08_browser_e2e.py`：用 Edge + 假攝影機在網站上端到端測試即時辨識 | `logs/browser_e2e/`、`docs/e2e_*.png` |

## 重現

```powershell
# 需要 Python 3.12 (python.org 官方版) 與 NVIDIA GPU
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python -m pip install timm pillow requests tqdm pandas onnx onnxruntime scikit-learn

curl "https://data.taipei/api/v1/dataset/6afa114d-38a2-4e3c-9cfd-29d3bd26b65b?scope=resourceAquire&limit=1000" -o data/raw/taipei_zoo_animals_raw.json
.\.venv\Scripts\python -X utf8 scripts\01_build_species_list.py
.\.venv\Scripts\python -X utf8 scripts\02_download_images.py --per-class 300
.\.venv\Scripts\python -X utf8 scripts\03_train.py --epochs 15
.\.venv\Scripts\python -X utf8 scripts\04_export_onnx.py
.\.venv\Scripts\python -X utf8 scripts\05_evaluate.py
.\.venv\Scripts\python -X utf8 scripts\06_quantize_onnx.py
.\.venv\Scripts\python -X utf8 scripts\07_web_test.py --per-class 3

# 網站端到端測試 (需 pip install playwright；使用系統內建 Edge)
# 先在專案根目錄 (smart-zoo-guide/) 另開視窗啟動後端：
#   zoo_ai\.venv\Scripts\python -m uvicorn backend.main:app --port 8765
.\.venv\Scripts\python -X utf8 scripts\08_browser_e2e.py
```

## 模型

- 架構：**ConvNeXt-Tiny**（timm `convnext_tiny.fb_in22k_ft_in1k`，約 2800 萬參數），ImageNet-22k 預訓練後在本資料集全模型微調。
- 輸入 224×224；RandAugment、RandomResizedCrop、Random Erasing、label smoothing 0.1、AdamW + cosine、bf16 混合精度。
- 資料依檔名 hash 切成 train/val/test = 80/10/10。
- 推論：後端用 onnxruntime（CPU 即可），回傳 top-5；最高機率 < 0.45 視為「無法確定」。前端用 EMA 平滑連續畫格。

## 結果（2026-11-15 訓練）

- 資料：313 筆園區動物 → 267 個物種類別 → 下載 70,583 張影像（iNaturalist 70,120、GBIF 464）
- 影像少於 20 張而排除 6 類（巨棘竹節蟲、安南龜、泰國小紅翅竹節蟲、穗鬚原鯉、小扁竹節蟲、紅藍吸蜜鸚鵡），**最終模型 261 類**
- train 56,439 / val 7,138 / test 6,938；RTX 5070 Ti 上每 epoch 約 70 秒，共 15 epochs
- **Test top-1 88.3%、top-5 96.4%**（詳見 `models/eval_report.json`，由 `scripts/05_evaluate.py` 產生）

| 信心度門檻 | 覆蓋率 | 給答案時準確率 |
|---|---|---|
| 0.30 | 95.5% | 91.3% |
| **0.45（預設）** | **90.4%** | **93.9%** |
| 0.60 | 84.6% | 96.2% |
| 0.75 | 77.4% | 98.0% |

常見混淆皆為外型相近物種：智利紅鶴↔大紅鶴、小爪水獺↔歐亞水獺、大頭家蟻↔堅硬雙針家蟻、鼬獾↔白鼻心。

### 模型量化（部署用）

FP32 ONNX 112 MB 超過 GitHub 單檔 100 MB 上限，因此後端使用 INT8 動態量化模型（只量化 MatMul/Gemm，卷積維持 FP32）：

| 模型 | 大小 | Test top-1 | Test top-5 |
|---|---|---|---|
| FP32 | 112.2 MB | 88.37% | 96.53% |
| **INT8（後端使用）** | **34.2 MB** | **88.33%** | **96.48%** |

CPU 延遲受機器負載影響很大；在無其他負載時交錯量測，INT8 比 FP32 快約 25–30%。若連卷積一起量化（ConvInteger），CPU 上反而變慢，故不採用。

### 網路圖片測試（訓練集以外）

從 Wikimedia Commons 依學名各抓 3 張（排除 iNaturalist 轉存、地圖、標本、論文圖版等），共 **682 張 / 246 類**：

- **top-1 89.1%、top-5 95.7%**（INT8 模型），與 test split 相當，表示模型對不同來源的照片也能泛化
- 信心度 ≥ 0.45 時對 93.0% 的圖片給出答案，其中 94.8% 正確
- 高信心度錯誤多為近緣種：藍冠鴿→維多利亞冠鴿、家驢→非洲野驢、小葵花鳳頭鸚鵡→葵花鳳頭鸚鵡
- 模擬相機畫格大小：長邊 320 / 480 / 640 px 的 top-1 為 89.4% / 89.6% / 89.6%，差異很小，前端維持 320 px 以節省流量

### 網站端到端測試（瀏覽器）

用 Microsoft Edge（無頭模式）+ Chromium 假攝影機播放 6 張網路測試圖，實際操作網頁「開啟即時辨識」：

| 動物 | 結果 | 網頁顯示 |
|---|---|---|
| 非洲獅 | ✅ | ✅ 非洲獅（94.9%）· 非洲動物區 |
| 大貓熊 | ✅ | ✅ 大貓熊（92.8%）· 新光特展館（大貓熊館） |
| 無尾熊 | ✅ | ✅ 無尾熊（92.7%）· 無尾熊館 |
| 臺灣藍鵲 | ✅ | ✅ 臺灣藍鵲（89.6%）· 鳥園區 |
| 網紋長頸鹿 | ✅ | ✅ 網紋長頸鹿（94.7%）· 非洲動物區 |
| 亞洲象 | ❌ 未確定 | 🔍 辨識中…可能是：亞洲象 43%、非洲象 39%（低於門檻，未給錯誤答案） |

瀏覽器 console 無錯誤。截圖見 `docs/e2e_*.png`。

> 註：`02_download_images.py` 在本次訓練後才加入「排除糞便/足跡/骨骸等存在證據照片」的過濾。目前模型的訓練資料中仍含少量這類照片；重新下載並重訓可望再提升一些準確率。

## 限制

- 亞種無法以影像區分，已合併到種（例：臺灣黑熊與亞洲黑熊同一類、蘭嶼豬與臺灣野豬同一類）。
- 訓練影像多為野外或一般圈養照片，與木柵園區實際場景仍有差距；建議之後在園區實拍影像再微調。
- 亞洲象／非洲象、紅鶴兩種、水獺兩種等近緣種較易混淆；網站在不確定時會顯示候選而不直接下結論。
- 沒有「非動物 / 背景」類別，只靠信心度門檻排除，對準人、建築物時仍可能誤判。
- 影像授權：皆為 Creative Commons，部分為 NC（非商業）授權；作者與來源記錄於 `data/images_metadata.csv`，若對外發布須遵守各授權條款。
