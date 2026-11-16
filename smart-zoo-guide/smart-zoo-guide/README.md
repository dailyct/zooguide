# 🦁 智慧動物園導覽 Smart Zoo Guide

手機網頁上的動物園 AI 導遊：拍照認動物、用說的或打字問問題、依興趣與剩餘時間推薦下一站，並在地圖上畫出整條參觀路線。

| 功能 | 做法 |
|---|---|
| 相機辨識 | 上傳照片 → Gemini 多模態辨識（離線模式：依檔名判斷） |
| 導覽問答 | RAG：從 `backend/data/knowledge/` 檢索 → Gemini 生成（離線模式：直接回覆檢索到的段落） |
| 語音 | 瀏覽器內建語音辨識／朗讀；不支援時改為錄音後由後端轉文字 |
| 推薦與路線 | 規則式 Agent：興趣、距離、剩餘時間、新鮮度加權評分 |
| 使用者資料 | SQLite：興趣、已參觀、剩餘時間、對話紀錄 |

## 快速開始

```bash
cd smart-zoo-guide/smart-zoo-guide          # 專案根目錄（有 backend/ 與 frontend/ 的那層）
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

cp .env.example .env                        # 可選：填入 GEMINI_API_KEY
uvicorn backend.main:app --reload
```

開啟 <http://127.0.0.1:8000>，API 文件在 <http://127.0.0.1:8000/docs>。

### 離線模式

沒有設定 `GEMINI_API_KEY` 時一切照常運作，只是：

- 問答直接回覆知識庫裡最相關的段落（畫面右上角會顯示「離線模式」）
- 相機辨識只看檔名，例如 `tiger.jpg` 會被認成老虎
- 語音轉文字（後端版）不可用；瀏覽器內建的語音辨識不受影響

## 專案結構

```
frontend/                 純靜態網頁，由 FastAPI 掛載在 /
├─ index.html  css/style.css
└─ js/  api.js（請求與 DOM 工具）  map.js（SVG 地圖）  camera.js（上傳前縮圖）
        voice.js（語音輸入與朗讀）  app.js（畫面流程）
backend/
├─ main.py                FastAPI 入口、啟動時建立資料表
├─ config.py              路徑、環境變數、評分常數
├─ api/                   HTTP 層：chat / vision / voice / recommendation / route / profile
├─ agent/                 決策層：agent（推薦、路線）/ decision（計分）/ state / tools
├─ rag/                   ingest（切段）→ embeddings → vector_store → retriever
├─ services/              llm / vision / stt / tts（外部能力封裝）
├─ database/              schema.sql、models.py、database.py（SQLite，標準函式庫）
└─ data/                  animals.json、routes.json、zones.json、knowledge/*.txt
tests/                    pytest
```

## API

| 方法 | 路徑 | 說明 |
|---|---|---|
| GET | `/api/health` | 狀態與 AI 模式（`gemini` / `offline`） |
| GET | `/api/route/map` | 地圖座標、動物清單、距離表、興趣標籤 |
| POST | `/api/recommend` | 下一站推薦。只需 `user_id`，其餘欄位沒帶就用資料庫中的使用者資料 |
| POST | `/api/route` | 在剩餘時間內規劃完整路線 |
| POST | `/api/chat` | 導覽問答 `{user_id, message, current_animal?}` |
| POST | `/api/vision` | 上傳照片辨識動物（multipart：`file`、`user_id`） |
| POST | `/api/voice/stt` | 音訊轉文字（需要 Gemini） |
| POST | `/api/voice/tts` | 整理成適合朗讀的文字（發聲由瀏覽器負責） |
| GET / PUT | `/api/profile/{user_id}` | 讀取／更新興趣、位置、剩餘時間、已參觀 |
| POST | `/api/profile/{user_id}/visit` | 標記已參觀，並扣除步行與參觀時間 |

## 推薦怎麼算

`總分 = 興趣 × 0.40 + 距離 × 0.25 + 時間 × 0.20 + 新鮮度 × 0.15`

- **時間是硬性條件**：走過去加參觀時間超過剩餘時間的動物直接排除，不會被推薦。
- **新鮮度**：這隻動物的標籤有多少是你前面還沒看過的。
- 沒選任何興趣時，興趣分一律給 0.5（由距離與新鮮度決定順序）。
- 步行速度與距離基準在 `config.py`、`routes.json`。

## 新增一隻動物

1. `backend/data/animals.json`：加上名稱、別名、標籤、參觀時間、所屬展區。
2. `backend/data/zones.json`：加上地圖座標。
3. `backend/data/routes.json`：補上它與其他地點的距離（需雙向）。
4. `backend/data/knowledge/<動物id>.txt`：寫知識（段落之間空一行）。檔名就是動物 id。

向量庫會在下次啟動檢索時自動重建，也可手動執行 `python -m backend.rag.ingest`。
`tests/test_agent.py::test_data_files_are_consistent` 會檢查以上四處是否都有補齊。

## 測試

```bash
pytest
```

測試使用暫存資料庫並強制離線模式，不需要 API Key，也不會動到你的資料。

## Docker

```bash
docker build -t zooguide .
docker run -p 8080:8080 -e GEMINI_API_KEY=你的金鑰 zooguide
```

資料庫與向量庫寫在容器內；需要保留資料時，請把 `backend/data/zoo.db` 與 `vector_db/` 掛成 volume。
