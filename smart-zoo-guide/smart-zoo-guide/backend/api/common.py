"""各 router 共用的小工具。"""
from typing import Optional

from fastapi import HTTPException, UploadFile

from backend import config
from backend.database import database


def resolve_profile(user_id: str, current_location: Optional[str] = None, remaining_time: Optional[int] = None,
                    interests: Optional[dict] = None, visited: Optional[list] = None) -> dict:
    """以資料庫中的使用者資料為底，用請求中「有帶」的欄位覆蓋，回傳 Agent 使用的 dict。"""
    profile = database.get_profile(user_id)
    return {
        "current_location": current_location if current_location is not None else profile.current_location,
        "remaining_time": remaining_time if remaining_time is not None else profile.remaining_time,
        "interests": interests if interests is not None else profile.interests,
        "visited": visited if visited is not None else profile.visited,
    }


def read_upload(file: UploadFile) -> bytes:
    """讀取上傳檔案，超過大小上限回 413。"""
    data = file.file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"檔案太大，上限 {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    if not data:
        raise HTTPException(status_code=400, detail="上傳的檔案是空的")
    return data
