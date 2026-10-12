"""Module 1 / step 1: build the YOLO training split from the raw dataset zips.

Sources (both YOLO format, downloaded by training/download_datasets.py):
  A) jojomoi-meme/fog_fire_detection  (HF, CC-BY-4.0)  ~40.9k mostly outdoor / CCTV frames, 0=Fire 1=Smoke
  B) shahriar-5/ISFire-4               (HF, MIT)        ~7.4k indoor frames, 4 fine classes
     mapped: black smoke->smoke, blue fire->fire, white-gray smoke->smoke, yellow-orange fire->fire

The full sets are far too large to train on CPU overnight, so we draw a *stratified*
subset (fire-only / smoke-only / both / negative) straight out of each zip and write the
PDF section 7.2 layout:

    dataset/yolo/images/{train,val,test}/
    dataset/yolo/labels/{train,val,test}/
    configs/data.yaml

Also writes dataset/manifest.json + dataset/DATASET_REGISTER.md (PDF 6.3 dataset register).

Usage:
    python training/prepare_dataset.py                       # defaults below
    python training/prepare_dataset.py --train 2000,1000 --val 400,200 --test 400,200
      (comma-separated = images per source, in the order of SOURCES)
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
OUT = ROOT / "dataset" / "yolo"
CLASS_NAMES = {0: "fire", 1: "smoke"}
SPLIT_MAP = {"train": "train", "valid": "val", "val": "val", "test": "test"}
PAT = re.compile(r"(?:^|/)(train|valid|val|test)/(images|labels)/([^/]+)$")
IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

SOURCES = [
    {
        "name": "wildfire-40k",
        "zip": ROOT / "dataset" / "raw" / "dataset.zip",
        "url": "https://huggingface.co/datasets/jojomoi-meme/fog_fire_detection",
        "license": "CC-BY-4.0 (Roboflow Universe joachim-serv/wildfire-j4okv)",
        "class_map": {0: 0, 1: 1},
        "prefix": "wf",
    },
    {
        "name": "ISFire-4 (indoor)",
        "zip": ROOT / "dataset" / "raw_isfire" / "Dataset.zip",
        "url": "https://huggingface.co/datasets/shahriar-5/ISFire-4",
        "license": "MIT (Roboflow Universe, IICT BUET)",
        "class_map": {0: 1, 1: 0, 2: 1, 3: 0},
        "prefix": "is",
    },
]


def remap_label(text: str, class_map: dict) -> str:
    out = []
    for line in text.splitlines():
        p = line.split()
        if len(p) < 5:
            continue
        try:
            cid = class_map.get(int(float(p[0])))
        except ValueError:
            continue
        if cid is None:
            continue
        out.append(" ".join([str(cid), *p[1:5]]))
    return "\n".join(out) + ("\n" if out else "")


def classify_label(text: str) -> str:
    """fire / smoke / both / negative, from a (remapped) label file text."""
    ids = set()
    for line in text.splitlines():
        p = line.split()
        if p:
            ids.add(int(p[0]))
    if ids == {0}:
        return "fire"
    if ids == {1}:
        return "smoke"
    if ids >= {0, 1}:
        return "both"
    return "negative"


def safe_name(name: str) -> bool:
    return ".." not in name and not name.startswith(("/", "\\"))


def parse_counts(s: str, n: int) -> list[int]:
    parts = [int(x) for x in s.split(",")]
    if len(parts) == 1:
        parts = parts * n
    if len(parts) != n:
        raise SystemExit(f"expected {n} comma-separated counts, got {s}")
    return parts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="2000,1000")
    ap.add_argument("--val", default="400,200")
    ap.add_argument("--test", default="400,200")
    ap.add_argument("--negatives", type=float, default=0.15, help="fraction of each split kept as negatives (if available)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    sources = [s for s in SOURCES if s["zip"].exists()]
    missing = [s["name"] for s in SOURCES if not s["zip"].exists()]
    if missing:
        print("WARNING: missing sources (skipped):", missing)
    if not sources:
        raise SystemExit("no dataset zips found - run training/download_datasets.py first")
    wanted = {"train": parse_counts(args.train, len(SOURCES)), "val": parse_counts(args.val, len(SOURCES)),
              "test": parse_counts(args.test, len(SOURCES))}

    rng = random.Random(args.seed)
    t0 = time.time()
    for split in ("train", "val", "test"):
        (OUT / "images" / split).mkdir(parents=True, exist_ok=True)
        (OUT / "labels" / split).mkdir(parents=True, exist_ok=True)
        for old in (OUT / "images" / split).iterdir():
            old.unlink()
        for old in (OUT / "labels" / split).iterdir():
            old.unlink()

    manifest = {"classes": CLASS_NAMES, "seed": args.seed, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "sources": [], "splits": {s: {"images": 0, "by_content": Counter(), "boxes": Counter()} for s in wanted}}

    for src_i, src in enumerate(SOURCES):
        if not src["zip"].exists():
            continue
        zf = zipfile.ZipFile(src["zip"])
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
        print(f"[{src['name']}] indexed in {time.time()-t0:.1f}s:", {s: len(v) for s, v in index.items()})

        buckets: dict[str, dict[str, list]] = {s: defaultdict(list) for s in index}
        labels_cache: dict[tuple, str] = {}
        for split, stems in index.items():
            for stem, files in stems.items():
                if "image" not in files:
                    continue
                txt = remap_label(zf.read(files["label"]).decode("utf-8", "ignore"), src["class_map"]) if "label" in files else ""
                labels_cache[(split, stem)] = txt
                buckets[split][classify_label(txt)].append(stem)
        avail = {s: {k: len(v) for k, v in buckets[s].items()} for s in buckets}
        print(f"[{src['name']}] available:", avail)

        src_summary = {"name": src["name"], "url": src["url"], "license": src["license"],
                       "class_map": {str(k): CLASS_NAMES[v] for k, v in src["class_map"].items()}, "available": avail, "used": {}}
        for split, counts in wanted.items():
            n = counts[src_i]
            b = buckets.get(split, {})
            if not b or n <= 0:
                continue
            for lst in b.values():
                rng.shuffle(lst)
            n_neg = min(int(n * args.negatives), len(b.get("negative", [])))
            n_pos = n - n_neg
            pos_cats = [c for c in ("fire", "smoke", "both") if b.get(c)]
            picks, per = [], {c: 0 for c in pos_cats}
            while len(picks) < n_pos and any(per[c] < len(b[c]) for c in pos_cats):
                for c in pos_cats:  # round-robin -> fire / smoke balanced
                    if per[c] < len(b[c]) and len(picks) < n_pos:
                        picks.append((c, b[c][per[c]]))
                        per[c] += 1
            picks += [("negative", s) for s in b.get("negative", [])[:n_neg]]

            cats = Counter()
            for cat, stem in picks:
                files = index[split][stem]
                img_name = files["image"]
                out_stem = f"{src['prefix']}_{pathlib.Path(img_name).stem}"[:120]
                (OUT / "images" / split / (out_stem + pathlib.Path(img_name).suffix.lower())).write_bytes(zf.read(img_name))
                txt = labels_cache[(split, stem)]
                (OUT / "labels" / split / (out_stem + ".txt")).write_text(txt)
                for line in txt.splitlines():
                    manifest["splits"][split]["boxes"][CLASS_NAMES[int(line.split()[0])]] += 1
                cats[cat] += 1
            manifest["splits"][split]["images"] += len(picks)
            manifest["splits"][split]["by_content"].update(cats)
            src_summary["used"][split] = dict(cats)
            print(f"[{src['name']}] {split}: {len(picks)} images {dict(cats)}")
        manifest["sources"].append(src_summary)
        zf.close()

    for s in manifest["splits"].values():
        s["by_content"] = dict(s["by_content"])
        s["boxes"] = dict(s["boxes"])

    data_yaml = ROOT / "configs" / "data.yaml"
    data_yaml.write_text(
        "# Generated by training/prepare_dataset.py\n"
        f"path: {OUT.as_posix()}\n"
        "train: images/train\nval: images/val\ntest: images/test\n"
        "names:\n" + "".join(f"  {k}: {v}\n" for k, v in CLASS_NAMES.items())
    )
    (ROOT / "dataset" / "manifest.json").write_text(json.dumps(manifest, indent=2))

    rows = "\n".join(
        f"| {s} | {m['images']} | {m['by_content'].get('fire',0)} | {m['by_content'].get('smoke',0)} | "
        f"{m['by_content'].get('both',0)} | {m['by_content'].get('negative',0)} | "
        f"{m['boxes'].get('fire',0)} | {m['boxes'].get('smoke',0)} |"
        for s, m in manifest["splits"].items()
    )
    src_rows = "\n".join(
        f"| {s['name']} | {s['url']} | {s['license']} | {', '.join(f'{k}->{v}' for k, v in s['class_map'].items())} | "
        f"{' / '.join(f'{sp}:{sum(c.values())}' for sp, c in s['used'].items())} |"
        for s in manifest["sources"]
    )
    (ROOT / "dataset" / "DATASET_REGISTER.md").write_text(
        "# Dataset Register\n\n"
        "| Source | URL | Licence / permission | Class mapping (source id -> ours) | Images used (train/val/test) |\n|---|---|---|---|---|\n"
        + src_rows + "\n\n"
        "| Field | Value |\n|---|---|\n"
        "| Format | YOLO (class cx cy w h, normalised 0-1) |\n"
        "| Classes | 0 = fire, 1 = smoke |\n"
        f"| Sampling | stratified subset per source, seed {args.seed}, up to {args.negatives:.0%} negatives per split where available |\n"
        "| Preprocessing | none; Ultralytics augmentation applied at train time only |\n"
        f"| Created | {manifest['created']} |\n\n"
        "## Split summary\n\n"
        "| Split | Images | fire-only | smoke-only | both | negative | fire boxes | smoke boxes |\n"
        "|---|---|---|---|---|---|---|---|\n" + rows + "\n\n"
        "Splits follow the upstream train/valid/test partitions of each source, so frames from the same "
        "source video do not leak between train and test.\n"
    )
    print(f"done in {time.time()-t0:.1f}s -> {OUT}")
    print(json.dumps({k: {"images": v["images"], "boxes": v["boxes"]} for k, v in manifest["splits"].items()}, indent=1))


if __name__ == "__main__":
    main()
