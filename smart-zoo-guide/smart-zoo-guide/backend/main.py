import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# 匯入各個 API 路由模組
from backend.api import chat, vision, voice, recommendation, route

app = FastAPI(title="Smart Zoo Guide API - Pro Version")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# 註冊 API 路由，並設定統一路徑前綴
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(vision.router, prefix="/api/vision", tags=["Vision"])
app.include_router(voice.router, prefix="/api/voice", tags=["Voice"])
app.include_router(recommendation.router, prefix="/api/recommend", tags=["Recommendation"])
app.include_router(route.router, prefix="/api/route", tags=["Route"])

# 掛載前端靜態檔案
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")