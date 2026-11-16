"""SQLite 存取層（使用標準函式庫，不需額外套件）。"""
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator, List, Optional

from backend import config
from backend.database.models import ChatMessage, UserProfile

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

# 預設興趣：新使用者第一次進來時的起始值
DEFAULT_INTERESTS = {"carnivore": 0.5, "herbivore": 0.5, "cute": 0.5, "large": 0.5}


def _connect() -> sqlite3.Connection:
    db_dir = os.path.dirname(config.DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """取得連線，離開時自動 commit（發生例外則 rollback）並關閉。"""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_initialized_paths = set()


def init_db() -> None:
    """建立資料表（可重複執行；同一個資料庫檔案在程式生命週期內只會真正執行一次）。"""
    if config.DB_PATH in _initialized_paths and os.path.exists(config.DB_PATH):
        return
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = f.read()
    with get_connection() as conn:
        conn.executescript(schema)
    _initialized_paths.add(config.DB_PATH)


def ensure_user(user_id: str) -> None:
    """確保使用者存在；第一次出現時寫入預設興趣。"""
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone()
        if row:
            return
        conn.execute(
            "INSERT INTO users (id, remaining_time, current_location) VALUES (?, ?, ?)",
            (user_id, config.DEFAULT_REMAINING_TIME, config.DEFAULT_LOCATION),
        )
        conn.executemany(
            "INSERT INTO user_interests (user_id, interest, weight) VALUES (?, ?, ?)",
            [(user_id, k, v) for k, v in DEFAULT_INTERESTS.items()],
        )


def get_profile(user_id: str) -> UserProfile:
    ensure_user(user_id)
    with get_connection() as conn:
        user = conn.execute(
            "SELECT remaining_time, current_location FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        interests = conn.execute(
            "SELECT interest, weight FROM user_interests WHERE user_id = ?", (user_id,)
        ).fetchall()
        visits = conn.execute(
            "SELECT animal_id FROM user_visits WHERE user_id = ? ORDER BY visited_at, rowid",
            (user_id,),
        ).fetchall()
    return UserProfile(
        user_id=user_id,
        current_location=user["current_location"],
        remaining_time=user["remaining_time"],
        interests={r["interest"]: r["weight"] for r in interests},
        visited=[r["animal_id"] for r in visits],
    )


def save_profile(profile: UserProfile) -> UserProfile:
    """以傳入的內容完整覆寫使用者資料（興趣與已參觀清單皆整批取代）。"""
    ensure_user(profile.user_id)
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET remaining_time = ?, current_location = ? WHERE id = ?",
            (profile.remaining_time, profile.current_location, profile.user_id),
        )
        conn.execute("DELETE FROM user_interests WHERE user_id = ?", (profile.user_id,))
        conn.executemany(
            "INSERT INTO user_interests (user_id, interest, weight) VALUES (?, ?, ?)",
            [(profile.user_id, k, max(0.0, min(1.0, float(v)))) for k, v in profile.interests.items()],
        )
        conn.execute("DELETE FROM user_visits WHERE user_id = ?", (profile.user_id,))
        conn.executemany(
            "INSERT OR IGNORE INTO user_visits (user_id, animal_id) VALUES (?, ?)",
            [(profile.user_id, a) for a in profile.visited],
        )
    return get_profile(profile.user_id)


def mark_visited(user_id: str, animal_id: str) -> None:
    ensure_user(user_id)
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO user_visits (user_id, animal_id) VALUES (?, ?)",
            (user_id, animal_id),
        )


def log_interaction(user_id: str, action: str, animal_id: Optional[str] = None, detail: Optional[str] = None) -> None:
    ensure_user(user_id)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO interactions (user_id, animal_id, action, detail) VALUES (?, ?, ?, ?)",
            (user_id, animal_id, action, detail),
        )


def add_chat_message(user_id: str, role: str, content: str) -> None:
    ensure_user(user_id)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO chat_messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )


def get_chat_history(user_id: str, limit: int = config.CHAT_HISTORY_LIMIT) -> List[ChatMessage]:
    """回傳最近 limit 則訊息，由舊到新。"""
    ensure_user(user_id)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT role, content FROM chat_messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [ChatMessage(role=r["role"], content=r["content"]) for r in reversed(rows)]
