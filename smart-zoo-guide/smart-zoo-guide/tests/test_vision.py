import hashlib
import io
import os

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.main import app
from backend.services import vision as vision_service

client = TestClient(app)
needs_model = pytest.mark.skipif(not vision_service.model_available(),
                                 reason="尚未匯出 backend/models/zoo_classifier.onnx")


def _jpeg(color=(120, 160, 90), size=(400, 300)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "JPEG")
    return buf.getvalue()


def test_status():
    r = client.get("/api/vision/status")
    assert r.status_code == 200
    assert "model_loaded" in r.json()


def test_rejects_empty_upload():
    r = client.post("/api/vision/", files={"image": ("a.jpg", b"", "image/jpeg")})
    assert r.status_code in (400, 503)


@needs_model
def test_rejects_non_image():
    r = client.post("/api/vision/", files={"image": ("a.jpg", b"not an image", "image/jpeg")})
    assert r.status_code == 400


@needs_model
def test_predict_shape():
    r = client.post("/api/vision/", files={"image": ("f.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 200
    d = r.json()
    assert len(d["top_k"]) == 5
    assert 0.0 <= d["confidence"] <= 1.0
    assert isinstance(d["recognized"], bool)
    probs = [t["confidence"] for t in d["top_k"]]
    assert probs == sorted(probs, reverse=True)


@needs_model
def test_predict_real_sample():
    """若本機有下載訓練影像，用 test split 的大貓熊照片 (訓練沒看過) 做煙霧測試。
    資料中含夜間相機陷阱、糞便等難例，因此要求 ≥ 80% 而非 100%。"""
    sample_dir = os.path.join(os.path.dirname(__file__), "..", "zoo_ai", "data", "images",
                              "Ailuropoda_melanoleuca")
    if not os.path.isdir(sample_dir):
        pytest.skip("沒有本機訓練影像")
    # 與 zoo_ai/scripts/03_train.py 相同的切分規則：md5(檔名) % 100 >= 90 為 test (訓練沒看過)
    files = sorted(f for f in os.listdir(sample_dir)
                   if int(hashlib.md5(f.encode()).hexdigest(), 16) % 100 >= 90)
    hits = 0
    for f in files:
        with open(os.path.join(sample_dir, f), "rb") as fh:
            d = client.post("/api/vision/", files={"image": (f, fh.read(), "image/jpeg")}).json()
        hits += d["animal"] == "Ailuropoda_melanoleuca"
    assert files and hits / len(files) >= 0.8
