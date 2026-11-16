from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.agent.agent import get_agent
from backend.api.common import read_upload
from backend.database import database
from backend.services import vision

router = APIRouter()


@router.post("")
def recognize_animal(file: UploadFile = File(...), user_id: str = Form("anonymous")):
    agent = get_agent()
    data = read_upload(file)
    try:
        result = vision.recognize(data, file.filename, agent.animals)
    except vision.InvalidImage as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"影像辨識服務暫時無法使用：{exc}")

    database.log_interaction(user_id, "vision", result["animal"], f"confidence={result['confidence']}")
    result["animal_info"] = agent.get_animal(result["animal"]) if result["animal"] else None
    return result
