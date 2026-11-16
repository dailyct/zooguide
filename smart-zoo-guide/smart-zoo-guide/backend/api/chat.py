import logging
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend import config
from backend.agent.agent import get_agent
from backend.agent.tools import find_animal_in_text
from backend.database import database
from backend.rag import retriever
from backend.services import llm

router = APIRouter()
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是一位親切的動物園導覽員，使用繁體中文回答遊客的問題。\n"
    "請只根據「參考資料」回答；參考資料沒有提到的內容，請誠實說明目前沒有相關資料，不要編造。\n"
    "回答請簡短（約 3 到 5 句話），語氣活潑但不誇張，適合直接朗讀。不要使用 Markdown 符號。"
)


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=500)
    current_animal: Optional[str] = None  # 遊客目前正在看的動物 id（可選）


def _offline_reply(chunks: List[dict]) -> str:
    if not chunks:
        return "（離線模式）目前的導覽資料裡找不到相關內容，可以換個方式問問看。"
    body = "\n".join(c["text"] for c in chunks[:2])
    return f"（離線模式）以下是相關的導覽資料：\n{body}"


@router.post("")
def chat(req: ChatRequest):
    agent = get_agent()
    database.ensure_user(req.user_id)

    # 問題中提到的動物優先；沒提到就用遊客目前正在看的那隻
    animal_id = find_animal_in_text(req.message, agent.animals) or (
        req.current_animal if req.current_animal in agent.animals else None
    )

    chunks = retriever.retrieve(req.message, k=config.RAG_TOP_K, animal_id=animal_id)
    if not chunks and animal_id:
        chunks = retriever.retrieve(req.message, k=config.RAG_TOP_K)

    history = database.get_chat_history(req.user_id)
    mode = "offline"
    reply = None

    if llm.is_available():
        context = "\n".join(f"- {c['text']}" for c in chunks) or "（沒有找到相關資料）"
        user_turn = f"參考資料：\n{context}\n\n遊客的問題：{req.message}"
        messages = [{"role": m.role, "content": m.content} for m in history]
        while messages and messages[0]["role"] != "user":
            messages.pop(0)  # Gemini 要求對話必須以 user 開頭；歷史被截斷時可能從 assistant 開始
        messages.append({"role": "user", "content": user_turn})
        try:
            reply = llm.generate(SYSTEM_PROMPT, messages)
            mode = "gemini"
        except Exception:  # 網路、額度或模型錯誤時降級，不讓遊客看到 500
            logger.exception("LLM 呼叫失敗，改用離線回答")

    if reply is None:
        reply = _offline_reply(chunks)

    database.add_chat_message(req.user_id, "user", req.message)
    database.add_chat_message(req.user_id, "assistant", reply)
    database.log_interaction(req.user_id, "chat", animal_id, req.message[:200])

    return {
        "reply": reply,
        "animal": animal_id,
        "mode": mode,
        "sources": [{"animal_id": c["metadata"].get("animal_id"), "text": c["text"]} for c in chunks],
    }
