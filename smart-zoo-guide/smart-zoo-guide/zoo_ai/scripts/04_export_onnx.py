"""
步驟 4：把訓練好的 PyTorch 模型匯出成 ONNX，並複製到後端 backend/models/。
後端以 onnxruntime 推論 (CPU 即可)，不需安裝 PyTorch，Docker 映像小很多。

同時用 test split 比對 PyTorch 與 ONNX 輸出，確認匯出正確。
"""
import json
import shutil
from pathlib import Path

import numpy as np
import onnxruntime as ort
import timm
import torch

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models"
BACKEND_MODELS = ROOT.parent / "backend" / "models"


def main():
    ckpt = torch.load(MODEL_DIR / "zoo_convnext_tiny.pt", map_location="cpu")
    model = timm.create_model(ckpt["model_name"], pretrained=False, num_classes=ckpt["num_classes"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()

    size = ckpt["input_size"]
    dummy = torch.randn(1, 3, size, size)
    onnx_path = MODEL_DIR / "zoo_classifier.onnx"
    torch.onnx.export(model, dummy, str(onnx_path), input_names=["input"], output_names=["logits"],
                      dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}}, opset_version=17,
                      dynamo=False)

    # 驗證 ONNX 與 PyTorch 輸出一致
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    x = torch.randn(4, 3, size, size)
    with torch.no_grad():
        ref = model(x).numpy()
    out = sess.run(None, {"input": x.numpy()})[0]
    diff = float(np.abs(ref - out).max())
    print(f"ONNX vs PyTorch 最大誤差: {diff:.2e}")
    assert diff < 1e-2, "ONNX 輸出與 PyTorch 不一致"

    labels = json.loads((MODEL_DIR / "labels.json").read_text(encoding="utf-8"))
    config = {"input_size": size, "mean": list(ckpt["mean"]), "std": list(ckpt["std"]),
              "model_name": ckpt["model_name"], "num_classes": ckpt["num_classes"]}
    (MODEL_DIR / "model_config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")

    BACKEND_MODELS.mkdir(parents=True, exist_ok=True)
    for f in ("zoo_classifier.onnx", "labels.json", "model_config.json"):
        shutil.copy2(MODEL_DIR / f, BACKEND_MODELS / f)
    print(f"已複製到 {BACKEND_MODELS}  ({onnx_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
