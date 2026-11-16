"""
步驟 3：訓練動物物種影像分類模型。

模型：ConvNeXt-Tiny (timm: convnext_tiny.fb_in22k_ft_in1k)
      ImageNet-22k 預訓練 → 在臺北市立動物園物種影像上做遷移學習 (full fine-tune)。
訓練細節：
  * 輸入 224x224，RandAugment(m7,n2) + RandomResizedCrop + 水平翻轉 + Random Erasing
  * AdamW + cosine LR + warmup，label smoothing 0.1，AMP 混合精度
  * 前 1 epoch 只訓練分類頭 (backbone 凍結)，之後全部解凍
  * 依影像檔名 hash 切分 train/val/test = 80/10/10 (可重現)

輸出：models/zoo_convnext_tiny.pt   (state_dict + 類別資訊)
      models/labels.json            (類別順序 + 中文名 + 館區)
      models/train_history.json
用法：python scripts/03_train.py [--epochs 15] [--batch 96] [--min-images 20]
"""
import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import timm
import torch
import torch.nn as nn
from PIL import Image
from timm.data import create_transform, resolve_data_config
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
IMG_DIR = ROOT / "data" / "images"
SPECIES = ROOT / "data" / "species.json"
MODEL_DIR = ROOT / "models"
MODEL_NAME = "convnext_tiny.fb_in22k_ft_in1k"


def split_of(name: str) -> str:
    h = int(hashlib.md5(name.encode()).hexdigest(), 16) % 100
    return "train" if h < 80 else ("val" if h < 90 else "test")


class ImgDS(Dataset):
    def __init__(self, items, tf):
        self.items, self.tf = items, tf

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        p, y = self.items[i]
        try:
            im = Image.open(p).convert("RGB")
        except Exception:
            im = Image.new("RGB", (224, 224))
        return self.tf(im), y


