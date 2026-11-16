"""集中管理設定：所有路徑與環境變數都從這裡讀取。

沒有設定 GEMINI_API_KEY 時，系統會自動進入「離線模式」：
問答改用本機檢索結果回覆，相機辨識改用檔名提示，其餘功能照常運作。
"""
import os

from dotenv import load_dotenv

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(BACKEND_DIR)

# 讀取專案根目錄的 .env（不存在也不會報錯）
load_dotenv(os.path.join(BASE_DIR, ".env"))

# --- 路徑 ---
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
DATA_DIR = os.path.join(BACKEND_DIR, "data")
KNOWLEDGE_DIR = os.path.join(DATA_DIR, "knowledge")
DB_PATH = os.environ.get("ZOO_DB_PATH", os.path.join(DATA_DIR, "zoo.db"))
VECTOR_DB_PATH = os.environ.get("ZOO_VECTOR_DB_PATH", os.path.join(BASE_DIR, "vector_db", "store.json"))

# --- Gemini ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_EMBEDDING_MODEL = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")

# --- 導覽邏輯 ---
DEFAULT_REMAINING_TIME = 60      # 使用者預設剩餘時間（分鐘）
DEFAULT_LOCATION = "entrance"    # 使用者預設所在位置
MAX_DISTANCE_FOR_SCORE = 500     # 距離分數的基準（公尺），超過即為 0 分
DEFAULT_WALK_SPEED = 60          # 預設步行速度（公尺／分鐘）

# --- RAG / 對話 ---
RAG_TOP_K = 3
CHAT_HISTORY_LIMIT = 6           # 帶入 LLM 的歷史訊息數
MAX_IMAGE_SIDE = 1024            # 上傳圖片縮放後的最長邊（像素）
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def has_gemini() -> bool:
    return bool(GEMINI_API_KEY)
