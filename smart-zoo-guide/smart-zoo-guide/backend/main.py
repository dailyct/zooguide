from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend import config
from backend.api import chat, profile, recommendation, route, vision, voice
from backend.database import database


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()  # 啟動時建立資料表
    yield


app = FastAPI(title="Smart Zoo Guide API - Pro Version", lifespan=lifespan)


@app.get("/api/health")
def health():
    from backend.services import llm

    return {"status": "ok", "llm": "gemini" if llm.is_available() else "offline"}


# 註冊 API 路由，並設定統一路徑前綴
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(vision.router, prefix="/api/vision", tags=["Vision"])
app.include_router(voice.router, prefix="/api/voice", tags=["Voice"])
app.include_router(recommendation.router, prefix="/api/recommend", tags=["Recommendation"])
app.include_router(route.router, prefix="/api/route", tags=["Route"])
app.include_router(profile.router, prefix="/api/profile", tags=["Profile"])

# 掛載前端靜態檔案（必須放在最後，否則會蓋掉上面的 /api 路由）
app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
