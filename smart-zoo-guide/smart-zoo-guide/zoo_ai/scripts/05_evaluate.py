"""
步驟 5：在 test split 上詳細評估模型 (供專題報告使用)。

輸出 models/eval_report.json 與終端摘要：
  * 整體 top-1 / top-5
  * 各信心度門檻下的「覆蓋率 / 準確率」(決定後端 VISION_CONFIDENCE_THRESHOLD)
  * 各物種準確率 (最差 15 類) 與最常見混淆對
  * 依動物類別 (哺乳綱/鳥綱/...) 分組的準確率
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import timm
import torch
from timm.data import create_transform
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib import import_module  # noqa: E402

train_mod = import_module("03_train")
ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models"


def main():
    labels = json.loads((MODEL_DIR / "labels.json").read_text(encoding="utf-8"))
    ckpt = torch.load(MODEL_DIR / "zoo_convnext_tiny.pt", map_location="cuda")
    model = timm.create_model(ckpt["model_name"], num_classes=ckpt["num_classes"]).cuda().eval()
    model.load_state_dict(ckpt["state_dict"])

    _, splits, _ = train_mod.build_items(min_images=20)
    tf = create_transform(input_size=224, mean=ckpt["mean"], std=ckpt["std"], crop_pct=0.95,
                          interpolation="bicubic", is_training=False)
    dl = DataLoader(train_mod.ImgDS(splits["test"], tf), 192, num_workers=4)

    ys, preds, confs, top5 = [], [], [], []
    with torch.no_grad():
        for x, y in dl:
            with torch.autocast("cuda", dtype=torch.bfloat16):
                p = model(x.cuda()).float().softmax(1).cpu()
            c, i = p.max(1)
            ys += y.tolist(); preds += i.tolist(); confs += c.tolist()
            top5 += (p.topk(5, 1).indices == y[:, None]).any(1).tolist()
    n = len(ys)
    correct = [a == b for a, b in zip(ys, preds)]
    report = {"n_test": n, "top1": sum(correct) / n, "top5": sum(top5) / n}

    print(f"Test 影像 {n} 張  top-1 {report['top1']:.4f}  top-5 {report['top5']:.4f}\n")
    print("信心度門檻 | 覆蓋率 (有給答案的比例) | 給答案時的準確率")
    report["thresholds"] = []
    for t in (0.0, 0.3, 0.45, 0.6, 0.75, 0.9):
        sel = [ok for ok, c in zip(correct, confs) if c >= t]
        cov, acc = len(sel) / n, (sum(sel) / len(sel) if sel else 0)
        report["thresholds"].append({"threshold": t, "coverage": cov, "accuracy": acc})
        print(f"   {t:.2f}     |        {cov:6.1%}          |     {acc:6.1%}")

    per = defaultdict(lambda: [0, 0])
    conf_pairs = Counter()
    for y, p in zip(ys, preds):
        per[y][1] += 1
        per[y][0] += y == p
        if y != p:
            conf_pairs[(y, p)] += 1
    per_cls = sorted(((per[i][0] / per[i][1], per[i][1], i) for i in per))
    report["per_class"] = [{"key": labels[i]["key"], "name_zh": labels[i]["name_zh"], "acc": a, "n": m}
                           for a, m, i in per_cls]
    print("\n最難辨識的 15 類：")
    for a, m, i in per_cls[:15]:
        print(f"   {a:6.1%} (n={m:3d})  {labels[i]['name_zh']}  {labels[i]['scientific_name']}")
    print("\n最常見的混淆：")
    report["confusions"] = []
    for (y, p), c in conf_pairs.most_common(12):
        report["confusions"].append({"true": labels[y]["name_zh"], "pred": labels[p]["name_zh"], "count": c})
        print(f"   {labels[y]['name_zh']} → 誤認為 {labels[p]['name_zh']}  ×{c}")

    grp = defaultdict(lambda: [0, 0])
    for y, ok in zip(ys, correct):
        g = labels[y]["class_zh"] or "其他"
        grp[g][0] += ok
        grp[g][1] += 1
    report["by_group"] = {g: {"acc": a / m, "n": m} for g, (a, m) in grp.items()}
    print("\n依動物類別：")
    for g, (a, m) in sorted(grp.items(), key=lambda kv: -kv[1][1]):
        print(f"   {g:<6} {a / m:6.1%}  (n={m})")

    (MODEL_DIR / "eval_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                                encoding="utf-8")


if __name__ == "__main__":
    main()
