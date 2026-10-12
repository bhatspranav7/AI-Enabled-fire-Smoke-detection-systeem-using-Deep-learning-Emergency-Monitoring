"""Module 1 / step 1: build the YOLO training split from the raw dataset zip.

Source: jojomoi-meme/fog_fire_detection on Hugging Face (CC-BY-4.0, compiled from
Roboflow Universe fire-detection collections). ~40.9k images, classes 0=fire 1=smoke.

The full set is far too large to train on CPU overnight, so we draw a *stratified*
subset (fire-only / smoke-only / both / negative) straight out of the zip and write it
in the PDF section 7.2 layout:

    dataset/yolo/images/{train,val,test}/
    dataset/yolo/labels/{train,val,test}/
    configs/data.yaml

Also writes dataset/manifest.json + dataset/DATASET_REGISTER.md (PDF 6.3 dataset register).

Usage:
    python training/prepare_dataset.py --train 3000 --val 600 --test 600
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import re
import time
import zipfile
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW_ZIP = ROOT / "dataset" / "raw" / "dataset.zip"
OUT = ROOT / "dataset" / "yolo"
CLASS_NAMES = {0: "fire", 1: "smoke"}
SPLIT_MAP = {"train": "train", "valid": "val", "val": "val", "test": "test"}
PAT = re.compile(r"(?:^|/)(train|valid|val|test)/(images|labels)/([^/]+)$")
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def classify_label(text: str) -> str:
    """fire / smoke / both / negative, from the label file text."""
    ids = set()
    for line in text.splitlines():
        parts = line.split()
        if parts:
            try:
                ids.add(int(float(parts[0])))
            except ValueError:
                continue
    if ids == {0}:
        return "fire"
    if ids == {1}:
        return "smoke"
    if ids >= {0, 1}:
        return "both"
    return "negative"


def safe_name(name: str) -> bool:
    return ".." not in name and not name.startswith("/") and not name.startswith("\\")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=3000)
    ap.add_argument("--val", type=int, default=600)
    ap.add_argument("--test", type=int, default=600)
    ap.add_argument("--negatives", type=float, default=0.15, help="fraction of each split kept as negatives (if available)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--zip", default=str(RAW_ZIP))
    args = ap.parse_args()

    rng = random.Random(args.seed)
    t0 = time.time()
    zf = zipfile.ZipFile(args.zip)

    # ---- index the zip: split -> stem -> {image: name, label: name}
    index: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(dict))
    for info in zf.infolist():
        if info.is_dir() or not safe_name(info.filename):
            continue
        m = PAT.search(info.filename.replace("\\", "/"))
        if not m:
            continue
        split, kind, fname = m.groups()
        split = SPLIT_MAP[split]
        stem = pathlib.Path(fname).stem
        if kind == "images" and pathlib.Path(fname).suffix.lower() in IMG_EXT:
            index[split][stem]["image"] = info.filename
        elif kind == "labels" and fname.lower().endswith(".txt"):
            index[split][stem]["label"] = info.filename
    print(f"indexed zip in {time.time()-t0:.1f}s:", {s: len(v) for s, v in index.items()})

    # ---- categorise every image by its label content
    buckets: dict[str, dict[str, list]] = {s: defaultdict(list) for s in index}
    for split, stems in index.items():
        for stem, files in stems.items():
            if "image" not in files:
                continue
            if "label" in files:
                cat = classify_label(zf.read(files["label"]).decode("utf-8", "ignore"))
            else:
                cat = "negative"
            buckets[split][cat].append(stem)
    for split in buckets:
        print(split, {k: len(v) for k, v in buckets[split].items()})

    # ---- stratified sampling
    wanted = {"train": args.train, "val": args.val, "test": args.test}
    chosen: dict[str, list] = {}
    for split, n in wanted.items():
        b = buckets.get(split, {})
        if not b:
            print(f"WARNING: split {split} not found in zip")
            chosen[split] = []
            continue
        for lst in b.values():
            rng.shuffle(lst)
        n_neg = min(int(n * args.negatives), len(b.get("negative", [])))
        n_pos = n - n_neg
        pos_cats = [c for c in ("fire", "smoke", "both") if b.get(c)]
        picks = []
        # round-robin across positive categories so fire and smoke are balanced
        per = {c: 0 for c in pos_cats}
        while len(picks) < n_pos and any(per[c] < len(b[c]) for c in pos_cats):
            for c in pos_cats:
                if per[c] < len(b[c]) and len(picks) < n_pos:
                    picks.append((c, b[c][per[c]]))
                    per[c] += 1
        picks += [("negative", s) for s in b.get("negative", [])[:n_neg]]
        rng.shuffle(picks)
        chosen[split] = picks

    # ---- extract only the chosen files
    for split in ("train", "val", "test"):
        (OUT / "images" / split).mkdir(parents=True, exist_ok=True)
        (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)

    manifest = {
        "source": "https://huggingface.co/datasets/jojomoi-meme/fog_fire_detection",
        "license": "CC-BY-4.0 (per dataset metadata); images compiled from Roboflow Universe fire-detection collections",
        "classes": CLASS_NAMES,
        "seed": args.seed,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "splits": {},
    }
    box_counts = {s: Counter() for s in chosen}
    for split, picks in chosen.items():
        cats = Counter()
        for cat, stem in picks:
            files = index[split][stem]
            img_name = files["image"]
            img_out = OUT / "images" / split / pathlib.Path(img_name).name
            img_out.write_bytes(zf.read(img_name))
            lbl_out = OUT / "labels" / split / (pathlib.Path(img_name).stem + ".txt")
            if "label" in files:
                txt = zf.read(files["label"]).decode("utf-8", "ignore")
                for line in txt.splitlines():
                    p = line.split()
                    if p:
                        box_counts[split][CLASS_NAMES.get(int(float(p[0])), "other")] += 1
                lbl_out.write_text(txt)
            else:
                lbl_out.write_text("")  # explicit empty label = negative image
            cats[cat] += 1
        manifest["splits"][split] = {
            "images": len(picks),
            "by_content": dict(cats),
            "boxes": dict(box_counts[split]),
        }
        print(f"{split}: {len(picks)} images  {dict(cats)}  boxes={dict(box_counts[split])}")

    # ---- data.yaml + manifest + register
    data_yaml = ROOT / "configs" / "data.yaml"
    data_yaml.write_text(
        "# Generated by training/prepare_dataset.py\n"
        f"path: {OUT.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "names:\n"
        + "".join(f"  {k}: {v}\n" for k, v in CLASS_NAMES.items())
    )
    (ROOT / "dataset" / "manifest.json").write_text(json.dumps(manifest, indent=2))

    reg = ROOT / "dataset" / "DATASET_REGISTER.md"
    rows = "\n".join(
        f"| {s} | {m['images']} | {m['by_content'].get('fire',0)} | {m['by_content'].get('smoke',0)} | "
        f"{m['by_content'].get('both',0)} | {m['by_content'].get('negative',0)} | "
        f"{m['boxes'].get('fire',0)} | {m['boxes'].get('smoke',0)} |"
        for s, m in manifest["splits"].items()
    )
    reg.write_text(
        "# Dataset Register\n\n"
        "| Field | Value |\n|---|---|\n"
        f"| Source | {manifest['source']} |\n"
        f"| License / permission | {manifest['license']} |\n"
        "| Format | YOLO (class cx cy w h, normalised 0-1) |\n"
        "| Classes | 0 = fire, 1 = smoke |\n"
        f"| Sampling | stratified subset, seed {args.seed}, {args.negatives:.0%} negatives where available |\n"
        "| Preprocessing | none beyond Ultralytics default augmentation at train time |\n"
        f"| Created | {manifest['created']} |\n\n"
        "## Split summary\n\n"
        "| Split | Images | fire-only | smoke-only | both | negative | fire boxes | smoke boxes |\n"
        "|---|---|---|---|---|---|---|---|\n" + rows + "\n\n"
        "Splits are taken from the upstream train/valid/test partition, so frames from the same "
        "source video do not leak between train and test.\n"
    )
    print(f"done in {time.time()-t0:.1f}s -> {OUT}\n{data_yaml}\n{reg}")


if __name__ == "__main__":
    main()