def build_items(min_images):
    meta = {c["key"]: c for c in json.loads(SPECIES.read_text(encoding="utf-8"))["classes"]}
    keys = sorted(k for k in meta if (IMG_DIR / k).is_dir()
                  and len(list((IMG_DIR / k).glob("*.jpg"))) >= min_images)
    dropped = sorted(k for k in meta if k not in keys)
    splits = {"train": [], "val": [], "test": []}
    for idx, k in enumerate(keys):
        for p in sorted((IMG_DIR / k).glob("*.jpg")):
            splits[split_of(p.name)].append((str(p), idx))
    labels = [{
        "index": i, "key": k, "scientific_name": meta[k]["scientific_name"],
        "name_zh": meta[k]["display_name_zh"], "names_zh": meta[k]["zoo_names_zh"],
        "name_en": ", ".join(meta[k]["zoo_names_en"]) or meta[k].get("inat_common_name", ""),
        "locations": meta[k]["locations"], "inat_taxon_id": meta[k]["inat_taxon_id"],
        "class_zh": meta[k]["class_zh"], "conservation": meta[k]["conservation"],
        "lat": meta[k]["lat"], "lng": meta[k]["lng"],
    } for i, k in enumerate(keys)]
    return labels, splits, dropped


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    n = c1 = c5 = 0
    loss_sum = 0.0
    crit = nn.CrossEntropyLoss()
    for x, y in loader:
        x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            out = model(x)
        loss_sum += crit(out.float(), y).item() * len(y)
        top5 = out.topk(5, 1).indices
        c1 += (top5[:, 0] == y).sum().item()
        c5 += (top5 == y[:, None]).any(1).sum().item()
        n += len(y)
    return {"loss": loss_sum / n, "top1": c1 / n, "top5": c5 / n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch", type=int, default=96)
    ap.add_argument("--lr", type=float, default=4e-4)
    ap.add_argument("--min-images", type=int, default=20)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    torch.manual_seed(0)
    device = "cuda"
    torch.backends.cudnn.benchmark = True
    MODEL_DIR.mkdir(exist_ok=True)

    labels, splits, dropped = build_items(args.min_images)
    nc = len(labels)
    print(f"類別數 {nc}；train {len(splits['train'])} / val {len(splits['val'])} / test {len(splits['test'])}")
    if dropped:
        print(f"影像不足 {args.min_images} 張而排除的類別 ({len(dropped)}): {dropped}")
    (MODEL_DIR / "labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=2), encoding="utf-8")

    model = timm.create_model(MODEL_NAME, pretrained=True, num_classes=nc, drop_path_rate=0.1)
    cfg = resolve_data_config({}, model=model)
    cfg["input_size"] = (3, 224, 224)
    tf_train = create_transform(**cfg, is_training=True, auto_augment="rand-m7-n2-inc1",
                                re_prob=0.25, scale=(0.35, 1.0))
    tf_eval = create_transform(**{**cfg, "crop_pct": 0.95}, is_training=False)
    model.to(device).to(memory_format=torch.channels_last)

    dl_kw = dict(num_workers=args.workers, pin_memory=True, persistent_workers=True)
    train_dl = DataLoader(ImgDS(splits["train"], tf_train), args.batch, shuffle=True, drop_last=True, **dl_kw)
    # Windows 上每個 worker 程序啟動很慢 (實測約 40 秒/個)，評估用 loader 只開少量 worker
    eval_kw = dict(num_workers=min(4, args.workers), pin_memory=True, persistent_workers=True)
    val_dl = DataLoader(ImgDS(splits["val"], tf_eval), args.batch * 2, **eval_kw)
    test_dl = DataLoader(ImgDS(splits["test"], tf_eval), args.batch * 2, **eval_kw)

    head_params = list(model.get_classifier().parameters())
    head_ids = {id(p) for p in head_params}
    body_params = [p for p in model.parameters() if id(p) not in head_ids]
    opt = torch.optim.AdamW([{"params": body_params, "lr": args.lr * 0.5},
                             {"params": head_params, "lr": args.lr * 2}], weight_decay=0.05)
    base_lrs = [g["lr"] for g in opt.param_groups]
    steps_per_epoch = len(train_dl)
    total = steps_per_epoch * args.epochs
    warm = steps_per_epoch

    def set_lr(step):
        f = step / warm if step < warm else 0.5 * (1 + math.cos(math.pi * (step - warm) / max(1, total - warm)))
        for g, b in zip(opt.param_groups, base_lrs):
            g["lr"] = b * max(f, 0.01)

    crit = nn.CrossEntropyLoss(label_smoothing=0.1)
    history, best, step = [], 0.0, 0
    for ep in range(args.epochs):
        freeze = ep == 0
        for p in body_params:
            p.requires_grad_(not freeze)
        model.train()
        t0, run_loss, seen = time.time(), 0.0, 0
        for x, y in train_dl:
            set_lr(step)
            step += 1
            x = x.to(device, non_blocking=True).to(memory_format=torch.channels_last)
            y = y.to(device, non_blocking=True)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                loss = crit(model(x), y)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            run_loss += loss.item() * len(y)
            seen += len(y)
        v = evaluate(model, val_dl, device)
        rec = {"epoch": ep + 1, "train_loss": run_loss / seen, **{f"val_{k}": val for k, val in v.items()},
               "sec": round(time.time() - t0, 1)}
        history.append(rec)
        print(json.dumps(rec), flush=True)
        if v["top1"] > best:
            best = v["top1"]
            torch.save({"model_name": MODEL_NAME, "num_classes": nc, "state_dict": model.state_dict(),
                        "input_size": 224, "mean": cfg["mean"], "std": cfg["std"]},
                       MODEL_DIR / "zoo_convnext_tiny.pt")

    ckpt = torch.load(MODEL_DIR / "zoo_convnext_tiny.pt", map_location=device)
    model.load_state_dict(ckpt["state_dict"])
    t = evaluate(model, test_dl, device)
    print(f"\n最佳 val top1 = {best:.4f}；test: {json.dumps(t)}")
    (MODEL_DIR / "train_history.json").write_text(json.dumps(
        {"model": MODEL_NAME, "num_classes": nc, "args": vars(args), "history": history,
         "best_val_top1": best, "test": t, "dropped_classes": dropped,
         "n_train": len(splits["train"]), "n_val": len(splits["val"]), "n_test": len(splits["test"])},
        indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
