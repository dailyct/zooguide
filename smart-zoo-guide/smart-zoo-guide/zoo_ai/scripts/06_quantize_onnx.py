"""
步驟 6：把 ONNX 模型做 INT8 動態量化 (權重 int8)，並在 test split 上和 FP32 比較準確率與速度。

原因：FP32 模型 112MB 超過 GitHub 單檔 100MB 上限；INT8 約 1/4 大小，CPU 推論也較快。
若 INT8 top-1 下降 ≤ 1 個百分點，就以 INT8 取代 backend/models/zoo_classifier.onnx。

用法：python scripts/06_quantize_onnx.py [--max-images 0(全部)]
"""
import argparse
import hashlib
import json
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
from onnxruntime.quantization import QuantType, quant_pre_process, quantize_dynamic
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models"
IMG_DIR = ROOT / "data" / "images"
BACKEND_MODELS = ROOT.parent / "backend" / "models"


def preprocess(path, size, mean, std):
    # 與 backend/services/vision.py 相同：短邊縮放 (crop_pct 0.95) + 中央裁切
    img = Image.open(path).convert("RGB")
    scale = size / 0.95 / min(img.size)
    img = img.resize((max(size, round(img.width * scale)), max(size, round(img.height * scale))), Image.BICUBIC)
    l, t = (img.width - size) // 2, (img.height - size) // 2
    x = np.asarray(img.crop((l, t, l + size, t + size)), dtype=np.float32).transpose(2, 0, 1) / 255.0
    return (x - mean) / std


def evaluate(model_path, items, cfg, batch=64):
    opts = ort.SessionOptions()
    opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess = ort.InferenceSession(str(model_path), opts, providers=["CPUExecutionProvider"])
    mean = np.array(cfg["mean"], np.float32).reshape(3, 1, 1)
    std = np.array(cfg["std"], np.float32).reshape(3, 1, 1)
    c1 = c5 = 0
    infer_t = 0.0
    for i in range(0, len(items), batch):
        chunk = items[i:i + batch]
        x = np.stack([preprocess(p, cfg["input_size"], mean, std) for p, _ in chunk])
        y = np.array([c for _, c in chunk])
        t0 = time.perf_counter()
        logits = sess.run(None, {"input": x})[0]
        infer_t += time.perf_counter() - t0
        top5 = np.argsort(-logits, 1)[:, :5]
        c1 += int((top5[:, 0] == y).sum())
        c5 += int((top5 == y[:, None]).any(1).sum())
    # 單張延遲 (即時影像情境，batch=1)
    x1 = x[:1]
    for _ in range(3):
        sess.run(None, {"input": x1})
    t0 = time.perf_counter()
    for _ in range(20):
        sess.run(None, {"input": x1})
    lat = (time.perf_counter() - t0) / 20 * 1000
    n = len(items)
    return {"top1": c1 / n, "top5": c5 / n, "n": n, "latency_ms_batch1": lat,
            "throughput_img_s": n / infer_t}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-images", type=int, default=0)
    args = ap.parse_args()

    fp32 = MODEL_DIR / "zoo_classifier.onnx"
    int8 = MODEL_DIR / "zoo_classifier.int8.onnx"
    # onnx 的 C++ shape inference 無法寫入含中文字的路徑 → 在系統暫存資料夾 (英文路徑) 中處理
    with tempfile.TemporaryDirectory() as tmp:
        t_in, t_pre, t_out = (Path(tmp) / n for n in ("in.onnx", "pre.onnx", "int8.onnx"))
        shutil.copy2(fp32, t_in)
        quant_pre_process(str(t_in), str(t_pre))
        # 只量化 MatMul/Gemm (ConvNeXt 的 MLP 層，佔大部分參數)；卷積維持 FP32。
        # 實測若連 Conv 一起量化 (ConvInteger)，CPU 上反而變慢 (151ms → 261ms/張)。
        quantize_dynamic(str(t_pre), str(t_out), weight_type=QuantType.QInt8, per_channel=True,
                         op_types_to_quantize=["MatMul", "Gemm"])
        shutil.copy2(t_out, int8)
    print(f"FP32 {fp32.stat().st_size / 1e6:.1f} MB → INT8 {int8.stat().st_size / 1e6:.1f} MB")

    labels = json.loads((MODEL_DIR / "labels.json").read_text(encoding="utf-8"))
    cfg = json.loads((MODEL_DIR / "model_config.json").read_text(encoding="utf-8"))
    items = []
    for lab in labels:  # test split：md5(檔名) % 100 >= 90 (與 03_train.py 相同)
        for p in sorted((IMG_DIR / lab["key"]).glob("*.jpg")):
            if int(hashlib.md5(p.name.encode()).hexdigest(), 16) % 100 >= 90:
                items.append((p, lab["index"]))
    if args.max_images:
        rng = np.random.default_rng(0)
        items = [items[i] for i in sorted(rng.choice(len(items), args.max_images, replace=False))]

    res = {}
    for name, path in (("fp32", fp32), ("int8", int8)):
        res[name] = evaluate(path, items, cfg)
        r = res[name]
        print(f"{name}: top1 {r['top1']:.4f}  top5 {r['top5']:.4f}  "
              f"單張延遲 {r['latency_ms_batch1']:.1f} ms  吞吐 {r['throughput_img_s']:.0f} img/s  (n={r['n']})")
    res["size_mb"] = {"fp32": fp32.stat().st_size / 1e6, "int8": int8.stat().st_size / 1e6}
    (MODEL_DIR / "quantization_report.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    drop = res["fp32"]["top1"] - res["int8"]["top1"]
    # 只以準確率決定 (延遲受機器負載影響很大，不穩定；無負載時交錯量測 INT8 約快 25~30%)
    if drop <= 0.01:
        shutil.copy2(int8, BACKEND_MODELS / "zoo_classifier.onnx")
        print(f"top-1 下降 {drop * 100:.2f} 個百分點 (≤1)，已用 INT8 模型取代 backend/models/zoo_classifier.onnx")
    else:
        shutil.copy2(fp32, BACKEND_MODELS / "zoo_classifier.onnx")
        print(f"top-1 下降 {drop * 100:.2f} 個百分點 (>1)，後端維持 FP32 模型 (需 Git LFS 才能推上 GitHub)")


if __name__ == "__main__":
    main()
