"""
動物物種影像辨識服務 (ONNX Runtime 推論)。

模型由 zoo_ai/ 訓練：ConvNeXt-Tiny (ImageNet-22k 預訓練) 在臺北市立動物園物種影像
(iNaturalist + GBIF) 上微調，匯出為 backend/models/zoo_classifier.onnx。
"""
import io
import json
import os
import threading
from typing import Dict, List, Optional

import numpy as np
from PIL import Image, ImageOps

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(BASE_DIR, "models")
MODEL_PATH = os.path.join(MODEL_DIR, "zoo_classifier.onnx")
LABELS_PATH = os.path.join(MODEL_DIR, "labels.json")
CONFIG_PATH = os.path.join(MODEL_DIR, "model_config.json")

# 最高機率低於此值時視為「無法確定」(畫面中可能沒有動物，或是非園區物種)
CONFIDENCE_THRESHOLD = float(os.getenv("VISION_CONFIDENCE_THRESHOLD", "0.45"))


class ZooVisionClassifier:
    def __init__(self, model_path: str = MODEL_PATH, labels_path: str = LABELS_PATH,
                 config_path: str = CONFIG_PATH):
        import onnxruntime as ort

        with open(labels_path, encoding="utf-8") as f:
            self.labels: List[Dict] = json.load(f)
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        self.size = int(cfg["input_size"])
        self.mean = np.array(cfg["mean"], dtype=np.float32).reshape(3, 1, 1)
        self.std = np.array(cfg["std"], dtype=np.float32).reshape(3, 1, 1)

        providers = [p for p in ("CUDAExecutionProvider", "CPUExecutionProvider")
                     if p in ort.get_available_providers()]
        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(model_path, sess_options=opts, providers=providers)
        self.input_name = self.session.get_inputs()[0].name

    def preprocess(self, img: Image.Image) -> np.ndarray:
        img = ImageOps.exif_transpose(img).convert("RGB")
        # 短邊縮放後中央裁切 (與訓練時的評估轉換一致，crop_pct=0.95)
        scale = self.size / 0.95 / min(img.size)
        img = img.resize((max(self.size, round(img.width * scale)),
                          max(self.size, round(img.height * scale))), Image.BICUBIC)
        left = (img.width - self.size) // 2
        top = (img.height - self.size) // 2
        img = img.crop((left, top, left + self.size, top + self.size))
        x = np.asarray(img, dtype=np.float32).transpose(2, 0, 1) / 255.0
        return ((x - self.mean) / self.std)[None]

    def predict(self, image_bytes: bytes, top_k: int = 5) -> Dict:
        img = Image.open(io.BytesIO(image_bytes))
        logits = self.session.run(None, {self.input_name: self.preprocess(img)})[0][0]
        e = np.exp(logits - logits.max())
        probs = e / e.sum()
        idx = np.argsort(-probs)[:top_k]
        top = [self._label_out(int(i), float(probs[i])) for i in idx]
        best = top[0]
        return {
            "recognized": best["confidence"] >= CONFIDENCE_THRESHOLD,
            "threshold": CONFIDENCE_THRESHOLD,
            "animal": best["key"],
            "name": best["name_zh"],
            "confidence": round(best["confidence"], 4),
            "top_k": top,
        }

    def _label_out(self, i: int, p: float) -> Dict:
        lab = self.labels[i]
        return {
            "key": lab["key"],
            "name_zh": lab["name_zh"],
            "name_en": lab["name_en"],
            "scientific_name": lab["scientific_name"],
            "locations": lab["locations"],
            "conservation": lab.get("conservation", ""),
            "confidence": round(p, 4),
        }


_classifier: Optional[ZooVisionClassifier] = None
_lock = threading.Lock()


def get_classifier() -> ZooVisionClassifier:
    """延遲載入 (第一次請求時才載入模型)，並確保只載入一次。"""
    global _classifier
    if _classifier is None:
        with _lock:
            if _classifier is None:
                if not os.path.exists(MODEL_PATH):
                    raise FileNotFoundError(
                        f"找不到模型 {MODEL_PATH}，請先執行 zoo_ai/scripts/03_train.py 與 04_export_onnx.py")
                _classifier = ZooVisionClassifier()
    return _classifier


def model_available() -> bool:
    return os.path.exists(MODEL_PATH) and os.path.exists(LABELS_PATH)
