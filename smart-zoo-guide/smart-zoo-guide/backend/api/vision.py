from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.services import vision as vision_service

router = APIRouter()

MAX_IMAGE_BYTES = 8 * 1024 * 1024


@router.post("/")
def recognize(image: UploadFile = File(..., description="相機畫面 (JPEG/PNG)")):
    """接收前端即時影像的一個畫格，回傳臺北市立動物園物種辨識結果 (top-5)。

    使用一般 def (非 async)：FastAPI 會放到 threadpool 執行，模型推論不會卡住事件迴圈。
    """
    data = image.file.read(MAX_IMAGE_BYTES + 1)
    if not data:
        raise HTTPException(400, "未收到影像")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "影像過大 (上限 8MB)")
    try:
        clf = vision_service.get_classifier()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    try:
        return clf.predict(data)
    except Exception as e:  # PIL 無法解析等
        raise HTTPException(400, f"無法辨識影像：{e}")


@router.get("/status")
def status():
    ok = vision_service.model_available()
    info = {"model_loaded": ok}
    if ok:
        clf = vision_service.get_classifier()
        info.update({"num_classes": len(clf.labels), "input_size": clf.size,
                     "providers": clf.session.get_providers()})
    return info


@router.get("/labels")
def labels():
    """目前模型可辨識的所有物種清單。"""
    try:
        clf = vision_service.get_classifier()
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    return [{"key": l["key"], "name_zh": l["name_zh"], "scientific_name": l["scientific_name"],
             "locations": l["locations"]} for l in clf.labels]
