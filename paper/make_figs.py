"""Build the paper figures and fill measured numbers into paper.tex.

    python paper/make_figs.py

Reads:  models/runs/fire_smoke_v1/results.csv   (training curves)
        models/eval/BoxPR_curve.png, confusion_matrix_normalized.png   (from training/evaluate.py)
        models/eval_metrics.json, models/training_config.json
Writes: paper/figs/results.png, paper/figs/BoxPR_curve.png, paper/figs/confusion_matrix_normalized.png
        paper/paper.tex  (the \newcommand metric macros at the top)
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIGS = ROOT / "paper" / "figs"
FIGS.mkdir(exist_ok=True)
RUN = ROOT / "models" / "runs" / "fire_smoke_v1"
TEX = ROOT / "paper" / "paper.tex"

# ---------------------------------------------------------------- training curves
csv = RUN / "results.csv"
if csv.exists():
    df = pd.read_csv(csv)
    df.columns = [c.strip() for c in df.columns]
    ep = df["epoch"]
    fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.6))
    ax[0].plot(ep, df["train/box_loss"], "-o", ms=3, label="train box")
    ax[0].plot(ep, df["train/cls_loss"], "-o", ms=3, label="train cls")
    ax[0].plot(ep, df["val/box_loss"], "--s", ms=3, label="val box")
    ax[0].plot(ep, df["val/cls_loss"], "--s", ms=3, label="val cls")
    ax[0].set_xlabel("epoch"); ax[0].set_ylabel("loss"); ax[0].legend(fontsize=7, ncol=2); ax[0].grid(alpha=.3)
    ax[1].plot(ep, df["metrics/precision(B)"], "-o", ms=3, label="precision")
    ax[1].plot(ep, df["metrics/recall(B)"], "-o", ms=3, label="recall")
    ax[1].plot(ep, df["metrics/mAP50(B)"], "-s", ms=3, label="mAP@0.5")
    ax[1].plot(ep, df["metrics/mAP50-95(B)"], "-s", ms=3, label="mAP@0.5:0.95")
    ax[1].set_xlabel("epoch"); ax[1].set_ylim(0, 1); ax[1].legend(fontsize=7, ncol=2); ax[1].grid(alpha=.3)
    for a in ax:
        a.tick_params(labelsize=8); a.xaxis.label.set_size(8); a.yaxis.label.set_size(8)
    fig.tight_layout()
    fig.savefig(FIGS / "results.png", dpi=220)
    print("wrote results.png from", len(df), "epochs")

# ---------------------------------------------------------------- eval plots
for name in ("BoxPR_curve.png", "confusion_matrix_normalized.png"):
    src = ROOT / "models" / "eval" / name
    if src.exists():
        shutil.copy2(src, FIGS / name)
        print("copied", name)
    else:
        print("MISSING", src)

# ---------------------------------------------------------------- numbers -> tex macros
vals = {}
mp = ROOT / "models" / "eval_metrics.json"
if mp.exists():
    m = json.loads(mp.read_text())
    o, pc, op, lat = m["overall"], m["per_class"], m["operating_point"], m["latency"]
    f3 = lambda x: f"{x:.3f}"
    vals.update({
        "Ptot": f3(o["precision"]), "Rtot": f3(o["recall"]), "Ftot": f3(o["f1"]), "MAPtot": f3(o["mAP50"]), "MAPStot": f3(o["mAP50-95"]),
        "Pfire": f3(pc["fire"]["precision"]), "Rfire": f3(pc["fire"]["recall"]), "Ffire": f3(pc["fire"]["f1"]),
        "MAPfire": f3(pc["fire"]["mAP50"]), "MAPSfire": f3(pc["fire"]["mAP50-95"]),
        "Psmoke": f3(pc["smoke"]["precision"]), "Rsmoke": f3(pc["smoke"]["recall"]), "Fsmoke": f3(pc["smoke"]["f1"]),
        "MAPsmoke": f3(pc["smoke"]["mAP50"]), "MAPSsmoke": f3(pc["smoke"]["mAP50-95"]),
        "OPconf": str(op["conf"]), "OPprec": f3(op["precision"]), "OPrec": f3(op["recall"]),
        "OPtp": str(op["tp"]), "OPfp": str(op["fp"]), "OPfn": str(op["fn"]),
        "OPnegclean": str(op["negatives_clean"]), "OPneg": str(op["negatives"]),
        "OPnegrate": f3(op["negative_image_false_alarm_rate"] or 0),
        "LATmean": str(lat["mean_ms"]), "LATpnf": str(lat["p95_ms"]), "LATfps": str(lat["fps"]),
    })
tc = ROOT / "models" / "training_config.json"
if tc.exists():
    vals["TRAINmin"] = str(json.loads(tc.read_text()).get("training_time_minutes", 0))

if vals:
    tex = TEX.read_text(encoding="utf-8")
    for k, v in vals.items():
        repl = "\\newcommand{\\" + k + "}{" + v + "}"
        tex, n = re.subn(r"\\newcommand\{\\" + k + r"\}\{[^}]*\}", lambda _m, r=repl: r, tex)
        if n != 1:
            print("WARN macro not found:", k)
    TEX.write_text(tex, encoding="utf-8")
    print("filled", len(vals), "macros into paper.tex")
else:
    print("no eval_metrics.json yet - macros left as-is")
